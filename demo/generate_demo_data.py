"""
Generate realistic-looking but fully fictitious Swiss finance data.

All names, IBANs, amounts, and descriptions are completely made up.
No real personal data is used anywhere in this script.

Usage:
    flask --app run.py shell
    >>> exec(open("demo/generate_demo_data.py").read())

Or via the seed_demo() function from another script.
"""

import random
from datetime import date, timedelta

from app import db
from app.models import (
    Account,
    Category,
    Invoice,
    InvoiceTitleRule,
    Transaction,
    TransactionLine,
)
from app.importers.base import make_hash


def seed_demo():
    """Populate the database with fictitious demo data."""
    _clear_existing()
    categories = _create_categories()
    accounts = _create_accounts()
    _create_transactions(accounts, categories)
    _create_invoices(categories)
    db.session.commit()
    print("Demo data seeded successfully.")


def _clear_existing():
    """Remove all existing data for a clean demo."""
    TransactionLine.query.delete()
    Transaction.query.delete()
    Invoice.query.delete()
    InvoiceTitleRule.query.delete()
    Category.query.delete()
    Account.query.delete()
    db.session.commit()


def _create_categories() -> dict[str, Category]:
    """Create a realistic Swiss household category tree."""
    tree = {
        "Wohnen": ["Miete", "Nebenkosten", "Hausrat"],
        "Lebensmittel": ["Supermarkt", "Restaurant"],
        "Transport": ["ÖV", "Auto", "Velo"],
        "Versicherung": ["Krankenversicherung", "Haftpflicht"],
        "Energie": ["Strom", "Gas"],
        "Kommunikation": ["Telefon", "Internet"],
        "Steuern": [],
        "Gesundheit": ["Arzt", "Apotheke"],
        "Freizeit": ["Sport", "Kultur"],
        "Einkommen": ["Gehalt", "Nebenverdienst"],
    }
    cats: dict[str, Category] = {}
    for parent_name, children in tree.items():
        parent = Category(name=parent_name)
        db.session.add(parent)
        db.session.flush()
        cats[parent_name] = parent
        for child_name in children:
            child = Category(name=child_name, parent_id=parent.id)
            db.session.add(child)
            db.session.flush()
            cats[child_name] = child
    return cats


def _create_accounts() -> list[Account]:
    """Create three fictitious bank accounts."""
    accounts = [
        Account(
            name="Fantasie Privatkonto",
            iban="CH9300762011623852957",
            type="checking",
            currency="CHF",
        ),
        Account(
            name="Beispiel Sparkonto",
            iban="CH4308307000289537320",
            type="savings",
            currency="CHF",
        ),
        Account(
            name="Muster Revolut",
            iban="CH2089144416544565844",
            type="checking",
            currency="CHF",
        ),
    ]
    db.session.add_all(accounts)
    db.session.flush()
    return accounts


# Fully made-up merchants and descriptions
_EXPENSE_TEMPLATES = [
    ("Einkauf Alpenhof Markt AG", "Supermarkt", 45.80, 180.50),
    ("Einkauf Bergkäse Laden", "Supermarkt", 22.30, 95.60),
    ("Einkauf Waldquelle Bio", "Supermarkt", 35.00, 145.00),
    ("Restaurant Sonnenberg", "Restaurant", 32.00, 98.50),
    ("Pizzeria Bellavista", "Restaurant", 18.50, 52.00),
    ("SBB Halbtax-Abo", "ÖV", 185.00, 185.00),
    ("Postauto Bern-Thun", "ÖV", 8.40, 24.60),
    ("Tanken Fantasie Garage", "Auto", 60.00, 110.00),
    ("Veloflick Zweirad GmbH", "Velo", 45.00, 120.00),
    ("Fitnesspark Alpenblick", "Sport", 69.00, 69.00),
    ("Kino Sternenlicht", "Kultur", 16.50, 32.00),
    ("Apotheke Zur Linde", "Apotheke", 12.00, 85.00),
    ("Dr. med. Schneeberg", "Arzt", 150.00, 350.00),
    ("Mondschein Telecom AG", "Telefon", 49.00, 49.00),
    ("Alpennet Internet AG", "Internet", 39.90, 39.90),
]

_INCOME_TEMPLATES = [
    ("Gehalt Musterwerk AG", "Gehalt", 5200.00, 6800.00),
    ("Nebenverdienst Beratung", "Nebenverdienst", 500.00, 1500.00),
]

_RECURRING_EXPENSES = [
    ("Miete Fantasiegasse 12", "Miete", 1450.00),
    ("Nebenkosten Fantasiegasse 12", "Nebenkosten", 180.00),
    ("Alpenenergie Strom AG", "Strom", 85.00),
    ("Gaswerk Mustertal", "Gas", 65.00),
    ("Panorama Versicherung", "Krankenversicherung", 380.00),
    ("Schutzschild Haftpflicht", "Haftpflicht", 28.50),
    ("Hausrat Burgversicherung", "Hausrat", 22.00),
]


