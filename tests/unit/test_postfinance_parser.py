"""Unit tests for the PostFinance parser."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from app.importers import postfinance
from app.importers.base import date_from_ddmmyy


class _FakePdf:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakePage:
    def __init__(self, words=None, text=""):
        self._words = words or []
        self._text = text

    def extract_words(self):
        return self._words

    def extract_text(self):
        return self._text


class TestPostFinanceMetadata:
    def test_extracts_bank_account_name_and_type(self, monkeypatch):
        monkeypatch.setattr(
            postfinance,
            "_read_first_page_lines",
            lambda _: [
                "PostFinance AG",
                "Alex Beispiel",
                "Privatkonto",
                "Kontoauszug 01.02.2026 - 29.02.2026 Datum: 01.03.2026",
                "IBAN CH53 0900 0000 1234 5678 9 CHF",
            ],
        )

        metadata = postfinance.extract_account_metadata(
            Path("REP_P_CH5309000000123456789_1108239329_0_2026020105141049.pdf")
        )

        assert metadata["iban"] == "CH5309000000123456789"
        assert metadata["name"] == "PostFinance Privatkonto - Alex Beispiel"
        assert metadata["type"] == "checking"


class TestPostFinanceParser:
    def test_parses_credit_and_debit_rows(self, monkeypatch):
        words = [
            {"text": "Text", "x0": 119.1, "top": 404.0},
            {"text": "Gutschrift", "x0": 310.9, "top": 404.0},
            {"text": "Lastschrift", "x0": 388.5, "top": 404.0},
            {"text": "Valuta", "x0": 458.7, "top": 404.0},
            {"text": "Saldo", "x0": 539.3, "top": 404.0},
            {"text": "31.03.24", "x0": 65.2, "top": 425.9},
            {"text": "Kontostand", "x0": 119.1, "top": 425.4},
            {"text": "2", "x0": 527.0, "top": 425.9},
            {"text": "563.03", "x0": 534.9, "top": 425.9},
            {"text": "03.04.24", "x0": 65.2, "top": 447.8},
            {"text": "GUTSCHRIFT", "x0": 119.1, "top": 447.8},
            {"text": "311.25", "x0": 325.2, "top": 447.8},
            {"text": "03.04.24", "x0": 450.4, "top": 447.8},
            {"text": "2", "x0": 526.9, "top": 447.9},
            {"text": "874.28", "x0": 534.9, "top": 447.9},
            {"text": "ABSENDER:", "x0": 119.1, "top": 468.9},
            {"text": "NORDLICHT", "x0": 119.1, "top": 479.4},
            {"text": "05.04.24", "x0": 65.2, "top": 595.0},
            {"text": "LASTSCHRIFT", "x0": 119.1, "top": 594.9},
            {"text": "1", "x0": 396.6, "top": 595.0},
            {"text": "000.00", "x0": 404.5, "top": 595.0},
            {"text": "05.04.24", "x0": 450.4, "top": 595.0},
            {"text": "1", "x0": 526.9, "top": 595.1},
            {"text": "874.28", "x0": 534.9, "top": 595.1},
            {"text": "BERNER", "x0": 119.1, "top": 605.5},
            {"text": "KANTONALBANK", "x0": 151.7, "top": 605.5},
        ]

        fake_pdfplumber = SimpleNamespace(
            open=lambda _: _FakePdf([_FakePage(words=words)])
        )
        monkeypatch.setitem(sys.modules, "pdfplumber", fake_pdfplumber)

        result = postfinance.parse_postfinance_pdf(Path("statement.pdf"))

        assert len(result) == 2
        assert result[0]["type"] == "income"
        assert result[0]["amount"] == 311.25
        assert result[0]["saldo"] == 2874.28
        assert "ABSENDER:" in result[0]["description"]
        assert "NORDLICHT" in result[0]["description"]
        assert result[1]["type"] == "expense"
        assert result[1]["amount"] == 1000.0
        assert result[1]["saldo"] == 1874.28
        assert "BERNER KANTONALBANK" in result[1]["description"]

    def test_merges_continuation_row_with_amount_and_saldo(self, monkeypatch):
        words = [
            {"text": "Text", "x0": 119.1, "top": 404.0},
            {"text": "Gutschrift", "x0": 311.4, "top": 404.0},
            {"text": "Lastschrift", "x0": 387.9, "top": 404.0},
            {"text": "Valuta", "x0": 459.0, "top": 404.0},
            {"text": "Saldo", "x0": 539.2, "top": 404.0},
            {"text": "31.12.25", "x0": 65.2, "top": 447.8},
            {"text": "ZINSABSCHLUSS", "x0": 119.1, "top": 447.8},
            {"text": "01.01.2025", "x0": 188.1, "top": 447.8},
            {"text": "-", "x0": 237.2, "top": 447.8},
            {"text": "0.00", "x0": 414.5, "top": 447.9},
            {"text": "31.12.25", "x0": 449.1, "top": 447.8},
            {"text": "31.12.2025", "x0": 119.1, "top": 458.6},
            {"text": "PREIS", "x0": 119.1, "top": 479.4},
            {"text": "FÜR", "x0": 143.3, "top": 479.4},
            {"text": "5.00", "x0": 414.5, "top": 479.6},
            {"text": "31.12.25", "x0": 449.1, "top": 479.4},
            {"text": "469.07", "x0": 533.4, "top": 479.6},
            {"text": "BANKPAKET", "x0": 119.1, "top": 490.2},
            {"text": "SMART", "x0": 168.7, "top": 490.2},
            {"text": "11.2025", "x0": 198.8, "top": 490.2},
        ]
        fake_pdfplumber = SimpleNamespace(
            open=lambda _: _FakePdf([_FakePage(words=words)])
        )
        monkeypatch.setitem(sys.modules, "pdfplumber", fake_pdfplumber)

        result = postfinance.parse_postfinance_pdf(Path("year_end_statement.pdf"))

        assert len(result) == 2
        assert result[0]["amount"] == 0.0
        assert result[0]["description"] == "ZINSABSCHLUSS 01.01.2025 | 31.12.2025"
        assert result[1]["amount"] == 5.0
        assert result[1]["saldo"] == 469.07
        assert "PREIS FÜR" in result[1]["description"]
        assert "BANKPAKET SMART 11.2025" in result[1]["description"]

    def test_skips_total_summary_row(self, monkeypatch):
        words = [
            {"text": "Text", "x0": 119.1, "top": 404.0},
            {"text": "Gutschrift", "x0": 311.4, "top": 404.0},
            {"text": "Lastschrift", "x0": 387.9, "top": 404.0},
            {"text": "Valuta", "x0": 459.0, "top": 404.0},
            {"text": "Saldo", "x0": 539.2, "top": 404.0},
            {"text": "31.12.25", "x0": 65.2, "top": 447.8},
            {"text": "PREIS", "x0": 119.1, "top": 447.8},
            {"text": "FÜR", "x0": 143.3, "top": 447.8},
            {"text": "5.00", "x0": 414.5, "top": 447.9},
            {"text": "31.12.25", "x0": 449.1, "top": 447.8},
            {"text": "469.07", "x0": 533.4, "top": 447.9},
            {"text": "Total", "x0": 119.1, "top": 468.6},
            {"text": "0.00", "x0": 325.2, "top": 468.6},
        ]
        fake_pdfplumber = SimpleNamespace(
            open=lambda _: _FakePdf([_FakePage(words=words)])
        )
        monkeypatch.setitem(sys.modules, "pdfplumber", fake_pdfplumber)

        result = postfinance.parse_postfinance_pdf(Path("year_end_statement.pdf"))

        assert len(result) == 1
        assert result[0]["description"] == "PREIS FÜR"

    def test_does_not_turn_integer_merchant_code_into_amount(self, monkeypatch):
        words = [
            {"text": "Text", "x0": 119.1, "top": 100.0},
            {"text": "Gutschrift", "x0": 311.4, "top": 100.0},
            {"text": "Lastschrift", "x0": 387.9, "top": 100.0},
            {"text": "Valuta", "x0": 459.0, "top": 100.0},
            {"text": "Saldo", "x0": 539.2, "top": 100.0},
            {"text": "03.05.25", "x0": 65.2, "top": 120.0},
            {"text": "APPLE", "x0": 119.1, "top": 120.0},
            {"text": "PAY", "x0": 145.7, "top": 120.0},
            {"text": "KAUF/DIENSTLEISTUNG", "x0": 163.4, "top": 120.0},
            {"text": "VOM", "x0": 259.9, "top": 120.0},
            {"text": "67.10", "x0": 408.8, "top": 120.0},
            {"text": "02.05.25", "x0": 449.1, "top": 120.0},
            {"text": "02.05.2025", "x0": 119.1, "top": 132.0},
            {"text": "KARTEN", "x0": 119.1, "top": 144.0},
            {"text": "NR.", "x0": 152.9, "top": 144.0},
            {"text": "XXXX5318", "x0": 168.1, "top": 144.0},
            {"text": "MCDONALD'S", "x0": 119.1, "top": 156.0},
            {"text": "RESTAURANT", "x0": 175.3, "top": 156.0},
            {"text": "20034", "x0": 230.9, "top": 156.0},
            {"text": "OLTEN", "x0": 119.1, "top": 168.0},
            {"text": "(CH)", "x0": 148.1, "top": 168.0},
        ]
        fake_pdfplumber = SimpleNamespace(
            open=lambda _: _FakePdf([_FakePage(words=words)])
        )
        monkeypatch.setitem(sys.modules, "pdfplumber", fake_pdfplumber)

        result = postfinance.parse_postfinance_pdf(Path("merchant_code.pdf"))

        assert len(result) == 1
        assert result[0]["amount"] == 67.10
        assert "MCDONALD'S RESTAURANT" in result[0]["description"]
        assert "OLTEN (CH)" in result[0]["description"]


class TestPostFinanceNormalization:
    def test_normalizes_legacy_merged_row(self, app, db, monkeypatch):
        from app.models import Account, Transaction

        account = Account(name="PostFinance Privatkonto - Demo", iban="CH5309000000123456789", type="checking")
        db.session.add(account)
        db.session.flush()
        db.session.add(
            Transaction(
                account_id=account.id,
                date=date_from_ddmmyy("31.12.25"),
                raw_description="ZINSABSCHLUSS 01.01.2025 - | 31.12.2025 | PREIS FÜR 5.00 31.12.25 469.07 | BANKPAKET SMART 11.2025 | Total 0.00 5.00",
                amount=0.0,
                type="expense",
                saldo=469.07,
                pdf_source="REP_P_CH5309000000123456789_1108239329_0_2026010111592267.pdf",
                import_hash="legacy-row",
            )
        )
        db.session.commit()

        pdf_path = app.config["BEWEGUNGEN_DIR"] / "REP_P_CH5309000000123456789_1108239329_0_2026010111592267.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n")

        monkeypatch.setattr(
            postfinance,
            "extract_account_metadata",
            lambda _: {"iban": "CH5309000000123456789", "name": account.name, "type": "checking"},
        )
        monkeypatch.setattr(
            postfinance,
            "parse_postfinance_pdf",
            lambda _: [
                {
                    "date": date_from_ddmmyy("31.12.25"),
                    "description": "ZINSABSCHLUSS 01.01.2025 | 31.12.2025",
                    "amount": 0.0,
                    "type": "income",
                    "saldo": None,
                },
                {
                    "date": date_from_ddmmyy("31.12.25"),
                    "description": "PREIS FÜR | BANKPAKET SMART 11.2025",
                    "amount": 5.0,
                    "type": "expense",
                    "saldo": 469.07,
                },
            ],
        )

        with app.app_context():
            stats = postfinance.normalize_postfinance_transactions()
            rows = Transaction.query.order_by(Transaction.id.asc()).all()

        assert stats == {"normalized": 1, "skipped": 0, "errors": 0}
        assert len(rows) == 2
        assert rows[0].raw_description == "ZINSABSCHLUSS 01.01.2025 | 31.12.2025"
        assert rows[1].raw_description == "PREIS FÜR | BANKPAKET SMART 11.2025"
