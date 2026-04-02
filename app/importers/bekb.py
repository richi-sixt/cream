"""BEKB-specific parsers and import helpers.

The `03-Bewegungen` directory contains two relevant BEKB document families:
- monthly account statements (`Kontoauszug`)
- single transaction notices (`Gutschrifts_Belastungsanzeige`)

This module parses both document types, derives account metadata from the PDF,
and stores transactions per IBAN instead of assuming one hard-coded account.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from flask import current_app, has_app_context

from app import db
from app.models import Account, Transaction, TransactionLine
from .base import date_from_ddmmyy, get_or_create_account, group_words_by_row, make_hash, parse_chf

_IBAN_RE = re.compile(r"CH\d{2}", re.IGNORECASE)
_IBAN_ANYWHERE_RE = re.compile(r"(CH\d{2}(?:\s*\d){17})", re.IGNORECASE)
_AMOUNT_AT_END_RE = re.compile(r"\s+([\d][\d']*\.\d{2})\s*$")
_MAIN_TX_RE = re.compile(r"^\d{2}\.\d{2}\.\d{2}\s")
_NOTICE_VALUE_RE = re.compile(
    r"Valuta\s*(\d{2}\.\d{2}\.\d{4})\s+CHF\s+([\d' ]+\.\d{2})",
    re.IGNORECASE,
)
_NOTICE_SALDO_RE = re.compile(
    r"(?:zu Ihren Gunsten|zu Ihren Lasten)\s+CHF\s+([\d' ]+\.\d{2})",
    re.IGNORECASE,
)
_SKIP_RE = re.compile(
    r"^(Berner Kantonalbank|Bachstrasse 21|Bahnhofstrasse 2|4614.H|3401Burgdorf|"
    r"Privatkonto|Lautend auf:|Kontoauszug per|Datum Buchungstext|IBAN CH77|IBAN CH78|"
    r"IBAN CH26|IBAN CH49|IBAN CH60|KFF\d{10,})",
    re.IGNORECASE,
)

_ACCOUNT_KIND_TO_TYPE = {
    "sparkonto": "savings",
    "privatkonto": "checking",
    "privatkonto plus": "checking",
    "finanzierungskonto": "other",
}
_BANK_NAME_ALIASES = {
    "berner kantonalbank ag": "BEKB",
    "berner kantonalbank": "BEKB",
}


def _normalize_iban(raw_iban: str) -> str:
    """Return a compact Swiss IBAN without whitespace."""
    return re.sub(r"\s+", "", raw_iban).upper()


def _extract_iban_from_filename(pdf_path: Path) -> Optional[str]:
    """Extract the leading IBAN from BEKB filenames when present."""
    match = _IBAN_ANYWHERE_RE.search(pdf_path.name)
    if not match:
        return None
    return _normalize_iban(match.group(1))


def _read_pdf_text(pdf_path: Path) -> str:
    """Read all text from a PDF file using pdfplumber."""
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _read_first_page_lines(pdf_path: Path) -> list[str]:
    """Read non-empty lines from the first PDF page."""
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return []
        text = pdf.pages[0].extract_text() or ""
    return [line.strip() for line in text.splitlines() if line.strip()]


def _extract_account_kind(lines: list[str]) -> Optional[str]:
    """Extract the account kind label from the first page."""
    for line in lines:
        lower = line.lower()
        if "konto" not in lower:
            continue
        if line.startswith("IBAN ") or line.startswith("Kontoauszug per"):
            continue
        if line.startswith("Berner Kantonalbank") or line.startswith("Datum Buchungstext"):
            continue
        if any(keyword in lower for keyword in _ACCOUNT_KIND_TO_TYPE):
            return line
    return None


def _extract_bank_name(lines: list[str]) -> Optional[str]:
    """Extract a normalized bank name from the first page."""
    for line in lines:
        lowered = line.lower()
        for raw_name, alias in _BANK_NAME_ALIASES.items():
            if raw_name in lowered:
                return alias
    return None


def _extract_account_holder(lines: list[str]) -> Optional[str]:
    """Extract the human-readable account holder or account label."""
    for idx, line in enumerate(lines):
        if not line.startswith("IBAN "):
            continue
        for candidate in lines[idx + 1 : idx + 6]:
            if re.match(r"^\d{4}\b", candidate):
                break
            if any(char.isalpha() for char in candidate):
                return candidate
    return None


def extract_account_metadata(pdf_path: Path) -> dict[str, Optional[str]]:
    """Extract account metadata from a BEKB document.

    The importer falls back to the filename IBAN when OCR text is noisy.
    """
    try:
        lines = _read_first_page_lines(pdf_path)
    except ImportError:
        lines = []

    iban = _extract_iban_from_filename(pdf_path)
    if not iban:
        for line in lines:
            if not line.startswith("IBAN "):
                continue
            match = _IBAN_ANYWHERE_RE.search(line)
            if match:
                iban = _normalize_iban(match.group(1))
                break

    account_kind = _extract_account_kind(lines)
    holder = _extract_account_holder(lines)
    bank_name = _extract_bank_name(lines) or "Bank"
    configured_name = None
    if iban and has_app_context():
        configured_name = current_app.config.get("ACCOUNT_NAME_OVERRIDES", {}).get(iban)

    if configured_name:
        name = configured_name
    elif account_kind and holder and holder.lower() not in account_kind.lower():
        name = f"{bank_name} {account_kind} - {holder}"
    elif account_kind:
        name = f"{bank_name} {account_kind}"
    elif holder:
        name = f"{bank_name} - {holder}"
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
        "bank_name": bank_name,
        "account_kind": account_kind,
        "type": account_type,
    }


def _clean_flat_lines(pdf_path: Path) -> list[str]:
    """Return all content lines across all pages without page furniture."""
    try:
        import pdfplumber
    except ImportError:
        return []

    result: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                stripped = line.strip()
                if stripped and not _SKIP_RE.match(stripped):
                    result.append(stripped)
    return result


def _get_detail_lines(flat_lines: list[str], date_str: str, amount: float) -> list[str]:
    """Locate detail lines for a statement row describing an e-banking order."""
    amount_str = f"{amount:,.2f}".replace(",", "'")

    start_index: Optional[int] = None
    for index, line in enumerate(flat_lines):
        if line.startswith(date_str) and "E-Banking-Auftrag" in line and amount_str in line:
            start_index = index + 1
            break

    if start_index is None:
        return []

    detail_lines: list[str] = []
    for line in flat_lines[start_index:]:
        if _MAIN_TX_RE.match(line):
            break
        detail_lines.append(line)
    return detail_lines


def _parse_single_block(block: list[str], override_amount: Optional[float] = None) -> Optional[dict]:
    """Parse one detail block into recipient, amount, and destination IBAN."""
    if not block:
        return None

    first_line = block[0]
    amount_match = _AMOUNT_AT_END_RE.search(first_line)

    if amount_match:
        amount = parse_chf(amount_match.group(1)) or 0.0
        recipient = first_line[: amount_match.start()].strip()
    else:
        amount = override_amount or 0.0
        recipient = first_line.strip()

    if recipient.endswith("-") and len(block) > 1:
        next_line = block[1]
        if not _IBAN_RE.match(next_line) and not re.match(r"^\d{4}", next_line):
            recipient = recipient[:-1] + next_line

    iban: Optional[str] = None
    for line in block:
        if _IBAN_RE.match(line):
            iban = _normalize_iban(line)[:21]
            break

    return {"recipient": recipient.strip(), "amount": amount, "iban": iban}


def _parse_sub_entries(detail_lines: list[str], total_amount: float) -> list[dict]:
    """Parse e-banking detail rows into one or more child transfers."""
    lines = [line for line in detail_lines if line.strip()]
    if not lines:
        return []

    is_multi_entry = lines[0] == "."
    if not is_multi_entry:
        entry = _parse_single_block(lines, override_amount=total_amount)
        return [entry] if entry else []

    blocks: list[list[str]] = []
    current_block: list[str] = []
    for line in lines:
        if line == ".":
            if current_block:
                blocks.append(current_block)
            current_block = []
        else:
            current_block.append(line)
    if current_block:
        blocks.append(current_block)

    parsed_entries: list[dict] = []
    for block in blocks:
        entry = _parse_single_block(block)
        if entry:
            parsed_entries.append(entry)
    return parsed_entries


def parse_bekb_pdf(pdf_path: Path) -> list[dict]:
    """Parse a monthly BEKB account statement into transaction dictionaries."""
    try:
        import pdfplumber
    except ImportError:
        current_app.logger.error("pdfplumber is not installed.")
        return []

    flat_lines = _clean_flat_lines(pdf_path)
    transactions: list[dict] = []
    date_pattern = re.compile(r"^\d{2}\.\d{2}\.\d{2}$")

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()

            columns: dict[str, float] = {}
            for word in words:
                if word["text"] in ("Belastung", "Gutschrift", "Valuta", "Saldo"):
                    columns[word["text"]] = word["x0"]

            if "Belastung" not in columns:
                continue

            credit_x = columns["Gutschrift"]
            balance_x = columns["Saldo"]
            rows = group_words_by_row(words)

            for row_words in rows.values():
                texts = [word["text"] for word in row_words]
                xs = [word["x0"] for word in row_words]

                if not texts or not date_pattern.match(texts[0]) or xs[0] >= 55:
                    continue

                if len(texts) >= 2 and texts[1] == "Saldovortrag":
                    continue

                amount: Optional[float] = None
                tx_type: Optional[str] = None
                balance: Optional[float] = None
                description_parts: list[str] = []

                for word in row_words[1:]:
                    x = word["x0"]
                    text = word["text"]
                    if date_pattern.match(text) and x >= columns.get("Valuta", 440) - 15:
                        continue
                    number = parse_chf(text)
                    if number is not None:
                        if x >= balance_x - 20:
                            balance = number
                        elif x >= credit_x:
                            amount, tx_type = number, "income"
                        elif x >= columns["Belastung"] - 10:
                            amount, tx_type = number, "expense"
                        else:
                            description_parts.append(text)
                    elif x < columns["Belastung"] - 5:
                        description_parts.append(text)

                tx_date = date_from_ddmmyy(texts[0])
                if tx_date and amount is not None:
                    description = " ".join(description_parts).strip() or "-"
                    tx = {
                        "date": tx_date,
                        "description": description,
                        "amount": amount,
                        "type": tx_type or "expense",
                        "saldo": balance,
                        "lines": [],
                    }

                    if "E-Banking-Auftrag" in description:
                        detail_lines = _get_detail_lines(flat_lines, texts[0], amount)
                        tx["lines"] = _parse_sub_entries(detail_lines, amount)

                    transactions.append(tx)

    return transactions


def _extract_notice_counterparty(text: str) -> Optional[str]:
    """Extract the most helpful counterparty label from a notice."""
    patterns = [
        r"Bezahlt von:\s*CHF\s+[\d' ]+\.\d{2}\s+([^\n]+)",
        r"Ursprünglicher Begünstigter:\s+([^\n]+)",
        r"Urspruenglicher Beguenstigter:\s+([^\n]+)",
        r"Begünstigter:\s+([^\n]+)",
        r"Beguenstigter:\s+([^\n]+)",
        r"Zahlungsempfänger:\s+([^\n]+)",
        r"Zahlungsempfaenger:\s+([^\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def parse_bekb_notice(pdf_path: Path) -> list[dict]:
    """Parse a BEKB credit/debit notice into a single transaction dictionary."""
    try:
        text = _read_pdf_text(pdf_path)
    except ImportError:
        current_app.logger.error("pdfplumber is not installed.")
        return []

    value_match = _NOTICE_VALUE_RE.search(text)
    if not value_match:
        return []

    value_date = _parse_notice_value_date(value_match.group(1))
    amount = parse_chf(value_match.group(2))
    if value_date is None or amount is None:
        return []

    lower_text = text.lower()
    if "zahlungseingang" in lower_text or "gutschrift" in lower_text:
        description = "Zahlungseingang"
        tx_type = "income"
    else:
        description = "Belastungsanzeige"
        tx_type = "expense"

    if "rückleitung" in lower_text:
        description = "Zahlungseingang (Rückleitung)"

    counterparty = _extract_notice_counterparty(text)
    if counterparty:
        description = f"{description}: {counterparty}"

    balance_match = _NOTICE_SALDO_RE.search(text)
    balance = parse_chf(balance_match.group(1)) if balance_match else None

    return [
        {
            "date": value_date,
            "description": description,
            "amount": amount,
            "type": tx_type,
            "saldo": balance,
            "lines": [],
        }
    ]


def _parse_notice_value_date(raw_date: str):
    """Parse BEKB notice value dates in `dd.mm.yyyy` and `dd.mm.yy` formats."""
    raw = raw_date.strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass

    # Backwards-compatible fallback for older OCR variants.
    return date_from_ddmmyy(raw[:8])


def parse_bekb_document(pdf_path: Path) -> list[dict]:
    """Dispatch parsing based on the BEKB document family."""
    if "Kontoauszug" in pdf_path.name:
        return parse_bekb_pdf(pdf_path)
    if "Gutschrifts_Belastungsanzeige" in pdf_path.name:
        return parse_bekb_notice(pdf_path)
    return []


def _build_transaction_hashes(raw_transaction: dict, account_iban: str) -> tuple[str, str]:
    """Return both new and legacy import hashes for backwards compatibility."""
    new_hash = make_hash(account_iban, raw_transaction["date"], raw_transaction["amount"], raw_transaction["description"])
    legacy_hash = make_hash(raw_transaction["date"], raw_transaction["amount"], raw_transaction["description"])
    return new_hash, legacy_hash


def _ensure_account(metadata: dict[str, Optional[str]]) -> Account:
    """Create or update an account entry from parsed metadata."""
    iban = metadata.get("iban") or "UNKNOWN"
    name = metadata.get("name") or iban
    account_type = metadata.get("type") or "checking"

    account = get_or_create_account(iban, name)
    if account.name != name and name:
        account.name = name
    if account.type != account_type and account_type:
        account.type = account_type
    return account


def reparse_transaction_lines() -> dict:
    """Backfill child transfer rows for already imported e-banking statements."""
    movements_dir: Path = current_app.config["BEWEGUNGEN_DIR"]
    stats = {"updated": 0, "skipped": 0, "errors": 0}

    if not movements_dir.exists():
        current_app.logger.warning("Movements directory not found: %s", movements_dir)
        return stats

    for pdf in sorted(movements_dir.rglob("*.pdf")):
        if "Kontoauszug" not in pdf.name:
            continue
        try:
            metadata = extract_account_metadata(pdf)
            account_iban = metadata.get("iban") or _extract_iban_from_filename(pdf) or "UNKNOWN"
            raw_transactions = parse_bekb_pdf(pdf)
            for raw in raw_transactions:
                if "E-Banking-Auftrag" not in raw.get("description", ""):
                    continue
                if not raw.get("lines"):
                    continue

                new_hash, legacy_hash = _build_transaction_hashes(raw, account_iban)
                tx = Transaction.query.filter(
                    Transaction.import_hash.in_([new_hash, legacy_hash])
                ).first()
                if not tx:
                    stats["skipped"] += 1
                    continue
                if tx.lines:
                    stats["skipped"] += 1
                    continue

                for position, line_data in enumerate(raw["lines"]):
                    db.session.add(
                        TransactionLine(
                            transaction_id=tx.id,
                            position=position,
                            recipient=line_data["recipient"],
                            amount=line_data["amount"],
                            iban=line_data.get("iban"),
                        )
                    )

                stats["updated"] += 1
        except Exception as exc:  # pragma: no cover - defensive logging path
            current_app.logger.error("Failed to reparse %s: %s", pdf.name, exc)
            stats["errors"] += 1

    db.session.commit()
    return stats


def import_bank_documents() -> dict:
    """Import supported BEKB PDFs from `03-Bewegungen/`."""
    movements_dir: Path = current_app.config["BEWEGUNGEN_DIR"]
    stats = {"imported": 0, "skipped": 0, "errors": 0}

    if not movements_dir.exists():
        current_app.logger.warning("Movements directory not found: %s", movements_dir)
        return stats

    for pdf in sorted(movements_dir.rglob("*.pdf")):
        if not any(token in pdf.name for token in ("Kontoauszug", "Gutschrifts_Belastungsanzeige")):
            continue
        if Transaction.query.filter_by(pdf_source=pdf.name).first():
            stats["skipped"] += 1
            continue

        try:
            metadata = extract_account_metadata(pdf)
            account_iban = metadata.get("iban") or _extract_iban_from_filename(pdf)
            if not account_iban:
                current_app.logger.warning("Skipping %s because no IBAN could be derived.", pdf.name)
                stats["errors"] += 1
                continue

            account = _ensure_account({**metadata, "iban": account_iban})
            raw_transactions = parse_bekb_document(pdf)

            for raw in raw_transactions:
                new_hash, legacy_hash = _build_transaction_hashes(raw, account_iban)
                if Transaction.query.filter(Transaction.import_hash.in_([new_hash, legacy_hash])).first():
                    stats["skipped"] += 1
                    continue

                tx = Transaction(
                    account_id=account.id,
                    date=raw["date"],
                    raw_description=raw["description"],
                    amount=raw["amount"],
                    type=raw["type"],
                    saldo=raw.get("saldo"),
                    pdf_source=pdf.name,
                    import_hash=new_hash,
                )
                db.session.add(tx)
                db.session.flush()

                for position, line_data in enumerate(raw.get("lines", [])):
                    db.session.add(
                        TransactionLine(
                            transaction_id=tx.id,
                            position=position,
                            recipient=line_data["recipient"],
                            amount=line_data["amount"],
                            iban=line_data.get("iban"),
                        )
                    )

                stats["imported"] += 1
        except Exception as exc:  # pragma: no cover - defensive logging path
            current_app.logger.error("Failed to import %s: %s", pdf.name, exc)
            stats["errors"] += 1

    db.session.commit()
    return stats


def repair_bekb_notice_dates() -> dict:
    """Repair already imported BEKB notice rows with wrong parsed years."""
    movements_dir: Path = current_app.config["BEWEGUNGEN_DIR"]
    stats = {"updated": 0, "unchanged": 0, "missing": 0, "errors": 0}

    if not movements_dir.exists():
        current_app.logger.warning("Movements directory not found: %s", movements_dir)
        return stats

    for pdf in sorted(movements_dir.rglob("*.pdf")):
        if "Gutschrifts_Belastungsanzeige" not in pdf.name:
            continue

        try:
            parsed = parse_bekb_notice(pdf)
            if not parsed:
                stats["missing"] += 1
                continue

            tx = Transaction.query.filter_by(pdf_source=pdf.name).first()
            if tx is None:
                stats["missing"] += 1
                continue

            raw = parsed[0]
            account_iban = tx.account.iban if tx.account else None
            if not account_iban:
                account_iban = extract_account_metadata(pdf).get("iban")
            if not account_iban:
                stats["errors"] += 1
                continue

            new_hash, legacy_hash = _build_transaction_hashes(raw, account_iban)

            if (
                tx.date == raw["date"]
                and tx.amount == raw["amount"]
                and tx.type == raw["type"]
                and (tx.saldo or None) == raw.get("saldo")
                and tx.raw_description == raw["description"]
                and tx.import_hash in (new_hash, legacy_hash)
            ):
                stats["unchanged"] += 1
                continue

            collision = (
                Transaction.query
                .filter(
                    Transaction.id != tx.id,
                    Transaction.import_hash.in_([new_hash, legacy_hash]),
                )
                .first()
            )
            if collision:
                current_app.logger.warning(
                    "Skipped hash-collision repair for %s (tx_id=%s, collides with tx_id=%s).",
                    pdf.name,
                    tx.id,
                    collision.id,
                )
                stats["errors"] += 1
                continue

            tx.date = raw["date"]
            tx.raw_description = raw["description"]
            tx.amount = raw["amount"]
            tx.type = raw["type"]
            tx.saldo = raw.get("saldo")
            tx.import_hash = new_hash
            stats["updated"] += 1
        except Exception as exc:  # pragma: no cover - defensive logging path
            current_app.logger.error("Failed to repair %s: %s", pdf.name, exc)
            stats["errors"] += 1

    db.session.commit()
    return stats


def sync_account_name_overrides() -> dict:
    """Apply configured `ACCOUNT_NAME_OVERRIDES` to existing account rows."""
    overrides: dict = current_app.config.get("ACCOUNT_NAME_OVERRIDES", {}) or {}
    stats = {"updated": 0, "unchanged": 0, "missing": 0}

    for iban, target_name in overrides.items():
        account = Account.query.filter_by(iban=iban).first()
        if account is None:
            stats["missing"] += 1
            continue
        if account.name == target_name:
            stats["unchanged"] += 1
            continue
        account.name = target_name
        stats["updated"] += 1

    db.session.commit()
    return stats


# Backwards-compatible aliases while the rest of the codebase transitions to English names.
import_kontoauszuege = import_bank_documents

__all__ = [
    "extract_account_metadata",
    "import_bank_documents",
    "import_kontoauszuege",
    "parse_bekb_document",
    "parse_bekb_notice",
    "parse_bekb_pdf",
    "repair_bekb_notice_dates",
    "sync_account_name_overrides",
    "reparse_transaction_lines",
    "_parse_single_block",
    "_parse_sub_entries",
]
