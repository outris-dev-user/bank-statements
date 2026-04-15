# Data model

Derived from the UX decisions in [ux-decisions.md](ux-decisions.md) and the wireframes in [ux-wireframes.md](ux-wireframes.md). This is the shape the backend persistence and the API should adopt for Phase 1.

## Core entities

```
Case
 └─ Person [0..n]
     └─ Account [0..n]
         └─ Statement [0..n]     (one uploaded PDF = one Statement)
             └─ Transaction [0..n]
                 └─ entities: Map<EntityTypeName, EntityValue>
                 └─ tags: Set<TagName>
                 └─ audit_log: List<EditEvent>
```

Key shape: every `Transaction` owns a flexible `entities` map — not fixed columns for counterparty/category — which lets new entity types be added without schema migration.

---

## Case

One investigation. A case can span multiple persons and multiple accounts.

```python
class Case:
    id: UUID
    fir_number: str                  # required; primary user-facing identifier
    title: str                       # short description
    officer_name: str
    status: Literal["active", "archived", "closed"]
    created_at: datetime
    updated_at: datetime
    created_by: UserId
    # denormalised counts for list view
    statement_count: int
    transaction_count: int
    flag_count: int
```

**Why persons are children of Case, not the other way around:** one case investigating Suraj + his wife + his company. Conversely, one person may appear in multiple cases (Suraj as defendant in case A, witness in case B). Same-person-across-cases is a Phase 4 concern (cross-case intelligence).

## Person

A human (or legal entity) whose statements are under investigation.

```python
class Person:
    id: UUID
    case_id: UUID                    # person is scoped to a case
    name: str                        # canonical name (user-editable)
    aliases: List[str]               # other names seen in statements
    pan: Optional[str]
    aadhaar_masked: Optional[str]
    phone: Optional[str]
    notes: Optional[str]
    created_at: datetime
```

**Why person is scoped to a case, not global:** a person in case A and a person in case B with the same name might or might not be the same human. Global entity resolution is deferred. Within a case, entity resolution is feasible (user curates their own case).

## Account

A bank account (or credit card) held by a person.

```python
class Account:
    id: UUID
    person_id: UUID
    bank: str                        # "HDFC", "ICICI", "Kotak", …
    account_type: Literal["SA", "CA", "CC", "OD", "LOAN", "OTHER"]
    account_number: str              # can be masked "****8420"
    ifsc: Optional[str]
    holder_name: str                 # as printed on the statement
    currency: str                    # default "INR"
    created_at: datetime
```

**Why account is its own entity (not just a field on Transaction):** enables the tab-per-account UX, per-account running balance, per-account aggregates. Also the correct locus for "re-upload this file" operations.

## Statement

A single uploaded PDF = one Statement row.

```python
class Statement:
    id: UUID
    account_id: UUID
    source_file_name: str            # original filename
    source_file_hash: str            # sha256, enables dedup
    source_file_path: str            # where the PDF is stored
    period_start: date
    period_end: date
    opening_balance: Decimal
    closing_balance: Decimal
    declared_total_debits: Decimal
    declared_total_credits: Decimal
    declared_txn_count: Optional[int]
    # extraction results
    extracted_txn_count: int
    sum_check_debits_pct: float      # e.g. 100.0 = perfect
    sum_check_credits_pct: float
    extraction_status: Literal["pending", "parsed", "verified", "reextracting"]
    extractor_version: str           # which parser commit produced this
    uploaded_at: datetime
    uploaded_by: UserId
```

**Why the hash:** user uploads a file twice by accident → we detect + reject. Also enables "re-extract" semantics: same file, newer parser → replace transactions, bump `extractor_version`.

## Transaction

The row.

```python
class Transaction:
    id: UUID
    statement_id: UUID               # which PDF it came from
    account_id: UUID                 # denormalised for cross-statement queries
    case_id: UUID                    # denormalised
    # positional / core financial fields
    row_index: int                   # position within statement for stable sort
    txn_date: date
    value_date: Optional[date]
    amount: Decimal                  # always positive
    direction: Literal["Dr", "Cr"]
    running_balance: Decimal
    raw_description: str             # unmodified OCR text
    # flexible entities — the key-value store
    entities: Dict[EntityTypeName, EntityValue]
    tags: Set[TagName]
    # edit & review state
    confidence: Literal["high", "medium", "low"]
    flags: List[FlagKind]            # [SUM_CHECK_CONTRIBUTOR, NEEDS_REVIEW, …]
    review_status: Literal["unreviewed", "reviewed", "flagged"]
    edit_count: int
    # relationships
    linked_counterparty_entity_id: Optional[UUID]   # → CounterpartyEntity
    # audit
    created_at: datetime
    updated_at: datetime
```

