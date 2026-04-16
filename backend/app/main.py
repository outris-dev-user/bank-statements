"""LedgerFlow FastAPI stub.

Phase 1 surface — read-only enough to replace the frontend's static
realData.ts with live HTTP calls, plus a PATCH endpoint so the
EditDrawer's Save button can actually persist.

Routes:
  GET  /api/cases
  GET  /api/cases/{case_id}
  GET  /api/cases/{case_id}/transactions   (paginated)
  GET  /api/statements/{statement_id}
  PATCH /api/transactions/{txn_id}
  GET  /api/health

Not yet implemented (deliberately — see STATUS.md Phase 1 next steps):
  POST /api/cases/{case_id}/statements     (multipart upload + parse)
  POST /api/cases                          (create case)

Run:
    cd backend
    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    Case, CaseDetail, Transaction, TransactionPage, TransactionPatch, Statement,
)
from app.store import store

app = FastAPI(
    title="LedgerFlow",
    version="0.1.0",
    description="Forensic bank-statement analysis backend.",
)

# Allow the Vite dev server (and a reasonable production origin later) to call us
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "cases": len(store.cases),
        "persons": len(store.persons),
        "accounts": len(store.accounts),
        "statements": len(store.statements),
        "transactions": len(store.transactions),
    }


@app.get("/api/cases", response_model=list[Case])
def list_cases() -> list[Case]:
    return list(store.cases.values())


@app.get("/api/cases/{case_id}", response_model=CaseDetail)
def get_case(case_id: str) -> CaseDetail:
    case = store.cases.get(case_id)
    if not case:
        raise HTTPException(404, f"Case {case_id} not found")
    persons = [p for p in store.persons.values() if p.case_id == case_id]
    person_ids = {p.id for p in persons}
    accounts = [a for a in store.accounts.values() if a.person_id in person_ids]
    return CaseDetail(case=case, persons=persons, accounts=accounts)


@app.get("/api/cases/{case_id}/transactions", response_model=TransactionPage)
def list_case_transactions(
    case_id: str,
    account_id: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> TransactionPage:
    if case_id not in store.cases:
        raise HTTPException(404, f"Case {case_id} not found")
    all_txns = [t for t in store.transactions.values() if t.case_id == case_id]
    if account_id:
        all_txns = [t for t in all_txns if t.account_id == account_id]
    # stable order: row_index within statement, then statement_id
    all_txns.sort(key=lambda t: (t.statement_id, t.row_index))
    return TransactionPage(
        total=len(all_txns),
        offset=offset,
        limit=limit,
        items=all_txns[offset : offset + limit],
    )


@app.get("/api/statements/{statement_id}", response_model=Statement)
def get_statement(statement_id: str) -> Statement:
    stmt = store.statements.get(statement_id)
    if not stmt:
        raise HTTPException(404, f"Statement {statement_id} not found")
    return stmt


@app.patch("/api/transactions/{txn_id}", response_model=Transaction)
def patch_transaction(txn_id: str, patch: TransactionPatch) -> Transaction:
    txn = store.transactions.get(txn_id)
    if not txn:
        raise HTTPException(404, f"Transaction {txn_id} not found")

    # Build audit records before mutation
    events = store.audit.setdefault(txn_id, [])
    now = datetime.utcnow().isoformat(timespec="seconds")
    for field, new_val in patch.model_dump(exclude_unset=True).items():
        old_val = getattr(txn, field)
        events.append({
            "field": field,
            "old": str(old_val)[:200],
            "new": str(new_val)[:200],
            "at": now,
            "by": "unknown",  # auth wiring comes later
        })

    # Apply mutation
    if patch.entities is not None:
        txn.entities = patch.entities
    if patch.tags is not None:
        txn.tags = patch.tags
    if patch.amount is not None:
        txn.amount = patch.amount
    if patch.txn_date is not None:
        txn.txn_date = patch.txn_date
    if patch.review_status is not None:
        txn.review_status = patch.review_status

    txn.edit_count += 1
    return txn


@app.get("/api/transactions/{txn_id}/audit")
def get_transaction_audit(txn_id: str) -> list[dict]:
    if txn_id not in store.transactions:
        raise HTTPException(404, f"Transaction {txn_id} not found")
    return store.audit.get(txn_id, [])
