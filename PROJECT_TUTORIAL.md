# C.R.E.A.M. — Project Tutorial

> **C**ash **R**ules **E**verything **A**round **M**e — a personal
> finance management app for Swiss bank accounts and invoices,
> built with Flask.

---

## Table of Contents

1. [What is this project?](#1-what-is-this-project)
2. [Tech stack at a glance](#2-tech-stack-at-a-glance)
3. [Project structure](#3-project-structure)
4. [How Flask works here](#4-how-flask-works-here)
5. [Data models](#5-data-models)
6. [Shared importer utilities](#6-shared-importer-utilities)
7. [BEKB bank importer](#7-bekb-bank-importer)
8. [PostFinance importer](#8-postfinance-importer)
9. [Revolut importer](#9-revolut-importer)
10. [Invoice importer](#10-invoice-importer)
11. [REST API routes](#11-rest-api-routes)
12. [The dashboard UI](#12-the-dashboard-ui)
13. [CLI commands](#13-cli-commands)
14. [Testing](#14-testing)
15. [How to replicate this project from scratch](#15-how-to-replicate-this-project-from-scratch)

---

## <span id="1-what-is-this-project">1. What is this project?</span>

C.R.E.A.M. is a personal bookkeeping application designed
for Swiss residents who receive bank statements and invoices
as PDF files. Instead of manually typing every transaction
into a spreadsheet, you drop your PDF statements into
designated folders and the app parses them automatically —
extracting dates, amounts, recipients, and even QR-bill
payment slips. You review and correct entries through a
dark-mode dashboard running locally in your browser.

The name is a playful nod to the Wu-Tang Clan classic,
because — well — cash rules everything around us.

---

## <span id="2-tech-stack-at-a-glance">2. Tech stack at a glance</span>

| Technology | What it does here | Learn more |
|---|---|---|
| **Python 3.14** | Application language | [python.org](https://docs.python.org/3/) |
| **Flask 3.x** | Web framework — routes, templates, CLI | [Flask docs](https://flask.palletsprojects.com/) |
| **SQLAlchemy** | ORM — maps Python classes to database tables | [SQLAlchemy docs](https://docs.sqlalchemy.org/) |
| **Flask-Migrate** | Database schema migrations via Alembic | [Flask-Migrate docs](https://flask-migrate.readthedocs.io/) |
| **SQLite** | Lightweight file-based relational database | [SQLite docs](https://sqlite.org/docs.html) |
| **pdfplumber** | Primary PDF text extraction engine | [pdfplumber on GitHub](https://github.com/jsvine/pdfplumber) |
| **pdfminer-six** | Low-level PDF parsing (pdfplumber dependency) | [pdfminer-six docs](https://pdfminersix.readthedocs.io/) |
| **pypdfium2** | Alternative PDF renderer | [pypdfium2 on PyPI](https://pypi.org/project/pypdfium2/) |
| **Pillow** | Image processing for PDF page rendering | [Pillow docs](https://pillow.readthedocs.io/) |
| **Jinja2** | Server-side HTML templating | [Jinja2 docs](https://jinja.palletsprojects.com/) |
| **Chart.js** | Client-side charts (income/expense trends) | [Chart.js docs](https://www.chartjs.org/docs/) |
| **python-dotenv** | Loads `.env` files into environment variables | [python-dotenv docs](https://saurabh-kumar.com/python-dotenv/) |
| **pytest** | Test runner and fixtures | [pytest docs](https://docs.pytest.org/) |

---

## <span id="3-project-structure">3. Project structure</span>

```
cream/
├── app/                            # Main application package
│   ├── __init__.py                 # App factory + CLI commands
│   ├── config.py                   # Environment-based config
│   ├── models.py                   # All 6 ORM models
│   ├── main/                       # Web views blueprint
│   │   ├── __init__.py
│   │   └── routes.py               # Dashboard + import trigger
│   ├── api/                        # REST API blueprint
│   │   ├── __init__.py
│   │   └── routes.py               # CRUD endpoints
│   ├── importers/                  # PDF parsing engines
│   │   ├── __init__.py             # Importer registry
│   │   ├── base.py                 # Shared helpers
│   │   ├── bekb.py                 # BEKB bank parser
│   │   ├── postfinance.py          # PostFinance parser
│   │   ├── revolut.py              # Revolut parser
│   │   └── invoices.py             # QR-bill / invoice parser
│   └── templates/main/
│       └── dashboard.html          # Single-page dashboard
├── tests/
│   ├── conftest.py                 # Fixtures (in-memory DB)
│   ├── unit/                       # Parser unit tests
│   └── integration/                # API endpoint tests
├── migrations/                     # Alembic DB migrations
├── data/                           # SQLite database (cream.db)
├── example/                        # Example PDF directories
│   ├── 01-Rechnungen-Pendent/      # Pending invoices
│   ├── 02-Rechnungen-Bezahlt/      # Paid invoices
│   └── 03-Bewegungen/              # Bank statements
├── reports/                        # Import analysis reports
├── .env.example                    # Example environment config
├── .env.local                      # Real config (git-ignored)
├── requirements.txt                # Production dependencies
├── requirements-dev.txt            # Dev dependencies
├── run.py                          # Entry point
└── pytest.ini                      # Test configuration
```

The three directories under `example/` mirror the real
folder structure that the app reads from in production.
Pending invoices go into `01-Rechnungen-Pendent/`, paid
invoices into `02-Rechnungen-Bezahlt/`, and all bank
statements (BEKB, PostFinance, Revolut) into `03-Bewegungen/`.

---

## <span id="4-how-flask-works-here">4. How Flask works here</span>

### The application factory pattern

Instead of creating a global `app = Flask(__name__)` at
module level, C.R.E.A.M. uses the *application factory
pattern* — a function called `create_app()` that builds and
returns a fully configured Flask instance:

```python
# app/__init__.py
def create_app(config_name: str = "default") -> Flask:
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    migrate.init_app(app, db)

    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix="/api")

    return app
```

This is valuable because it lets you create multiple app
instances with different configurations — one for development
(with `DEBUG=True`), one for testing (with an in-memory
SQLite database), and one for production. The test suite
creates a fresh app per test, guaranteeing clean state.

> 📖 [Flask Application Factory](https://flask.palletsprojects.com/en/stable/patterns/appfactories/)

### Blueprints

Flask *blueprints* are like mini-applications that group
related routes together. C.R.E.A.M. uses two:

- **`main`** — serves the dashboard at `/` and handles
  the import trigger at `/import`
- **`api`** — provides REST endpoints under `/api/` for
  updating transactions, invoices, and categories

Blueprints keep concerns separated. The dashboard rendering
logic lives in `app/main/routes.py`, while JSON API logic
lives in `app/api/routes.py`. Neither file needs to know
about the other.

> 📖 [Flask Blueprints](https://flask.palletsprojects.com/en/stable/blueprints/)

### Template filters and globals

The factory also registers custom Jinja2 helpers:

```python
@app.template_filter("month_label")
def month_label(s: str) -> str:
    """Convert `2024-03` into `March 2024`."""
    d = datetime.strptime(s + "-01", "%Y-%m-%d")
    return d.strftime("%B %Y")

@app.template_global()
def fmt_chf(val) -> str:
    """Format a number as `CHF 1'234.50` (Swiss convention)."""
    if val is None:
        return "—"
    return f"CHF {val:,.2f}".replace(",", "'")
```

The `fmt_chf` filter uses Python's comma-based thousands
separator and then swaps commas for apostrophes — that is the
Swiss convention for grouping digits. You will see
`CHF 1'470.00` instead of `CHF 1,470.00`.

> 📖 [Jinja2 Template Filters](https://jinja.palletsprojects.com/en/stable/templates/#filters)

### Configuration

Three environment classes live in `app/config.py`:

```python
class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "cream-dev-key"
    PENDENT_DIR  = _env_path("PENDENT_DIR",  ...)
    BEZAHLT_DIR  = _env_path("BEZAHLT_DIR",  ...)
    BEWEGUNGEN_DIR = _env_path("BEWEGUNGEN_DIR", ...)
    ACCOUNT_NAME_OVERRIDES = _env_json_dict("ACCOUNT_NAME_OVERRIDES")

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///data/cream.db"

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
```

The `_env_path()` helper resolves relative paths against
the project root, and `_env_json_dict()` parses a JSON
object from an environment variable — used to map IBANs
to custom display names.

> 📖 [Flask Configuration Handling](https://flask.palletsprojects.com/en/stable/config/)

---

## <span id="5-data-models">5. Data models</span>

All models live in `app/models.py` and use SQLAlchemy's
modern `Mapped` type annotations. Here is the entity
relationship at a glance:

```
Category (self-referential: parent/children)
  ├── has many → Transaction
  ├── has many → Invoice
  └── has many → InvoiceTitleRule

Account
  └── has many → Transaction
                   └── has many → TransactionLine
```

### Category

```python
class Category(db.Model):
    id       : Mapped[int]
    name     : Mapped[str]            # e.g. "Energie"
    color    : Mapped[Optional[str]]  # hex color like "#4caf50"
    icon     : Mapped[Optional[str]]  # emoji icon
    parent_id: Mapped[Optional[int]]  # self-referential FK
```

Categories form a tree. A category like "Gas" can be a child
of "Energie", displayed as `Energie/Gas`. The self-referential
`parent_id` foreign key enables unlimited nesting depth. Think
of it like folders on your computer — each folder can contain
subfolders.

> 📖 [SQLAlchemy Self-Referential Relationships](https://docs.sqlalchemy.org/en/20/orm/self_referential.html)

### Account

```python
class Account(db.Model):
    TYPES = ("checking", "savings", "investment", "crypto", "other")

    id      : Mapped[int]
    name    : Mapped[str]             # e.g. "BEKB Privatkonto"
    iban    : Mapped[Optional[str]]   # unique IBAN
    type    : Mapped[str]             # one of TYPES
    currency: Mapped[str]             # default "CHF"
```

Each bank account has a unique IBAN. The importer creates
accounts automatically when it encounters a new IBAN in a
PDF statement.

### Transaction

```python
class Transaction(db.Model):
    id             : Mapped[int]
    account_id     : Mapped[int]          # FK → Account
    date           : Mapped[date]
    raw_description: Mapped[str]          # original from PDF
    title          : Mapped[Optional[str]]# user-corrected label
    amount         : Mapped[float]
    type           : Mapped[str]          # "income" or "expense"
    saldo          : Mapped[Optional[float]]
    category_id    : Mapped[Optional[int]]# FK → Category
    import_hash    : Mapped[str]          # unique SHA1
```

The `raw_description` preserves exactly what the PDF parser
extracted. The `title` field is for your human-friendly
correction — the dashboard shows `title` when set, falling
back to `raw_description`.

The `import_hash` is the key to *idempotent imports*. Every
time you re-import, the app computes a SHA1 hash from the
account IBAN, date, amount, and description. If that hash
already exists in the database, the row is skipped. This
means you can safely re-import the same PDF as many times as
you want without creating duplicates.

> 📖 [SQLAlchemy Mapped Columns](https://docs.sqlalchemy.org/en/20/orm/mapped_attributes.html)

### TransactionLine

```python
class TransactionLine(db.Model):
    id             : Mapped[int]
    transaction_id : Mapped[int]      # FK → Transaction
    position       : Mapped[int]      # ordering index
    recipient      : Mapped[str]      # individual payee
    amount         : Mapped[float]
    iban           : Mapped[Optional[str]]
```

When you pay multiple bills in a single e-banking order,
BEKB groups them into one transaction. TransactionLines
break that bundle back into its individual transfers. Think
of a Transaction as a shopping bag and TransactionLines as
the individual items inside.

### Invoice

```python
class Invoice(db.Model):
    STATUSES = ("pending", "paid")

    id          : Mapped[int]
    filename    : Mapped[str]
    page_index  : Mapped[int]          # supports multi-slip PDFs
    slip_label  : Mapped[Optional[str]]# e.g. "Kirchensteuer"
    title       : Mapped[Optional[str]]
    raw_issuer  : Mapped[Optional[str]]
    amount      : Mapped[Optional[float]]
    invoice_date: Mapped[Optional[date]]
    due_date    : Mapped[Optional[date]]
    paid_date   : Mapped[Optional[date]]
    source_year : Mapped[Optional[int]]
    status      : Mapped[str]          # "pending" or "paid"
    import_hash : Mapped[str]          # unique SHA1
```

Invoices are imported from two folders: pending invoices
from `01-Rechnungen-Pendent/` and paid ones from
`02-Rechnungen-Bezahlt/`. The `source_year` is extracted
from the folder path (e.g., `/2024/rechnung.pdf` → 2024),
which helps when the invoice itself does not contain a clear
date.

The `days_until_due` property computes how many days remain
until the due date, powering the urgency badges in the
dashboard ("Überfällig 5d" or "Fällig in 3 Tagen").

### InvoiceTitleRule

```python
class InvoiceTitleRule(db.Model):
    id         : Mapped[int]
    raw_issuer : Mapped[str]          # unique, e.g. "Steueramt"
    title      : Mapped[str]          # e.g. "Steuern Kanton"
    category_id: Mapped[Optional[int]]# FK → Category
```

This is the app's *learning mechanism*. When you correct an
invoice's title and click "Remember Title", the app saves a
rule: "Whenever the issuer is X, set the title to Y and the
category to Z." Future imports from the same issuer get that
title and category pre-filled automatically. Over time, the
app learns your preferences and requires fewer corrections.

---

## <span id="6-shared-importer-utilities">6. Shared importer utilities</span>

All importers share common helper functions defined in
`app/importers/base.py`. These small functions handle the
messy realities of parsing Swiss financial PDFs.

### parse_chf — normalizing money strings

```python
def parse_chf(s: str) -> Optional[float]:
    s = (s.replace("'", "")       # Swiss thousands: 1'234
          .replace(" ", "")       # space grouping
          .replace(",", ".")      # European decimal
          .replace("O", "0")      # OCR: capital O → zero
          .replace("o", "0"))     # OCR: lowercase o → zero
    parts = s.split(".")
    if len(parts) > 2:
        s = "".join(parts[:-1]) + "." + parts[-1]
    return float(s)
```

Swiss financial documents use apostrophes as thousands
separators (`1'234.50`), and OCR engines sometimes mistake
the digit `0` for the letter `O`. This function handles both
cases. The multi-dot collapse handles edge cases where OCR
produces `1.234.50` (European dot-as-thousands notation).

### make_hash — stable duplicate detection

```python
def make_hash(*parts) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode()).hexdigest()
```

Every transaction and invoice gets a SHA1 hash computed from
its key fields. This hash is stored in a `UNIQUE` column,
acting as a *natural deduplication key*. Re-importing the
same PDF simply skips rows whose hashes already exist.

### group_words_by_row — reconstructing table rows

```python
def group_words_by_row(words: list, y_tolerance: int = 3):
    rows: dict = {}
    for w in words:
        y = round(w["top"] / y_tolerance) * y_tolerance
        rows.setdefault(y, []).append(w)
    return {y: sorted(ws, key=lambda w: w["x0"])
            for y, ws in sorted(rows.items())}
```

pdfplumber gives you individual words with `(x, y)`
coordinates. This function groups them back into rows by
rounding their vertical position. Think of it like sorting
scattered Scrabble tiles back onto their rows — words that
share approximately the same `y` coordinate belong to the
same line.

> 📖 [pdfplumber word extraction](https://github.com/jsvine/pdfplumber#extracting-words)

---

## <span id="7-bekb-bank-importer">7. BEKB bank importer</span>

The BEKB (Berner Kantonalbank) importer in
`app/importers/bekb.py` is the most complex parser. It
handles two document families:

### Monthly account statements (Kontoauszug)

These multi-page PDFs contain a table with columns:
Date | Description | Debit | Credit | Valuta | Saldo.

The parser uses pdfplumber's word-level extraction to
reconstruct table rows by their x/y coordinates:

```python
# Detect column positions from header words
for word in words:
    if word["text"] in ("Belastung", "Gutschrift",
                        "Valuta", "Saldo"):
        columns[word["text"]] = word["x0"]
```

Once it knows where each column starts (in PDF points),
it classifies every number on a row: numbers near the
"Belastung" (debit) column x-position are expenses,
numbers near "Gutschrift" (credit) are income, and
numbers near "Saldo" are the running balance.

This approach is called *positional parsing* — it uses
the physical layout of the PDF rather than relying on
fragile text patterns.

### E-banking detail blocks

When a transaction description contains "E-Banking-Auftrag"
(e-banking order), the parser looks for a detail block
listing individual transfers:

```python
def _parse_sub_entries(detail_lines, total_amount):
    # Multi-entry blocks start with "." separators
    is_multi_entry = lines[0] == "."
    if not is_multi_entry:
        return [_parse_single_block(lines)]

    # Split on "." markers into individual blocks
    blocks = []
    current_block = []
    for line in lines:
        if line == ".":
            if current_block:
                blocks.append(current_block)
            current_block = []
        else:
            current_block.append(line)
```

Each block yields a `TransactionLine` with recipient name,
amount, and destination IBAN. The parser also handles
hyphenated names that span two lines (e.g., `Müller-` on
one line and `Meier` on the next).

### Single transaction notices (Gutschrifts/Belastungsanzeige)

These simpler documents describe a single credit or debit.
The parser extracts the value date and amount via regex:

```python
_NOTICE_VALUE_RE = re.compile(
    r"Valuta\s*(\d{2}\.\d{2}\.\d{4})\s+CHF\s+"
    r"([\d' ]+\.\d{2})",
    re.IGNORECASE,
)
```

It then determines the transaction type from keywords
like "Zahlungseingang" (incoming payment) or
"Belastungsanzeige" (debit notice), and extracts the
counterparty name from fields like "Begünstigter:"
(beneficiary).

> 📖 [pdfplumber extract_words()](https://github.com/jsvine/pdfplumber#extracting-words)

---

## <span id="8-postfinance-importer">8. PostFinance importer</span>

The PostFinance importer (`app/importers/postfinance.py`)
handles statements from Switzerland's PostFinance bank.

Key characteristics:
- Extracts the IBAN from the filename (PostFinance PDFs
  encode the IBAN in the filename)
- Uses the same positional word-grouping approach as BEKB
- Includes robust repair commands for legacy data:
  `repair-postfinance-saldi`,
  `normalize-postfinance-transactions`
- Supports a CSV-based repair workflow where you can
  manually mark corrections in a spreadsheet, then
  preview and apply them via CLI commands

The importer follows the same pattern as BEKB: discover
PDFs → parse each one → compute hashes → skip duplicates →
store new transactions.

> 📖 [PostFinance e-finance](https://www.postfinance.ch/en/private.html)

---

## <span id="9-revolut-importer">9. Revolut importer</span>

The Revolut importer (`app/importers/revolut.py`) handles
Revolut e-money account statements.

### Statement detection

```python
_STATEMENT_NAME_RE = re.compile(
    r"^account-statement_.*\.pdf$", re.IGNORECASE
)
```

Only files matching `account-statement_*.pdf` are processed.

### Transaction parsing

Revolut statements use a fixed-width format:

```
DD Mon YYYY Description Amount CHF Balance CHF
```

The parser matches each line against this regex pattern,
then groups continuation lines that start with prefixes
like `To:`, `From:`, `Card:`, or `Reference:`.

### Type inference — the clever part

Determining whether a transaction is income or expense
is non-trivial because Revolut statements do not label
them explicitly. The parser uses a two-tier strategy:

```python
def _infer_type(description, amount, balance,
                previous_balance):
    # Primary: balance delta analysis
    if previous_balance is not None:
        delta = round(balance - previous_balance, 2)
        if abs(abs(delta) - amount) <= 0.05:
            return "income" if delta >= 0 else "expense"

    # Fallback: text hints
    if any(hint in description.lower()
           for hint in ("payment from", "cashback",
                        "salary", "refund", "interest")):
        return "income"
    return "expense"
```

The primary method compares the running balance before and
after: if the balance went up by approximately the
transaction amount, it is income. The 0.05 CHF tolerance
handles rounding differences from currency conversions.
When no previous balance is available (first transaction),
it falls back to keyword matching.

This is a pattern called *delta-based inference* — instead
of parsing labels, you derive meaning from the numerical
difference between consecutive states.

> 📖 [Revolut statements](https://www.revolut.com/help/profile-and-plan/verifying-identity/downloading-my-revolut-account-statement)

---

## <span id="10-invoice-importer">10. Invoice importer</span>

The invoice importer (`app/importers/invoices.py`) parses
Swiss QR-bill PDFs and traditional invoices. It is the
parser that deals with the most varied input formats.

### Multi-slip detection

A single PDF page can contain multiple payment slips
(common for tax bills). The parser splits pages on the
separator line:

```python
_TRENNLINIE = re.compile(
    r"vor\s*der?\s*einzahlung\s*abzutrennen",
    re.IGNORECASE,
)
```

This matches the physical perforation instruction
("vor der Einzahlung abzutrennen" = "tear off before
payment") that appears between slips on Swiss QR-bills.

### Amount extraction — priority cascade

The amount parser tries patterns in order of specificity:

1. **Inline payment request:**
   `Bitte bezahlen Sie den Betrag von CHF 1'470.00 bis 31.03.2026`
2. **QR-bill canonical format:**
   `Währung Betrag CHF 1'470.00`
3. **Invoice-specific patterns** (8 fallback regexes):
   `Rechnungsbetrag CHF`, `Total CHF`, `Gesamtbetrag CHF`,
   `Fr. 1'470.00`, `CHF 1'470.00`, etc.

Each matched amount must exceed CHF 5 to filter out false
positives from reference numbers or dates that look like
amounts.

### Issuer extraction — ranked candidate selection

The issuer (who sent the invoice) is identified by a
*ranked scoring system*:

```python
# Priority order:
# 1. Legal entities: "AG", "GmbH", "SA", etc.
# 2. Strong preferred: Steueramt, Krankenkasse, Spital...
# 3. Preferred: Service, Bank, Finanzen, Stadt, Kanton...
# 4. Generic: any remaining alphabetic candidate line
```

The parser walks through all text lines, filtering out
URLs, IBANs, email addresses, and skip phrases like
"Ihr persönliches Beratungsteam". Candidates are sorted
into ranked buckets, and the highest-priority match wins.

The `normalize_invoice_issuer()` function then cleans up
common OCR errors — for example, "Steuerarnt" becomes
"Steueramt" (the OCR misread the `m` as `rn`).

### Title rules — the learning loop

After import, users can click "Remember Title" on any
invoice. This creates an `InvoiceTitleRule` mapping the
raw issuer to a clean title and optional category. On the
next import, `apply_invoice_title_rule()` checks if a
rule exists for the issuer and pre-fills the title:

```python
def apply_invoice_title_rule(slip: dict) -> dict:
    rule = InvoiceTitleRule.query.filter_by(
        raw_issuer=slip.get("raw_issuer")
    ).first()
    if rule:
        slip["title"] = rule.title
        if rule.category_id:
            slip["category_id"] = rule.category_id
    return slip
```

Over time, this reduces manual corrections to near zero
for recurring invoices (rent, insurance, taxes, etc.).

> 📖 [Swiss QR-bill specification (SIX)](https://www.six-group.com/en/products-services/banking-services/payment-standardization/standards/qr-bill.html)

---

## <span id="11-rest-api-routes">11. REST API routes</span>

All API endpoints live in `app/api/routes.py` under the
`/api/` prefix. They return JSON and are consumed by the
dashboard's vanilla JavaScript.

### Transactions

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/transactions` | List (filterable by month, account, category, IBAN) |
| `PATCH` | `/api/transactions/<id>` | Update title, category, or notes |

### Invoices

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/invoices` | List (filterable by status, category, year) |
| `PATCH` | `/api/invoices/<id>` | Update title, amount, status, dates, category, notes |
| `DELETE` | `/api/invoices/<id>` | Delete for re-import testing |
| `POST` | `/api/invoices/<id>/remember-title` | Save issuer → title rule |

### Categories

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/categories` | List all with hierarchy paths and usage counts |
| `POST` | `/api/categories` | Create (with optional parent) |
| `PATCH` | `/api/categories/<id>` | Update name, color, icon, parent |
| `DELETE` | `/api/categories/<id>` | Delete (only if unused and no children) |

### Cycle detection in categories

When you move a category to a new parent, the API
prevents circular hierarchies:

```python
def _validate_category_parent(cat, parent_id):
    if parent_id == cat.id:
        abort(400, "category cannot be its own parent")

    cursor = db.session.get(Category, parent_id)
    while cursor is not None:
        if cursor.id == cat.id:
            abort(400, "cyclic hierarchy not allowed")
        cursor = cursor.parent
```

This walks up the ancestor chain from the proposed parent.
If it ever reaches the category being moved, that would
create a cycle (A → B → A), so the request is rejected.
This is a classic *cycle detection* algorithm on a
linked-list-style tree.

> 📖 [Flask JSON APIs](https://flask.palletsprojects.com/en/stable/patterns/javascript/)

---

## <span id="12-the-dashboard-ui">12. The dashboard UI</span>

The entire frontend lives in a single Jinja2 template:
`app/templates/main/dashboard.html` (~930 lines). It uses
inline CSS and vanilla JavaScript — no build step, no
npm, no React. This is a deliberate choice: for a
personal tool, simplicity trumps scalability.

### Layout

```
┌──────────────────────────────────────────┐
│ 💰 C.R.E.A.M. | [🔄 PDFs importieren]   │
├──────────────────────────────────────────┤
│ KPI cards: Saldo | Einnahmen | Ausgaben  │
│            | Offene Rechnungen            │
├──────────────────────────────────────────┤
│ Tabs: [Kontobewegungen] [Rechnungen]     │
│       [Kategorien]                        │
├──────────────────────────────────────────┤
│ Active tab content                        │
└──────────────────────────────────────────┘
```

### Tab 1: Kontobewegungen (Transactions)

- **Chart.js bar chart** showing monthly income vs. expense
- **Filters:** account, category, year, month
- **Monthly accordions:** collapsible blocks per month,
  each showing total income, expenses, and net balance
- **Inline editing:** click a transaction to change its
  title, category, or notes via the API
- **Detail expansion:** e-banking orders expand to show
  individual TransactionLines (recipients + IBANs)

### Tab 2: Rechnungen (Invoices)

- **Card layout** with status badges (pending/paid)
- **Urgency indicators:** "Überfällig (5d)" in red,
  "Fällig in 3 Tagen" in yellow
- **Inline actions:** edit amount, change status,
  remember title, open PDF, delete
- **Filters:** status, category, year

### Tab 3: Kategorien (Categories)

- **Tree view** of all categories with hierarchy
- **Usage statistics** per category (transaction count,
  invoice count, rule count)
- **Safe delete:** only deletable when no items reference
  the category and it has no children

### Dark mode design

The UI uses CSS custom properties for a dark theme:

```css
:root {
    --bg:      #181a20;
    --surface: #23262f;
    --text:    #e0e0e0;
}
```

Green indicates income, red indicates expenses, and blue
is used for interactive elements. The design uses 12px
border-radius and subtle transitions throughout.

### JavaScript interactions

All mutations are done via `fetch()` calls to the REST
API. The page does not reload — responses update the DOM
directly. Toast notifications confirm success or show
errors.

> 📖 [Chart.js Bar Chart](https://www.chartjs.org/docs/latest/charts/bar.html)
> 📖 [Jinja2 Templates](https://jinja.palletsprojects.com/en/stable/templates/)

---

## <span id="13-cli-commands">13. CLI commands</span>

C.R.E.A.M. registers several Flask CLI commands for data
repair and maintenance. These are registered in
`app/__init__.py` using Click decorators and run via:

```bash
flask --app run.py <command>
```

| Command | Purpose |
|---------|---------|
| `reparse-lines` | Backfill TransactionLines for already-imported BEKB e-banking orders |
| `backfill-source-year` | Extract year from folder paths for existing invoices |
| `repair-postfinance-saldi` | Re-parse PostFinance PDFs and fix incorrect saldo values |
| `normalize-postfinance-transactions` | Split legacy merged PostFinance rows into separate entries |
| `repair-bekb-notice-dates` | Fix BEKB notice rows with incorrectly parsed years |
| `sync-account-name-overrides` | Apply `ACCOUNT_NAME_OVERRIDES` config to existing accounts |
| `preview-postfinance-marked-repairs` | Dry-run repair plan from a manually marked CSV |
| `apply-postfinance-marked-repairs` | Apply the repairs from the marked CSV |

These commands follow a common pattern: they are
*non-destructive by default*. The PostFinance workflow even
has a dedicated preview step so you can review what will
change before applying anything.

> 📖 [Flask CLI](https://flask.palletsprojects.com/en/stable/cli/)

---

## <span id="14-testing">14. Testing</span>

Tests live in `tests/` and use pytest with pytest-flask.

### Test fixtures (`tests/conftest.py`)

```python
@pytest.fixture
def app(tmp_path):
    """Fresh Flask app with an in-memory DB per test."""
    # Creates temp directories for PDF folders
    # Uses TestingConfig with sqlite:///:memory:
    # Returns a fully initialized app

@pytest.fixture
def client(app):
    """Flask test client for HTTP assertions."""
    return app.test_client()
```

Each test gets a completely fresh database — no leftover
state from previous tests. The `tmp_path` fixture (built
into pytest) provides a unique temporary directory per test.

### Unit tests

Each parser module has dedicated unit tests:

- **`test_bekb_parser.py`** — tests for
  `_parse_single_block()` and `_parse_sub_entries()`:
  recipient extraction, IBAN normalization, hyphenated
  names, multi-entry splitting on "." separators
- **`test_postfinance_parser.py`** — amount parsing with
  Swiss formatting, date parsing, saldo extraction
- **`test_revolut_parser.py`** — statement filename
  matching, opening balance extraction, date parsing,
  income/expense type inference
- **`test_invoices.py`** — amount pattern matching (QR-bill
  vs. invoice patterns), due date extraction, issuer
  ranking, slip label detection
- **`test_invoice_import_flow.py`** — end-to-end import
  pipeline, hash-based deduplication, title rule application
- **`test_base.py`** — shared utilities: CHF parsing edge
  cases, date formatting, hash generation, row grouping

### Integration tests

**`test_api.py`** tests the full HTTP request/response
cycle for API endpoints: creating, updating, and deleting
categories; updating transactions and invoices; category
hierarchy validation (cycle prevention); title rule saving.

### Running tests

```bash
pytest                          # run all tests
pytest tests/unit/              # unit tests only
pytest tests/integration/       # integration tests only
pytest -v                       # verbose output
```

> 📖 [pytest documentation](https://docs.pytest.org/en/stable/)
> 📖 [pytest-flask](https://pytest-flask.readthedocs.io/)

---

## <span id="15-how-to-replicate-this-project-from-scratch">15. How to replicate this project from scratch</span>

If you wanted to build something similar, here is the
recommended order:

1. **Set up the project skeleton.** Create a Python virtual
   environment, install Flask, Flask-SQLAlchemy, and
   Flask-Migrate. Create the `app/` package with an
   `__init__.py` containing the application factory. Create
   `run.py` as the entry point.

2. **Define your data models.** Start with `Account` and
   `Transaction` — these are the core. Add `Category` for
   organization. Use `flask db init` and `flask db migrate`
   to create your first migration.

3. **Build the base importer utilities.** Write `parse_chf`,
   `make_hash`, and `group_words_by_row` in
   `app/importers/base.py`. These small functions will be
   reused by every bank-specific parser.

4. **Write your first bank parser.** Pick whichever bank
   you use most. Install `pdfplumber` and experiment with
   extracting text from a real PDF. Start with the simplest
   document type (e.g., single-transaction notices before
   multi-page statements).

5. **Create the importer registry.** Set up
   `app/importers/__init__.py` with a `BANK_IMPORTERS`
   dictionary and a `run_full_import()` function that
   loops through all registered importers.

6. **Add the invoice parser.** Swiss QR-bills have a
   fairly standardized format, so regex patterns work
   well. Start with amount and due date extraction, then
   add issuer detection.

7. **Build the REST API.** Create the `api` blueprint
   with CRUD endpoints for transactions, invoices, and
   categories. Use `request.get_json()` for input and
   `jsonify()` for output.

8. **Build the dashboard.** Start with a simple Jinja2
   template that lists transactions. Add filters, then
   tabs, then the chart. Use `fetch()` for inline editing
   rather than full page reloads.

9. **Add the title rule system.** This is a small but
   high-value feature. Store issuer → title mappings and
   apply them during import.

10. **Write tests.** Start with unit tests for your
    parsers — these are the most fragile part of the
    system. Use in-memory SQLite for fast test execution.

11. **Add CLI repair commands** as needed. As you import
    real data, you will discover edge cases and OCR errors
    that need batch correction. Write CLI commands for
    these rather than manual SQL fixes.

12. **Configure environment variables.** Use `.env.local`
    (git-ignored) for your real NAS paths and any account
    name overrides. Keep `.env.example` tracked so others
    can see what is expected.

---

*This tutorial was generated from the C.R.E.A.M. source
code. For questions about specific files or features, ask
for a deeper dive into any section.*
