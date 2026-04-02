"""Unit tests for `importers/base.py`."""

from datetime import date

import pytest

from app.importers.base import parse_chf, make_hash, date_from_ddmmyy


# ── parse_chf ────────────────────────────────────────────────────────────────

class TestParseChf:
    def test_apostrophe_thousands_separator(self):
        """Standard Swiss format with apostrophe thousands separators."""
        assert parse_chf("1'470.00") == 1470.0

    def test_space_thousands_separator(self):
        """QR bills may use spaces as thousands separators."""
        assert parse_chf("2 522.75") == 2522.75

    def test_multiple_dots(self):
        """OCR may produce multiple dots."""
        assert parse_chf("7'.568.25") == 7568.25

    def test_large_amount(self):
        assert parse_chf("23'713.29") == 23713.29

    def test_letter_o_instead_of_zero_uppercase(self):
        """OCR may confuse zero with uppercase O."""
        assert parse_chf("1'47O.OO") == 1470.0

    def test_letter_o_instead_of_zero_lowercase(self):
        assert parse_chf("1'470.o0") == 1470.0

    def test_simple_number(self):
        assert parse_chf("100.00") == 100.0

    def test_invalid_returns_none(self):
        assert parse_chf("abc") is None

    def test_empty_returns_none(self):
        assert parse_chf("") is None

    def test_letters_only_returns_none(self):
        assert parse_chf("CHF") is None

    def test_comma_as_decimal_separator(self):
        """Comma decimals are normalized as well."""
        assert parse_chf("1470,00") == 1470.0


# ── make_hash ────────────────────────────────────────────────────────────────

class TestMakeHash:
    def test_stable_hash(self):
        """The same input should produce the same hash."""
        assert make_hash("test.pdf", 0) == make_hash("test.pdf", 0)

    def test_different_page_index(self):
        """Different page indexes should change the hash."""
        assert make_hash("test.pdf", 0) != make_hash("test.pdf", 1)

    def test_different_file_names(self):
        assert make_hash("a.pdf", 0) != make_hash("b.pdf", 0)

    def test_sha1_length(self):
        """A SHA1 hex digest always has 40 characters."""
        h = make_hash("file.pdf", 0)
        assert len(h) == 40
        assert all(c in "0123456789abcdef" for c in h)

    def test_multiple_parts(self):
        """The helper accepts any number of input parts."""
        h = make_hash(date(2026, 1, 15), 100.0, "Migros")
        assert len(h) == 40


# ── date_from_ddmmyy ─────────────────────────────────────────────────────────

class TestDateFromDdmmyy:
    def test_standard_date(self):
        assert date_from_ddmmyy("04.02.26") == date(2026, 2, 4)

    def test_millennium_date(self):
        assert date_from_ddmmyy("31.12.99") == date(2099, 12, 31)

    def test_iso_format_returns_none(self):
        """ISO input is not accepted by this parser."""
        assert date_from_ddmmyy("2026-02-04") is None

    def test_too_short_returns_none(self):
        assert date_from_ddmmyy("4.2.26") is None

    def test_invalid_returns_none(self):
        assert date_from_ddmmyy("32.01.26") is None
