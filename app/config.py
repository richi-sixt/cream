"""Configuration classes for different environments."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent

DATA_ROOT = BASE_DIR.parent

load_dotenv(BASE_DIR / ".env.example")
load_dotenv(BASE_DIR / ".env.local", override=True)


def _env_path(name: str, default: Path) -> Path:
    """Return a path from the environment or fall back to the given default."""
    path = Path(os.environ.get(name, str(default))).expanduser()
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    return path


def _env_json_dict(name: str) -> dict[str, str]:
    """Parse a JSON object from an environment variable."""
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return {}

    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}

    if not isinstance(parsed, dict):
        return {}

    return {str(key): str(value) for key, value in parsed.items()}


class Config:
    """Shared base configuration."""

    SECRET_KEY = os.environ.get("SECRET_KEY") or "cream-dev-key-change-in-prod"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    PENDENT_DIR = _env_path("PENDENT_DIR", DATA_ROOT / "01-Rechnungen-Pendent")
    BEZAHLT_DIR = _env_path("BEZAHLT_DIR", DATA_ROOT / "02-Rechnungen-Bezahlt")
    BEWEGUNGEN_DIR = _env_path("BEWEGUNGEN_DIR", DATA_ROOT / "03-Bewegungen")

    # Optional per-IBAN display names:
    ACCOUNT_NAME_OVERRIDES: dict[str, str] = _env_json_dict("ACCOUNT_NAME_OVERRIDES")

    # Serve PDFs inline via HTTP instead of opening in OS viewer:
    SERVE_PDF_INLINE: bool = os.environ.get("SERVE_PDF_INLINE", "").lower() in ("true", "1", "yes")

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR / 'data' / 'cream.db'}"


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL")
        or f"sqlite:///{BASE_DIR / 'data' / 'cream.db'}"
    )


config = {
    "development": DevelopmentConfig,
    "testing":     TestingConfig,
    "production":  ProductionConfig,
    "default":     DevelopmentConfig,
}
