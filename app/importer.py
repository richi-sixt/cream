"""Backwards-compatible import shim."""

from app.importers import import_bank_documents, import_invoices, import_kontoauszuege, import_rechnungen, run_full_import  # noqa: F401
from app.importers.base import parse_chf, make_hash  # noqa: F401
from app.importers.invoices import extract_slip_data, parse_invoice_slips  # noqa: F401
from app.importers.bekb import parse_bekb_pdf  # noqa: F401

__all__ = [
    "run_full_import",
    "import_bank_documents",
    "import_invoices",
    "import_kontoauszuege",
    "import_rechnungen",
    "parse_chf",
    "make_hash",
    "extract_slip_data",
    "parse_invoice_slips",
    "parse_bekb_pdf",
]
