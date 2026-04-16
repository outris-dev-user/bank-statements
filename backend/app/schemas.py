"""Pydantic schemas — mirror the frontend's TypeScript types in src/app/data/mockData.ts.

These are the contract between FastAPI and the frontend. Keep in sync with
the TypeScript interfaces; the fields should align exactly.
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


class EntityValue(BaseModel):
    value: str
    source: Literal["extracted", "user_edited", "auto_resolved"]
    confidence: float


Direction = Literal["Dr", "Cr"]
Confidence = Literal["high", "medium", "low"]
ReviewStatus = Literal["unreviewed", "reviewed", "flagged"]
AccountType = Literal["SA", "CA", "CC", "OD"]
CaseStatus = Literal["active", "archived", "closed"]


class Case(BaseModel):
    id: str
    fir_number: str
    title: str
    officer_name: str
    status: CaseStatus
    created_at: str
    updated_at: str
    statement_count: int = 0
    transaction_count: int = 0
    flag_count: int = 0


class Person(BaseModel):
    id: str
    case_id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    pan: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class Account(BaseModel):
    id: str
    person_id: str
    bank: str
    account_type: AccountType
    account_number: str
    holder_name: str
    currency: str = "INR"
    transaction_count: int = 0
    has_warnings: bool = False


class Statement(BaseModel):
    id: str
    account_id: str
    source_file_name: str
    period_start: str
    period_end: str
    opening_balance: float = 0.0
    closing_balance: float = 0.0
    extracted_txn_count: int = 0
    sum_check_debits_pct: float = 100.0
    sum_check_credits_pct: float = 100.0
    uploaded_at: str
    uploaded_by: str


class Transaction(BaseModel):
    id: str
    statement_id: str
    account_id: str
    case_id: str
    row_index: int
    txn_date: str
    amount: float
    direction: Direction
    running_balance: float
    raw_description: str
    entities: dict[str, EntityValue] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    confidence: Confidence = "high"
    flags: list[str] = Field(default_factory=list)
    review_status: ReviewStatus = "unreviewed"
    edit_count: int = 0


class TransactionPatch(BaseModel):
    """Body for PATCH /api/transactions/:id — partial update."""
    entities: Optional[dict[str, EntityValue]] = None
    tags: Optional[list[str]] = None
    amount: Optional[float] = None
    direction: Optional[Direction] = None
    txn_date: Optional[str] = None
    review_status: Optional[ReviewStatus] = None


class CaseDetail(BaseModel):
    """Composite payload for GET /api/cases/:id — case + persons + accounts."""
    case: Case
    persons: list[Person]
    accounts: list[Account]


class TransactionPage(BaseModel):
    """Paginated list for GET /api/cases/:id/transactions."""
    total: int
    offset: int
    limit: int
    items: list[Transaction]


class MonthlyPoint(BaseModel):
    month: str          # YYYY-MM
    dr_total: float
    cr_total: float
    count: int


class TopCounterparty(BaseModel):
    name: str
    count: int
    total_dr: float
    total_cr: float


class CategoryBreakdown(BaseModel):
    category: str
    count: int
    total_dr: float
    total_cr: float


class Entity(BaseModel):
    """Resolved counterparty entity — one per distinct real-world party."""
    id: str
    case_id: str
    name: str
    canonical_key: str
    entity_type: str = "counterparty"
    pan: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    linked_person_id: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)
    created_at: str
    auto_created: bool = True
    txn_count: int = 0
    total_dr: float = 0.0
    total_cr: float = 0.0


class EntityDetail(BaseModel):
    entity: Entity
    transactions: list[Transaction]


class EntityLinkRequest(BaseModel):
    entity_id: str
    role: str = "counterparty"


class EntityCreate(BaseModel):
    name: str
    entity_type: str = "counterparty"
    pan: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    linked_person_id: Optional[str] = None


class CaseSummary(BaseModel):
    """Payload for GET /api/cases/:id/summary."""
    total_dr: float
    total_cr: float
    net: float
    txn_count: int
    flag_count: int
    reviewed_count: int
    unreviewed_count: int
    flagged_count: int
    monthly: list[MonthlyPoint]
    top_counterparties: list[TopCounterparty]
    categories: list[CategoryBreakdown]
