"""
tests/unit/test_api_helpers.py — Unit tests for API helper functions.

Covers: _parse_csv_ints, _parse_csv_strings, _normalize_search_token,
        _escape_like, and Category model properties (path, depth).
"""

import pytest


class TestParseCsvInts:
    """Tests for _parse_csv_ints."""

    def _call(self, raw):
        from app.api.routes import _parse_csv_ints
        return _parse_csv_ints(raw)

    def test_empty_string(self):
        assert self._call("") == []

    def test_none(self):
        assert self._call(None) == []

    def test_single_value(self):
        assert self._call("42") == [42]

    def test_multiple_values(self):
        assert self._call("1,2,3") == [1, 2, 3]

    def test_whitespace_around_values(self):
        assert self._call(" 10 , 20 , 30 ") == [10, 20, 30]

    def test_trailing_comma(self):
        assert self._call("5,") == [5]

    def test_non_numeric_skipped(self):
        assert self._call("1,abc,3") == [1, 3]

    def test_mixed_empty_tokens(self):
        assert self._call(",1,,2,") == [1, 2]


class TestParseCsvStrings:
    """Tests for _parse_csv_strings."""

    def _call(self, raw):
        from app.api.routes import _parse_csv_strings
        return _parse_csv_strings(raw)

    def test_empty_string(self):
        assert self._call("") == []

    def test_none(self):
        assert self._call(None) == []

    def test_comma_separated(self):
        assert self._call("Migros,Coop") == ["Migros", "Coop"]

    def test_semicolon_separated(self):
        assert self._call("Migros;Coop") == ["Migros", "Coop"]

    def test_mixed_separators(self):
        assert self._call("Migros;Coop,Denner") == ["Migros", "Coop", "Denner"]

    def test_whitespace_stripped(self):
        assert self._call(" Migros , Coop ") == ["Migros", "Coop"]

    def test_empty_tokens_skipped(self):
        assert self._call(",Migros,,") == ["Migros"]


class TestNormalizeSearchToken:
    """Tests for _normalize_search_token."""

    def _call(self, value):
        from app.api.routes import _normalize_search_token
        return _normalize_search_token(value)

    def test_lowercase_and_strip_special(self):
        assert self._call("Haus-Halt") == "haushalt"

    def test_empty_string(self):
        assert self._call("") == ""

    def test_none(self):
        assert self._call(None) == ""

    def test_alphanumeric_preserved(self):
        assert self._call("abc123") == "abc123"

    def test_spaces_removed(self):
        assert self._call("a b c") == "abc"

    def test_dots_removed(self):
        assert self._call("S.B.B.") == "sbb"


class TestEscapeLike:
    """Tests for _escape_like."""

    def _call(self, value):
        from app.api.routes import _escape_like
        return _escape_like(value)

    def test_no_special_chars(self):
        assert self._call("hello") == "hello"

    def test_percent_escaped(self):
        assert self._call("100%") == r"100\%"

    def test_underscore_escaped(self):
        assert self._call("foo_bar") == r"foo\_bar"

    def test_both_escaped(self):
        assert self._call("50%_off") == r"50\%\_off"

    def test_empty_string(self):
        assert self._call("") == ""


class TestCategoryModelProperties:
    """Tests for Category.path and Category.depth properties."""

    def test_root_category_path(self, app, db):
        from app.models import Category
        cat = Category(name="Wohnen")
        db.session.add(cat)
        db.session.commit()
        assert cat.path == "Wohnen"

    def test_nested_category_path(self, app, db):
        from app.models import Category
        parent = Category(name="Energie")
        db.session.add(parent)
        db.session.flush()
        child = Category(name="Strom", parent_id=parent.id)
        db.session.add(child)
        db.session.commit()
        assert child.path == "Energie/Strom"

    def test_three_levels_deep(self, app, db):
        from app.models import Category
        root = Category(name="Versicherung")
        db.session.add(root)
        db.session.flush()
        mid = Category(name="Kranken", parent_id=root.id)
        db.session.add(mid)
        db.session.flush()
        leaf = Category(name="Zusatz", parent_id=mid.id)
        db.session.add(leaf)
        db.session.commit()
        assert leaf.path == "Versicherung/Kranken/Zusatz"
        assert leaf.depth == 2

    def test_root_depth_zero(self, app, db):
        from app.models import Category
        cat = Category(name="Transport")
        db.session.add(cat)
        db.session.commit()
        assert cat.depth == 0

    def test_child_depth_one(self, app, db):
        from app.models import Category
        parent = Category(name="Lebensmittel")
        db.session.add(parent)
        db.session.flush()
        child = Category(name="Supermarkt", parent_id=parent.id)
        db.session.add(child)
        db.session.commit()
        assert child.depth == 1
