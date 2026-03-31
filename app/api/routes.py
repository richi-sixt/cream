"""REST API routes for manual corrections."""

from datetime import date

from flask import jsonify, request, abort
from sqlalchemy import desc, extract, nulls_last

from app.api import bp
from app.models import Account, Category, Invoice, Transaction
from app import db


@bp.route("/transactions/<int:tx_id>", methods=["PATCH"])
def update_transaction(tx_id: int):
    """Update editable transaction fields."""
    tx = db.get_or_404(Transaction, tx_id)
    data: dict = request.get_json(silent=True) or {}

    allowed = ("title", "category_id", "notes")
    for field in allowed:
        if field in data:
            setattr(tx, field, data[field] or None)

    db.session.commit()
    return jsonify(tx.to_dict())


@bp.route("/transactions", methods=["GET"])
def list_transactions():
    """List transactions, optionally filtered by month or account."""
    month = request.args.get("month", "").strip()
    account_id = request.args.get("account_id", "").strip()
    iban = request.args.get("iban", "").strip().replace(" ", "").upper()

    q = Transaction.query.join(Account).order_by(desc(Transaction.date))

    if account_id:
        try:
            q = q.filter(Transaction.account_id == int(account_id))
        except ValueError:
            pass
    elif iban:
        q = q.filter(Account.iban == iban)

    if month:
        try:
            year  = int(month[:4])
            mon   = int(month[5:7])
            q = q.filter(
                extract("year",  Transaction.date) == year,
                extract("month", Transaction.date) == mon,
            )
        except (ValueError, IndexError):
            pass

    txs = q.limit(500).all()
    return jsonify([t.to_dict() for t in txs])


@bp.route("/invoices/<int:inv_id>", methods=["PATCH"])
def update_invoice(inv_id: int):
    """Update editable invoice fields."""
    inv = db.get_or_404(Invoice, inv_id)
    data: dict = request.get_json(silent=True) or {}

    allowed = ("title", "amount", "status", "due_date", "paid_date", "category_id", "notes")
    for field in allowed:
        if field not in data:
            continue
        val = data[field]

        if field in ("due_date", "paid_date"):
            if val:
                try:
                    val = date.fromisoformat(val)
                except ValueError:
                    abort(400, f"Invalid date: {val}")
            else:
                val = None

        if field == "amount":
            if val is not None:
                try:
                    val = float(str(val).replace("'", "").replace(",", ".").replace(" ", ""))
                    if val <= 0:
                        abort(400, "Amount must be positive")
                except ValueError:
                    abort(400, f"Invalid amount: {val}")

        if field == "status" and val not in Invoice.STATUSES:
            abort(400, f"Invalid status: {val}")

        setattr(inv, field, val)

    db.session.commit()
    return jsonify(inv.to_dict())


@bp.route("/invoices", methods=["GET"])
def list_invoices():
    """List invoices, optionally filtered by status and year."""
    status = request.args.get("status", "").strip()
    year   = request.args.get("year", "").strip()

    q = Invoice.query.order_by(nulls_last(Invoice.due_date))

    if status:
        q = q.filter(Invoice.status == status)

    if year:
        try:
            q = q.filter(extract("year", Invoice.due_date) == int(year))
        except ValueError:
            pass

    return jsonify([i.to_dict() for i in q.all()])


@bp.route("/categories", methods=["GET"])
def list_categories():
    cats = Category.query.order_by(Category.name).all()
    return jsonify([c.to_dict() for c in cats])


@bp.route("/categories", methods=["POST"])
def create_category():
    data: dict = request.get_json(silent=True) or {}
    if not data.get("name"):
        abort(400, "name is required")

    cat = Category(
        name      = data["name"],
        color     = data.get("color"),
        icon      = data.get("icon"),
        parent_id = data.get("parent_id"),
    )
    db.session.add(cat)
    db.session.commit()
    return jsonify(cat.to_dict()), 201
