"""Dashboard routes and main views."""

import subprocess
from datetime import date
from pathlib import Path

from flask import render_template, jsonify, abort, current_app, request

from sqlalchemy import desc, extract, func, nulls_last, select

from app import db
from app.main import bp
from app.models import Account, Category, Invoice, Transaction, TransactionLine


def _category_path(cat: Category) -> str:
    """Build a display path like `Energie/Gas` from the hierarchy."""
    names: list[str] = []
    cursor: Category | None = cat
    while cursor is not None:
        names.append(cursor.name)
        cursor = cursor.parent
    return "/".join(reversed(names))


@bp.route("/")
def dashboard():
    """Render the finance dashboard with optional transaction and invoice filters."""
    account_id_str = request.args.get("account_id", "").strip()
    tx_category_id_str = request.args.get("tx_category_id", "").strip()
    tx_year = request.args.get("tx_year", "").strip()
    tx_month = request.args.get("tx_month", "").strip()

    selected_account_id: int | None = None
    if account_id_str:
        try:
            selected_account_id = int(account_id_str)
        except ValueError:
            account_id_str = ""

    selected_tx_category_id: int | None = None
    if tx_category_id_str:
        try:
            selected_tx_category_id = int(tx_category_id_str)
        except ValueError:
            tx_category_id_str = ""

    inv_status = request.args.get("inv_status", "pending").strip()
    inv_category_id_str = request.args.get("inv_category_id", "").strip()
    inv_year = request.args.get("inv_year", "").strip()
    inv_month = request.args.get("inv_month", "").strip()

    selected_inv_category_id: int | None = None
    if inv_category_id_str:
        try:
            selected_inv_category_id = int(inv_category_id_str)
        except ValueError:
            inv_category_id_str = ""

    accounts = Account.query.order_by(Account.name).all()

    q = Transaction.query.join(Account).order_by(desc(Transaction.date))

    if selected_account_id:
        q = q.filter(Transaction.account_id == selected_account_id)
    if selected_tx_category_id:
        q = q.filter(Transaction.category_id == selected_tx_category_id)
    if tx_year:
        try:
            q = q.filter(extract("year", Transaction.date) == int(tx_year))
        except ValueError:
            tx_year = ""
    if tx_month:
        try:
            q = q.filter(extract("month", Transaction.date) == int(tx_month))
        except ValueError:
            tx_month = ""

    transactions = q.all()
    months: dict = {}
    for tx in transactions:
        key = tx.date.strftime("%Y-%m")
        months.setdefault(key, {"income": 0.0, "expense": 0.0, "transactions": []})
        months[key][tx.type] += tx.amount
        months[key]["transactions"].append(tx)

    tx_years_stmt = (
        select(func.strftime("%Y", Transaction.date).label("yr"))
        .select_from(Transaction)
        .join(Account)
        .distinct()
        .order_by(func.strftime("%Y", Transaction.date).desc())
    )
    if selected_account_id:
        tx_years_stmt = tx_years_stmt.where(Transaction.account_id == selected_account_id)
    available_tx_years: list[str] = db.session.execute(tx_years_stmt).scalars().all()

    inv_q = Invoice.query.order_by(nulls_last(Invoice.due_date))

    if inv_status in Invoice.STATUSES:
        inv_q = inv_q.filter(Invoice.status == inv_status)
    if selected_inv_category_id:
        inv_q = inv_q.filter(Invoice.category_id == selected_inv_category_id)

    if inv_year:
        try:
            y = int(inv_year)
            from sqlalchemy import or_, and_
            inv_q = inv_q.filter(
                or_(
                    Invoice.source_year == y,
                    and_(Invoice.source_year.is_(None), extract("year", Invoice.due_date) == y),
                )
            )
        except ValueError:
            inv_year = ""
    if inv_month:
        try:
            inv_q = inv_q.filter(extract("month", Invoice.due_date) == int(inv_month))
        except ValueError:
            inv_month = ""

    invoices = inv_q.all()

    from sqlalchemy import union, literal_column, cast, String
    years_from_source = select(cast(Invoice.source_year, String).label("yr")).where(Invoice.source_year.is_not(None))
    years_from_due    = select(func.strftime("%Y", Invoice.due_date).label("yr")).where(
        Invoice.due_date.is_not(None), Invoice.source_year.is_(None)
    )
    all_years_stmt = union(years_from_source, years_from_due).order_by("yr")
    raw_years: list[str] = db.session.execute(all_years_stmt).scalars().all()
    available_inv_years  = sorted(set(raw_years), reverse=True)

    saldo_q = Transaction.query.filter(Transaction.saldo.is_not(None)).order_by(desc(Transaction.date))
    if selected_account_id:
        saldo_q = saldo_q.filter(Transaction.account_id == selected_account_id)
    latest_tx = saldo_q.first()
    latest_saldo = latest_tx.saldo if latest_tx else None

    total_pending = sum(i.amount or 0.0 for i in invoices)
    categories = Category.query.order_by(Category.name).all()
    category_options = [
        {"id": c.id, "name": c.name, "path": _category_path(c)}
        for c in categories
    ]
    category_options.sort(key=lambda c: c["path"].lower())

    sorted_months = sorted(months.items())
    chart_data = {
        "labels":  [k for k, _ in sorted_months],
        "income":  [round(v["income"],  2) for _, v in sorted_months],
        "expense": [round(v["expense"], 2) for _, v in sorted_months],
    }

    return render_template(
        "main/dashboard.html",
        months=dict(sorted(months.items(), reverse=True)),
        invoices=invoices,
        latest_saldo=latest_saldo,
        total_pending=total_pending,
        categories=categories,
        category_options=category_options,
        today=date.today(),
        chart_data=chart_data,
        accounts=accounts,
        selected_account_id=selected_account_id,
        selected_tx_category_id=selected_tx_category_id,
        tx_year=tx_year,
        tx_month=tx_month,
        available_tx_years=available_tx_years,
        inv_status=inv_status,
        selected_inv_category_id=selected_inv_category_id,
        inv_year=inv_year,
        inv_month=inv_month,
        available_inv_years=available_inv_years,
    )


