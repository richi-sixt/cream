from flask import Blueprint

bp = Blueprint("api", __name__)

from app.api import routes as _routes  # noqa: F401, E402 — registriert Route-Handler
