from flask import Blueprint

bp = Blueprint("main", __name__)

from app.main import routes as _routes  # noqa: F401, E402 — registriert Route-Handler
