"""SQLAlchemy setup + ORM models.

One SQLite file per deployment. Schema created on startup (no Alembic
yet — will add when the schema starts moving in production).

The ORM models are the *storage* shape. The Pydantic schemas in
`schemas.py` are the *wire* shape. They're intentionally decoupled so
we can evolve storage without breaking API contracts.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    create_engine, Column, String, Integer, Float, Boolean, ForeignKey, JSON,
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session,
)

BACKEND = Path(__file__).parent.parent
REPO = BACKEND.parent
DB_PATH = BACKEND / "ledgerflow.sqlite"
DB_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DB_URL, echo=False, future=True, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


class Base(DeclarativeBase):
    pass


class CaseRow(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    fir_number: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    officer_name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="active")
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)

    persons: Mapped[list["PersonRow"]] = relationship(back_populates="case", cascade="all, delete-orphan")


class PersonRow(Base):
    __tablename__ = "persons"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    aliases_json: Mapped[str] = mapped_column(String, default="[]")
    pan: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    case: Mapped[CaseRow] = relationship(back_populates="persons")
    accounts: Mapped[list["AccountRow"]] = relationship(back_populates="person", cascade="all, delete-orphan")


class AccountRow(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("persons.id"), index=True)
    bank: Mapped[str] = mapped_column(String)
    account_type: Mapped[str] = mapped_column(String)
    account_number: Mapped[str] = mapped_column(String)
    holder_name: Mapped[str] = mapped_column(String)
    currency: Mapped[str] = mapped_column(String, default="INR")
    transaction_count: Mapped[int] = mapped_column(Integer, default=0)
    has_warnings: Mapped[bool] = mapped_column(Boolean, default=False)

    person: Mapped[PersonRow] = relationship(back_populates="accounts")
    statements: Mapped[list["StatementRow"]] = relationship(back_populates="account", cascade="all, delete-orphan")


class StatementRow(Base):
    __tablename__ = "statements"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    source_file_name: Mapped[str] = mapped_column(String)
    source_file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    period_start: Mapped[str] = mapped_column(String)
    period_end: Mapped[str] = mapped_column(String)
    opening_balance: Mapped[float] = mapped_column(Float, default=0.0)
    closing_balance: Mapped[float] = mapped_column(Float, default=0.0)
    extracted_txn_count: Mapped[int] = mapped_column(Integer, default=0)
    sum_check_debits_pct: Mapped[float] = mapped_column(Float, default=100.0)
    sum_check_credits_pct: Mapped[float] = mapped_column(Float, default=100.0)
    uploaded_at: Mapped[str] = mapped_column(String)
    uploaded_by: Mapped[str] = mapped_column(String)

    account: Mapped[AccountRow] = relationship(back_populates="statements")
    transactions: Mapped[list["TransactionRow"]] = relationship(back_populates="statement", cascade="all, delete-orphan")


class TransactionRow(Base):
    __tablename__ = "transactions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    statement_id: Mapped[str] = mapped_column(ForeignKey("statements.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    row_index: Mapped[int] = mapped_column(Integer)
    txn_date: Mapped[str] = mapped_column(String, index=True)
    amount: Mapped[float] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String)       # Dr / Cr
    running_balance: Mapped[float] = mapped_column(Float)
    raw_description: Mapped[str] = mapped_column(String)
    entities_json: Mapped[str] = mapped_column(String, default="{}")   # Dict[str, EntityValue]
    tags_json: Mapped[str] = mapped_column(String, default="[]")       # list[str]
    confidence: Mapped[str] = mapped_column(String, default="high")
    flags_json: Mapped[str] = mapped_column(String, default="[]")
    review_status: Mapped[str] = mapped_column(String, default="unreviewed")
    edit_count: Mapped[int] = mapped_column(Integer, default=0)

    statement: Mapped[StatementRow] = relationship(back_populates="transactions")


class EditEventRow(Base):
    __tablename__ = "edit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True)
    actor: Mapped[str] = mapped_column(String, default="unknown")
    field: Mapped[str] = mapped_column(String)
    old_value: Mapped[str] = mapped_column(String)
    new_value: Mapped[str] = mapped_column(String)
    at: Mapped[str] = mapped_column(String)


def init_db(reset: bool = False) -> None:
    """Create tables if they don't exist. If `reset=True`, drops first.

    Passing `LEDGERFLOW_RESET_DB=1` at process start also resets.
    """
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return SessionLocal()
