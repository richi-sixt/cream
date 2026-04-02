"""Regression tests for invoice import status/year preservation."""

from datetime import date
from pathlib import Path

from app.importers.invoices import _import_from_dir
from app.importers.base import make_hash
from app.models import Invoice


def _touch_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n%EOF\n")


def test_pending_reimport_does_not_downgrade_paid_or_source_year(app, db, monkeypatch):
    pdf = app.config["PENDENT_DIR"] / "2025-Rechnung-Steuern.pdf"
    _touch_pdf(pdf)

    monkeypatch.setattr(
        "app.importers.invoices.parse_invoice_slips",
        lambda _pdf: [
            {
                "filename": "2025-Rechnung-Steuern.pdf",
                "page_index": 0,
                "slip_label": "Direkte Bundessteuer 2025",
                "raw_issuer": "Steueramt des Kantons Solothurn",
                "amount": 1470.0,
                "invoice_date": date(2025, 12, 10),
                "due_date": date(2026, 3, 31),
            }
        ],
    )

    h = make_hash("2025-Rechnung-Steuern.pdf", 0)
    existing = Invoice(
        filename="2025-Rechnung-Steuern.pdf",
        page_index=0,
        import_hash=h,
        status="paid",
        source_year=2026,
        due_date=date(2026, 3, 31),
        title="Direkte Bundessteuer 2025",
    )
    db.session.add(existing)
    db.session.commit()

    stats = _import_from_dir(app.config["PENDENT_DIR"], "pending")
    db.session.refresh(existing)

    assert stats["imported"] == 0
    assert existing.status == "paid"
    assert existing.source_year == 2026


def test_paid_folder_promotes_pending_status(app, db, monkeypatch):
    pdf = app.config["BEZAHLT_DIR"] / "2026" / "rechnung.pdf"
    _touch_pdf(pdf)

    monkeypatch.setattr(
        "app.importers.invoices.parse_invoice_slips",
        lambda _pdf: [
            {
                "filename": "rechnung.pdf",
                "page_index": 0,
                "slip_label": None,
                "raw_issuer": "Beispiel AG",
                "amount": 120.0,
                "invoice_date": date(2026, 1, 1),
                "due_date": date(2026, 2, 1),
            }
        ],
    )

    h = make_hash("rechnung.pdf", 0)
    existing = Invoice(
        filename="rechnung.pdf",
        page_index=0,
        import_hash=h,
        status="pending",
    )
    db.session.add(existing)
    db.session.commit()

    stats = _import_from_dir(app.config["BEZAHLT_DIR"], "paid")
    db.session.refresh(existing)

    assert stats["imported"] == 1
    assert existing.status == "paid"
    assert existing.source_year == 2026