@bp.route("/import", methods=["POST"])
def trigger_import():
    """Run the PDF import and return import statistics."""
    from app.importers import run_full_import
    stats = run_full_import()
    return jsonify({"ok": True, "stats": stats})


@bp.route("/search")
def search_page():
    """Render advanced transaction search and filter view."""
    accounts = Account.query.order_by(Account.name).all()
    categories = Category.query.order_by(Category.name).all()
    category_options = [
        {"id": c.id, "name": c.name, "path": _category_path(c)}
        for c in categories
    ]
    category_options.sort(key=lambda c: c["path"].lower())

    years = [
        y for y in db.session.query(func.strftime("%Y", Transaction.date)).distinct().all()
        if y[0]
    ]
    available_years = sorted([y[0] for y in years], reverse=True)
    available_months = [f"{m:02d}" for m in range(1, 13)]

    description_rows = (
        db.session.query(Transaction.raw_description)
        .distinct()
        .order_by(Transaction.raw_description.asc())
        .limit(300)
        .all()
    )
    recipient_rows = (
        db.session.query(TransactionLine.recipient)
        .distinct()
        .order_by(TransactionLine.recipient.asc())
        .limit(300)
        .all()
    )

    return render_template(
        "main/search.html",
        accounts=accounts,
        category_options=category_options,
        available_years=available_years,
        available_months=available_months,
        raw_description_options=[row[0] for row in description_rows if row[0]],
        recipient_options=[row[0] for row in recipient_rows if row[0]],
    )


@bp.route("/open-pdf/<path:filename>")
def open_pdf(filename: str):
    """Open a PDF in the operating system's default viewer."""
    safe_name = Path(filename).name

    search_dirs: list[Path] = [
        current_app.config["PENDENT_DIR"],
        current_app.config["BEZAHLT_DIR"],
        current_app.config["BEWEGUNGEN_DIR"],
    ]

    target: Path | None = None
    for d in search_dirs:
        if not d.exists():
            continue
        candidate = d / safe_name
        if candidate.is_file():
            target = candidate
            break
        matches = list(d.rglob(safe_name))
        if matches:
            target = matches[0]
            break

    if target is None:
        abort(404, f"PDF not found: {safe_name}")

    try:
        subprocess.run(["open", str(target)], check=True)
    except Exception as e:
        abort(500, f"Could not open PDF: {e}")

    return jsonify({"ok": True, "opened": safe_name})
