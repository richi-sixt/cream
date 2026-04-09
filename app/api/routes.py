"""REST API routes for manual corrections."""

from datetime import date

from flask import jsonify, request, abort
from sqlalchemy import and_, case, desc, exists, extract, func, nulls_last, or_
from sqlalchemy.orm import Query

from app.api import bp
from app.models import (
    Account,
    Category,
    Invoice,
    InvoiceTitleRule,
    Transaction,
    TransactionLine,
)
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
    category_id = request.args.get("category_id", "").strip()
    iban = request.args.get("iban", "").strip().replace(" ", "").upper()

    q = Transaction.query.join(Account).order_by(desc(Transaction.date))

    if account_id:
        try:
            q = q.filter(Transaction.account_id == int(account_id))
        except ValueError:
            pass
    elif iban:
        q = q.filter(Account.iban == iban)

    if category_id:
        try:
            q = q.filter(Transaction.category_id == int(category_id))
        except ValueError:
            pass

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


@bp.route("/transactions/search", methods=["GET"])
def search_transactions():
    """Advanced transaction search with grouping and aggregate totals."""
    params = _parse_tx_search_params(request.args)
    group_by = params["group_by"]

    totals_query = (
        db.session.query(
            func.coalesce(
                func.sum(case((Transaction.type == "income", Transaction.amount), else_=0.0)),
                0.0,
            ).label("income"),
            func.coalesce(
                func.sum(case((Transaction.type == "expense", Transaction.amount), else_=0.0)),
                0.0,
            ).label("expense"),
            func.count(Transaction.id).label("count"),
        )
        .select_from(Transaction)
        .join(Account, Account.id == Transaction.account_id)
    )
    totals_query = _apply_transaction_search_filters(totals_query, params)
    income_total, expense_total, tx_count = totals_query.one()
    income_total = float(income_total or 0.0)
    expense_total = float(expense_total or 0.0)

    response: dict = {
        "totals": {
            "positive": round(income_total, 2),
            "negative": round(expense_total, 2),
            "sum": round(income_total - expense_total, 2),
            "count": int(tx_count or 0),
        },
        "group_by": group_by or "",
    }

    if not group_by:
        tx_query = (
            Transaction.query.join(Account, Account.id == Transaction.account_id)
            .order_by(desc(Transaction.date), desc(Transaction.id))
        )
        tx_query = _apply_transaction_search_filters(tx_query, params)
        rows = tx_query.limit(1000).all()
        response["rows"] = [tx.to_dict() for tx in rows]
        return jsonify(response)

    if group_by == "recipient":
        amount_expr = func.coalesce(TransactionLine.amount, Transaction.amount)
        grouped_query = (
            db.session.query(
                func.coalesce(TransactionLine.recipient, "(No recipient)").label("group_value"),
                func.coalesce(
                    func.sum(case((Transaction.type == "income", amount_expr), else_=0.0)),
                    0.0,
                ).label("income"),
                func.coalesce(
                    func.sum(case((Transaction.type == "expense", amount_expr), else_=0.0)),
                    0.0,
                ).label("expense"),
                func.count().label("row_count"),
            )
            .select_from(Transaction)
            .join(Account, Account.id == Transaction.account_id)
            .outerjoin(TransactionLine, TransactionLine.transaction_id == Transaction.id)
        )
        grouped_query = _apply_transaction_search_filters(grouped_query, params)
        grouped_query = grouped_query.group_by(func.coalesce(TransactionLine.recipient, "(No recipient)"))
    else:
        group_map = {
            "account": Account.name,
            "raw_description": Transaction.raw_description,
            "category": func.coalesce(Category.name, "Uncategorized"),
            "year": func.strftime("%Y", Transaction.date),
            "month": func.strftime("%m", Transaction.date),
        }
        group_expr = group_map.get(group_by)
        if group_expr is None:
            abort(400, "Invalid group_by value")

        grouped_query = (
            db.session.query(
                group_expr.label("group_value"),
                func.coalesce(
                    func.sum(case((Transaction.type == "income", Transaction.amount), else_=0.0)),
                    0.0,
                ).label("income"),
                func.coalesce(
                    func.sum(case((Transaction.type == "expense", Transaction.amount), else_=0.0)),
                    0.0,
                ).label("expense"),
                func.count(Transaction.id).label("row_count"),
            )
            .select_from(Transaction)
            .join(Account, Account.id == Transaction.account_id)
            .outerjoin(Category, Category.id == Transaction.category_id)
        )
        grouped_query = _apply_transaction_search_filters(grouped_query, params)
        grouped_query = grouped_query.group_by(group_expr)

    grouped_rows = []
    for r in grouped_query.all():
        income = float(r.income or 0.0)
        expense = float(r.expense or 0.0)
        grouped_rows.append(
            {
                "group": r.group_value or "—",
                "positive": round(income, 2),
                "negative": round(expense, 2),
                "sum": round(income - expense, 2),
                "count": int(r.row_count or 0),
            }
        )

    grouped_rows.sort(key=lambda row: abs(row["sum"]), reverse=True)
    response["rows"] = grouped_rows
    return jsonify(response)


