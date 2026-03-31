"""Invoice parser for Swiss QR-bill PDFs."""

import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from flask import current_app

from app import db
from app.models import Invoice
from .base import parse_chf, make_hash

# Amount patterns

# Standard Swiss format with apostrophe grouping, for example `1'470.00`
AMOUNT_RE = r"([\d]['\d]*(?:['.]\d+)+)"
# QR-specific format also allows spaces as thousands separators (`2 522.75`)
_QR_AMOUNT_RE = r"([\d][\d ']*\.\d{2})"

_BETRAG_PATTERNS = [
    r"Rechnungsbetrag\s+(?:inkl\.?\s*MWST\s+in\s+CHF\s+)?" + AMOUNT_RE,
    r"Total\s+Steuerbetrag\s+" + AMOUNT_RE,
    r"Rächnigstotal\s+CHF\s+" + AMOUNT_RE,
    r"Netto-Betrag\s+CHF\s+" + AMOUNT_RE,
    r"Total\s+(?:Rechnungsbetrag|Behandlung|einfache\s+Staatssteuer)?\s*(?:CHF\s*|Fr\.\s*)?" + AMOUNT_RE,
    # Accept `Gesamtbetrag CHF 1'470.00`, but not `Gesamtbetrag zahlbar bis: 31.03.2026`
    # where the date could otherwise be mistaken for an amount.
    r"Gesamtbetrag\s+(?:CHF|Fr\.)\s*" + AMOUNT_RE,
    r"Fr\.\s*" + AMOUNT_RE,
    r"CHF\s+" + AMOUNT_RE,
]

# OCR can produce several variants of the line that separates two slips on one page.
_TRENNLINIE = re.compile(
    r"vor\s*der?\s*einzahlung\s*abzutrennen",
    re.IGNORECASE,
)


def extract_slip_data(text: str) -> dict:
    """
    Extract metadata from one payment-slip text block.

    Returns:
        {"amount": float|None, "due_date": date|None, "slip_label": str|None}
    """
    result: dict = {"amount": None, "due_date": None, "slip_label": None}

    # Priority 1: canonical Swiss QR-bill pattern
    qr_m = re.search(
        r"(?:Währung|Wahrung|Currency)\s+(?:Betrag|Betmg|Amount)\s+"
        r"(?:CHF|EUR)\s+" + _QR_AMOUNT_RE,
        text, re.IGNORECASE,
    )
    if qr_m:
        result["amount"] = parse_chf(qr_m.group(1))

    # Priority 2: fallback invoice-text patterns
    if not result["amount"]:
        for pat in _BETRAG_PATTERNS:
            for m in re.finditer(pat, text, re.IGNORECASE):
                val = parse_chf(m.group(1))
                if val and val > 5:
                    result["amount"] = val
                    break
            if result["amount"]:
                break

    # Due date
    m = re.search(
        r"(?:zahlbar bis|fällig(?:keitsdatum)?|Zahlbar bis)[:\s]+(\d{1,2}\.\d{1,2}\.\d{2,4})",
        text, re.IGNORECASE,
    )
    if m:
        for fmt in ("%d.%m.%Y", "%d.%m.%y"):
            try:
                result["due_date"] = datetime.strptime(m.group(1), fmt).date()
                break
            except ValueError:
                pass

    # Slip label
    label_m = re.search(
        r"(\d+\.\s*Rate"
        r"|Ordentliche\s+Steuer\s+(?:Bund|Staat|Gemeinde)\s+\d{4}"
        r"|Direkte\s+Bundessteuer(?:\s+\d{4})?"
        r"|Bundessteuer|Kantonssteuer|Staatssteuer|Gemeindesteuer|Kirchensteuer"
        r"|Einkommenssteuer)",
        text, re.IGNORECASE,
    )
    if label_m:
        result["slip_label"] = label_m.group(1).strip()

    return result


