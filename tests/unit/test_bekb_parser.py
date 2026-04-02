"""Unit tests for the BEKB parser helpers."""

from datetime import date
from pathlib import Path

from app.importers import bekb
from app.importers.bekb import _parse_single_block, _parse_sub_entries


class TestParseSingleBlock:
    def test_extracts_amount_from_end_of_first_line(self):
        block = ["Alpen Versicherung 561.70", "CH5600791234567890123"]
        result = _parse_single_block(block)
        assert result is not None
        assert result["recipient"] == "Alpen Versicherung"
        assert result["amount"] == 561.70

    def test_extracts_iban(self):
        block = ["Nordlicht Gesundheit 1491.10", "CH5600791234567890124"]
        result = _parse_single_block(block)
        assert result is not None
        assert result["iban"] == "CH5600791234567890124"

    def test_returns_none_for_empty_block(self):
        assert _parse_single_block([]) is None

    def test_uses_override_amount_when_needed(self):
        block = ["Pro Infirmis", "CH4400791234567890125"]
        result = _parse_single_block(block, override_amount=250.0)
        assert result is not None
        assert result["amount"] == 250.0
        assert result["recipient"] == "Pro Infirmis"

    def test_merges_hyphenated_names(self):
        block = [
            "Schweizerische Alpen Versiche- 561.70",
            "rungsgesellschaft AG",
            "CH5600791234567890123",
        ]
        result = _parse_single_block(block)
        assert result is not None
        assert "Versicherungsgesellschaft" in result["recipient"]

    def test_trims_spaces_from_iban(self):
        block = ["Empfaenger 100.00", "CH56 0079 1234 5678 901"]
        result = _parse_single_block(block)
        assert result is not None
        assert result["iban"] == "CH56007912345678901"


class TestParseSubEntries:
    def test_single_recipient_uses_total_amount(self):
        lines = ["Pro Infirmis", "CH4400791234567890125"]
        result = _parse_sub_entries(lines, total_amount=250.0)
        assert result == [
            {
                "recipient": "Pro Infirmis",
                "amount": 250.0,
                "iban": "CH4400791234567890125",
            }
        ]

    def test_multi_recipient_splits_on_separator_lines(self):
        lines = [
            ".",
            "Alpenkasse 561.70",
            "CH5600791234567890123",
            ".",
            "Nordlicht 1491.10",
            "CH5600791234567890124",
        ]
        result = _parse_sub_entries(lines, total_amount=2052.80)
        assert len(result) == 2
        assert result[0]["recipient"] == "Alpenkasse"
        assert result[0]["amount"] == 561.70
        assert result[1]["recipient"] == "Nordlicht"
        assert result[1]["amount"] == 1491.10

    def test_empty_lines_return_empty_list(self):
        assert _parse_sub_entries(["  ", "\t", ""], total_amount=0.0) == []


class TestAccountMetadata:
    def test_extracts_account_name_and_type_from_first_page(self, monkeypatch):
        monkeypatch.setattr(
            bekb,
            "_read_first_page_lines",
            lambda _: [
                "Berner Kantonalbank AG",
                "Finanzierungskonto",
                "IBAN CH88 0079 0042 9742 4173 9 Herr und Frau",
                "Hauskonto Alex Beispiel & Robin Beispiel",
                "Beispielweg 6",
            ],
        )

        metadata = bekb.extract_account_metadata(
            Path("CH8800790042974241739_20220624_0001_Gutschrifts_Belastungsanzeige.pdf")
        )

        assert metadata["iban"] == "CH8800790042974241739"
        assert metadata["name"] == "BEKB Finanzierungskonto - Hauskonto Alex Beispiel & Robin Beispiel"
        assert metadata["type"] == "other"

    def test_prefers_configured_account_name(self, monkeypatch, app):
        lines = [
            "Berner Kantonalbank AG",
            "Privatkonto Plus",
            "IBAN CH11 0079 0042 9742 4146 6 Herr und Frau",
            "Alex Beispiel & Robin Beispiel",
        ]
        monkeypatch.setattr(bekb, "_read_first_page_lines", lambda _: lines)
        with app.app_context():
            app.config["ACCOUNT_NAME_OVERRIDES"] = {
                "CH1100790042974241466": "BEKB Privatkonto Beispiel"
            }
            metadata = bekb.extract_account_metadata(
                Path("CH1100790042974241466_20260131_Kontoauszug.pdf")
            )

        assert metadata["name"] == "BEKB Privatkonto Beispiel"


class TestBekbNoticeParser:
    def test_parses_credit_notice(self, monkeypatch):
        monkeypatch.setattr(
            bekb,
            "_read_pdf_text",
            lambda _: (
                "Gutschriftsanzeige per 24.12.2020 Datum:24.12.2020\n"
                "Zahlungseingang\n"
                "Bezahlt von: CHF 1'000.00\n"
                "Alex Beispiel & Robin Beispiel\n"
                "Gutschrift\n"
                "Valuta24.12.2020 CHF 1'000.00\n"
                "Neuer Saldo\n"
                "zu Ihren Gunsten CHF 10'085.80\n"
            ),
        )

        result = bekb.parse_bekb_notice(Path("notice.pdf"))

        assert result == [
            {
                "date": date(2020, 12, 24),
                "description": "Zahlungseingang: Alex Beispiel & Robin Beispiel",
                "amount": 1000.0,
                "type": "income",
                "saldo": 10085.80,
                "lines": [],
            }
        ]

    def test_keeps_four_digit_year_in_notice_value_date(self, monkeypatch):
        monkeypatch.setattr(
            bekb,
            "_read_pdf_text",
            lambda _: (
                "Gutschriftsanzeige per 23.01.2026 Datum:23.01.2026\n"
                "Zahlungseingang\n"
                "Bezahlt von: CHF 1'000.00\n"
                "Alex Beispiel & Robin Beispiel\n"
                "Gutschrift\n"
                "Valuta23.01.2026 CHF 1'000.00\n"
                "Neuer Saldo\n"
                "zu Ihren Gunsten CHF 4'743.56\n"
            ),
        )

        result = bekb.parse_bekb_notice(Path("notice_2026.pdf"))

        assert result[0]["date"] == date(2026, 1, 23)

    def test_marks_returned_payments_explicitly(self, monkeypatch):
        monkeypatch.setattr(
            bekb,
            "_read_pdf_text",
            lambda _: (
                "Gutschriftsanzeige per 02.12.2022 Datum:02.12.2022\n"
                "Zahlungseingang (Rueckleitung)\n"
                "Urspruenglicher Beguenstigter:\n"
                "Robin Beispiel\n"
                "Gutschrift\n"
                "Valuta02.12.2022 CHF 1'025.00\n"
                "Neuer Saldo\n"
                "zu Ihren Gunsten CHF 10'409.65\n"
            ),
        )

        result = bekb.parse_bekb_notice(Path("returned_notice.pdf"))

        assert result[0]["description"] == "Zahlungseingang: Robin Beispiel"
        assert result[0]["amount"] == 1025.0
        assert result[0]["type"] == "income"
