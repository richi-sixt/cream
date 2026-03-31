"""Shared helper functions for importers."""

import hashlib
import re
from datetime import date
from pathlib import Path
from typing import Optional

from flask import current_app

from app import db
from app.models import Account


def parse_chf(s: str) -> Optional[float]:
    """Normalize a CHF amount string into a float."""
    s = (s.replace("'", "")
          .replace(" ", "")
          .replace(",", ".")
          .replace("O", "0")
          .replace("o", "0"))
    parts = s.split(".")
    if len(parts) > 2:
        s = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(s)
    except ValueError:
        return None


def date_from_ddmmyy(s: str) -> Optional[date]:
    """Convert `DD.MM.YY` into `date`, returning `None` for invalid input."""
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{2})$", s)
    if not m:
        return None
    try:
        return date(2000 + int(m[3]), int(m[2]), int(m[1]))
    except ValueError:
        return None


def make_hash(*parts) -> str:
    """Create a stable SHA1 hash from arbitrary values."""
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode()).hexdigest()


def group_words_by_row(words: list, y_tolerance: int = 3) -> dict:
    """Group pdfplumber words by approximate row position."""
    rows: dict = {}
    for w in words:
        y = round(w["top"] / y_tolerance) * y_tolerance
        rows.setdefault(y, []).append(w)
    return {y: sorted(ws, key=lambda w: w["x0"]) for y, ws in sorted(rows.items())}


def get_or_create_account(iban: str, name: str) -> Account:
    """Return an existing account or create a new one."""
    account = Account.query.filter_by(iban=iban).first()
    if not account:
        account = Account(name=name, iban=iban, type="checking", currency="CHF")
        db.session.add(account)
        db.session.flush()
    return account
