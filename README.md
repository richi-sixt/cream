# C.R.E.A.M.

> **C**ash **R**ules **E**verything **A**round **M**e — a personal
> finance management app for Swiss bank accounts and invoices,
> built with Flask.

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

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.14 |
| Framework | Flask 3.x |
| ORM / Migrations | SQLAlchemy + Flask-Migrate (Alembic) |
| PDF Parsing | pdfplumber |
| Frontend | Jinja2 + vanilla JS |
| Database | SQLite |
| Testing | pytest + pytest-flask |

---

## Features

### Bank imports

- Dedicated importers for BEKB, PostFinance and Revolut
- Recursive document discovery in `03-Bewegungen/` (bank subfolders supported)
- Multi-account support via IBAN-aware matching
- Duplicate protection with stable import hashes
- Repair and normalization CLI helpers for legacy PostFinance imports

### Invoice imports

- Import from pending and paid folders
- Parse amount, due date, invoice date, and issuer from Swiss invoice/QR PDFs
- Manual correction directly in UI (title, amount, due date, status, category)
- Delete single invoice DB entries for clean re-import testing
- Remember title rules per issuer, including category defaults

### Categories

- Assign categories to transactions and invoices in the UI
- Filter both dashboard tabs by category
- Manage categories in dedicated `Kategorien` tab:
  - create
  - search/filter
  - rename
  - safe delete when unused
  - hierarchy with parent/child paths (for example `Energie/Gas`)

### Search & Filter
- Advanced transaction search and filter view.
- Multi-Select account, category, year & amount
- Text filter for description, recipients with pattern matching
- Group result by account, category, description, recipients, year or month

---

## Project Story

I started this learning project in **2021**.

The first edition imported PDF files, but I still had to insert key data manually (account, positive/negative amount, category, and other fields), because building reliable PDF parsing and regex extraction on my own was too hard at the time.

With AI support, I was finally able to complete robust importer/parser flows for my bank accounts and make the project production-usable for my personal workflow.

---

## Setup

### 1. Create and activate virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 3. Configure environment

Use `.env.local` for your private real paths and `.env.example` for tracked demo/example paths.

Important variables:

- `PENDENT_DIR`
- `BEZAHLT_DIR`
- `BEWEGUNGEN_DIR`
- `ACCOUNT_NAME_OVERRIDES`

### 4. Initialize database

```bash
source .venv/bin/activate
flask --app run.py db upgrade
```

### 5. Start app

```bash
source .venv/bin/activate
python run.py
```

---

## Testing

Always run inside the venv:

```bash
source .venv/bin/activate
pytest -q
```

---

## Documentation

For full documentation and workflow details, see:

- [ ] Update
