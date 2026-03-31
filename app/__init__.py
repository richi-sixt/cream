"""Application factory for cream."""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

from app.config import config

db      = SQLAlchemy()
migrate = Migrate()


def create_app(config_name: str = "default") -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    migrate.init_app(app, db)

    from app import models  # noqa: F401

    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix="/api")

    from datetime import datetime

    @app.template_filter("month_label")
    def month_label(s: str) -> str:
        """Convert `YYYY-MM` into a localized month label."""
        try:
            d = datetime.strptime(s + "-01", "%Y-%m-%d")
            return d.strftime("%B %Y")
        except ValueError:
            return s

    @app.template_global()
    def fmt_chf(val) -> str:
        if val is None:
            return "—"
        return f"CHF {val:,.2f}".replace(",", "'")

    @app.context_processor
    def inject_now():
        return {"now": datetime.now()}

    import click

    @app.cli.command("reparse-lines")
    def reparse_lines_cmd():
        """Backfill detail lines for already imported e-banking transactions."""
        from app.importers.bekb import reparse_transaction_lines
        stats = reparse_transaction_lines()
        click.echo(
            f"Done: {stats['updated']} updated, "
            f"{stats['skipped']} skipped, "
            f"{stats['errors']} errors."
        )

    @app.cli.command("backfill-source-year")
    def backfill_source_year_cmd():
        """Backfill `source_year` for existing invoices from file paths."""
        from app.models import Invoice
        from app.importers.invoices import _extract_source_year
        from pathlib import Path

        updated = 0
        for config_key in ("PENDENT_DIR", "BEZAHLT_DIR"):
            base_dir = app.config[config_key]
            if not base_dir.exists():
                continue
            for pdf in base_dir.rglob("*.pdf"):
                year = _extract_source_year(pdf)
                if not year:
                    continue
                invs = Invoice.query.filter_by(filename=pdf.name, source_year=None).all()
                for inv in invs:
                    inv.source_year = year
                    updated += 1

        db.session.commit()
        click.echo(f"Backfilled source_year for {updated} invoices.")

    @app.cli.command("repair-postfinance-saldi")
    def repair_postfinance_saldi_cmd():
        """Reparse PostFinance PDFs and repair incorrect imported saldi."""
        from app.importers.postfinance import repair_postfinance_saldi

        stats = repair_postfinance_saldi()
        click.echo(
            f"Done: {stats['updated']} updated, "
            f"{stats['unchanged']} unchanged, "
            f"{stats['missing']} missing, "
            f"{stats['errors']} errors."
        )

    @app.cli.command("normalize-postfinance-transactions")
    def normalize_postfinance_transactions_cmd():
        """Split legacy merged PostFinance rows into separate transactions."""
        from app.importers.postfinance import normalize_postfinance_transactions

        stats = normalize_postfinance_transactions()
        click.echo(
            f"Done: {stats['normalized']} normalized, "
            f"{stats['skipped']} skipped, "
            f"{stats['errors']} errors."
        )

    @app.cli.command("preview-postfinance-marked-repairs")
    @click.option(
        "--csv-path",
        "csv_path",
        default="reports/postfinance_marked_orange_unique_targets.csv",
        show_default=True,
        help="CSV exported from the marked PostFinance comparison workbook.",
    )
    def preview_postfinance_marked_repairs_cmd(csv_path: str):
        """Build a dry-run repair plan from the marked PostFinance CSV."""
        from pathlib import Path
        from app.importers.postfinance import preview_marked_postfinance_repairs

        stats = preview_marked_postfinance_repairs(Path(csv_path))
        click.echo(
            f"Done: {stats['targets']} targets, "
            f"{stats['insert_missing']} insert_missing, "
            f"{stats['update_existing']} update_existing, "
            f"{stats['already_matches']} already_matches, "
            f"{stats['already_exists_other_id']} already_exists_other_id, "
            f"{stats['missing_pdf']} missing_pdf, "
            f"{stats['missing_parser_row']} missing_parser_row, "
            f"{stats['errors']} errors."
        )
        click.echo(f"Report: {stats['report_path']}")

    @app.cli.command("apply-postfinance-marked-repairs")
    @click.option(
        "--csv-path",
        "csv_path",
        default="reports/postfinance_marked_orange_unique_targets.csv",
        show_default=True,
        help="CSV exported from the marked PostFinance comparison workbook.",
    )
    def apply_postfinance_marked_repairs_cmd(csv_path: str):
        """Apply the marked PostFinance repairs."""
        from pathlib import Path
        from app.importers.postfinance import apply_marked_postfinance_repairs

        stats = apply_marked_postfinance_repairs(Path(csv_path))
        click.echo(
            f"Done: {stats['targets']} targets, "
            f"{stats['inserted']} inserted, "
            f"{stats['updated']} updated, "
            f"{stats['skipped']} skipped, "
            f"{stats['errors']} errors."
        )

    import os
    db_path = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if "sqlite:///" in db_path and ":memory:" not in db_path:
        db_dir = db_path.replace("sqlite:///", "")
        db_parent = os.path.dirname(db_dir)
        if db_parent:
            os.makedirs(db_parent, exist_ok=True)

    return app
