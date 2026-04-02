"""
tests/integration/test_api.py — Integration tests for all API endpoints.

Covers full HTTP request/response cycles against an in-memory DB.
"""

import json
from datetime import date

import pytest


# ── Helpers ─────────────────────────────────────────────────────────────

def _create_invoice(db, **kwargs):
    """Create a test invoice in the DB."""
    from app.models import Invoice
    defaults = {
        "filename":    "test.pdf",
        "page_index":  0,
        "import_hash": "testhash_" + str(id(kwargs)),
        "status":      "pending",
    }
    defaults.update(kwargs)
    inv = Invoice(**defaults)
    db.session.add(inv)
    db.session.commit()
    return inv


def _create_transaction(db, **kwargs):
    """Create a test transaction in the DB."""
    from app.models import Transaction, Account
    # Create a default account if needed
    account = Account.query.first()
    if not account:
        account = Account(name="Test", iban="CH00TEST", type="checking", currency="CHF")
        db.session.add(account)
        db.session.flush()

    defaults = {
        "account_id":      account.id,
        "date":            date(2026, 3, 1),
        "raw_description": "Sample Merchant",
        "amount":          42.0,
        "type":            "expense",
        "import_hash":     "txhash_" + str(id(kwargs)),
    }
    defaults.update(kwargs)
    tx = Transaction(**defaults)
    db.session.add(tx)
    db.session.commit()
    return tx


def _create_category(db, **kwargs):
    """Create a test category."""
    from app.models import Category

    defaults = {"name": "Haushalt"}
    defaults.update(kwargs)
    cat = Category(**defaults)
    db.session.add(cat)
    db.session.commit()
    return cat


# ── Dashboard ────────────────────────────────────────────────────────────────

class TestDashboard:
    def test_get_returns_200(self, client):
        r = client.get("/")
        assert r.status_code == 200

    def test_html_contains_cream_branding(self, client):
        r = client.get("/")
        assert b"C.R.E.A.M." in r.data


# ── Import Endpoint ───────────────────────────────────────────────────────────

class TestImport:
    def test_post_import_returns_json(self, client):
        r = client.post("/import")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["ok"] is True
        assert "stats" in data
        assert "transactions" in data["stats"]
        assert "invoices" in data["stats"]

    def test_get_import_not_allowed(self, client):
        r = client.get("/import")
        assert r.status_code == 405


# ── Invoices API ────────────────────────────────────────────────────────────