@bp.route("/invoices/<int:inv_id>", methods=["PATCH"])
def update_invoice(inv_id: int):
    """Update editable invoice fields."""
    inv = db.get_or_404(Invoice, inv_id)
    data: dict = request.get_json(silent=True) or {}

    allowed = ("title", "amount", "status", "due_date", "paid_date", "source_year", "category_id", "notes")
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

        if field == "source_year":
            if val in ("", None):
                val = None
            else:
                try:
                    val = int(val)
                except (TypeError, ValueError):
                    abort(400, f"Invalid source_year: {val}")
                if val < 2000 or val > 2100:
                    abort(400, f"Invalid source_year: {val}")

        setattr(inv, field, val)

    db.session.commit()
    return jsonify(inv.to_dict())


@bp.route("/invoices/<int:inv_id>", methods=["DELETE"])
def delete_invoice(inv_id: int):
    """Delete a single invoice so it can be reimported from the source PDF."""
    inv = db.get_or_404(Invoice, inv_id)
    db.session.delete(inv)
    db.session.commit()
    return jsonify({"ok": True, "deleted_id": inv_id})


@bp.route("/invoices/<int:inv_id>/remember-title", methods=["POST"])
def remember_invoice_title(inv_id: int):
    """Remember the current invoice title for similar future imports."""
    inv = db.get_or_404(Invoice, inv_id)
    data: dict = request.get_json(silent=True) or {}

    title = (data.get("title") or inv.title or inv.display_title or "").strip()
    if not title:
        abort(400, "A title is required")
    if not inv.raw_issuer:
        abort(400, "This invoice has no issuer to match similar invoices")

    rule = InvoiceTitleRule.query.filter_by(raw_issuer=inv.raw_issuer).first()
    created = False
    if rule is None:
        rule = InvoiceTitleRule(raw_issuer=inv.raw_issuer, title=title)
        db.session.add(rule)
        created = True
    else:
        rule.title = title

    if inv.category_id is not None:
        rule.category_id = inv.category_id

    if not inv.title:
        inv.title = title

    db.session.commit()
    return jsonify({
        "ok": True,
        "created": created,
        "rule": rule.to_dict(),
        "invoice": inv.to_dict(),
    })


@bp.route("/invoices", methods=["GET"])
def list_invoices():
    """List invoices, optionally filtered by status and year."""
    status = request.args.get("status", "").strip()
    category_id = request.args.get("category_id", "").strip()
    year   = request.args.get("year", "").strip()

    q = Invoice.query.order_by(nulls_last(Invoice.due_date))

    if status:
        q = q.filter(Invoice.status == status)

    if category_id:
        try:
            q = q.filter(Invoice.category_id == int(category_id))
        except ValueError:
            pass

    if year:
        try:
            q = q.filter(extract("year", Invoice.due_date) == int(year))
        except ValueError:
            pass

    return jsonify([i.to_dict() for i in q.all()])


