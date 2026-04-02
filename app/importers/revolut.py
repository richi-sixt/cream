"""Revolut statement parser and importer."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from flask import current_app, has_app_context

from app import db
from app.models import Account, Transaction
from .base import get_or_create_account, make_hash, parse_chf

_BANK_NAME = "Revolut"
_STATEMENT_NAME_RE = re.compile(r"^account-statement_.*\.pdf$", re.IGNORECASE)
_IBAN_RE = re.compile(r"\bIBAN\s+([A-Z]{2}[A-Z0-9]{13,32})\b")
_AMOUNT_RE = r"([0-9][0-9,]*\.[0-9]{2})"
_TX_LINE_RE = re.compile(
    rf"^(\d{{1,2}})\s+([A-Za-z]{{3}})\s+(\d{{4}})\s+(.+?)\s+{_AMOUNT_RE}\s+CHF\s+{_AMOUNT_RE}\s+CHF$"
)
_OPENING_BALANCE_RE = re.compile(
    rf"^Account\s+\(E-Money\)\s+{_AMOUNT_RE}\s+CHF\b",
    re.IGNORECASE,
)
_CONTINUATION_PREFIXES = (
    "To:",
    "From:",
    "Card:",
    "Reference:",
    "Revolut Rate",
)
_INCOME_HINTS = (
    "payment from",
    "cashback",
    "salary",
    "refund",
    "interest",
)


def _is_revolut_statement(pdf_path: Path) -> bool:
    """Return whether a PDF filename matches Revolut statement exports."""
    return bool(_STATEMENT_NAME_RE.match(pdf_path.name))


def _read_pdf_lines(pdf_path: Path) -> list[str]:
    """Read all non-empty text lines from a PDF file."""
    import pdfplumber

    lines: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines.extend(line.strip() for line in text.splitlines() if line.strip())
    return lines


def _read_first_page_lines(pdf_path: Path) -> list[str]:
    """Read first-page lines for account metadata extraction."""
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return []
        text = pdf.pages[0].extract_text() or ""
    return [line.strip() for line in text.splitlines() if line.strip()]


def _extract_opening_balance(lines: list[str]) -> Optional[float]:
    """Extract opening balance from summary table when available."""
    for line in lines:
        m = _OPENING_BALANCE_RE.match(line)
        if not m:
            continue
        opening = parse_chf(m.group(1))
        if opening is not None:
            return opening
    return None


def _parse_date(day: str, mon: str, year: str) -> Optional[datetime.date]:
    """Parse Revolut transaction dates like `3 Jan 2020`."""
    try:
        return datetime.strptime(f"{int(day)} {mon} {year}", "%d %b %Y").date()
    except ValueError:
        return None


def _infer_type(
    description: str,
    amount: float,
    balance: float,
    previous_balance: Optional[float],
) -> str:
    """Infer transaction type using balance deltas and fallback text hints."""
    if previous_balance is not None:
        delta = round(balance - previous_balance, 2)
        if abs(abs(delta) - amount) <= 0.05:
            return "income" if delta >= 0 else "expense"
    lowered = description.lower()
    if any(hint in lowered for hint in _INCOME_HINTS):
        return "income"
    return "expense"


def _normalize_description(description: str, details: list[str]) -> str:
    """Build a stable description including useful continuation lines."""
    extras = [d for d in details if d and not d.startswith("Date Description Money out Money in Balance")]
    if extras:
        return " | ".join([description] + extras)
    return description


def extract_account_metadata(pdf_path: Path) -> dict[str, Optional[str]]:
    """Extract Revolut account metadata from statement header."""
    try:
        lines = _read_first_page_lines(pdf_path)
    except ImportError:
        lines = []

    iban = None
    for line in lines:
        m = _IBAN_RE.search(line)
        if m:
            iban = m.group(1).replace(" ", "").upper()
            break

    holder = None
    for idx, line in enumerate(lines):
        if line.lower().startswith("revolut"):
            if idx + 1 < len(lines):
                candidate = lines[idx + 1].strip()
                if candidate and "statement" not in candidate.lower():
                    holder = candidate.title()
                    break

    configured_name = None
    if iban and has_app_context():
        configured_name = current_app.config.get("ACCOUNT_NAME_OVERRIDES", {}).get(iban)

    if configured_name:
        name = configured_name
    elif holder:
        name = f"{_BANK_NAME} - {holder}"
    else:
        name = iban or f"{_BANK_NAME} Account"

    return {
        "iban": iban,
        "name": name,
        "bank_name": _BANK_NAME,
        "account_kind": "E-Money",
        "type": "checking",
    }


def _ensure_account(metadata: dict[str, Optional[str]]) -> Account:
    """Create or update account row from Revolut metadata."""
    iban = metadata.get("iban") or "REVOLUT-UNKNOWN"
    name = metadata.get("name") or iban
    account = get_or_create_account(iban, name)
    if name and account.name != name:
        account.name = name
    if account.type != "checking":
        account.type = "checking"
    if account.currency != "CHF":
        account.currency = "CHF"
    return account


def parse_revolut_statement(pdf_path: Path) -> list[dict]:
    """Parse Revolut statement rows into transaction dictionaries."""
    try:
        lines = _read_pdf_lines(pdf_path)
    except ImportError:
        current_app.logger.error("pdfplumber is not installed.")
        return []

    transactions: list[dict] = []
    opening_balance = _extract_opening_balance(lines)
    previous_balance = opening_balance
    current: Optional[dict] = None
    detail_lines: list[str] = []

    def flush_current():
        nonlocal current, detail_lines, previous_balance
        if current is None:
            return
        current["description"] = _normalize_description(current["description"], detail_lines)
        transactions.append(current)
        previous_balance = current["saldo"]
        current = None
        detail_lines = []

    for line in lines:
        m = _TX_LINE_RE.match(line)
        if m:
            flush_current()
            tx_date = _parse_date(m.group(1), m.group(2), m.group(3))
            if tx_date is None:
                continue
            description = m.group(4).strip()
            amount = parse_chf(m.group(5))
            balance = parse_chf(m.group(6))
            if amount is None or balance is None:
                continue
            tx_type = _infer_type(description, amount, balance, previous_balance)
            current = {
                "date": tx_date,
                "description": description,
                "amount": amount,
                "type": tx_type,
                "saldo": balance,
                "lines": [],
            }
            continue

        if current and line.startswith(_CONTINUATION_PREFIXES):
            detail_lines.append(line)

    flush_current()
    return transactions


def import_revolut_documents() -> dict:
    """Import supported Revolut statement PDFs from `03-Bewegungen/`."""
    movements_dir: Path = current_app.config["BEWEGUNGEN_DIR"]
    stats = {"imported": 0, "skipped": 0, "errors": 0}

    if not movements_dir.exists():
        current_app.logger.warning("Movements directory not found: %s", movements_dir)
        return stats

    for pdf in sorted(movements_dir.rglob("*.pdf")):
        if not _is_revolut_statement(pdf):
            continue
        try:
            metadata = extract_account_metadata(pdf)
            account = _ensure_account(metadata)
            account_iban = account.iban or metadata.get("iban") or "REVOLUT-UNKNOWN"
            rows = parse_revolut_statement(pdf)
            for row in rows:
                tx_hash = make_hash(
                    account_iban,
                    row["date"],
                    row["amount"],
                    row["type"],
                    row["description"],
                    row.get("saldo"),
                )
                if Transaction.query.filter_by(import_hash=tx_hash).first():
                    stats["skipped"] += 1
                    continue

                db.session.add(
                    Transaction(
                        account_id=account.id,
                        date=row["date"],
                        raw_description=row["description"],
                        amount=row["amount"],
                        type=row["type"],
                        saldo=row.get("saldo"),
                        pdf_source=pdf.name,
                        import_hash=tx_hash,
                    )
                )
                stats["imported"] += 1
        except Exception as exc:  # pragma: no cover - defensive logging path
            current_app.logger.error("Failed to import %s: %s", pdf.name, exc)
            stats["errors"] += 1

    db.session.commit()
    return stats


__all__ = [
    "extract_account_metadata",
    "import_revolut_documents",
    "parse_revolut_statement",
]