def _create_transactions(
    accounts: list[Account], categories: dict[str, Category]
):
    """Generate 6 months of fictitious transactions."""
    main_account = accounts[0]
    savings = accounts[1]
    revolut = accounts[2]

    saldo = 12500.00
    tx_count = 0
    start_date = date(2025, 11, 1)

    for month_offset in range(6):
        month_start = date(
            start_date.year + (start_date.month + month_offset - 1) // 12,
            (start_date.month + month_offset - 1) % 12 + 1,
            1,
        )

        # Monthly salary (1st of month)
        template = random.choice(_INCOME_TEMPLATES)
        desc, cat_name, amt_lo, amt_hi = template
        amount = round(random.uniform(amt_lo, amt_hi), 2)
        saldo += amount
        tx = Transaction(
            account_id=main_account.id,
            date=month_start,
            raw_description=desc,
            amount=amount,
            type="income",
            saldo=round(saldo, 2),
            category_id=categories.get(cat_name, categories.get("Einkommen")).id,
            import_hash=make_hash("demo", main_account.iban, month_start, desc, tx_count),
            pdf_source="demo_kontoauszug.pdf",
        )
        db.session.add(tx)
        tx_count += 1

        # Recurring expenses (1st-5th of month)
        for rec_desc, rec_cat, rec_amount in _RECURRING_EXPENSES:
            day = random.randint(1, 5)
            tx_date = month_start.replace(day=min(day, 28))
            saldo -= rec_amount
            tx = Transaction(
                account_id=main_account.id,
                date=tx_date,
                raw_description=rec_desc,
                amount=rec_amount,
                type="expense",
                saldo=round(saldo, 2),
                category_id=categories.get(rec_cat, categories.get("Wohnen")).id,
                import_hash=make_hash("demo", main_account.iban, tx_date, rec_desc, tx_count),
                pdf_source="demo_kontoauszug.pdf",
            )
            db.session.add(tx)
            tx_count += 1

        # Variable expenses (spread throughout month)
        num_expenses = random.randint(8, 15)
        for _ in range(num_expenses):
            template = random.choice(_EXPENSE_TEMPLATES)
            desc, cat_name, amt_lo, amt_hi = template
            amount = round(random.uniform(amt_lo, amt_hi), 2)
            day = random.randint(1, 28)
            tx_date = month_start.replace(day=day)
            saldo -= amount

            acct = random.choices(
                [main_account, revolut], weights=[0.7, 0.3]
            )[0]

            tx = Transaction(
                account_id=acct.id,
                date=tx_date,
                raw_description=desc,
                amount=amount,
                type="expense",
                saldo=round(saldo, 2) if acct == main_account else None,
                category_id=categories.get(cat_name).id,
                import_hash=make_hash("demo", acct.iban, tx_date, desc, tx_count),
                pdf_source="demo_kontoauszug.pdf",
            )
            db.session.add(tx)
            tx_count += 1

        # One bundled e-banking order per month
        ebank_date = month_start.replace(day=random.randint(10, 20))
        ebank_total = 0.0
        lines_data = [
            ("Stadtwerke Fantasieberg", round(random.uniform(80, 150), 2), "CH1234500000012345678"),
            ("Fantasie Telecom SA", round(random.uniform(30, 80), 2), "CH9876500000098765432"),
            ("Muster Haushaltsversicherung", round(random.uniform(40, 90), 2), "CH5555500000055555555"),
        ]
        for _, amt, _ in lines_data:
            ebank_total += amt
        ebank_total = round(ebank_total, 2)
        saldo -= ebank_total

        ebank_tx = Transaction(
            account_id=main_account.id,
            date=ebank_date,
            raw_description="E-Banking-Auftrag Sammelzahlung",
            amount=ebank_total,
            type="expense",
            saldo=round(saldo, 2),
            import_hash=make_hash("demo", main_account.iban, ebank_date, "ebank", tx_count),
            pdf_source="demo_kontoauszug.pdf",
        )
        db.session.add(ebank_tx)
        db.session.flush()
        tx_count += 1

        for pos, (recipient, amt, iban) in enumerate(lines_data, 1):
            line = TransactionLine(
                transaction_id=ebank_tx.id,
                position=pos,
                recipient=recipient,
                amount=amt,
                iban=iban,
            )
            db.session.add(line)

        # Savings interest (quarterly)
        if month_offset % 3 == 2:
            interest = round(random.uniform(5, 25), 2)
            tx = Transaction(
                account_id=savings.id,
                date=month_start.replace(day=28),
                raw_description="Zinsgutschrift",
                amount=interest,
                type="income",
                saldo=round(8500 + interest, 2),
                category_id=categories.get("Einkommen").id,
                import_hash=make_hash("demo", savings.iban, month_start, "zins", tx_count),
                pdf_source="demo_kontoauszug.pdf",
            )
            db.session.add(tx)
            tx_count += 1


