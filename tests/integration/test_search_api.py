"""
tests/integration/test_search_api.py — Integration tests for advanced search API.

All data is fully made-up with fictitious names and amounts.
"""

import json
from datetime import date

import pytest

from app.models import Account, Category, Transaction, TransactionLine
from app import db as _db


def _seed_data(db):
    """Seed a small dataset of made-up transactions for search tests."""
    acct_a = Account(name="Hauptkonto Muster", iban="CH0000000000000000001", type="checking", currency="CHF")
    acct_b = Account(name="Sparkonto Muster", iban="CH0000000000000000002", type="savings", currency="CHF")
    db.session.add_all([acct_a, acct_b])
    db.session.flush()

    cat = Category(name="Lebensmittel")
    db.session.add(cat)
    db.session.flush()

    txs = [
        Transaction(
            account_id=acct_a.id, date=date(2026, 1, 15),
            raw_description="Einkauf Muster-Laden AG",
            amount=85.50, type="expense", import_hash="search_h1",
            category_id=cat.id,
        ),
        Transaction(
            account_id=acct_a.id, date=date(2026, 2, 10),
            raw_description="Gehalt Muster GmbH",
            amount=5200.00, type="income", import_hash="search_h2",
        ),
        Transaction(
            account_id=acct_b.id, date=date(2026, 1, 20),
            raw_description="Zinsgutschrift",
            amount=12.30, type="income", import_hash="search_h3",
        ),
        Transaction(
            account_id=acct_a.id, date=date(2026, 3, 5),
            raw_description="E-Banking Sammelauftrag",
            amount=350.00, type="expense", import_hash="search_h4",
        ),
    ]
    db.session.add_all(txs)
    db.session.flush()

    # Add transaction lines to the Sammelauftrag
    lines = [
        TransactionLine(transaction_id=txs[3].id, position=1, recipient="Fantasie Strom AG", amount=150.00, iban="CH1234567890123456789"),
        TransactionLine(transaction_id=txs[3].id, position=2, recipient="Beispiel Versicherung", amount=200.00, iban="CH9876543210987654321"),
    ]
    db.session.add_all(lines)
    db.session.commit()

    return {"acct_a": acct_a, "acct_b": acct_b, "cat": cat, "txs": txs}


class TestSearchNoGrouping:
    """Test /api/transactions/search without group_by."""

    def test_returns_all_transactions(self, client, db):
        _seed_data(db)
        r = client.get("/api/transactions/search")
        assert r.status_code == 200
        data = r.get_json()
        assert data["group_by"] == ""
        assert len(data["rows"]) == 4
        assert data["totals"]["count"] == 4

    def test_filter_by_account(self, client, db):
        seed = _seed_data(db)
        r = client.get(f"/api/transactions/search?account_ids={seed['acct_b'].id}")
        data = r.get_json()
        assert len(data["rows"]) == 1
        assert data["rows"][0]["raw_description"] == "Zinsgutschrift"

    def test_filter_by_category(self, client, db):
        seed = _seed_data(db)
        r = client.get(f"/api/transactions/search?category_ids={seed['cat'].id}")
        data = r.get_json()
        assert len(data["rows"]) == 1

    def test_filter_by_year(self, client, db):
        _seed_data(db)
        r = client.get("/api/transactions/search?years=2026")
        data = r.get_json()
        assert data["totals"]["count"] == 4

    def test_filter_by_month(self, client, db):
        _seed_data(db)
        r = client.get("/api/transactions/search?months=1")
        data = r.get_json()
        assert data["totals"]["count"] == 2

    def test_filter_by_description(self, client, db):
        _seed_data(db)
        r = client.get("/api/transactions/search?raw_descriptions=Muster-Laden")
        data = r.get_json()
        assert data["totals"]["count"] == 1

    def test_filter_by_recipient(self, client, db):
        _seed_data(db)
        r = client.get("/api/transactions/search?recipients=Fantasie Strom")
        data = r.get_json()
        assert data["totals"]["count"] == 1

    def test_empty_result(self, client, db):
        _seed_data(db)
        r = client.get("/api/transactions/search?years=1999")
        data = r.get_json()
        assert data["totals"]["count"] == 0
        assert data["rows"] == []

    def test_totals_math(self, client, db):
        _seed_data(db)
        r = client.get("/api/transactions/search")
        data = r.get_json()
        assert data["totals"]["positive"] == round(5200.00 + 12.30, 2)
        assert data["totals"]["negative"] == round(85.50 + 350.00, 2)


class TestSearchGrouped:
    """Test /api/transactions/search with group_by parameter."""

    def test_group_by_account(self, client, db):
        _seed_data(db)
        r = client.get("/api/transactions/search?group_by=account")
        data = r.get_json()
        assert data["group_by"] == "account"
        groups = {row["group"]: row for row in data["rows"]}
        assert "Hauptkonto Muster" in groups
        assert "Sparkonto Muster" in groups

    def test_group_by_category(self, client, db):
        _seed_data(db)
        r = client.get("/api/transactions/search?group_by=category")
        data = r.get_json()
        groups = {row["group"] for row in data["rows"]}
        assert "Lebensmittel" in groups
        assert "Uncategorized" in groups

    def test_group_by_year(self, client, db):
        _seed_data(db)
        r = client.get("/api/transactions/search?group_by=year")
        data = r.get_json()
        assert len(data["rows"]) == 1
        assert data["rows"][0]["group"] == "2026"

    def test_group_by_month(self, client, db):
        _seed_data(db)
        r = client.get("/api/transactions/search?group_by=month")
        data = r.get_json()
        months = {row["group"] for row in data["rows"]}
        assert months == {"01", "02", "03"}

    def test_group_by_raw_description(self, client, db):
        _seed_data(db)
        r = client.get("/api/transactions/search?group_by=raw_description")
        data = r.get_json()
        assert len(data["rows"]) == 4

    def test_group_by_recipient(self, client, db):
        _seed_data(db)
        r = client.get("/api/transactions/search?group_by=recipient")
        data = r.get_json()
        groups = {row["group"] for row in data["rows"]}
        assert "Fantasie Strom AG" in groups
        assert "Beispiel Versicherung" in groups

    def test_invalid_group_by(self, client, db):
        _seed_data(db)
        r = client.get("/api/transactions/search?group_by=invalid")
        assert r.status_code == 400

    def test_grouped_rows_sorted_by_abs_sum(self, client, db):
        _seed_data(db)
        r = client.get("/api/transactions/search?group_by=account")
        data = r.get_json()
        sums = [abs(row["sum"]) for row in data["rows"]]
        assert sums == sorted(sums, reverse=True)


class TestSearchSpecialChars:
    """Test that LIKE wildcards in search tokens are escaped."""

    def test_percent_in_description_doesnt_match_all(self, client, db):
        _seed_data(db)
        r = client.get("/api/transactions/search?raw_descriptions=100%25")
        data = r.get_json()
        assert data["totals"]["count"] == 0

    def test_underscore_in_description(self, client, db):
        _seed_data(db)
        # underscore is escaped in the LIKE literal path, but the normalized
        # path strips both _ and - so it still matches via normalization
        r = client.get("/api/transactions/search?raw_descriptions=Muster_Laden")
        data = r.get_json()
        assert data["totals"]["count"] == 1
