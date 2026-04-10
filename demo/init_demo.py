"""
Initialize the demo environment: seed database + generate PDFs.

Usage:
    python demo/init_demo.py
"""

from pathlib import Path

from app import create_app, db
from demo.generate_demo_data import seed_demo


def init():
    app = create_app("production")

    demo_base = Path("demo/example")
    app.config.update(
        PENDENT_DIR=demo_base / "01-Rechnungen-Pendent",
        BEZAHLT_DIR=demo_base / "02-Rechnungen-Bezahlt",
        BEWEGUNGEN_DIR=demo_base / "03-Bewegungen",
        SERVE_PDF_INLINE=True,
    )

    with app.app_context():
        db.create_all()
        seed_demo()

    # Generate PDFs (optional, requires fpdf2)
    try:
        from demo.generate_demo_pdfs import generate_all
        generate_all(demo_base)
    except ImportError:
        print("Skipping PDF generation (fpdf2 not installed)")

    print("Demo initialization complete.")


if __name__ == "__main__":
    init()