def _create_invoices(categories: dict[str, Category]):
    """Generate fictitious pending and paid invoices."""
    today = date.today()

    pending_invoices = [
        {
            "filename": "2026-04-rechnung-alpenenergie.pdf",
            "raw_issuer": "Alpenenergie Strom AG",
            "title": "Stromrechnung Q1 2026",
            "amount": 245.80,
            "due_date": today + timedelta(days=12),
            "status": "pending",
            "category": "Strom",
            "source_year": 2026,
        },
        {
            "filename": "2026-04-rechnung-panorama.pdf",
            "raw_issuer": "Panorama Versicherung AG",
            "title": "Krankenversicherung April",
            "amount": 380.00,
            "due_date": today + timedelta(days=5),
            "status": "pending",
            "category": "Krankenversicherung",
            "source_year": 2026,
        },
        {
            "filename": "2026-04-rechnung-fantasie-steueramt.pdf",
            "raw_issuer": "Steueramt Fantasieberg",
            "title": "Gemeindesteuer 2025",
            "amount": 1870.50,
            "due_date": today + timedelta(days=25),
            "status": "pending",
            "category": "Steuern",
            "source_year": 2026,
        },
        {
            "filename": "2026-04-rechnung-gaswerk.pdf",
            "raw_issuer": "Gaswerk Mustertal AG",
            "title": "Gasrechnung Heizperiode",
            "amount": 520.00,
            "due_date": today - timedelta(days=3),
            "status": "pending",
            "category": "Gas",
            "source_year": 2026,
        },
        {
            "filename": "2026-04-rechnung-zahnarzt.pdf",
            "raw_issuer": "Zahnklinik Alpenpanorama",
            "title": "Zahnkontrolle",
            "amount": 185.00,
            "due_date": today + timedelta(days=18),
            "status": "pending",
            "category": "Arzt",
            "source_year": 2026,
        },
    ]

    paid_invoices = [
        {
            "filename": "2026-03-rechnung-miete.pdf",
            "raw_issuer": "Immobilien Fantasiegasse GmbH",
            "title": "Miete März 2026",
            "amount": 1450.00,
            "due_date": date(2026, 3, 1),
            "paid_date": date(2026, 2, 28),
            "status": "paid",
            "category": "Miete",
            "source_year": 2026,
        },
        {
            "filename": "2026-03-rechnung-telecom.pdf",
            "raw_issuer": "Mondschein Telecom AG",
            "title": "Mobilabo März",
            "amount": 49.00,
            "due_date": date(2026, 3, 15),
            "paid_date": date(2026, 3, 10),
            "status": "paid",
            "category": "Telefon",
            "source_year": 2026,
        },
        {
            "filename": "2026-02-rechnung-internet.pdf",
            "raw_issuer": "Alpennet Internet AG",
            "title": "Internet Februar",
            "amount": 39.90,
            "due_date": date(2026, 2, 20),
            "paid_date": date(2026, 2, 18),
            "status": "paid",
            "category": "Internet",
            "source_year": 2026,
        },
        {
            "filename": "2026-02-rechnung-haftpflicht.pdf",
            "raw_issuer": "Schutzschild Versicherung AG",
            "title": "Haftpflicht Jahresprämie",
            "amount": 342.00,
            "due_date": date(2026, 2, 1),
            "paid_date": date(2026, 1, 29),
            "status": "paid",
            "category": "Haftpflicht",
            "source_year": 2026,
        },
        {
            "filename": "2026-01-rechnung-fitness.pdf",
            "raw_issuer": "Fitnesspark Alpenblick",
            "title": "Jahresabo Fitness",
            "amount": 828.00,
            "due_date": date(2026, 1, 15),
            "paid_date": date(2026, 1, 12),
            "status": "paid",
            "category": "Sport",
            "source_year": 2026,
        },
    ]

    all_invoices = pending_invoices + paid_invoices
    for idx, inv_data in enumerate(all_invoices):
        cat = categories.get(inv_data.get("category"))
        inv = Invoice(
            filename=inv_data["filename"],
            page_index=0,
            raw_issuer=inv_data.get("raw_issuer"),
            title=inv_data.get("title"),
            amount=inv_data.get("amount"),
            due_date=inv_data.get("due_date"),
            paid_date=inv_data.get("paid_date"),
            source_year=inv_data.get("source_year"),
            status=inv_data["status"],
            category_id=cat.id if cat else None,
            import_hash=make_hash("demo_inv", inv_data["filename"], idx),
        )
        db.session.add(inv)

    # Create some title rules for the demo
    for inv_data in all_invoices[:5]:
        if inv_data.get("raw_issuer") and inv_data.get("title"):
            cat = categories.get(inv_data.get("category"))
            rule = InvoiceTitleRule(
                raw_issuer=inv_data["raw_issuer"],
                title=inv_data["title"],
                category_id=cat.id if cat else None,
            )
            db.session.add(rule)


if __name__ == "__main__":
    from app import create_app
    app = create_app("development")
    with app.app_context():
        seed_demo()
