"""Entry point for the cream Flask application."""

import os

from app import create_app, db

app = create_app(os.environ.get("FLASK_ENV", "development"))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(
        host="127.0.0.1",
        port=5001,
        debug=True,
    )
