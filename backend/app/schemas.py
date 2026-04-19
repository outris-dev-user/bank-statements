"""Pydantic schemas — mirror the frontend's TypeScript types in src/app/data/mockData.ts.

These are the contract between FastAPI and the frontend. Keep in sync with
the TypeScript interfaces; the fields should align exactly.
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


class EntityValue(BaseModel):
    value: str
    # `source` tracks where a field came from so the UI can show provenance
    # and the overlay pipeline can be audited:
    #   extracted    — deterministic regex parser or a direct PDF field match
    #   user_edited  — investigator edited this value in the UI
    #   auto_resolved — inferred downstream (e.g. entity clustering)
    #   llm_overlay  — Claude/Gemini cleaned up a noisy deterministic value
    #                  (e.g. card-number-polluted HDFC POS narrations)
    source: Literal["extracted", "user_edited", "auto_resolved", "llm_overlay"]
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


EntityTypeLiteral = Literal[
    "individual", "business", "bank", "government",
    "related_party", "self", "unknown",
    "merchant", "counterparty",  # legacy values still on older entities
]


class AnomalyFinding(BaseModel):
    """One row from the LLM's statement-level anomaly scan. `txn_indices`
    are 0-based positions in the `transactions` array when the LLM produced
    this; clients may want to map them back to real transaction ids."""
    type: str
    severity: Literal["high", "medium", "low"]
    description: str
    txn_indices: list[int] = Field(default_factory=list)


class StatementIntegrity(BaseModel):
    looks_complete: Optional[bool] = None
    gaps_noticed: Optional[str] = None


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
    # Statement-level LLM analysis — all optional, populated only when an
    # LLM call succeeded during extraction.
    narrative_summary: Optional[str] = None
    anomalies: list[AnomalyFinding] = Field(default_factory=list)
    risk_level: Optional[Literal["high", "medium", "low"]] = None
    statement_integrity: Optional[StatementIntegrity] = None
    # sha256 of the source PDF (for duplicate-upload detection).
    file_hash: Optional[str] = None


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
    # LLM-supplied per-txn signals. Nullable; populated only when an LLM
    # call produced them (overlay path or pure-LLM fallback).
    llm_entity_type: Optional[EntityTypeLiteral] = None
    is_self_transfer: Optional[bool] = None
    notable_reason: Optional[str] = None


class TransactionPatch(BaseModel):
    """Body for PATCH /api/transactions/:id — partial update."""
    entities: Optional[dict[str, EntityValue]] = None
    tags: Optional[list[str]] = None
    amount: Optional[float] = None
    direction: Optional[Direction] = None
    txn_date: Optional[str] = None
    review_status: Optional[ReviewStatus] = None


class CaseDetail(BaseModel):
    """Composite payload for GET /api/cases/:id — case + persons + accounts + statements."""
    case: Case
    persons: list[Person]
    accounts: list[Account]
    statements: list[Statement] = Field(default_factory=list)


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


class PatternHit(BaseModel):
    """One forensic pattern's aggregate result across the case."""
    name: str             # e.g. "STRUCTURING_SUSPECTED"
    label: str            # human-readable display name
    description: str
    severity: str         # "low" / "medium" / "high"
    count: int            # number of transactions with this flag
    sample_txn_ids: list[str] = Field(default_factory=list)


class GraphNode(BaseModel):
    id: str                 # namespaced: "person:p1" / "account:a1" / "entity:e12"
    label: str
    type: Literal["person", "account", "entity"]
    size: int = 1           # for visual weighting — derived from txn count
    meta: dict = Field(default_factory=dict)


class GraphEdgeSample(BaseModel):
    id: str
    txn_date: str
    amount: float
    direction: Literal["Dr", "Cr"]
    raw_description: str


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: Literal["owns", "flow_in", "flow_out"]
    total_amount: float = 0.0
    txn_count: int = 0
    # ISO date of the first and last contributing txn. Used by the canvas
    # date-range filter to include/exclude edges by their activity window.
    # Empty for `owns` edges (no transactions).
    date_min: str = ""
    date_max: str = ""
    sample_txn_ids: list[str] = Field(default_factory=list)
    sample_txns: list[GraphEdgeSample] = Field(default_factory=list)


class CaseGraph(BaseModel):
    case_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    # Monthly txn activity buckets ("2024-03" → count), used by the canvas
    # date-range filter's mini bar chart. Sorted chronologically.
    monthly_activity: list[dict] = Field(default_factory=list)


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
    patterns: list[PatternHit] = Field(default_factory=list)
