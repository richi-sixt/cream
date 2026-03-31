"""PostFinance-specific statement parser and importer."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Optional

from flask import current_app, has_app_context

from app import db
from app.models import Account, Transaction
from .base import get_or_create_account, group_words_by_row, make_hash, parse_chf

_DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{2}$")
_IBAN_FILENAME_RE = re.compile(r"(CH\d{19})", re.IGNORECASE)
_BANK_NAME = "PostFinance"
_ACCOUNT_KIND_TO_TYPE = {
    "privatkonto": "checking",
    "sparkonto": "savings",
    "geschäftskonto": "checking",
}
_SKIP_DESCRIPTION_PREFIXES = (
    "Kontostand",
    "Total",
    "Bitte überprüfen",
    "Bitte ueberpruefen",
)


def _starts_with_skip_prefix(text: str) -> bool:
    """Return whether a parsed description is statement furniture."""
    return text.startswith(_SKIP_DESCRIPTION_PREFIXES)


def _parse_postfinance_amount(text: str) -> Optional[float]:
    """Parse statement amounts only when they include a decimal separator."""
    normalized = text.strip().replace("'", "").replace(" ", "")
    if "." not in normalized and "," not in normalized:
        return None
    return parse_chf(text)


def _normalize_iban(raw_iban: str) -> str:
    """Return a compact IBAN without spaces."""
    return re.sub(r"\s+", "", raw_iban).upper()


def _extract_iban_from_filename(pdf_path: Path) -> Optional[str]:
    """Extract the account IBAN encoded in the PostFinance filename."""
    match = _IBAN_FILENAME_RE.search(pdf_path.name)
    return _normalize_iban(match.group(1)) if match else None


def _read_first_page_lines(pdf_path: Path) -> list[str]:
    """Read non-empty text lines from the first page of a PDF."""
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return []
        text = pdf.pages[0].extract_text() or ""
    return [line.strip() for line in text.splitlines() if line.strip()]


def _extract_account_kind(lines: list[str]) -> Optional[str]:
    """Extract the account type label from the first page."""
    for line in lines:
        lowered = line.lower()
        if any(kind in lowered for kind in _ACCOUNT_KIND_TO_TYPE):
            return line
    return None


def _extract_holder_name(lines: list[str]) -> Optional[str]:
    """Extract the account holder shown in the address block."""
    seen_website = False
    for candidate in lines:
        if candidate.startswith("PostFinance AG"):
            continue
        if candidate.startswith("www."):
            seen_website = True
            continue
        if candidate.startswith("Sie werden betreut von"):
            continue
        if candidate.startswith("Telefon") or candidate.startswith("www."):
            continue
        if " und Team" in candidate:
            continue
        if candidate.startswith("Herr") or candidate.startswith("Frau"):
            continue
        if candidate.startswith("Privatkonto") or candidate.startswith("Kontoauszug"):
            continue
        if re.match(r"^\d{2}\.\d{2}\.\d{2}\s+Kontostand", candidate):
            break
        if not seen_website and any(char.isdigit() for char in candidate):
            continue
        if any(char.isalpha() for char in candidate) and not any(char.isdigit() for char in candidate):
            return candidate
    return None


def extract_account_metadata(pdf_path: Path) -> dict[str, Optional[str]]:
    """Extract account metadata for a PostFinance statement."""
    try:
        lines = _read_first_page_lines(pdf_path)
    except ImportError:
        lines = []

    iban = _extract_iban_from_filename(pdf_path)
    if not iban:
        for line in lines:
            if line.startswith("IBAN "):
                iban = _normalize_iban(line.split("IBAN", 1)[1].replace("CHF", "").strip())
                break

    account_kind = _extract_account_kind(lines)
    holder = _extract_holder_name(lines)
    configured_name = None
    if iban and has_app_context():
        configured_name = current_app.config.get("ACCOUNT_NAME_OVERRIDES", {}).get(iban)

    if configured_name:
        name = configured_name
    elif account_kind and holder:
        name = f"{_BANK_NAME} {account_kind} - {holder}"
    elif account_kind:
        name = f"{_BANK_NAME} {account_kind}"
    elif holder:
        name = f"{_BANK_NAME} - {holder}"
    else:
        name = iban or pdf_path.stem

    account_type = "checking"
    if account_kind:
        lowered_kind = account_kind.lower()
        for fragment, mapped_type in _ACCOUNT_KIND_TO_TYPE.items():
            if fragment in lowered_kind:
                account_type = mapped_type
                break

    return {
        "iban": iban,
        "name": name,
        "bank_name": _BANK_NAME,
        "account_kind": account_kind,
        "type": account_type,
    }


def _ensure_account(metadata: dict[str, Optional[str]]) -> Account:
    """Create or update an account row from parsed metadata."""
    iban = metadata.get("iban") or "UNKNOWN"
    name = metadata.get("name") or iban
    account_type = metadata.get("type") or "checking"

    account = get_or_create_account(iban, name)
    if name and account.name != name:
        account.name = name
    if account_type and account.type != account_type:
        account.type = account_type
    return account


def _normalize_description(text: Optional[str]) -> str:
    """Normalize parser descriptions for stable comparisons."""
    return re.sub(r"\s+", " ", text or "").strip()


def _description_contains_same_parts(left: Optional[str], right: Optional[str]) -> bool:
    """Fallback comparison for descriptions that may contain encoding artifacts."""
    left_norm = _normalize_description(left)
    right_norm = _normalize_description(right)
    if not left_norm or not right_norm:
        return False
    left_parts = [part.strip() for part in left_norm.split("|") if part.strip()]
    right_parts = [part.strip() for part in right_norm.split("|") if part.strip()]
    if not left_parts or not right_parts:
        return False
    return all(part in right_norm for part in left_parts) or all(part in left_norm for part in right_parts)


def _same_saldo(left: Optional[float], right: Optional[float]) -> bool:
    """Compare saldi while treating None as a meaningful value."""
    if left is None or right is None:
        return left is right
    return abs(left - right) < 0.005


def _find_pdf_by_name(movements_dir: Path, pdf_name: str) -> Optional[Path]:
    """Find a PDF below the recursive movements directory by filename."""
    try:
        return next(movements_dir.rglob(pdf_name))
    except StopIteration:
        return None


def _find_marked_parser_row(parsed_group: list[dict], marked: dict[str, str], parser_index: int) -> Optional[dict]:
    """Find the parser row referenced by a marked review row."""
    if 0 < parser_index <= len(parsed_group):
        return parsed_group[parser_index - 1]

    marked_amount_text = marked.get("parser_amount") or ""
    marked_type = marked.get("parser_type") or ""
    marked_saldo_text = marked.get("parser_saldo") or ""
    marked_description = marked.get("parser_description") or ""
    marked_amount = parse_chf(marked_amount_text) if marked_amount_text else None
    marked_saldo = parse_chf(marked_saldo_text) if marked_saldo_text else None

    numeric_candidates: list[dict] = []
    for parsed_row in parsed_group:
        if marked_amount is not None and abs(parsed_row["amount"] - marked_amount) >= 0.005:
            continue
        if marked_type and parsed_row["type"] != marked_type:
            continue
        if not _same_saldo(parsed_row.get("saldo"), marked_saldo):
            continue
        numeric_candidates.append(parsed_row)

    if len(numeric_candidates) == 1:
        return numeric_candidates[0]

    for parsed_row in numeric_candidates:
        if _description_contains_same_parts(parsed_row["description"], marked_description):
            return parsed_row

    return None


def parse_postfinance_pdf(pdf_path: Path) -> list[dict]:
    """Parse a PostFinance statement PDF into transaction dictionaries."""
    try:
        import pdfplumber
    except ImportError:
        current_app.logger.error("pdfplumber is not installed.")
        return []

    transactions: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            rows = group_words_by_row(words, y_tolerance=4)

            columns: dict[str, float] = {}
            for word in words:
                if word["text"] in ("Gutschrift", "Lastschrift", "Valuta", "Saldo", "Text"):
                    columns[word["text"]] = word["x0"]

            if "Text" not in columns or "Saldo" not in columns:
                continue

            credit_min = (columns["Text"] + columns["Gutschrift"]) / 2
            debit_min = (columns["Gutschrift"] + columns["Lastschrift"]) / 2
            value_min = (columns["Lastschrift"] + columns["Valuta"]) / 2
            saldo_min = (columns["Valuta"] + columns["Saldo"]) / 2

            current_tx: Optional[dict] = None
            for row_words in rows.values():
                texts = [word["text"] for word in row_words]
                xs = [word["x0"] for word in row_words]
                if not texts:
                    continue

                is_main_row = _DATE_RE.match(texts[0]) and xs[0] < columns["Text"]
                if is_main_row:
                    if current_tx:
                        transactions.append(current_tx)

                    description_parts: list[str] = []
                    credit_parts: list[str] = []
                    debit_parts: list[str] = []
                    value_date_parts: list[str] = []
                    balance_parts: list[str] = []

                    for word in row_words[1:]:
                        text = word["text"]
                        x = word["x0"]

                        if _DATE_RE.match(text):
                            value_date_parts.append(text)
                            continue

                        if x >= saldo_min:
                            balance_parts.append(text)
                        elif x >= value_min:
                            value_date_parts.append(text)
                        elif x >= debit_min:
                            debit_parts.append(text)
                        elif x >= credit_min:
                            credit_parts.append(text)
                        else:
                            description_parts.append(text)

                    credit_text = " ".join(credit_parts).strip()
                    debit_text = " ".join(debit_parts).strip()
                    balance_text = " ".join(balance_parts).strip()
                    parsed_credit = _parse_postfinance_amount(credit_text) if credit_text else None
                    parsed_debit = _parse_postfinance_amount(debit_text) if debit_text else None

                    amount: Optional[float]
                    tx_type: Optional[str]
                    if parsed_credit is not None:
                        amount = parsed_credit
                        tx_type = "income"
                    else:
                        amount = parsed_debit
                        tx_type = "expense" if parsed_debit is not None else None

                    value_date = " ".join(value_date_parts).strip() or None
                    balance = _parse_postfinance_amount(balance_text) if balance_text else None
                    description = " ".join(description_parts).strip()
                    if amount is None or _starts_with_skip_prefix(description):
                        current_tx = None
                        continue

                    current_tx = {
                        "date": texts[0],
                        "description": description,
                        "amount": amount,
                        "type": tx_type or "expense",
                        "saldo": balance,
                        "detail_lines": [],
                        "value_date": value_date,
                    }
                    continue

                has_amount_or_balance = any(
                    word["x0"] >= debit_min or word["x0"] >= credit_min or word["x0"] >= saldo_min
                    for word in row_words
                )
                if current_tx and xs[0] >= columns["Text"] - 5 and has_amount_or_balance:
                    continuation_desc: list[str] = []
                    credit_parts: list[str] = []
                    debit_parts: list[str] = []
                    value_date_parts: list[str] = []
                    balance_parts: list[str] = []

                    for word in row_words:
                        text = word["text"]
                        x = word["x0"]

                        if _DATE_RE.match(text):
                            value_date_parts.append(text)
                            continue

                        if x >= saldo_min:
                            balance_parts.append(text)
                        elif x >= value_min:
                            value_date_parts.append(text)
                        elif x >= debit_min:
                            debit_parts.append(text)
                        elif x >= credit_min:
                            credit_parts.append(text)
                        else:
                            continuation_desc.append(text)

                    continuation_text = " ".join(continuation_desc).strip()
                    if continuation_text:
                        cleaned_continuation = continuation_text
                    else:
                        cleaned_continuation = ""

                    credit_text = " ".join(credit_parts).strip()
                    debit_text = " ".join(debit_parts).strip()
                    balance_text = " ".join(balance_parts).strip()
                    value_date_text = " ".join(value_date_parts).strip()

                    parsed_credit = _parse_postfinance_amount(credit_text) if credit_text else None
                    parsed_debit = _parse_postfinance_amount(debit_text) if debit_text else None
                    parsed_amount = parsed_credit if parsed_credit is not None else parsed_debit
                    parsed_type = (
                        "income" if parsed_credit is not None else "expense" if parsed_debit is not None else None
                    )

                    if cleaned_continuation and _starts_with_skip_prefix(cleaned_continuation):
                        continue

                    # Some year-end statements omit the left-hand date on the next row
                    # but still contain a full debit/credit + value date + saldo block.
                    # Treat those as a new transaction rather than a continuation.
                    if (
                        parsed_amount is not None
                        and cleaned_continuation
                        and not _starts_with_skip_prefix(cleaned_continuation)
                        and not cleaned_continuation.startswith(("ABSENDER", "MITTEILUNGEN", "REFERENZEN", "SENDER"))
                        and current_tx.get("amount") is not None
                    ):
                        transactions.append(current_tx)
                        current_tx = {
                            "date": value_date_text or current_tx["date"],
                            "description": cleaned_continuation,
                            "amount": parsed_amount,
                            "type": parsed_type or "expense",
                            "saldo": _parse_postfinance_amount(balance_text) if balance_text else None,
                            "detail_lines": [],
                            "value_date": value_date_text or None,
                        }
                        continue

                    if cleaned_continuation:
                        current_tx["detail_lines"].append(cleaned_continuation)

                    if parsed_credit is not None:
                        current_tx["amount"] = parsed_credit
                        current_tx["type"] = "income"
                    elif parsed_debit is not None:
                        current_tx["amount"] = parsed_debit
                        current_tx["type"] = "expense"

                    if balance_text:
                        parsed_balance = _parse_postfinance_amount(balance_text)
                        if parsed_balance is not None:
                            current_tx["saldo"] = parsed_balance

                    if value_date_text:
                        current_tx["value_date"] = value_date_text
                    continue

                if current_tx and xs[0] >= columns["Text"] - 5:
                    continuation = " ".join(texts).strip()
                    if (
                        continuation
                        and not continuation.startswith("Post CH AG")
                        and not _starts_with_skip_prefix(continuation)
                    ):
                        current_tx["detail_lines"].append(continuation)

            if current_tx:
                transactions.append(current_tx)

    parsed_transactions: list[dict] = []
    for tx in transactions:
        description = tx["description"]
        if tx["detail_lines"]:
            description = " | ".join([description, *tx["detail_lines"]])
        parsed_transactions.append(
            {
                "date": tx["date"],
                "description": description,
                "amount": tx["amount"],
                "type": tx["type"],
                "saldo": tx["saldo"],
            }
        )

    # Convert string dates at the end to keep the main loop simple.
    from .base import date_from_ddmmyy

    result: list[dict] = []
    for tx in parsed_transactions:
        tx_date = date_from_ddmmyy(tx["date"])
        if tx_date is None:
            continue
        result.append({**tx, "date": tx_date})
    return result


def import_postfinance_documents() -> dict:
    """Import PostFinance statement PDFs from `03-Bewegungen/`."""
    movements_dir: Path = current_app.config["BEWEGUNGEN_DIR"]
    stats = {"imported": 0, "skipped": 0, "errors": 0}

    if not movements_dir.exists():
        current_app.logger.warning("Movements directory not found: %s", movements_dir)
        return stats

    for pdf in sorted(movements_dir.rglob("REP_P_*.pdf")):
        if Transaction.query.filter_by(pdf_source=pdf.name).first():
            stats["skipped"] += 1
            continue

        try:
            metadata = extract_account_metadata(pdf)
            account_iban = metadata.get("iban")
            if not account_iban:
                current_app.logger.warning("Skipping %s because no IBAN could be derived.", pdf.name)
                stats["errors"] += 1
                continue

            account = _ensure_account(metadata)
            raw_transactions = parse_postfinance_pdf(pdf)

            for raw in raw_transactions:
                import_hash = make_hash(account_iban, raw["date"], raw["amount"], raw["description"])
                if Transaction.query.filter_by(import_hash=import_hash).first():
                    stats["skipped"] += 1
                    continue

                db.session.add(
                    Transaction(
                        account_id=account.id,
                        date=raw["date"],
                        raw_description=raw["description"],
                        amount=raw["amount"],
                        type=raw["type"],
                        saldo=raw.get("saldo"),
                        pdf_source=pdf.name,
                        import_hash=import_hash,
                    )
                )
                stats["imported"] += 1
        except Exception as exc:  # pragma: no cover - defensive logging path
            current_app.logger.error("Failed to import %s: %s", pdf.name, exc)
            stats["errors"] += 1

    db.session.commit()
    return stats


def repair_postfinance_saldi() -> dict:
    """Reparse PostFinance PDFs and update already imported saldi when needed."""
    movements_dir: Path = current_app.config["BEWEGUNGEN_DIR"]
    stats = {"updated": 0, "unchanged": 0, "missing": 0, "errors": 0}

    if not movements_dir.exists():
        current_app.logger.warning("Movements directory not found: %s", movements_dir)
        return stats

    for pdf in sorted(movements_dir.rglob("REP_P_*.pdf")):
        try:
            metadata = extract_account_metadata(pdf)
            account_iban = metadata.get("iban")
            if not account_iban:
                stats["errors"] += 1
                continue

            raw_transactions = parse_postfinance_pdf(pdf)
            fallback_saldo_by_date: dict = {}
            for raw in raw_transactions:
                if raw.get("saldo") is not None:
                    fallback_saldo_by_date[raw["date"]] = raw["saldo"]

            for raw in raw_transactions:
                import_hash = make_hash(account_iban, raw["date"], raw["amount"], raw["description"])
                tx = Transaction.query.filter_by(import_hash=import_hash).first()
                if tx is None:
                    fallback_tx = (
                        Transaction.query.filter_by(pdf_source=pdf.name, date=raw["date"])
                        .filter(Transaction.saldo.is_(None))
                        .first()
                    )
                    if fallback_tx and raw.get("saldo") is not None:
                        fallback_tx.saldo = raw["saldo"]
                        stats["updated"] += 1
                    else:
                        stats["missing"] += 1
                    continue

                if tx.saldo != raw.get("saldo"):
                    tx.saldo = raw.get("saldo")
                    stats["updated"] += 1
                else:
                    stats["unchanged"] += 1

            for existing_tx in Transaction.query.filter_by(pdf_source=pdf.name).filter(Transaction.saldo.is_(None)).all():
                fallback_saldo = fallback_saldo_by_date.get(existing_tx.date)
                if fallback_saldo is not None:
                    existing_tx.saldo = fallback_saldo
                    stats["updated"] += 1
        except Exception as exc:  # pragma: no cover - defensive logging path
            current_app.logger.error("Failed to repair %s: %s", pdf.name, exc)
            stats["errors"] += 1

    db.session.commit()
    return stats


def normalize_postfinance_transactions() -> dict:
    """Split legacy merged PostFinance rows into separately parsed transactions."""
    movements_dir: Path = current_app.config["BEWEGUNGEN_DIR"]
    stats = {"normalized": 0, "skipped": 0, "errors": 0}

    if not movements_dir.exists():
        current_app.logger.warning("Movements directory not found: %s", movements_dir)
        return stats

    for pdf in sorted(movements_dir.rglob("REP_P_*.pdf")):
        try:
            metadata = extract_account_metadata(pdf)
            account_iban = metadata.get("iban")
            if not account_iban:
                stats["errors"] += 1
                continue

            parsed_rows = parse_postfinance_pdf(pdf)
            parsed_by_date: dict = {}
            for row in parsed_rows:
                parsed_by_date.setdefault(row["date"], []).append(row)

            existing_rows = (
                Transaction.query.filter_by(pdf_source=pdf.name)
                .order_by(Transaction.date.asc(), Transaction.id.asc())
                .all()
            )
            existing_by_date: dict = {}
            for row in existing_rows:
                existing_by_date.setdefault(row.date, []).append(row)

            for tx_date, existing_for_date in existing_by_date.items():
                parsed_for_date = parsed_by_date.get(tx_date, [])
                if len(existing_for_date) != 1 or len(parsed_for_date) <= 1:
                    stats["skipped"] += len(existing_for_date)
                    continue

                legacy_row = existing_for_date[0]
                if (
                    legacy_row.title
                    or legacy_row.notes
                    or legacy_row.category_id is not None
                    or legacy_row.lines
                    or "|" not in legacy_row.raw_description
                ):
                    stats["skipped"] += 1
                    continue

                recreated_rows: list[Transaction] = []
                seen_hashes: set[str] = set()
                can_normalize = True
                for parsed in parsed_for_date:
                    import_hash = make_hash(account_iban, parsed["date"], parsed["amount"], parsed["description"])
                    if import_hash in seen_hashes:
                        continue
                    seen_hashes.add(import_hash)

                    existing_hash_owner = Transaction.query.filter_by(import_hash=import_hash).first()
                    if existing_hash_owner and existing_hash_owner.id != legacy_row.id:
                        can_normalize = False
                        break

                    recreated_rows.append(
                        Transaction(
                            account_id=legacy_row.account_id,
                            date=parsed["date"],
                            raw_description=parsed["description"],
                            amount=parsed["amount"],
                            type=parsed["type"],
                            saldo=parsed.get("saldo"),
                            pdf_source=legacy_row.pdf_source,
                            import_hash=import_hash,
                        )
                    )

                if not can_normalize or len(recreated_rows) <= 1:
                    stats["skipped"] += 1
                    continue

                db.session.delete(legacy_row)
                db.session.flush()
                for recreated in recreated_rows:
                    db.session.add(recreated)
                stats["normalized"] += 1
        except Exception as exc:  # pragma: no cover - defensive logging path
            current_app.logger.error("Failed to normalize %s: %s", pdf.name, exc)
            stats["errors"] += 1

    db.session.commit()
    return stats


def preview_marked_postfinance_repairs(csv_path: Optional[Path] = None) -> dict:
    """Build a dry-run repair plan from a marked PostFinance review CSV."""
    stats, _ = _build_marked_postfinance_repair_plan(csv_path)
    return stats


def _build_marked_postfinance_repair_plan(csv_path: Optional[Path] = None) -> tuple[dict, list[dict[str, str]]]:
    """Build a repair plan from a marked PostFinance review CSV."""
    movements_dir: Path = current_app.config["BEWEGUNGEN_DIR"]
    if csv_path is None:
        csv_path = current_app.root_path
        csv_path = Path(current_app.root_path).parent / "reports" / "postfinance_marked_orange_unique_targets.csv"

    report_path = Path(current_app.root_path).parent / "reports" / "postfinance_marked_repair_plan.csv"
    stats = {
        "targets": 0,
        "insert_missing": 0,
        "update_existing": 0,
        "already_matches": 0,
        "already_exists_other_id": 0,
        "missing_pdf": 0,
        "missing_parser_row": 0,
        "errors": 0,
        "report_path": str(report_path),
    }

    if not csv_path.exists():
        raise FileNotFoundError(f"Marked review CSV not found: {csv_path}")

    plan_rows: list[dict[str, str]] = []
    parsed_cache: dict[str, list[dict]] = {}

    with csv_path.open(newline="", encoding="utf-8") as fh:
        marked_rows = list(csv.DictReader(fh))

    for marked in marked_rows:
        stats["targets"] += 1
        pdf_name = marked.get("pdf_source") or ""
        date_iso = marked.get("date") or ""
        parser_index_raw = marked.get("parser_index") or ""
        try:
            parser_index = int(parser_index_raw)
        except ValueError:
            parser_index = 0

        action = "error"
        note = ""
        matched_db_id = ""
        pdf_path = _find_pdf_by_name(movements_dir, pdf_name)
        if pdf_path is None:
            stats["missing_pdf"] += 1
            action = "missing_pdf"
            note = f"Could not find {pdf_name} below {movements_dir}"
            plan_rows.append(
                {
                    "action": action,
                    "pdf_source": pdf_name,
                    "date": date_iso,
                    "parser_index": parser_index_raw,
                    "db_id": marked.get("db_id") or "",
                    "matched_db_id": matched_db_id,
                    "db_amount": marked.get("db_amount") or "",
                    "db_saldo": marked.get("db_saldo") or "",
                    "parser_amount": marked.get("parser_amount") or "",
                    "parser_type": marked.get("parser_type") or "",
                    "parser_saldo": marked.get("parser_saldo") or "",
                    "db_description": marked.get("db_description") or "",
                    "parser_description": marked.get("parser_description") or "",
                    "same_day_db_ids": "",
                    "note": note,
                }
            )
            continue

        if pdf_name not in parsed_cache:
            parsed_cache[pdf_name] = parse_postfinance_pdf(pdf_path)
        parsed_group = [row for row in parsed_cache[pdf_name] if row["date"].isoformat() == date_iso]

        parsed_row = _find_marked_parser_row(parsed_group, marked, parser_index)
        if parsed_row is None:
            stats["missing_parser_row"] += 1
            action = "missing_parser_row"
            note = f"Parser index {parser_index_raw} not available for {pdf_name} on {date_iso}"
            plan_rows.append(
                {
                    "action": action,
                    "pdf_source": pdf_name,
                    "date": date_iso,
                    "parser_index": parser_index_raw,
                    "db_id": marked.get("db_id") or "",
                    "matched_db_id": matched_db_id,
                    "db_amount": marked.get("db_amount") or "",
                    "db_saldo": marked.get("db_saldo") or "",
                    "parser_amount": marked.get("parser_amount") or "",
                    "parser_type": marked.get("parser_type") or "",
                    "parser_saldo": marked.get("parser_saldo") or "",
                    "db_description": marked.get("db_description") or "",
                    "parser_description": marked.get("parser_description") or "",
                    "same_day_db_ids": "",
                    "note": note,
                }
            )
            continue

        db_group = (
            Transaction.query.filter_by(pdf_source=pdf_name)
            .filter(Transaction.date == parsed_row["date"])
            .order_by(Transaction.id.asc())
            .all()
        )
        same_day_db_ids = ",".join(str(tx.id) for tx in db_group)

        exact_match = None
        for tx in db_group:
            if (
                abs(tx.amount - parsed_row["amount"]) < 0.005
                and tx.type == parsed_row["type"]
                and _same_saldo(tx.saldo, parsed_row.get("saldo"))
                and _normalize_description(tx.raw_description) == _normalize_description(parsed_row["description"])
            ):
                exact_match = tx
                break

        requested_db_id = marked.get("db_id") or ""
        target_db = db.session.get(Transaction, int(requested_db_id)) if requested_db_id else None

        if target_db is not None:
            if (
                abs(target_db.amount - parsed_row["amount"]) < 0.005
                and target_db.type == parsed_row["type"]
                and _same_saldo(target_db.saldo, parsed_row.get("saldo"))
                and _normalize_description(target_db.raw_description) == _normalize_description(parsed_row["description"])
            ):
                action = "already_matches"
                matched_db_id = str(target_db.id)
                stats["already_matches"] += 1
            else:
                action = "update_existing"
                matched_db_id = str(target_db.id)
                stats["update_existing"] += 1
        elif exact_match is not None:
            action = "already_exists_other_id"
            matched_db_id = str(exact_match.id)
            stats["already_exists_other_id"] += 1
        else:
            action = "insert_missing"
            stats["insert_missing"] += 1

        plan_rows.append(
            {
                "action": action,
                "pdf_source": pdf_name,
                "date": date_iso,
                "parser_index": parser_index_raw,
                "db_id": requested_db_id,
                "matched_db_id": matched_db_id,
                "db_amount": marked.get("db_amount") or "",
                "db_saldo": marked.get("db_saldo") or "",
                "parser_amount": f"{parsed_row['amount']:.2f}",
                "parser_type": parsed_row["type"],
                "parser_saldo": "" if parsed_row.get("saldo") is None else f"{parsed_row['saldo']:.2f}",
                "db_description": marked.get("db_description") or "",
                "parser_description": parsed_row["description"],
                "same_day_db_ids": same_day_db_ids,
                "note": note,
            }
        )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "action",
                "pdf_source",
                "date",
                "parser_index",
                "db_id",
                "matched_db_id",
                "db_amount",
                "db_saldo",
                "parser_amount",
                "parser_type",
                "parser_saldo",
                "db_description",
                "parser_description",
                "same_day_db_ids",
                "note",
            ],
        )
        writer.writeheader()
        writer.writerows(plan_rows)

    return stats, plan_rows


def apply_marked_postfinance_repairs(csv_path: Optional[Path] = None) -> dict:
    """Apply marked PostFinance repairs from the reviewed CSV."""
    stats, plan_rows = _build_marked_postfinance_repair_plan(csv_path)
    result = {
        "targets": stats["targets"],
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
    }

    movements_dir: Path = current_app.config["BEWEGUNGEN_DIR"]
    pdf_cache: dict[str, list[dict]] = {}

    for row in plan_rows:
        action = row["action"]
        pdf_name = row["pdf_source"]
        date_iso = row["date"]

        if action in {"already_matches", "already_exists_other_id", "missing_pdf", "missing_parser_row"}:
            result["skipped"] += 1
            continue

        pdf_rows = pdf_cache.get(pdf_name)
        if pdf_rows is None:
            pdf_path = _find_pdf_by_name(movements_dir, pdf_name)
            if pdf_path is None:
                result["errors"] += 1
                continue
            pdf_rows = parse_postfinance_pdf(pdf_path)
            pdf_cache[pdf_name] = pdf_rows

        parser_amount = parse_chf(row["parser_amount"]) if row["parser_amount"] else None
        parser_saldo = parse_chf(row["parser_saldo"]) if row["parser_saldo"] else None
        parser_type = row["parser_type"]
        parser_description = row["parser_description"]

        parsed_row = None
        for candidate in pdf_rows:
            if candidate["date"].isoformat() != date_iso:
                continue
            if parser_amount is not None and abs(candidate["amount"] - parser_amount) >= 0.005:
                continue
            if candidate["type"] != parser_type:
                continue
            if not _same_saldo(candidate.get("saldo"), parser_saldo):
                continue
            if _normalize_description(candidate["description"]) != _normalize_description(parser_description):
                continue
            parsed_row = candidate
            break

        if parsed_row is None:
            result["errors"] += 1
            continue

        if action == "insert_missing":
            metadata = extract_account_metadata(_find_pdf_by_name(movements_dir, pdf_name))
            account = _ensure_account(metadata)
            account_iban = metadata.get("iban")
            if not account_iban:
                result["errors"] += 1
                continue
            import_hash = make_hash(account_iban, parsed_row["date"], parsed_row["amount"], parsed_row["description"])
            if Transaction.query.filter_by(import_hash=import_hash).first():
                result["skipped"] += 1
                continue
            db.session.add(
                Transaction(
                    account_id=account.id,
                    date=parsed_row["date"],
                    raw_description=parsed_row["description"],
                    amount=parsed_row["amount"],
                    type=parsed_row["type"],
                    saldo=parsed_row.get("saldo"),
                    pdf_source=pdf_name,
                    import_hash=import_hash,
                )
            )
            result["inserted"] += 1
            continue

        if action == "update_existing":
            db_id = row["db_id"]
            tx = db.session.get(Transaction, int(db_id)) if db_id else None
            if tx is None:
                result["errors"] += 1
                continue
            tx.raw_description = parsed_row["description"]
            tx.amount = parsed_row["amount"]
            tx.type = parsed_row["type"]
            tx.saldo = parsed_row.get("saldo")
            result["updated"] += 1
            continue

        result["skipped"] += 1

    db.session.commit()
    return result


__all__ = [
    "apply_marked_postfinance_repairs",
    "extract_account_metadata",
    "import_postfinance_documents",
    "normalize_postfinance_transactions",
    "parse_postfinance_pdf",
    "preview_marked_postfinance_repairs",
    "repair_postfinance_saldi",
]
