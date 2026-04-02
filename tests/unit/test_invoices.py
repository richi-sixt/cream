"""Unit tests for `importers/invoices.py`."""

from datetime import date

import pytest

from app.importers.invoices import apply_invoice_title_rule, extract_invoice_issuer, extract_slip_data
from app.models import InvoiceTitleRule


class TestExtractSlipData:

    # Amount extraction via Swiss QR standard

    def test_qr_amount_with_apostrophe(self):
        """Standard case with apostrophe thousands separators."""
        text = "Währung Betrag\nCHF 1'470.00\nOrdentliche Steuer Bund 2025"
        result = extract_slip_data(text)
        assert result["amount"] == 1470.0

    def test_qr_amount_with_space(self):
        """QR bills may use spaces as thousands separators."""
        text = "Währung Betrag\nCHF 2 522.75\n1. Rate zahlbar bis: 31.05.2026"
        result = extract_slip_data(text)
        assert result["amount"] == 2522.75

    def test_qr_amount_with_lowercase_chf(self):
        """OCR may produce a mixed-case currency code."""
        text = "Währung Betrag\ncHF 1 470.00"
        result = extract_slip_data(text)
        assert result["amount"] == 1470.0

    def test_qr_amount_with_betmg_ocr_artifact(self):
        """OCR may turn `Betrag` into `Betmg`."""
        text = "Währung Betmg\nCHF 1 470.00"
        result = extract_slip_data(text)
        assert result["amount"] == 1470.0

    # Regression tests for known parsing bugs

    def test_total_payable_by_ignores_date_as_amount(self):
        """
        Regression: a due date must not be mistaken for an amount.
        """
        text = (
            "Gesamtbetrag zahlbar bis: 31.03.2026\n"
            "Währung Betrag\nCHF 1 470.00"
        )
        result = extract_slip_data(text)
        assert result["amount"] == 1470.0
        assert result["amount"] != pytest.approx(3103.20)

    def test_total_amount_chf_is_detected(self):
        """`Gesamtbetrag CHF ...` is a legitimate amount pattern."""
        text = "Gesamtbetrag CHF 1'470.00"
        result = extract_slip_data(text)
        assert result["amount"] == 1470.0

    def test_payment_request_sentence_overrides_partial_line_items(self):
        text = (
            "Total zu Ihren Lasten 16.50\n"
            "Gesamttotal CHF zu Ihren Lasten 21.35\n"
            "Bitte bezahlen Sie den Betrag von CHF 21.35 bis 25.04.2026 per eBill. Vielen Dank."
        )
        result = extract_slip_data(text)
        assert result["amount"] == 21.35
        assert result["due_date"] == date(2026, 4, 25)

    # Due date extraction

    def test_due_on_date(self):
        text = "Zahlbar bis 31.03.2026\nCHF 1'470.00"
        result = extract_slip_data(text)
        assert result["due_date"] == date(2026, 3, 31)

    def test_due_installment(self):
        text = "1. Rate zahlbar bis: 31.05.2026\nCHF 2 522.75"
        result = extract_slip_data(text)
        assert result["due_date"] == date(2026, 5, 31)

    def test_no_date_returns_none(self):
        text = "Währung Betrag\nCHF 100.00"
        result = extract_slip_data(text)
        assert result["due_date"] is None

    # Slip label extraction

    def test_rate_label_1(self):
        text = "1. Rate zahlbar bis: 31.05.2026"
        result = extract_slip_data(text)
        assert result["slip_label"] == "1. Rate"

    def test_rate_label_3(self):
        text = "3. Rate zahlbar bis: 31.12.2026"
        result = extract_slip_data(text)
        assert result["slip_label"] == "3. Rate"

    def test_federal_direct_tax_label(self):
        text = "Ordentliche Steuer Bund 2025\nGesamtbetrag zahlbar bis: 31.03.2026"
        result = extract_slip_data(text)
        assert result["slip_label"] is not None
        assert "Bund" in result["slip_label"]

    def test_no_label_returns_none(self):
        text = "Währung Betrag\nCHF 500.00\nZahlbar bis 30.06.2026"
        result = extract_slip_data(text)
        assert result["slip_label"] is None

    # Empty text

    def test_empty_text(self):
        result = extract_slip_data("")
        assert result == {"amount": None, "due_date": None, "slip_label": None}


class TestExtractInvoiceIssuer:
    def test_prefers_company_line_over_generic_header(self):
        lines = [
            "Ihr persönliches Beratungsteam",
            "Team Beispiel",
            "support@example.test",
            "Leistungsabrechnung",
            "Helsana Versicherungen AG",
            "Service center, PO Box 123, 8000 Sample City, www.example-health.test",
        ]
        assert extract_invoice_issuer(lines) == "Helsana Versicherungen AG"

    def test_falls_back_to_first_meaningful_line(self):
        lines = [
            "Rechnung",
            "Beispielpraxis Zentrum",
            "Musterstrasse 4",
        ]
        assert extract_invoice_issuer(lines) == "Beispielpraxis Zentrum"

    def test_prefers_tax_office_over_ocr_garbage_header(self):
        lines = [
            "A, ,o rSO",
            "Steueramt des Kantons Solothurn tttttt K lOthr f n",
            "Finanzen und Dienste",
        ]
        assert extract_invoice_issuer(lines) == "Steueramt des Kantons Solothurn tttttt K lOthr f n"


class TestInvoiceTitleRules:
    def test_apply_invoice_title_rule_uses_matching_raw_issuer(self, db):
        db.session.add(InvoiceTitleRule(raw_issuer="Helsana Versicherungen AG", title="Helsana"))
        db.session.commit()

        slip = {
            "filename": "invoice.pdf",
            "page_index": 0,
            "raw_issuer": "Helsana Versicherungen AG",
            "amount": 21.35,
        }

        updated = apply_invoice_title_rule(slip)

        assert updated["title"] == "Helsana"

    def test_apply_invoice_title_rule_keeps_slip_without_match(self, db):
        slip = {
            "filename": "invoice.pdf",
            "page_index": 0,
            "raw_issuer": "Unknown Issuer",
            "amount": 21.35,
        }

        updated = apply_invoice_title_rule(slip)

        assert "title" not in updated
