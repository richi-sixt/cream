"""Import package for cream."""

from collections.abc import Callable

from .bekb import import_bank_documents, import_kontoauszuege
from .invoices import import_invoices, import_rechnungen
from .postfinance import import_postfinance_documents
from .revolut import import_revolut_documents

BankImporter = Callable[[], dict]

BANK_IMPORTERS: dict[str, BankImporter] = {
    "bekb": import_bank_documents,
    "postfinance": import_postfinance_documents,
    "revolut": import_revolut_documents,
}


def run_full_import() -> dict:
    """Run all imports and return combined statistics."""
    transaction_stats = {"imported": 0, "skipped": 0, "errors": 0}
    for importer in BANK_IMPORTERS.values():
        stats = importer()
        for key in transaction_stats:
            transaction_stats[key] += stats[key]

    return {
        "transactions": transaction_stats,
        "invoices":     import_invoices(),
    }

__all__ = [
    "BANK_IMPORTERS",
    "run_full_import",
    "import_bank_documents",
    "import_invoices",
    "import_postfinance_documents",
    "import_revolut_documents",
    "import_kontoauszuege",
    "import_rechnungen",
]
