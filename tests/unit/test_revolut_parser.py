"""Unit tests for Revolut statement parser/importer helpers."""

from datetime import date
from pathlib import Path

from app.importers import revolut


class TestRevolutStatementParser:
    def test_parses_transactions_with_continuation_lines(self, monkeypatch):
        monkeypatch.setattr(
            revolut,
            "_read_pdf_lines",
            lambda _: [
                "CHF Statement",
                "Account (E-Money) 2,371.38 CHF 105,285.16 CHF 104,539.97 CHF 1,626.19 CHF",
                "Date Description Money out Money in Balance",
                "3 Jan 2020 sample merchant 12.34 CHF 2,359.04 CHF",
                "To: 55.55 Sample Store, Demo City",
                "Card: 527346******7326",
                "9 Jan 2020 Payment from ALEX EXAMPLE + SAM EXAMPLE 4,000.00 CHF 6,359.04 CHF",
                "From: ALEX EXAMPLE + SAM EXAMPLE",
            ],
        )

        rows = revolut.parse_revolut_statement(Path("revolut.pdf"))

        assert len(rows) == 2
        assert rows[0]["date"] == date(2020, 1, 3)
        assert rows[0]["type"] == "expense"
        assert rows[0]["amount"] == 12.34
        assert rows[0]["saldo"] == 2359.04
        assert "To: 55.55 Sample Store, Demo City" in rows[0]["description"]
        assert rows[1]["type"] == "income"
        assert rows[1]["amount"] == 4000.00
        assert rows[1]["saldo"] == 6359.04

    def test_first_row_without_opening_uses_income_hint(self, monkeypatch):
        monkeypatch.setattr(
            revolut,
            "_read_pdf_lines",
            lambda _: [
                "Date Description Money out Money in Balance",
                "1 Apr 2026 Payment from ALEX EXAMPLE & SAM EXAMPLE 2,500.00 CHF 2,845.67 CHF",
            ],
        )

        rows = revolut.parse_revolut_statement(Path("revolut.pdf"))

        assert len(rows) == 1
        assert rows[0]["type"] == "income"
        assert rows[0]["date"] == date(2026, 4, 1)


class TestRevolutAccountMetadata:
    def test_extracts_iban_and_holder_name(self, monkeypatch):
        monkeypatch.setattr(
            revolut,
            "_read_first_page_lines",
            lambda _: [
                "CHF Statement",
                "Generated on the 2 Apr 2026",
                "Revolut Ltd",
                "ALEX EXAMPLE",
                "Example Street 1 IBAN LT00FAKEIBAN00000000001",
            ],
        )

        metadata = revolut.extract_account_metadata(Path("account-statement.pdf"))

        assert metadata["iban"] == "LT00FAKEIBAN00000000001"
        assert metadata["name"] == "Revolut - Alex Example"

    def test_prefers_configured_account_name(self, monkeypatch, app):
        monkeypatch.setattr(
            revolut,
            "_read_first_page_lines",
            lambda _: [
                "Revolut Ltd",
                "ALEX EXAMPLE",
                "Address line IBAN LT00FAKEIBAN00000000001",
            ],
        )
        with app.app_context():
            app.config["ACCOUNT_NAME_OVERRIDES"] = {
                "LT00FAKEIBAN00000000001": "Revolut Personal Account Demo"
            }
            metadata = revolut.extract_account_metadata(Path("account-statement.pdf"))

        assert metadata["name"] == "Revolut Personal Account Demo"