@bp.route("/categories", methods=["GET"])
def list_categories():
    cats = Category.query.order_by(Category.name).all()
    return jsonify([_category_payload(c) for c in cats])


@bp.route("/categories", methods=["POST"])
def create_category():
    data: dict = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        abort(400, "name is required")

    parent_id = data.get("parent_id")
    if parent_id is not None:
        try:
            parent_id = int(parent_id)
        except (TypeError, ValueError):
            abort(400, "parent_id must be an integer")
        if db.session.get(Category, parent_id) is None:
            abort(400, "parent category not found")

    cat = Category(
        name      = name,
        color     = data.get("color"),
        icon      = data.get("icon"),
        parent_id = parent_id,
    )
    db.session.add(cat)
    db.session.commit()
    return jsonify(_category_payload(cat)), 201


@bp.route("/categories/<int:cat_id>", methods=["PATCH"])
def update_category(cat_id: int):
    """Update editable category fields."""
    cat = db.get_or_404(Category, cat_id)
    data: dict = request.get_json(silent=True) or {}

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            abort(400, "name is required")
        cat.name = name

    if "color" in data:
        cat.color = data.get("color") or None

    if "icon" in data:
        cat.icon = data.get("icon") or None

    if "parent_id" in data:
        parent_id_raw = data.get("parent_id")
        if parent_id_raw in ("", None):
            cat.parent_id = None
        else:
            try:
                parent_id = int(parent_id_raw)
            except (TypeError, ValueError):
                abort(400, "parent_id must be an integer or null")

            _validate_category_parent(cat, parent_id)
            cat.parent_id = parent_id

    db.session.commit()
    return jsonify(_category_payload(cat))


@bp.route("/categories/<int:cat_id>", methods=["DELETE"])
def delete_category(cat_id: int):
    """Delete an unused category."""
    cat = db.get_or_404(Category, cat_id)
    payload = _category_payload(cat)
    if payload["usage_total"] > 0 or payload["child_count"] > 0:
        abort(
            400,
            "Category is still in use. Remove references first.",
        )

    db.session.delete(cat)
    db.session.commit()
    return jsonify({"ok": True, "deleted_id": cat_id})


def _category_payload(cat: Category) -> dict:
    """Return category JSON with usage counts for safe UI management."""
    tx_count = (
        db.session.query(func.count(Transaction.id))
        .filter(Transaction.category_id == cat.id)
        .scalar()
        or 0
    )
    inv_count = (
        db.session.query(func.count(Invoice.id))
        .filter(Invoice.category_id == cat.id)
        .scalar()
        or 0
    )
    rule_count = (
        db.session.query(func.count(InvoiceTitleRule.id))
        .filter(InvoiceTitleRule.category_id == cat.id)
        .scalar()
        or 0
    )
    child_count = (
        db.session.query(func.count(Category.id))
        .filter(Category.parent_id == cat.id)
        .scalar()
        or 0
    )

    data = cat.to_dict()
    data["path"] = _category_path(cat)
    data["depth"] = _category_depth(cat)
    data["tx_count"] = int(tx_count)
    data["invoice_count"] = int(inv_count)
    data["rule_count"] = int(rule_count)
    data["child_count"] = int(child_count)
    data["usage_total"] = int(tx_count + inv_count + rule_count)
    data["deletable"] = (data["usage_total"] == 0 and data["child_count"] == 0)
    return data


def _validate_category_parent(cat: Category, parent_id: int) -> None:
    """Ensure category parent changes stay inside a valid tree."""
    if parent_id == cat.id:
        abort(400, "category cannot be its own parent")

    parent = db.session.get(Category, parent_id)
    if parent is None:
        abort(400, "parent category not found")

    cursor = parent
    while cursor is not None:
        if cursor.id == cat.id:
            abort(400, "cyclic category hierarchy is not allowed")
        cursor = cursor.parent