**`amount` is always positive, direction separate.** Makes aggregation math trivial (sum by direction). Signed amount for display only.

**`raw_description` never changes.** Edits go to `entities`. This keeps an auditable OCR trail.

---

## The key-value entity model

The core architectural choice. Each transaction carries a dict of entities, where the key is an entity *type* (e.g. `"counterparty"`, `"channel"`, `"category"`, `"ref_number"`, `"location"`) and the value is an `EntityValue`.

```python
class EntityValue:
    value: str                       # the actual content: "CRED", "UPI", "Finance"
    source: Literal["extracted", "user_edited", "auto_resolved"]
    confidence: float                # 0.0 - 1.0
    linked_entity_id: Optional[UUID] # link to shared CanonicalEntity (e.g. person, merchant)
```

Example transaction's entities:
```json
{
  "channel":       {"value": "UPI",     "source": "extracted",    "confidence": 1.0},
  "counterparty":  {"value": "CRED",    "source": "extracted",    "confidence": 0.85, "linked_entity_id": "e7b2..."},
  "category":      {"value": "Finance", "source": "auto_resolved","confidence": 0.70},
  "ref_number":    {"value": "109108427041", "source": "extracted", "confidence": 1.0}
}
```

### Entity types (registered, extensible)

Entity types live in their own registry:

```python
class EntityType:
    name: str                        # "counterparty", "channel", "category", …
    display_name: str                # "Counterparty"
    is_promoted: bool                # True → shown as a column in the table
    is_user_defined: bool            # True → user created this type; False → system
    value_enum: Optional[List[str]]  # if present, value must be one of these (enum)
    icon: Optional[str]              # for display
    color: Optional[str]             # for chips
    scope: Literal["system", "case", "user"]   # where this type lives
```

**System-level types (pre-registered):**
- `channel` — enum: UPI / NEFT / IMPS / RTGS / ATM / POS / Cheque / Cash / Other
- `counterparty` — free text; can link to a `CanonicalEntity`
- `category` — starts with defaults (Food, Transfer, Salary, Rent, Shopping, Finance, Cash, Rewards, Other); users add new ones
- `ref_number` — free text
- `location` — free text

**Case-scope types:** user can add e.g. `"informant_code"` that only applies within their case.

**User-scope types:** across-case user preferences, e.g. `"risk_tier"`.

### Tags

Tags are a degenerate entity type — value-less, just a label applied to a row. Distinguishing feature: a row can have many tags but only one value per entity type.

```python
class Tag:
    name: str
    scope: Literal["system", "case", "user"]
    color: Optional[str]
```

**LEA-pattern tags** (e.g. "possible-hawala", "round-tripping", "suspicious-timing") are just user-scope tags. Users define them; surfacing them in filters/aggregates is built-in.

### Why not fixed columns for all these?

We considered having `counterparty`, `category`, `channel` as first-class `Transaction` fields. Three reasons we went key-value:

1. **Extensibility** — new entity types ("informant code", "shell-co marker", "trade-based-laundering vector") will emerge as LEA analysts use the tool. Adding a new column every time means schema migrations.
2. **User customisation** — users defining their own categories or tags is the explicit requirement. Not possible with a fixed schema.
3. **Sparse values** — most transactions have `channel + counterparty + category`. Only some have `location` or `location_city`. Fixed columns waste space; key-value is natural for optional fields.

**What we get as columns anyway:** the UI promotes a few entity types (Counterparty, Category) into the main table display based on `EntityType.is_promoted`. Changing which types are promoted is a user preference, not a schema change.

---

## Canonical entities (cross-row, within a case)

When the user links multiple rows to "the same CRED", they're creating a `CanonicalEntity` for that counterparty.

