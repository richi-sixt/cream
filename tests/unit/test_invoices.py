"""Unit tests for `importers/invoices.py`."""

from datetime import date

import pytest

from app.importers.invoices import extract_slip_data


class TestExtractSlipData:

    # Amount extraction via Swiss QR standard

    def test_qr_betrag_mit_apostroph(self):
        """Standard case with apostrophe thousands separators."""
        text = "Währung Betrag\nCHF 1'470.00\nOrdentliche Steuer Bund 2025"
        result = extract_slip_data(text)
        assert result["amount"] == 1470.0

    def test_qr_betrag_mit_leerzeichen(self):
        """QR bills may use spaces as thousands separators."""
        text = "Währung Betrag\nCHF 2 522.75\n1. Rate zahlbar bis: 31.05.2026"
        result = extract_slip_data(text)
        assert result["amount"] == 2522.75

    def test_qr_betrag_kleinbuchstaben_chf(self):
        """OCR may produce a mixed-case currency code."""
        text = "Währung Betrag\ncHF 1 470.00"
        result = extract_slip_data(text)
        assert result["amount"] == 1470.0

    def test_qr_betrag_betmg_ocr_artefakt(self):
        """OCR may turn `Betrag` into `Betmg`."""
        text = "Währung Betmg\nCHF 1 470.00"
        result = extract_slip_data(text)
        assert result["amount"] == 1470.0

    # Regression tests for known parsing bugs

    def test_gesamtbetrag_zahlbar_bis_kein_datum_als_betrag(self):
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

    def test_gesamtbetrag_chf_wird_erkannt(self):
        """`Gesamtbetrag CHF ...` is a legitimate amount pattern."""
        text = "Gesamtbetrag CHF 1'470.00"
        result = extract_slip_data(text)
        assert result["amount"] == 1470.0

    # Due date extraction

    def test_faellig_am(self):
        text = "Zahlbar bis 31.03.2026\nCHF 1'470.00"
        result = extract_slip_data(text)
        assert result["due_date"] == date(2026, 3, 31)

    def test_faellig_rate(self):
        text = "1. Rate zahlbar bis: 31.05.2026\nCHF 2 522.75"
        result = extract_slip_data(text)
        assert result["due_date"] == date(2026, 5, 31)

    def test_kein_datum_gibt_none(self):
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

    def test_ordentliche_steuer_bund(self):
        text = "Ordentliche Steuer Bund 2025\nGesamtbetrag zahlbar bis: 31.03.2026"
        result = extract_slip_data(text)
        assert result["slip_label"] is not None
        assert "Bund" in result["slip_label"]

    def test_kein_label_gibt_none(self):
        text = "Währung Betrag\nCHF 500.00\nZahlbar bis 30.06.2026"
        result = extract_slip_data(text)
        assert result["slip_label"] is None

    # Empty text

    def test_leerer_text(self):
        result = extract_slip_data("")
        assert result == {"amount": None, "due_date": None, "slip_label": None}