def parse_invoice_slips(pdf_path: Path) -> list[dict]:
    """
    Read an invoice PDF and return one dictionary per payment slip.
    """
    try:
        import pdfplumber
    except ImportError:
        return []

    slips: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        page_texts = [p.extract_text() or "" for p in pdf.pages]
        full_text  = "\n".join(page_texts)
        first_lines = full_text.split("\n")

    # Issuer: first useful line from the document
    raw_issuer: Optional[str] = None
    for line in first_lines:
        line = line.strip()
        if (len(line) > 3
                and not any(c.isdigit() for c in line[:3])
                and len(line) < 60
                and not any(kw in line.lower() for kw in
                            ["www.", "iban", "mwst", "seite", "tel", "fax"])):
            raw_issuer = line
            break

    # Invoice date from the full document text
    invoice_date: Optional[date] = None
    for pat in [
        r"Rechnungsdatum[:\s]+(\d{1,2}[.\s/]\d{1,2}[.\s/]\d{2,4})",
        r"Rechnungs-Datum[:\s]+(\d{2}\.\d{2}\.\d{4})",
        r"Datum[:\s]+(\d{2}\.\d{2}\.\d{4})",
    ]:
        m_date = re.search(pat, full_text, re.IGNORECASE)
        if m_date:
            for fmt in ("%d.%m.%Y", "%d.%m.%y"):
                try:
                    invoice_date = datetime.strptime(m_date.group(1).strip(), fmt).date()
                    break
                except ValueError:
                    pass
        if invoice_date:
            break

    # Identify slip pages and split them on separator lines
    raw_slips: list[tuple[int, int, str]] = []
    for i, text in enumerate(page_texts):
        if "Zahlteil" not in text and "Empfangsschein" not in text:
            continue
        parts     = _TRENNLINIE.split(text)
        sub_slips = [p for p in parts if "Zahlteil" in p or "Empfangsschein" in p]
        if not sub_slips:
            sub_slips = [text]
        for sub_idx, part in enumerate(sub_slips):
            raw_slips.append((i, sub_idx, part))

    # Fallback: treat the whole document as one slip
    if not raw_slips:
        raw_slips = [(len(page_texts) - 1, 0, full_text)]

    for page_idx, sub_idx, slip_text in raw_slips:
        slip_data = extract_slip_data(slip_text)

        # Amount fallback only when the document contains exactly one slip
        if slip_data["amount"] is None and len(raw_slips) == 1:
            for pat in _BETRAG_PATTERNS:
                for m in re.finditer(pat, full_text, re.IGNORECASE):
                    val = parse_chf(m.group(1))
                    if val and val > 5:
                        slip_data["amount"] = val
                        break
                if slip_data["amount"]:
                    break

        slips.append({
            "filename":     pdf_path.name,
            "page_index":   page_idx * 10 + sub_idx,
            "slip_label":   slip_data.get("slip_label"),
            "raw_issuer":   raw_issuer,
            "amount":       slip_data.get("amount"),
            "invoice_date": invoice_date,
            "due_date":     slip_data.get("due_date"),
        })

    return slips


def _extract_source_year(pdf_path: Path) -> Optional[int]:
    """
    Extract a year from the folder path or filename.
    """
    for part in pdf_path.parts:
        if part.isdigit() and len(part) == 4 and 2000 <= int(part) <= 2100:
            return int(part)
    name = pdf_path.name
    if len(name) >= 4 and name[:4].isdigit():
        y = int(name[:4])
        if 2000 <= y <= 2100:
            return y
    return None


def _import_from_dir(directory: Path, default_status: str) -> dict:
    """Shared logic for pending and paid invoice folders."""
    stats = {"imported": 0, "skipped": 0, "errors": 0}

    if not directory.exists():
        current_app.logger.warning(f"Directory not found: {directory}")
        return stats

    for pdf in sorted(directory.rglob("*.pdf")):
        source_year = _extract_source_year(pdf)

        # Skip only when every existing entry for the file already has the target status.
        existing_all = Invoice.query.filter_by(filename=pdf.name).all()
        if existing_all and all(e.status == default_status for e in existing_all):
            stats["skipped"] += 1
            continue

        try:
            slips = parse_invoice_slips(pdf)
            for slip in slips:
                h = make_hash(slip["filename"], slip["page_index"])
                existing = Invoice.query.filter_by(import_hash=h).first()
                if existing:
                    # The file moved from pending to paid: update the existing invoice.
                    if existing.status != default_status:
                        existing.status = default_status
                        if source_year:
                            existing.source_year = source_year
                        stats["imported"] += 1
                    else:
                        stats["skipped"] += 1
                    continue

                inv = Invoice(
                    filename     = slip["filename"],
                    page_index   = slip["page_index"],
                    slip_label   = slip.get("slip_label"),
                    raw_issuer   = slip.get("raw_issuer"),
                    amount       = slip.get("amount"),
                    invoice_date = slip.get("invoice_date"),
                    due_date     = slip.get("due_date"),
                    import_hash  = h,
                    status       = default_status,
                    source_year  = source_year,
                )
                db.session.add(inv)
                stats["imported"] += 1
        except Exception as e:
            current_app.logger.error(f"Failed to import {pdf.name}: {e}")
            stats["errors"] += 1

    db.session.commit()
    return stats


def import_rechnungen() -> dict:
    """
    Imports PDF from both invoice folders:
      01-Rechnungen-Pendent/ → status="pending"
      02-Rechnungen-Bezahlt/ → status="paid"

    Returns:
        {"imported": int, "skipped": int, "errors": int}
    """
    stats: dict = {"imported": 0, "skipped": 0, "errors": 0}

    for config_key, default_status in [
        ("PENDENT_DIR", "pending"),
        ("BEZAHLT_DIR", "paid"),
    ]:
        d = _import_from_dir(current_app.config[config_key], default_status)
        for k in stats:
            stats[k] += d[k]

    return stats


import_invoices = import_rechnungen
