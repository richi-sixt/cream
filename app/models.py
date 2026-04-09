"""SQLAlchemy database models for cream."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import db


def utc_now() -> datetime:
    """Return a naive UTC timestamp without using deprecated `utcnow()`."""
    return datetime.now(UTC).replace(tzinfo=None)


# ── Kategorien ───────────────────────────────────────────────────────────────

class Category(db.Model):
    """Hierarchical category for transactions and invoices."""

    __tablename__ = "categories"

    id       : Mapped[int]            = mapped_column(Integer, primary_key=True)
    name     : Mapped[str]            = mapped_column(String(80), nullable=False)
    color    : Mapped[Optional[str]]  = mapped_column(String(7),  nullable=True)
    icon     : Mapped[Optional[str]]  = mapped_column(String(10), nullable=True)
    parent_id: Mapped[Optional[int]]  = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True
    )

    children: Mapped[list[Category]] = relationship(
        "Category",
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    parent: Mapped[Optional[Category]] = relationship(
        "Category",
        back_populates="children",
        remote_side="Category.id",
    )

    transactions: Mapped[list[Transaction]] = relationship(
        "Transaction", back_populates="category"
    )
    invoices: Mapped[list[Invoice]] = relationship(
        "Invoice", back_populates="category"
    )
    title_rules: Mapped[list["InvoiceTitleRule"]] = relationship(
        "InvoiceTitleRule", back_populates="category"
    )

    def __repr__(self) -> str:
        return f"<Category {self.name}>"

    @property
    def path(self) -> str:
        """Slash-separated category path from root to this node."""
        names: list[str] = []
        cursor: Category | None = self
        while cursor is not None:
            names.append(cursor.name)
            cursor = cursor.parent
        return "/".join(reversed(names))

    @property
    def depth(self) -> int:
        """Zero-based hierarchy depth."""
        d = 0
        cursor = self.parent
        while cursor is not None:
            d += 1
            cursor = cursor.parent
        return d

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":        self.id,
            "name":      self.name,
            "color":     self.color,
            "icon":      self.icon,
            "parent_id": self.parent_id,
        }


# ── Konten ───────────────────────────────────────────────────────────────────

class Account(db.Model):
    """Bank, savings, or investment account."""

    __tablename__ = "accounts"

    TYPES = ("checking", "savings", "investment", "crypto", "other")

    id      : Mapped[int]           = mapped_column(Integer, primary_key=True)
    name    : Mapped[str]           = mapped_column(String(120), nullable=False)
    iban    : Mapped[Optional[str]] = mapped_column(String(34), unique=True, nullable=True)
    type    : Mapped[str]           = mapped_column(String(20), default="checking")
    currency: Mapped[str]           = mapped_column(String(3),  default="CHF")
    color   : Mapped[Optional[str]] = mapped_column(String(7),  nullable=True)

    transactions: Mapped[list[Transaction]] = relationship(
        "Transaction",
        back_populates="account",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Account {self.name}>"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":       self.id,
            "name":     self.name,
            "iban":     self.iban,
            "type":     self.type,
            "currency": self.currency,
            "color":    self.color,
        }


class Transaction(db.Model):
    """Single account transaction imported from a BEKB PDF."""

    __tablename__ = "transactions"

    TYPES = ("income", "expense")

    id             : Mapped[int]            = mapped_column(Integer, primary_key=True)
    account_id     : Mapped[int]            = mapped_column(
        Integer, ForeignKey("accounts.id"), nullable=False
    )
    date           : Mapped[date]           = mapped_column(db.Date, nullable=False, index=True)
    raw_description: Mapped[str]            = mapped_column(Text, nullable=False)
    title          : Mapped[Optional[str]]  = mapped_column(String(200), nullable=True)
    amount         : Mapped[float]          = mapped_column(Float, nullable=False)
    type           : Mapped[str]            = mapped_column(String(10), nullable=False)
    saldo          : Mapped[Optional[float]]= mapped_column(Float, nullable=True)
    category_id    : Mapped[Optional[int]]  = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True, index=True
    )
    pdf_source     : Mapped[Optional[str]]  = mapped_column(String(200), nullable=True)
    import_hash    : Mapped[str]            = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    notes          : Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    created_at     : Mapped[datetime]       = mapped_column(
        db.DateTime, default=utc_now
    )

    account : Mapped[Account]           = relationship("Account",  back_populates="transactions")
    category: Mapped[Optional[Category]]= relationship("Category", back_populates="transactions")
    lines   : Mapped[list["TransactionLine"]] = relationship(
        "TransactionLine",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="TransactionLine.position",
    )

    @property
    def display_title(self) -> str:
        """Prefer the manual title when present."""
        return self.title or self.raw_description

    def __repr__(self) -> str:
        return f"<Transaction {self.date} {self.amount} {self.type}>"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":              self.id,
            "account_id":      self.account_id,
            "account_name":    self.account.name if self.account else None,
            "date":            self.date.isoformat(),
            "raw_description": self.raw_description,
            "title":           self.title,
            "display_title":   self.display_title,
            "amount":          self.amount,
            "type":            self.type,
            "saldo":           self.saldo,
            "category_id":     self.category_id,
            "category_name":   self.category.name if self.category else None,
            "pdf_source":      self.pdf_source,
            "notes":           self.notes,
            "lines":           [l.to_dict() for l in self.lines],
        }


class TransactionLine(db.Model):
    """Child transfer line belonging to a bundled e-banking transaction."""

    __tablename__ = "transaction_lines"

    id             : Mapped[int]           = mapped_column(Integer, primary_key=True)
    transaction_id : Mapped[int]           = mapped_column(
        Integer, ForeignKey("transactions.id"), nullable=False
    )
    position       : Mapped[int]           = mapped_column(Integer, default=0)
    recipient      : Mapped[str]           = mapped_column(String(200), nullable=False)
    amount         : Mapped[float]         = mapped_column(Float, nullable=False)
    iban           : Mapped[Optional[str]] = mapped_column(String(40),  nullable=True)

    transaction: Mapped[Transaction] = relationship(
        "Transaction", back_populates="lines"
    )

    def __repr__(self) -> str:
        return f"<TransactionLine {self.recipient} {self.amount}>"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":             self.id,
            "transaction_id": self.transaction_id,
            "position":       self.position,
            "recipient":      self.recipient,
            "amount":         self.amount,
            "iban":           self.iban,
        }


class Invoice(db.Model):
    """Pending or paid invoice imported from the PDF folders."""

    __tablename__ = "invoices"

    STATUSES = ("pending", "paid")

    id          : Mapped[int]            = mapped_column(Integer, primary_key=True)
    filename    : Mapped[str]            = mapped_column(String(300), nullable=False)
    page_index  : Mapped[int]            = mapped_column(Integer, default=0, nullable=False)
    slip_label  : Mapped[Optional[str]]  = mapped_column(String(100), nullable=True)
    title       : Mapped[Optional[str]]  = mapped_column(String(200), nullable=True)
    raw_issuer  : Mapped[Optional[str]]  = mapped_column(String(200), nullable=True)
    amount      : Mapped[Optional[float]]= mapped_column(Float, nullable=True)
    invoice_date: Mapped[Optional[date]] = mapped_column(db.Date, nullable=True)
    due_date    : Mapped[Optional[date]] = mapped_column(db.Date, nullable=True, index=True)
    paid_date   : Mapped[Optional[date]] = mapped_column(db.Date, nullable=True)
    source_year : Mapped[Optional[int]]  = mapped_column(Integer, nullable=True)
    status      : Mapped[str]            = mapped_column(String(20), default="pending", index=True)
    category_id : Mapped[Optional[int]]  = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True, index=True
    )
    notes       : Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    import_hash : Mapped[str]            = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    created_at  : Mapped[datetime]       = mapped_column(
        db.DateTime, default=utc_now
    )
    updated_at  : Mapped[datetime]       = mapped_column(
        db.DateTime, default=utc_now, onupdate=utc_now
    )

    category: Mapped[Optional[Category]] = relationship(
        "Category", back_populates="invoices"
    )

    @property
    def display_title(self) -> str:
        return self.title or self.raw_issuer or self.filename

    @property
    def days_until_due(self) -> Optional[int]:
        if self.due_date:
            return (self.due_date - date.today()).days
        return None

    def __repr__(self) -> str:
        return f"<Invoice {self.filename} {self.status}>"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":             self.id,
            "filename":       self.filename,
            "page_index":     self.page_index,
            "slip_label":     self.slip_label,
            "title":          self.title,
            "display_title":  self.display_title,
            "raw_issuer":     self.raw_issuer,
            "amount":         self.amount,
            "invoice_date":   self.invoice_date.isoformat() if self.invoice_date else None,
            "due_date":       self.due_date.isoformat()     if self.due_date     else None,
            "paid_date":      self.paid_date.isoformat()    if self.paid_date    else None,
            "status":         self.status,
            "source_year":    self.source_year,
            "category_id":    self.category_id,
            "category_name":  self.category.name if self.category else None,
            "days_until_due": self.days_until_due,
            "notes":          self.notes,
        }


class InvoiceTitleRule(db.Model):
    """Remembered invoice title rule keyed by normalized issuer."""

    __tablename__ = "invoice_title_rules"

    id         : Mapped[int]            = mapped_column(Integer, primary_key=True)
    raw_issuer : Mapped[str]            = mapped_column(String(200), unique=True, nullable=False)
    title      : Mapped[str]            = mapped_column(String(200), nullable=False)
    category_id: Mapped[Optional[int]]  = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True
    )
    created_at : Mapped[datetime]       = mapped_column(
        db.DateTime, default=utc_now
    )
    updated_at : Mapped[datetime]       = mapped_column(
        db.DateTime, default=utc_now, onupdate=utc_now
    )

    category: Mapped[Optional[Category]] = relationship(
        "Category", back_populates="title_rules"
    )

    def __repr__(self) -> str:
        return f"<InvoiceTitleRule {self.raw_issuer} -> {self.title}>"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":          self.id,
            "raw_issuer":  self.raw_issuer,
            "title":       self.title,
            "category_id": self.category_id,
        }
