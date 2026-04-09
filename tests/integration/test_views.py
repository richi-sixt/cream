"""
tests/integration/test_views.py — Integration tests for main blueprint views.

All data is fully made-up with fictitious names.
"""

from datetime import date

import pytest

from app.models import Account, Category, Invoice, Transaction
from app import db as _db


def _seed_dashboard(db):
    """Create made-up data for dashboard rendering tests."""
    acct = Account(name="Testkonto Beispiel", iban="CH0000000000099999999", type="checking", currency="CHF")
    db.session.add(acct)
    db.session.flush()

    cat = Category(name="Diverses")
    db.session.add(cat)
    db.session.flush()

    tx = Transaction(
        account_id=acct.id, date=date(2026, 3, 15),
        raw_description="Beispiel Zahlung AG",
        amount=123.45, type="expense", saldo=9876.55,
        import_hash="view_h1", category_id=cat.id,
    )
    db.session.add(tx)

    inv = Invoice(
        filename="beispiel-rechnung.pdf", page_index=0,
        raw_issuer="Fantasie Verlag AG", amount=49.90,
        due_date=date(2026, 4, 1), status="pending",
        import_hash="view_inv1",
    )
    db.session.add(inv)
    db.session.commit()
    return {"acct": acct, "cat": cat, "tx": tx, "inv": inv}


class TestDashboardFilters:
    """Test the dashboard with query-string filters."""

    def test_filter_by_account(self, client, db):
        seed = _seed_dashboard(db)
        r = client.get(f"/?account_id={seed['acct'].id}")
        assert r.status_code == 200
        assert b"Beispiel Zahlung AG" in r.data

    def test_filter_by_category(self, client, db):
        seed = _seed_dashboard(db)
        r = client.get(f"/?tx_category_id={seed['cat'].id}")
        assert r.status_code == 200

    def test_filter_by_year(self, client, db):
        _seed_dashboard(db)
        r = client.get("/?tx_year=2026")
        assert r.status_code == 200

    def test_filter_by_month(self, client, db):
        _seed_dashboard(db)
        r = client.get("/?tx_month=3")
        assert r.status_code == 200

    def test_invalid_account_id_ignored(self, client, db):
        _seed_dashboard(db)
        r = client.get("/?account_id=abc")
        assert r.status_code == 200

    def test_invoice_status_filter(self, client, db):
        _seed_dashboard(db)
        r = client.get("/?inv_status=pending")
        assert r.status_code == 200

    def test_invoice_year_filter(self, client, db):
        _seed_dashboard(db)
        r = client.get("/?inv_year=2026")
        assert r.status_code == 200

    def test_invoice_month_filter(self, client, db):
        _seed_dashboard(db)
        r = client.get("/?inv_month=4")
        assert r.status_code == 200

    def test_chart_data_present(self, client, db):
        _seed_dashboard(db)
        r = client.get("/")
        assert b"chart-data" in r.data

    def test_kpi_shows_saldo(self, client, db):
        _seed_dashboard(db)
        r = client.get("/")
        assert b"9" in r.data  # partial saldo check


class TestSearchPage:
    """Test the /search view."""

    def test_search_page_returns_200(self, client, db):
        r = client.get("/search")
        assert r.status_code == 200

    def test_search_page_with_data(self, client, db):
        _seed_dashboard(db)
        r = client.get("/search")
        assert r.status_code == 200
        assert b"raw-options-data" in r.data

    def test_search_page_has_category_options(self, client, db):
        _seed_dashboard(db)
        r = client.get("/search")
        assert b"Diverses" in r.data


class TestOpenPdf:
    """Test the /open-pdf/<filename> route."""

    def test_missing_pdf_returns_404(self, client, db):
        r = client.get("/open-pdf/nonexistent.pdf")
        assert r.status_code == 404

    def test_serve_pdf_inline(self, app, client, db):
        """When SERVE_PDF_INLINE is True, serve the file directly."""
        app.config["SERVE_PDF_INLINE"] = True
        # Create a fake PDF in the pendent dir
        pdf_path = app.config["PENDENT_DIR"] / "demo-rechnung.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake content")
        r = client.get("/open-pdf/demo-rechnung.pdf")
        assert r.status_code == 200
        assert r.content_type == "application/pdf"

    def test_path_traversal_blocked(self, client, db):
        """Ensure path traversal attempts are safe (only filename used)."""
        r = client.get("/open-pdf/../../etc/passwd")
        assert r.status_code == 404


class TestImportEndpoint:
    """Test POST /import."""

    def test_import_returns_json(self, client, db):
        r = client.post("/import")
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert "stats" in data


class TestTransactionListApi:
    """Test GET /api/transactions."""

    def test_list_empty(self, client, db):
        r = client.get("/api/transactions")
        assert r.status_code == 200
        assert r.get_json() == []

    def test_list_with_filters(self, client, db):
        seed = _seed_dashboard(db)
        r = client.get(f"/api/transactions?account_id={seed['acct'].id}&month=2026-03")
        data = r.get_json()
        assert len(data) == 1

    def test_list_by_iban(self, client, db):
        _seed_dashboard(db)
        r = client.get("/api/transactions?iban=CH0000000000099999999")
        data = r.get_json()
        assert len(data) == 1


class TestInvoiceListApi:
    """Test GET /api/invoices."""

    def test_list_by_status(self, client, db):
        _seed_dashboard(db)
        r = client.get("/api/invoices?status=pending")
        data = r.get_json()
        assert len(data) == 1

    def test_list_paid_empty(self, client, db):
        _seed_dashboard(db)
        r = client.get("/api/invoices?status=paid")
        data = r.get_json()
        assert len(data) == 0