def _category_path(cat: Category) -> str:
    """Return slash-separated category path from root to node."""
    names: list[str] = []
    cursor: Category | None = cat
    while cursor is not None:
        names.append(cursor.name)
        cursor = cursor.parent
    return "/".join(reversed(names))


def _category_depth(cat: Category) -> int:
    """Return zero-based hierarchy depth."""
    depth = 0
    cursor = cat.parent
    while cursor is not None:
        depth += 1
        cursor = cursor.parent
    return depth


def _parse_csv_ints(raw: str) -> list[int]:
    values: list[int] = []
    for part in (raw or "").split(","):
        token = part.strip()
        if not token:
            continue
        try:
            values.append(int(token))
        except ValueError:
            continue
    return values


def _parse_csv_strings(raw: str) -> list[str]:
    values: list[str] = []
    for part in (raw or "").replace(";", ",").split(","):
        token = part.strip()
        if token:
            values.append(token)
    return values


def _normalize_search_token(value: str) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def _normalized_expr(column_expr):
    normalized = func.lower(column_expr)
    for char in (" ", ".", ",", "-", "_", "/", "\\", "'", '"', "&", "(", ")", ":", ";"):
        normalized = func.replace(normalized, char, "")
    return normalized


def _parse_tx_search_params(args) -> dict:
    return {
        "account_ids": _parse_csv_ints(args.get("account_ids", "")),
        "category_ids": _parse_csv_ints(args.get("category_ids", "")),
        "years": _parse_csv_ints(args.get("years", "")),
        "months": _parse_csv_ints(args.get("months", "")),
        "raw_descriptions": _parse_csv_strings(args.get("raw_descriptions", "")),
        "recipients": _parse_csv_strings(args.get("recipients", "")),
        "group_by": (args.get("group_by", "") or "").strip(),
    }


def _apply_transaction_search_filters(query: Query, params: dict) -> Query:
    account_ids = params.get("account_ids") or []
    category_ids = params.get("category_ids") or []
    years = [y for y in (params.get("years") or []) if 1900 <= y <= 2200]
    months = [m for m in (params.get("months") or []) if 1 <= m <= 12]
    raw_descriptions = params.get("raw_descriptions") or []
    recipients = params.get("recipients") or []

    if account_ids:
        query = query.filter(Transaction.account_id.in_(account_ids))
    if category_ids:
        query = query.filter(Transaction.category_id.in_(category_ids))
    if years:
        query = query.filter(extract("year", Transaction.date).in_(years))
    if months:
        query = query.filter(extract("month", Transaction.date).in_(months))

    if raw_descriptions:
        normalized_tokens = [_normalize_search_token(token) for token in raw_descriptions]
        normalized_tokens = [token for token in normalized_tokens if token]
        query = query.filter(
            or_(
                *[
                    func.lower(Transaction.raw_description).like(f"%{token.lower()}%")
                    for token in raw_descriptions
                ],
                *[
                    _normalized_expr(Transaction.raw_description).like(f"%{token}%")
                    for token in normalized_tokens
                ]
            )
        )

    if recipients:
        normalized_tokens = [_normalize_search_token(token) for token in recipients]
        normalized_tokens = [token for token in normalized_tokens if token]
        recipient_filter = exists().where(
            and_(
                TransactionLine.transaction_id == Transaction.id,
                or_(
                    *[
                        func.lower(TransactionLine.recipient).like(f"%{token.lower()}%")
                        for token in recipients
                    ],
                    *[
                        _normalized_expr(TransactionLine.recipient).like(f"%{token}%")
                        for token in normalized_tokens
                    ],
                ),
            )
        )
        query = query.filter(recipient_filter)

    return query
