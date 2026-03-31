"""Shared pytest fixtures for cream."""

import pytest

from app import create_app
from app import db as _db


@pytest.fixture()
def app(tmp_path):
    """Create a fresh in-memory Flask app per test."""
    application = create_app("testing")
    application.config.update(
        PENDENT_DIR=tmp_path / "01-Rechnungen-Pendent",
        BEZAHLT_DIR=tmp_path / "02-Rechnungen-Bezahlt",
        BEWEGUNGEN_DIR=tmp_path / "03-Bewegungen",
    )
    application.config["PENDENT_DIR"].mkdir(parents=True, exist_ok=True)
    application.config["BEZAHLT_DIR"].mkdir(parents=True, exist_ok=True)
    application.config["BEWEGUNGEN_DIR"].mkdir(parents=True, exist_ok=True)

    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    """Return a Flask test client."""
    return app.test_client()


@pytest.fixture()
def db(app):
    """Yield the database inside an application context."""
    with app.app_context():
        yield _db