```python
class CanonicalEntity:
    id: UUID
    case_id: UUID
    kind: Literal["counterparty", "person", "merchant", "cash", "external"]
    name: str
    aliases: List[str]
    # structured identifiers (any of these)
    upi_vpa: Optional[str]
    account_number: Optional[str]
    ifsc: Optional[str]
    phone: Optional[str]
    pan: Optional[str]
    # relationships
    linked_person_id: Optional[UUID]   # if this counterparty IS a person in the case
    tags: Set[TagName]
    created_at: datetime
```

**Entity resolution model:**
- **Auto-merge rule:** two `CanonicalEntity` records with the same `upi_vpa` OR `account_number` OR `phone` → auto-merge into one.
- **Suggest-merge rule:** two records with similar `name` (fuzzy match above threshold) but no structured identifier overlap → prompt user.
- **Manual link:** user explicitly links an unresolved `(unknown: 3511…)` transaction counterparty to a `CanonicalEntity`.

**Bulk accept for suggestions:** when a user links one row, the system scans for other rows with the same counterparty value and offers "Apply to 3 other rows?" — matching the UX in Screen 3b.

---

## Audit log

One entry per edit.

```python
class EditEvent:
    id: UUID
    transaction_id: UUID
    actor_user_id: UserId
    timestamp: datetime
    field: str                       # "amount", "entities.counterparty", "tags+", …
    old_value: str                   # serialised
    new_value: str                   # serialised
    reason: Optional[str]            # free-text rationale; optional in Phase 1
```

Phase 1 ships **minimal** — user + timestamp + field + old/new. Forensic-grade (hash chain, signed diffs) is a Phase 3 concern.

**Retention:** permanent within a case. Deleting a statement also deletes its audit log (cascaded).

---

## Flags

Flags are system-assigned (by parser, sum-check, or pattern detection). Users can also flag manually via `review_status = "flagged"`.

System flag kinds (initial set):
- `SUM_CHECK_CONTRIBUTOR` — this row's amount contributed to a sum-check mismatch
- `NEEDS_REVIEW` — low confidence on extraction
- `PARSER_WARNING` — parser fell back to a heuristic
- `LARGE_AMOUNT` — exceeds case-level threshold
- `UNUSUAL_HOUR` — timestamp at odd hour (if we capture time)
- `DUPLICATE_SUSPECT` — looks like a duplicate of another row

Phase 2 adds pattern-detector flags:
- `ROUND_AMOUNT`
- `JUST_BELOW_THRESHOLD`
- `SAME_DAY_FAN_OUT`
- `DORMANT_ACTIVATION`

Flags are cheap — compute them once during extraction, persist them, filter by them.

---

## Summary — the schema in one glance

```
Case (1) ──< (n) Person (1) ──< (n) Account (1) ──< (n) Statement (1) ──< (n) Transaction
                                                                                │
                                                                  entities: Map ├─→ EntityValue
                                                                  tags:     Set │
                                                                  audit:    List├─→ EditEvent
                                                                  canonical_id  └─→ CanonicalEntity (case-scoped)

EntityType registry (system + case-scope + user-scope)
Tag registry        (system + case-scope + user-scope)
```

## Implementation notes

1. **Backend stack:** Phase 1 targets SQLite (offline) + Postgres (SaaS) behind SQLAlchemy. The `entities` dict can be a JSON column in both.

2. **Entity type registry** lives in its own table, seeded with system types on first boot. Case-scoped types are soft-linked to the Case.

3. **Running balance is derived, not stored.** When a transaction's amount changes, recompute balances for all subsequent transactions in the same `statement_id` (or `account_id` for cross-statement views). Cache the result; invalidate on edit.

4. **The API surface** (Phase 1, rough):
   - `GET /cases`, `POST /cases`, `PATCH /cases/:id`
   - `GET /cases/:id/persons`, `POST /cases/:id/persons`
   - `POST /persons/:id/accounts`
   - `POST /accounts/:id/statements` (multipart upload; returns extraction progress stream)
   - `GET /statements/:id/transactions` (paginated; supports filters)
   - `PATCH /transactions/:id` (field-level; writes to audit log)
   - `POST /transactions/bulk` (for bulk tag / entity updates)
   - `GET /cases/:id/canonical-entities`, `POST /cases/:id/canonical-entities/merge`

5. **Phase 1 does NOT ship:**
   - Graph queries (Phase 3)
   - Algorithm pipelines (Phase 2+)
   - Cross-case queries (Phase 4)
