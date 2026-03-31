"""Unit tests for `importers/base.py`."""

from datetime import date

import pytest

from app.importers.base import parse_chf, make_hash, date_from_ddmmyy


# ── parse_chf ────────────────────────────────────────────────────────────────

class TestParseChf:
    def test_apostroph_tausender(self):
        """Standard Swiss format with apostrophe thousands separators."""
        assert parse_chf("1'470.00") == 1470.0

    def test_leerzeichen_tausender(self):
        """QR bills may use spaces as thousands separators."""
        assert parse_chf("2 522.75") == 2522.75

    def test_mehrere_punkte(self):
        """OCR may produce multiple dots."""
        assert parse_chf("7'.568.25") == 7568.25

    def test_grosser_betrag(self):
        assert parse_chf("23'713.29") == 23713.29

    def test_buchstabe_o_statt_null(self):
        """OCR may confuse zero with uppercase O."""
        assert parse_chf("1'47O.OO") == 1470.0

    def test_kleines_o_statt_null(self):
        assert parse_chf("1'470.o0") == 1470.0

    def test_einfache_zahl(self):
        assert parse_chf("100.00") == 100.0

    def test_ungueltig_gibt_none(self):
        assert parse_chf("abc") is None

    def test_leer_gibt_none(self):
        assert parse_chf("") is None

    def test_nur_buchstaben_gibt_none(self):
        assert parse_chf("CHF") is None

    def test_komma_als_dezimaltrennzeichen(self):
        """Comma decimals are normalized as well."""
        assert parse_chf("1470,00") == 1470.0


# ── make_hash ────────────────────────────────────────────────────────────────

class TestMakeHash:
    def test_stabiler_hash(self):
        """The same input should produce the same hash."""
        assert make_hash("test.pdf", 0) == make_hash("test.pdf", 0)

    def test_verschiedene_page_index(self):
        """Different page indexes should change the hash."""
        assert make_hash("test.pdf", 0) != make_hash("test.pdf", 1)

    def test_verschiedene_dateinamen(self):
        assert make_hash("a.pdf", 0) != make_hash("b.pdf", 0)

    def test_sha1_laenge(self):
        """A SHA1 hex digest always has 40 characters."""
        h = make_hash("file.pdf", 0)
        assert len(h) == 40
        assert all(c in "0123456789abcdef" for c in h)

    def test_mehrere_parts(self):
        """The helper accepts any number of input parts."""
        h = make_hash(date(2026, 1, 15), 100.0, "Migros")
        assert len(h) == 40


# ── date_from_ddmmyy ─────────────────────────────────────────────────────────

class TestDateFromDdmmyy:
    def test_normal(self):
        assert date_from_ddmmyy("04.02.26") == date(2026, 2, 4)

    def test_jahrtausend(self):
        assert date_from_ddmmyy("31.12.99") == date(2099, 12, 31)

    def test_iso_format_gibt_none(self):
        """ISO input is not accepted by this parser."""
        assert date_from_ddmmyy("2026-02-04") is None

    def test_zu_kurz_gibt_none(self):
        assert date_from_ddmmyy("4.2.26") is None

    def test_ungueltig_gibt_none(self):
        assert date_from_ddmmyy("32.01.26") is None
