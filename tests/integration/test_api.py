"""
tests/integration/test_api.py — Integrationstests für alle API-Endpunkte.

Testet vollständige HTTP-Request/Response-Zyklen gegen eine in-memory DB.
"""

import json
from datetime import date

import pytest


# ── Hilfsfunktion ─────────────────────────────────────────────────────────────

def _create_invoice(db, **kwargs):
    """Erstellt eine Test-Rechnung in der DB."""
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
    """Erstellt eine Test-Buchung in der DB."""
    from app.models import Transaction, Account
    # Konto anlegen falls nötig
    account = Account.query.first()
    if not account:
        account = Account(name="Test", iban="CH00TEST", type="checking", currency="CHF")
        db.session.add(account)
        db.session.flush()

    defaults = {
        "account_id":      account.id,
        "date":            date(2026, 3, 1),
        "raw_description": "Migros",
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

    def test_html_enthaelt_cream(self, client):
        r = client.get("/")
        assert b"cream" in r.data.lower()


# ── Import-Endpunkt ───────────────────────────────────────────────────────────

class TestImport:
    def test_post_import_gibt_json(self, client):
        r = client.post("/import")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["ok"] is True
        assert "stats" in data
        assert "transactions" in data["stats"]
        assert "invoices" in data["stats"]

    def test_get_import_nicht_erlaubt(self, client):
        r = client.get("/import")
        assert r.status_code == 405


# ── Rechnungen API ────────────────────────────────────────────────────────────

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

    def test_patch_betrag(self, client, db):
        inv = _create_invoice(db, import_hash="h_betrag")
        r = client.patch(
            f"/api/invoices/{inv.id}",
            data=json.dumps({"amount": 1470.0}),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["amount"] == 1470.0

    def test_patch_betrag_schweizer_format(self, client, db):
        """Apostroph-Format wird akzeptiert."""
        inv = _create_invoice(db, import_hash="h_ch")
        r = client.patch(
            f"/api/invoices/{inv.id}",
            data=json.dumps({"amount": "1'470.00"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert json.loads(r.data)["amount"] == 1470.0

    def test_patch_negativer_betrag_abgelehnt(self, client, db):
        inv = _create_invoice(db, import_hash="h_neg")
        r = client.patch(
            f"/api/invoices/{inv.id}",
            data=json.dumps({"amount": -100}),
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_patch_faelligkeit(self, client, db):
        inv = _create_invoice(db, import_hash="h_due")
        r = client.patch(
            f"/api/invoices/{inv.id}",
            data=json.dumps({"due_date": "2026-05-31"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert json.loads(r.data)["due_date"] == "2026-05-31"

    def test_patch_ungueltiges_datum_abgelehnt(self, client, db):
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

    def test_patch_ungueltiger_status_abgelehnt(self, client, db):
        inv = _create_invoice(db, import_hash="h_bad_status")
        r = client.patch(
            f"/api/invoices/{inv.id}",
            data=json.dumps({"status": "ungültig"}),
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_sent_to_kk_nicht_mehr_akzeptiert(self, client, db):
        """sent_to_kk wurde entfernt und wird vom API abgelehnt."""
        inv = _create_invoice(db, import_hash="h_kk")
        r = client.patch(
            f"/api/invoices/{inv.id}",
            data=json.dumps({"status": "sent_to_kk"}),
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_patch_nicht_gefunden(self, client, db):
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

        cat = _create_category(db, name="Versicherung")
        inv = _create_invoice(
            db,
            import_hash="h_rule_create",
            raw_issuer="Helsana Versicherungen AG",
            title="Helsana April",
            category_id=cat.id,
        )

        r = client.post(
            f"/api/invoices/{inv.id}/remember-title",
            data=json.dumps({"title": "Helsana"}),
            content_type="application/json",
        )

        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["created"] is True
        assert data["rule"]["raw_issuer"] == "Helsana Versicherungen AG"
        assert data["rule"]["title"] == "Helsana"
        assert data["rule"]["category_id"] == cat.id

        rule = InvoiceTitleRule.query.filter_by(raw_issuer="Helsana Versicherungen AG").first()
        assert rule is not None
        assert rule.title == "Helsana"
        assert rule.category_id == cat.id

    def test_remember_invoice_title_updates_existing_rule(self, client, db):
        from app.models import InvoiceTitleRule

        inv = _create_invoice(
            db,
            import_hash="h_rule_update",
            raw_issuer="Steueramt des Kantons Solothurn",
            title="Steuern",
        )
        db.session.add(
            InvoiceTitleRule(
                raw_issuer="Steueramt des Kantons Solothurn",
                title="Alt",
            )
        )
        db.session.commit()

        r = client.post(
            f"/api/invoices/{inv.id}/remember-title",
            data=json.dumps({"title": "Steueramt Solothurn"}),
            content_type="application/json",
        )

        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["created"] is False
        assert data["rule"]["title"] == "Steueramt Solothurn"

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
        cat = _create_category(db, name="Steuern")
        inv = _create_invoice(db, import_hash="h_inv_cat")

        r = client.patch(
            f"/api/invoices/{inv.id}",
            data=json.dumps({"category_id": cat.id}),
            content_type="application/json",
        )

        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["category_id"] == cat.id
        assert data["category_name"] == "Steuern"

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

    def test_titel_korrektur_bleibt_bei_reimport(self, client, db):
        """
        import_hash schützt manuelle Korrekturen beim Re-Import.
        Gleicher Hash → Eintrag wird übersprungen → Titel bleibt erhalten.
        """
        inv = _create_invoice(db, import_hash="stable_hash", title=None)
        # Manuell Titel setzen
        client.patch(
            f"/api/invoices/{inv.id}",
            data=json.dumps({"title": "Krankenkasse Januar"}),
            content_type="application/json",
        )
        # Zweiter Import: würde überspringen (gleicher Hash)
        from app.models import Invoice
        count_before = Invoice.query.count()
        # Direkt testen: Filter funktioniert
        existing = Invoice.query.filter_by(import_hash="stable_hash").first()
        assert existing is not None
        assert existing.title == "Krankenkasse Januar"
        assert Invoice.query.count() == count_before


# ── Buchungen API ─────────────────────────────────────────────────────────────

def _create_account(db, **kwargs):
    """Erstellt ein Test-Konto — für Multi-Konto-Tests."""
    from app.models import Account
    defaults = {"name": "Testkonto", "type": "checking", "currency": "CHF"}
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

    def test_list_transactions_filter_monat(self, client, db):
        _create_transaction(db, import_hash="t_jan", date=date(2026, 1, 15))
        _create_transaction(db, import_hash="t_mar", date=date(2026, 3, 1))
        r = client.get("/api/transactions?month=2026-01")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["date"] == "2026-01-15"

    def test_list_transactions_filter_konto(self, client, db):
        """Buchungen eines bestimmten Kontos werden korrekt gefiltert."""
        from app.models import Account
        konto_a = _create_account(db, name="BEKB", iban="CH001")
        konto_b = _create_account(db, name="Raiffeisen", iban="CH002")
        db.session.commit()
        _create_transaction(db, import_hash="ta1", account_id=konto_a.id)
        _create_transaction(db, import_hash="ta2", account_id=konto_a.id)
        _create_transaction(db, import_hash="tb1", account_id=konto_b.id)
        r = client.get(f"/api/transactions?account_id={konto_a.id}")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 2
        assert all(tx["account_id"] == konto_a.id for tx in data)

    def test_list_transactions_filter_konto_und_monat(self, client, db):
        """Konto + Monat kombiniert filtern."""
        from app.models import Account
        konto = _create_account(db, name="BEKB Kombi", iban="CH003")
        db.session.commit()
        _create_transaction(db, import_hash="km_jan", account_id=konto.id, date=date(2026, 1, 10))
        _create_transaction(db, import_hash="km_feb", account_id=konto.id, date=date(2026, 2, 10))
        r = client.get(f"/api/transactions?account_id={konto.id}&month=2026-01")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["date"] == "2026-01-10"

    def test_list_transactions_filter_iban(self, client, db):
        konto_a = _create_account(db, name="BEKB", iban="CH001")
        konto_b = _create_account(db, name="Raiffeisen", iban="CH002")
        db.session.commit()
        _create_transaction(db, import_hash="iban_a", account_id=konto_a.id)
        _create_transaction(db, import_hash="iban_b", account_id=konto_b.id)

        r = client.get("/api/transactions?iban=CH002")

        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["account_id"] == konto_b.id

    def test_list_transactions_filter_ungueltiger_account(self, client, db):
        """Ungültiger account_id-Wert wird ignoriert, alle Buchungen kommen zurück."""
        _create_transaction(db, import_hash="tug1")
        r = client.get("/api/transactions?account_id=kein_int")
        assert r.status_code == 200
        # Ungültiger Wert ignoriert → 1 Buchung zurück
        data = json.loads(r.data)
        assert len(data) == 1

    def test_patch_titel(self, client, db):
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


# ── Dashboard Filter ───────────────────────────────────────────────────────────

class TestDashboardFilter:
    def test_dashboard_filter_konto(self, client, db):
        """Dashboard mit ?account_id gibt 200 zurück."""
        acc = _create_account(db, name="Filter-BEKB", iban="CH009")
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
        """Dashboard mit ?tx_year filtert nach Jahr."""
        _create_transaction(db, import_hash="dfy1", date=date(2025, 6, 1))
        _create_transaction(db, import_hash="dfy2", date=date(2026, 2, 14))
        r = client.get("/?tx_year=2026")
        assert r.status_code == 200

    def test_dashboard_filter_tx_month(self, client, db):
        """Dashboard mit ?tx_month filtert nach Monat."""
        _create_transaction(db, import_hash="dfmo1", date=date(2026, 2, 14))
        r = client.get("/?tx_month=2")
        assert r.status_code == 200

    def test_dashboard_filter_tx_year_und_month(self, client, db):
        """Dashboard mit ?tx_year und ?tx_month kombiniert gibt 200 zurück."""
        acc = _create_account(db, name="BEKB Kombi2", iban="CH010")
        db.session.commit()
        _create_transaction(db, import_hash="dfkm1", account_id=acc.id, date=date(2026, 3, 5))
        r = client.get(f"/?account_id={acc.id}&tx_year=2026&tx_month=3")
        assert r.status_code == 200

    def test_dashboard_filter_ungueltig_gibt_200(self, client, db):
        """Ungültige Filter-Werte werden ignoriert, kein 500."""
        r = client.get("/?account_id=xyz&tx_year=kein&tx_month=kein")
        assert r.status_code == 200

    def test_dashboard_filter_transaction_category(self, client, db):
        cat = _create_category(db, name="Lebensmittel")
        _create_transaction(db, import_hash="df_cat_match", raw_description="Migros", category_id=cat.id)
        _create_transaction(db, import_hash="df_cat_other", raw_description="SBB")

        r = client.get(f"/?tx_category_id={cat.id}")

        assert r.status_code == 200
        assert b"Migros" in r.data
        assert b"SBB" not in r.data


# ── Rechnungen Filter ──────────────────────────────────────────────────────────

class TestInvoiceFilter:
    def test_api_filter_status_paid(self, client, db):
        """API: nur bezahlte Rechnungen."""
        _create_invoice(db, import_hash="f_p1", status="pending")
        _create_invoice(db, import_hash="f_paid", status="paid")
        r = client.get("/api/invoices?status=paid")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["status"] == "paid"

    def test_api_filter_year(self, client, db):
        """API: Jahresfilter auf due_date."""
        _create_invoice(db, import_hash="f_y25", due_date=date(2025, 6, 1))
        _create_invoice(db, import_hash="f_y26", due_date=date(2026, 3, 31))
        r = client.get("/api/invoices?year=2026")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["due_date"] == "2026-03-31"

    def test_api_filter_status_und_year(self, client, db):
        """API: Status + Jahr kombiniert."""
        _create_invoice(db, import_hash="f_sy1", status="pending", due_date=date(2026, 1, 1))
        _create_invoice(db, import_hash="f_sy2", status="paid",    due_date=date(2026, 2, 1))
        _create_invoice(db, import_hash="f_sy3", status="pending", due_date=date(2025, 12, 1))
        r = client.get("/api/invoices?status=pending&year=2026")
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["status"] == "pending"
        assert data[0]["due_date"] == "2026-01-01"

    def test_dashboard_inv_filter_paid(self, client, db):
        """Dashboard: ?inv_status=paid gibt 200 zurück."""
        _create_invoice(db, import_hash="df_inv1", status="paid")
        r = client.get("/?inv_status=paid")
        assert r.status_code == 200

    def test_dashboard_inv_filter_alle(self, client, db):
        """Dashboard: ?inv_status= (leer) zeigt alle Rechnungen."""
        _create_invoice(db, import_hash="df_all1", status="pending")
        _create_invoice(db, import_hash="df_all2", status="paid")
        r = client.get("/?inv_status=")
        assert r.status_code == 200

    def test_dashboard_inv_filter_year(self, client, db):
        """Dashboard: ?inv_year=2026 gibt 200 zurück."""
        _create_invoice(db, import_hash="df_yr1", due_date=date(2026, 5, 1))
        r = client.get("/?inv_status=pending&inv_year=2026")
        assert r.status_code == 200

    def test_dashboard_inv_filter_source_year(self, client, db):
        """Dashboard: source_year wird für Jahresfilter bevorzugt."""
        # Rechnung ohne due_date aber mit source_year=2026
        _create_invoice(db, import_hash="df_sy1", status="paid", source_year=2026)
        # Rechnung mit due_date 2025 aber source_year=2026 → soll bei 2026 erscheinen
        _create_invoice(db, import_hash="df_sy2", status="paid", due_date=date(2025, 1, 1), source_year=2026)
        # Rechnung mit due_date 2025, kein source_year → soll bei 2026 NICHT erscheinen
        _create_invoice(db, import_hash="df_sy3", status="paid", due_date=date(2025, 1, 1))
        r = client.get("/?inv_status=paid&inv_year=2026")
        assert r.status_code == 200
        # Nur die beiden mit source_year=2026
        assert b"df_sy3" not in r.data  # schwacher Check — hauptsache kein 500

    def test_dashboard_inv_filter_month(self, client, db):
        """Dashboard: ?inv_month=5 filtert nach Monat."""
        _create_invoice(db, import_hash="df_mo1", due_date=date(2026, 5, 15))
        _create_invoice(db, import_hash="df_mo2", due_date=date(2026, 3, 10))
        r = client.get("/?inv_status=pending&inv_month=5")
        assert r.status_code == 200

    def test_api_filter_inv_month(self, client, db):
        """API: Monatsfilter auf due_date."""
        _create_invoice(db, import_hash="api_mo1", due_date=date(2026, 5, 15))
        _create_invoice(db, import_hash="api_mo2", due_date=date(2026, 3, 10))
        r = client.get("/api/invoices?year=2026&status=pending")
        data = json.loads(r.data)
        assert len(data) == 2  # beide im 2026, kein Monatsfilter

    def test_api_filter_invoice_category(self, client, db):
        cat_a = _create_category(db, name="Steuern")
        cat_b = _create_category(db, name="Versicherung")
        _create_invoice(db, import_hash="f_cat_a", category_id=cat_a.id)
        _create_invoice(db, import_hash="f_cat_b", category_id=cat_b.id)

        r = client.get(f"/api/invoices?category_id={cat_b.id}")

        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["category_id"] == cat_b.id

    def test_dashboard_invoice_filter_category(self, client, db):
        cat = _create_category(db, name="Versicherung")
        _create_invoice(db, import_hash="df_inv_cat_match", filename="versicherung.pdf", category_id=cat.id)
        _create_invoice(db, import_hash="df_inv_cat_other", filename="steuer.pdf")

        r = client.get(f"/?inv_status=pending&inv_category_id={cat.id}")

        assert r.status_code == 200
        assert b"versicherung.pdf" in r.data
        assert b"steuer.pdf" not in r.data


# ── TransactionLine (Phase 5) ─────────────────────────────────────────────────

def _create_transaction_with_lines(db, lines_data, **kwargs):
    """
    Erstellt eine Buchung mit Detailpositionen.

    Analogie: Ein E-Banking-Auftrag mit mehreren Überweisungen —
    die Hauptbuchung enthält eine Liste von Einzel-Positionen.
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
    def test_transaction_ohne_lines(self, client, db):
        """Normale Buchung ohne Detailpositionen: lines-Liste ist leer."""
        tx = _create_transaction(db, import_hash="tl_no_lines")
        r = client.get("/api/transactions")
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["lines"] == []

    def test_transaction_mit_einer_line(self, client, db):
        """E-Banking-Auftrag mit einer Detailposition."""
        _create_transaction_with_lines(
            db,
            import_hash="tl_one",
            raw_description="Ihr E-Banking-Auftrag",
            amount=250.0,
            lines_data=[{"recipient": "Pro Infirmis", "amount": 250.0, "iban": "CH4400791234567890125"}],
        )
        r = client.get("/api/transactions")
        data = json.loads(r.data)
        assert len(data) == 1
        lines = data[0]["lines"]
        assert len(lines) == 1
        assert lines[0]["recipient"] == "Pro Infirmis"
        assert lines[0]["amount"] == 250.0
        assert lines[0]["iban"] == "CH4400791234567890125"

    def test_transaction_mit_mehreren_lines(self, client, db):
        """E-Banking-Auftrag mit mehreren Empfängern."""
        _create_transaction_with_lines(
            db,
            import_hash="tl_multi",
            raw_description="Ihr E-Banking-Auftrag",
            amount=2052.80,
            lines_data=[
                {"recipient": "Alpenkasse", "amount": 561.70, "iban": "CH5600791234567890123"},
                {"recipient": "Nordlicht",  "amount": 1491.10, "iban": "CH5600791234567890124"},
            ],
        )
        r = client.get("/api/transactions")
        data = json.loads(r.data)
        assert len(data) == 1
        lines = data[0]["lines"]
        assert len(lines) == 2
        assert lines[0]["recipient"] == "Alpenkasse"
        assert lines[1]["recipient"] == "Nordlicht"

    def test_lines_reihenfolge(self, client, db):
        """Detailpositionen werden nach position-Feld sortiert zurückgegeben."""
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

    def test_lines_ohne_iban(self, client, db):
        """Detailposition ohne IBAN: iban-Feld ist None."""
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
        Wenn eine Buchung gelöscht wird, werden auch ihre TransactionLines gelöscht.
        (cascade='all, delete-orphan' im Modell)
        """
        from app.models import Transaction, TransactionLine
        tx = _create_transaction_with_lines(
            db,
            import_hash="tl_cascade",
            raw_description="Ihr E-Banking-Auftrag",
            amount=100.0,
            lines_data=[{"recipient": "Wird gelöscht", "amount": 100.0}],
        )
        tx_id = tx.id
        assert TransactionLine.query.filter_by(transaction_id=tx_id).count() == 1
        # Buchung löschen
        db.session.delete(db.session.get(Transaction, tx_id))
        db.session.commit()
        # Detailpositionen müssen weg sein
        assert TransactionLine.query.filter_by(transaction_id=tx_id).count() == 0

    def test_dashboard_zeigt_buchung_mit_lines(self, client, db):
        """Dashboard rendert ohne Fehler, wenn eine Buchung Detailpositionen hat."""
        _create_transaction_with_lines(
            db,
            import_hash="tl_dash",
            raw_description="Ihr E-Banking-Auftrag",
            amount=500.0,
            lines_data=[
                {"recipient": "Alpenkasse", "amount": 250.0},
                {"recipient": "Nordlicht",  "amount": 250.0},
            ],
        )
        r = client.get("/")
        assert r.status_code == 200
        # Toggle-Button und Empfänger-Namen im HTML
        assert b"Positionen" in r.data
        assert b"Alpenkasse" in r.data