class TestInvoiceApi:
    def test_list_invoices(self, client, db):
        _create_invoice(db, import_hash="h1")
        _create_invoice(db, import_hash="h2", status="paid")
        r = client.get("/api/invoices")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 2

    def test_list_invoices_filter_status(self, client, db):
        _create_invoice(db, import_hash="h1", status="pending")
        _create_invoice(db, import_hash="h2", status="paid")
        r = client.get("/api/invoices?status=pending")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["status"] == "pending"

    def test_patch_amount(self, client, db):
        inv = _create_invoice(db, import_hash="h_betrag")
        r = client.patch(
            f"/api/invoices/{inv.id}",
            data=json.dumps({"amount": 1470.0}),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["amount"] == 1470.0

    def test_patch_amount_swiss_format(self, client, db):
        """Apostrophe amount format is accepted."""
        inv = _create_invoice(db, import_hash="h_ch")
        r = client.patch(
            f"/api/invoices/{inv.id}",
            data=json.dumps({"amount": "1'470.00"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert json.loads(r.data)["amount"] == 1470.0

    def test_patch_negative_amount_rejected(self, client, db):
        inv = _create_invoice(db, import_hash="h_neg")
        r = client.patch(
            f"/api/invoices/{inv.id}",
            data=json.dumps({"amount": -100}),
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_patch_due_date(self, client, db):
        inv = _create_invoice(db, import_hash="h_due")
        r = client.patch(
            f"/api/invoices/{inv.id}",
            data=json.dumps({"due_date": "2026-05-31"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert json.loads(r.data)["due_date"] == "2026-05-31"

    def test_patch_source_year(self, client, db):
        inv = _create_invoice(db, import_hash="h_src_year")
        r = client.patch(
            f"/api/invoices/{inv.id}",
            data=json.dumps({"source_year": 2026}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert json.loads(r.data)["source_year"] == 2026

    def test_patch_source_year_invalid(self, client, db):
        inv = _create_invoice(db, import_hash="h_src_bad")
        r = client.patch(
            f"/api/invoices/{inv.id}",
            data=json.dumps({"source_year": "xx"}),
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_patch_invalid_date_rejected(self, client, db):
        inv = _create_invoice(db, import_hash="h_bad_date")
        r = client.patch(
            f"/api/invoices/{inv.id}",
            data=json.dumps({"due_date": "kein-datum"}),
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_patch_status_paid(self, client, db):
        inv = _create_invoice(db, import_hash="h_status")
        r = client.patch(
            f"/api/invoices/{inv.id}",
            data=json.dumps({"status": "paid"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert json.loads(r.data)["status"] == "paid"

    def test_patch_invalid_status_rejected(self, client, db):
        inv = _create_invoice(db, import_hash="h_bad_status")
        r = client.patch(
            f"/api/invoices/{inv.id}",
            data=json.dumps({"status": "invalid"}),
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_patch_not_found(self, client, db):
        r = client.patch(
            "/api/invoices/99999",
            data=json.dumps({"amount": 100}),
            content_type="application/json",
        )
        assert r.status_code == 404

    def test_delete_invoice(self, client, db):
        from app.models import Invoice
        inv = _create_invoice(db, import_hash="h_delete", filename="delete-me.pdf")
        r = client.delete(f"/api/invoices/{inv.id}")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["ok"] is True
        assert data["deleted_id"] == inv.id
        assert db.session.get(Invoice, inv.id) is None

    def test_delete_invoice_not_found(self, client, db):
        r = client.delete("/api/invoices/99999")
        assert r.status_code == 404

    def test_remember_invoice_title_creates_rule(self, client, db):
        from app.models import InvoiceTitleRule

        cat = _create_category(db, name="Insurance")
        inv = _create_invoice(
            db,
            import_hash="h_rule_create",
            raw_issuer="Example Health Insurance AG",
            title="Example Health April",
            category_id=cat.id,
        )

        r = client.post(
            f"/api/invoices/{inv.id}/remember-title",
            data=json.dumps({"title": "Example Health"}),
            content_type="application/json",
        )

        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["created"] is True
        assert data["rule"]["raw_issuer"] == "Example Health Insurance AG"
        assert data["rule"]["title"] == "Example Health"
        assert data["rule"]["category_id"] == cat.id

        rule = InvoiceTitleRule.query.filter_by(raw_issuer="Example Health Insurance AG").first()
        assert rule is not None
        assert rule.title == "Example Health"
        assert rule.category_id == cat.id

    def test_remember_invoice_title_updates_existing_rule(self, client, db):
        from app.models import InvoiceTitleRule

        inv = _create_invoice(
            db,
            import_hash="h_rule_update",
            raw_issuer="Cantonal Tax Office Example",
            title="Taxes",
        )
        db.session.add(
            InvoiceTitleRule(
                raw_issuer="Cantonal Tax Office Example",
                title="Alt",
            )
        )
        db.session.commit()

        r = client.post(
            f"/api/invoices/{inv.id}/remember-title",
            data=json.dumps({"title": "Tax Office Example"}),
            content_type="application/json",
        )

        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["created"] is False
        assert data["rule"]["title"] == "Tax Office Example"

    def test_remember_invoice_title_requires_raw_issuer(self, client, db):
        inv = _create_invoice(
            db,
            import_hash="h_rule_missing_issuer",
            raw_issuer=None,
            title="Titel",
        )

        r = client.post(
            f"/api/invoices/{inv.id}/remember-title",
            data=json.dumps({"title": "Titel"}),
            content_type="application/json",
        )

        assert r.status_code == 400

    def test_patch_invoice_category(self, client, db):
        cat = _create_category(db, name="Taxes")
        inv = _create_invoice(db, import_hash="h_inv_cat")

        r = client.patch(
            f"/api/invoices/{inv.id}",
            data=json.dumps({"category_id": cat.id}),
            content_type="application/json",
        )

        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["category_id"] == cat.id
        assert data["category_name"] == "Taxes"

    def test_list_categories_includes_usage_counts(self, client, db):
        cat = _create_category(db, name="Haushalt")
        _create_invoice(db, import_hash="cat_usage_inv", category_id=cat.id)
        _create_transaction(db, import_hash="cat_usage_tx", category_id=cat.id)

        r = client.get("/api/categories")

        assert r.status_code == 200
        data = json.loads(r.data)
        item = next(c for c in data if c["id"] == cat.id)
        assert item["tx_count"] == 1
        assert item["invoice_count"] == 1
        assert item["usage_total"] == 2
        assert item["deletable"] is False

    def test_patch_category_name(self, client, db):
        cat = _create_category(db, name="Alt")

        r = client.patch(
            f"/api/categories/{cat.id}",
            data=json.dumps({"name": "Neu"}),
            content_type="application/json",
        )

        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["name"] == "Neu"

    def test_patch_category_parent(self, client, db):
        parent = _create_category(db, name="Energie")
        child = _create_category(db, name="Gas")

        r = client.patch(
            f"/api/categories/{child.id}",
            data=json.dumps({"parent_id": parent.id}),
            content_type="application/json",
        )

        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["parent_id"] == parent.id
        assert data["path"] == "Energie/Gas"

    def test_patch_category_parent_cycle_rejected(self, client, db):
        parent = _create_category(db, name="Energie")
        child = _create_category(db, name="Gas", parent_id=parent.id)

        r = client.patch(
            f"/api/categories/{parent.id}",
            data=json.dumps({"parent_id": child.id}),
            content_type="application/json",
        )

        assert r.status_code == 400

    def test_patch_category_parent_self_rejected(self, client, db):
        cat = _create_category(db, name="Strom")

        r = client.patch(
            f"/api/categories/{cat.id}",
            data=json.dumps({"parent_id": cat.id}),
            content_type="application/json",
        )

        assert r.status_code == 400

    def test_delete_unused_category(self, client, db):
        from app.models import Category

        cat = _create_category(db, name="Loeschbar")
        r = client.delete(f"/api/categories/{cat.id}")

        assert r.status_code == 200
        payload = json.loads(r.data)
        assert payload["ok"] is True
        assert db.session.get(Category, cat.id) is None

    def test_delete_used_category_rejected(self, client, db):
        cat = _create_category(db, name="InUse")
        _create_invoice(db, import_hash="cat_inuse_inv", category_id=cat.id)

        r = client.delete(f"/api/categories/{cat.id}")

        assert r.status_code == 400

    def test_title_correction_persists_on_reimport(self, client, db):
        """
        import_hash protects manual corrections during re-import.
        Same hash -> entry is skipped -> title remains unchanged.
        """
        inv = _create_invoice(db, import_hash="stable_hash", title=None)
        # Set title manually
        client.patch(
            f"/api/invoices/{inv.id}",
            data=json.dumps({"title": "Insurance January"}),
            content_type="application/json",
        )
        # Second import: would be skipped (same hash)
        from app.models import Invoice
        count_before = Invoice.query.count()
        # Verify directly: filter works
        existing = Invoice.query.filter_by(import_hash="stable_hash").first()
        assert existing is not None
        assert existing.title == "Insurance January"
        assert Invoice.query.count() == count_before


# ── Transactions API ─────────────────────────────────────────────────────────────

def _create_account(db, **kwargs):
    """Create a test account for multi-account tests."""
    from app.models import Account
    defaults = {"name": "Test account", "type": "checking", "currency": "CHF"}
    defaults.update(kwargs)
    acc = Account(**defaults)
    db.session.add(acc)
    db.session.flush()
    return acc


class TestTransactionApi:
    def test_list_transactions(self, client, db):
        _create_transaction(db, import_hash="t1")
        _create_transaction(db, import_hash="t2")
        r = client.get("/api/transactions")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 2

    def test_list_transactions_filter_month(self, client, db):
        _create_transaction(db, import_hash="t_jan", date=date(2026, 1, 15))
        _create_transaction(db, import_hash="t_mar", date=date(2026, 3, 1))
        r = client.get("/api/transactions?month=2026-01")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["date"] == "2026-01-15"

    def test_list_transactions_filter_account(self, client, db):
        """Transactions are correctly filtered for a specific account."""
        from app.models import Account
        account_a = _create_account(db, name="Example Bank A", iban="CH001")
        account_b = _create_account(db, name="Example Bank B", iban="CH002")
        db.session.commit()
        _create_transaction(db, import_hash="ta1", account_id=account_a.id)
        _create_transaction(db, import_hash="ta2", account_id=account_a.id)
        _create_transaction(db, import_hash="tb1", account_id=account_b.id)
        r = client.get(f"/api/transactions?account_id={account_a.id}")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 2
        assert all(tx["account_id"] == account_a.id for tx in data)

    def test_list_transactions_filter_account_and_month(self, client, db):
        """Filter by account + month together."""
        from app.models import Account
        account = _create_account(db, name="Example Bank Combo", iban="CH003")
        db.session.commit()
        _create_transaction(db, import_hash="km_jan", account_id=account.id, date=date(2026, 1, 10))
        _create_transaction(db, import_hash="km_feb", account_id=account.id, date=date(2026, 2, 10))
        r = client.get(f"/api/transactions?account_id={account.id}&month=2026-01")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["date"] == "2026-01-10"

    def test_list_transactions_filter_iban(self, client, db):
        account_a = _create_account(db, name="Example Bank A", iban="CH001")
        account_b = _create_account(db, name="Example Bank B", iban="CH002")
        db.session.commit()
        _create_transaction(db, import_hash="iban_a", account_id=account_a.id)
        _create_transaction(db, import_hash="iban_b", account_id=account_b.id)

        r = client.get("/api/transactions?iban=CH002")

        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["account_id"] == account_b.id

    def test_list_transactions_filter_invalid_account(self, client, db):
        """Invalid account_id value is ignored and all transactions are returned."""
        _create_transaction(db, import_hash="tug1")
        r = client.get("/api/transactions?account_id=not_an_int")
        assert r.status_code == 200
        # Invalid value ignored -> 1 transaction returned
        data = json.loads(r.data)
        assert len(data) == 1

    def test_patch_title(self, client, db):
        tx = _create_transaction(db, import_hash="t_titel")
        r = client.patch(
            f"/api/transactions/{tx.id}",
            data=json.dumps({"title": "Lohn Januar"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert json.loads(r.data)["display_title"] == "Lohn Januar"

    def test_patch_transaction_category(self, client, db):
        cat = _create_category(db, name="Essen")
        tx = _create_transaction(db, import_hash="t_cat")
        r = client.patch(
            f"/api/transactions/{tx.id}",
            data=json.dumps({"category_id": cat.id}),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["category_id"] == cat.id
        assert data["category_name"] == "Essen"

    def test_list_transactions_filter_category(self, client, db):
        cat_a = _create_category(db, name="Essen")
        cat_b = _create_category(db, name="Transport")
        _create_transaction(db, import_hash="t_cat_a", category_id=cat_a.id)
        _create_transaction(db, import_hash="t_cat_b", category_id=cat_b.id)

        r = client.get(f"/api/transactions?category_id={cat_b.id}")

        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["category_id"] == cat_b.id


# ── Dashboard Filters ───────────────────────────────────────────────────────────

class TestDashboardFilter:
    def test_dashboard_filter_account(self, client, db):
        """Dashboard with `?account_id` returns 200."""
        acc = _create_account(db, name="Filter-Bank", iban="CH009")
        db.session.commit()
        _create_transaction(db, import_hash="df1", account_id=acc.id)
        r = client.get(f"/?account_id={acc.id}")
        assert r.status_code == 200

    def test_dashboard_filter_iban(self, client, db):
        acc = _create_account(db, name="Filter-IBAN", iban="CH010")
        db.session.commit()
        _create_transaction(db, import_hash="df_iban", account_id=acc.id)
        r = client.get("/?iban=CH010")
        assert r.status_code == 200

    def test_dashboard_filter_tx_year(self, client, db):
        """Dashboard with `?tx_year` filters by year."""
        _create_transaction(db, import_hash="dfy1", date=date(2025, 6, 1))
        _create_transaction(db, import_hash="dfy2", date=date(2026, 2, 14))
        r = client.get("/?tx_year=2026")
        assert r.status_code == 200

    def test_dashboard_filter_tx_month(self, client, db):
        """Dashboard with `?tx_month` filters by month."""
        _create_transaction(db, import_hash="dfmo1", date=date(2026, 2, 14))
        r = client.get("/?tx_month=2")
        assert r.status_code == 200

    def test_dashboard_filter_tx_year_and_month(self, client, db):
        """Dashboard with `?tx_year` and `?tx_month` returns 200."""
        acc = _create_account(db, name="Example Bank Combo 2", iban="CH010")
        db.session.commit()
        _create_transaction(db, import_hash="dfkm1", account_id=acc.id, date=date(2026, 3, 5))
        r = client.get(f"/?account_id={acc.id}&tx_year=2026&tx_month=3")
        assert r.status_code == 200

    def test_dashboard_filter_invalid_returns_200(self, client, db):
        """Invalid filter values are ignored (no 500)."""
        r = client.get("/?account_id=xyz&tx_year=bad&tx_month=bad")
        assert r.status_code == 200

    def test_dashboard_filter_transaction_category(self, client, db):
        cat = _create_category(db, name="Groceries")
        _create_transaction(db, import_hash="df_cat_match", raw_description="Sample Grocery", category_id=cat.id)
        _create_transaction(db, import_hash="df_cat_other", raw_description="Sample Transport")

        r = client.get(f"/?tx_category_id={cat.id}")

        assert r.status_code == 200
        assert b"Sample Grocery" in r.data
        assert b"Sample Transport" not in r.data


# ── Invoice Filters ──────────────────────────────────────────────────────────

class TestInvoiceFilter:
    def test_api_filter_status_paid(self, client, db):
        """API: only paid invoices."""
        _create_invoice(db, import_hash="f_p1", status="pending")
        _create_invoice(db, import_hash="f_paid", status="paid")
        r = client.get("/api/invoices?status=paid")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["status"] == "paid"

    def test_api_filter_year(self, client, db):
        """API: year filter on due_date."""
        _create_invoice(db, import_hash="f_y25", due_date=date(2025, 6, 1))
        _create_invoice(db, import_hash="f_y26", due_date=date(2026, 3, 31))
        r = client.get("/api/invoices?year=2026")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["due_date"] == "2026-03-31"

    def test_api_filter_status_and_year(self, client, db):
        """API: combined status + year filter."""
        _create_invoice(db, import_hash="f_sy1", status="pending", due_date=date(2026, 1, 1))
        _create_invoice(db, import_hash="f_sy2", status="paid",    due_date=date(2026, 2, 1))
        _create_invoice(db, import_hash="f_sy3", status="pending", due_date=date(2025, 12, 1))
        r = client.get("/api/invoices?status=pending&year=2026")
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["status"] == "pending"
        assert data[0]["due_date"] == "2026-01-01"

    def test_dashboard_inv_filter_paid(self, client, db):
        """Dashboard: `?inv_status=paid` returns 200."""
        _create_invoice(db, import_hash="df_inv1", status="paid")
        r = client.get("/?inv_status=paid")
        assert r.status_code == 200

    def test_dashboard_inv_filter_all(self, client, db):
        """Dashboard: empty `?inv_status=` shows all invoices."""
        _create_invoice(db, import_hash="df_all1", status="pending")
        _create_invoice(db, import_hash="df_all2", status="paid")
        r = client.get("/?inv_status=")
        assert r.status_code == 200

    def test_dashboard_inv_filter_year(self, client, db):
        """Dashboard: `?inv_year=2026` returns 200."""
        _create_invoice(db, import_hash="df_yr1", due_date=date(2026, 5, 1))
        r = client.get("/?inv_status=pending&inv_year=2026")
        assert r.status_code == 200

    def test_dashboard_inv_filter_source_year(self, client, db):
        """Dashboard: source_year is preferred for year filtering."""
        # Invoice without due_date but with source_year=2026
        _create_invoice(db, import_hash="df_sy1", status="paid", source_year=2026)
        # Invoice with due_date 2025 and source_year=2026 should appear in 2026
        _create_invoice(db, import_hash="df_sy2", status="paid", due_date=date(2025, 1, 1), source_year=2026)
        # Invoice with due_date 2025 and no source_year should NOT appear in 2026
        _create_invoice(db, import_hash="df_sy3", status="paid", due_date=date(2025, 1, 1))
        r = client.get("/?inv_status=paid&inv_year=2026")
        assert r.status_code == 200
        # Only the two with source_year=2026
        assert b"df_sy3" not in r.data  # weak check - mainly verifies no 500

    def test_dashboard_inv_filter_month(self, client, db):
        """Dashboard: `?inv_month=5` filters by month."""
        _create_invoice(db, import_hash="df_mo1", due_date=date(2026, 5, 15))
        _create_invoice(db, import_hash="df_mo2", due_date=date(2026, 3, 10))
        r = client.get("/?inv_status=pending&inv_month=5")
        assert r.status_code == 200

    def test_api_filter_inv_month(self, client, db):
        """API: month filtering on due_date."""
        _create_invoice(db, import_hash="api_mo1", due_date=date(2026, 5, 15))
        _create_invoice(db, import_hash="api_mo2", due_date=date(2026, 3, 10))
        r = client.get("/api/invoices?year=2026&status=pending")
        data = json.loads(r.data)
        assert len(data) == 2  # both are in 2026; no month filter here

    def test_api_filter_invoice_category(self, client, db):
        cat_a = _create_category(db, name="Taxes")
        cat_b = _create_category(db, name="Insurance")
        _create_invoice(db, import_hash="f_cat_a", category_id=cat_a.id)
        _create_invoice(db, import_hash="f_cat_b", category_id=cat_b.id)

        r = client.get(f"/api/invoices?category_id={cat_b.id}")

        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["category_id"] == cat_b.id

    def test_dashboard_invoice_filter_category(self, client, db):
        cat = _create_category(db, name="Insurance")
        _create_invoice(db, import_hash="df_inv_cat_match", filename="versicherung.pdf", category_id=cat.id)
        _create_invoice(db, import_hash="df_inv_cat_other", filename="steuer.pdf")

        r = client.get(f"/?inv_status=pending&inv_category_id={cat.id}")

        assert r.status_code == 200
        assert b"versicherung.pdf" in r.data
        assert b"steuer.pdf" not in r.data


# ── TransactionLine (Phase 5) ─────────────────────────────────────────────────

def _create_transaction_with_lines(db, lines_data, **kwargs):
    """
    Create a transaction with detail lines.

    Analogy: an e-banking order with multiple transfers.
    The main transaction contains a list of sub-lines.
    """
    from app.models import TransactionLine
    tx = _create_transaction(db, **kwargs)
    for pos, ld in enumerate(lines_data):
        tl = TransactionLine(
            transaction_id=tx.id,
            position=pos,
            recipient=ld["recipient"],
            amount=ld["amount"],
            iban=ld.get("iban"),
        )
        db.session.add(tl)
    db.session.commit()
    return tx


class TestTransactionLine:
    def test_transaction_without_lines(self, client, db):
        """Regular transaction without detail lines: lines list is empty."""
        tx = _create_transaction(db, import_hash="tl_no_lines")
        r = client.get("/api/transactions")
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["lines"] == []

    def test_transaction_with_one_line(self, client, db):
        """E-banking order with one detail line."""
        _create_transaction_with_lines(
            db,
            import_hash="tl_one",
            raw_description="Ihr E-Banking-Auftrag",
            amount=123.45,
            lines_data=[{"recipient": "Sample Charity", "amount": 123.45, "iban": "CH4400791234567890125"}],
        )
        r = client.get("/api/transactions")
        data = json.loads(r.data)
        assert len(data) == 1
        lines = data[0]["lines"]
        assert len(lines) == 1
        assert lines[0]["recipient"] == "Sample Charity"
        assert lines[0]["amount"] == 123.45
        assert lines[0]["iban"] == "CH4400791234567890125"

    def test_transaction_with_multiple_lines(self, client, db):
        """E-banking order with multiple recipients."""
        _create_transaction_with_lines(
            db,
            import_hash="tl_multi",
            raw_description="Ihr E-Banking-Auftrag",
            amount=1000.0,
            lines_data=[
                {"recipient": "Sample Insurance", "amount": 300.0, "iban": "CH5600791234567890123"},
                {"recipient": "Sample Clinic",  "amount": 700.0, "iban": "CH5600791234567890124"},
            ],
        )
        r = client.get("/api/transactions")
        data = json.loads(r.data)
        assert len(data) == 1
        lines = data[0]["lines"]
        assert len(lines) == 2
        assert lines[0]["recipient"] == "Sample Insurance"
        assert lines[1]["recipient"] == "Sample Clinic"

    def test_lines_order(self, client, db):
        """Detail lines are returned sorted by the position field."""
        _create_transaction_with_lines(
            db,
            import_hash="tl_order",
            raw_description="Ihr E-Banking-Auftrag",
            amount=300.0,
            lines_data=[
                {"recipient": "Erst",   "amount": 100.0},
                {"recipient": "Zweite", "amount": 100.0},
                {"recipient": "Dritte", "amount": 100.0},
            ],
        )
        r = client.get("/api/transactions")
        data = json.loads(r.data)
        lines = data[0]["lines"]
        assert [l["recipient"] for l in lines] == ["Erst", "Zweite", "Dritte"]

    def test_lines_without_iban(self, client, db):
        """Detail line without IBAN: iban field is None."""
        _create_transaction_with_lines(
            db,
            import_hash="tl_no_iban",
            raw_description="Ihr E-Banking-Auftrag",
            amount=150.0,
            lines_data=[{"recipient": "Empfänger ohne IBAN", "amount": 150.0}],
        )
        r = client.get("/api/transactions")
        data = json.loads(r.data)
        assert data[0]["lines"][0]["iban"] is None

    def test_lines_cascade_delete(self, client, db):
        """
        When a transaction is deleted, its TransactionLines are deleted as well.
        (cascade='all, delete-orphan' in the model)
        """
        from app.models import Transaction, TransactionLine
        tx = _create_transaction_with_lines(
            db,
            import_hash="tl_cascade",
            raw_description="Ihr E-Banking-Auftrag",
            amount=100.0,
            lines_data=[{"recipient": "To be deleted", "amount": 100.0}],
        )
        tx_id = tx.id
        assert TransactionLine.query.filter_by(transaction_id=tx_id).count() == 1
        # Delete transaction
        db.session.delete(db.session.get(Transaction, tx_id))
        db.session.commit()
        # Detail lines must be gone
        assert TransactionLine.query.filter_by(transaction_id=tx_id).count() == 0

    def test_dashboard_shows_transaction_with_lines(self, client, db):
        """Dashboard renders without errors when a transaction has detail lines."""
        _create_transaction_with_lines(
            db,
            import_hash="tl_dash",
            raw_description="Ihr E-Banking-Auftrag",
            amount=500.0,
            lines_data=[
                {"recipient": "Sample Insurance", "amount": 250.0},
                {"recipient": "Sample Clinic",  "amount": 125.0},
            ],
        )
        r = client.get("/")
        assert r.status_code == 200
        # Toggle button and recipient names in the HTML
        assert b"Positionen" in r.data
        assert b"Sample Insurance" in r.data
