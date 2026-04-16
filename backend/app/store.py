"""SQLite-backed store.

Public API mirrors what main.py needs:

    store.list_cases() -> list[Case]
    store.get_case(case_id) -> CaseDetail | None
    store.list_case_transactions(case_id, account_id=None, offset=0, limit=100)
    store.get_statement(statement_id) -> Statement | None
    store.get_transaction(txn_id) -> Transaction | None
    store.patch_transaction(txn_id, patch) -> Transaction | None
    store.list_transaction_audit(txn_id) -> list[AuditEvent]
    store.create_case(fir_number, title, officer_name) -> Case
    store.ingest_statement(case_id, person_id, pdf_path, ...) -> (Statement, list[Transaction])
    store.seed_from_benchmarks()   # idempotent — re-runs the static seed if tables are empty

Data flows through Pydantic schemas at every external boundary; the
ORM rows stay inside this module.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from app.db import (
    Base, engine, get_session,
    CaseRow, PersonRow, AccountRow, StatementRow, TransactionRow, EditEventRow,
    EntityRow, TransactionEntityLinkRow,
    init_db,
)
from app.schemas import (
    Case, Person, Account, Statement, Transaction, EntityValue,
    CaseDetail, TransactionPage, TransactionPatch,
    CaseSummary, MonthlyPoint, TopCounterparty, CategoryBreakdown, PatternHit,
    Entity, EntityDetail, EntityCreate,
)


PATTERN_META = {
    "STRUCTURING_SUSPECTED": {
        "label": "Structuring suspected",
        "description": "≥3 transactions between ₹9L and ₹10L within 30 days — classic attempt to dodge FIU-IND CTR reporting.",
        "severity": "high",
    },
    "VELOCITY_SPIKE": {
        "label": "Velocity spike",
        "description": "≥10 transactions within a 24-hour window on the same account.",
        "severity": "medium",
    },
    "ROUND_AMOUNT_CLUSTER": {
        "label": "Round-amount cluster",
        "description": "≥5 transactions of round amounts (multiples of ₹10k or ₹50k) on the same account.",
        "severity": "medium",
    },
    "SUM_CHECK_CONTRIBUTOR": {
        "label": "Sum-check contributor",
        "description": "Transaction contributes to a mismatch between declared and extracted totals.",
        "severity": "low",
    },
    "NEEDS_REVIEW": {
        "label": "Needs manual review",
        "description": "Counterparty or channel couldn't be extracted with confidence.",
        "severity": "low",
    },
}


# ───── row → schema conversion ─────

def _case_row_to_schema(row: CaseRow, counts: Optional[dict] = None) -> Case:
    counts = counts or {}
    return Case(
        id=row.id,
        fir_number=row.fir_number,
        title=row.title,
        officer_name=row.officer_name,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        statement_count=counts.get("statements", 0),
        transaction_count=counts.get("transactions", 0),
        flag_count=counts.get("flags", 0),
    )


def _person_row_to_schema(row: PersonRow) -> Person:
    return Person(
        id=row.id, case_id=row.case_id, name=row.name,
        aliases=json.loads(row.aliases_json or "[]"),
        pan=row.pan, phone=row.phone, notes=row.notes,
    )


def _account_row_to_schema(row: AccountRow) -> Account:
    return Account(
        id=row.id, person_id=row.person_id, bank=row.bank,
        account_type=row.account_type, account_number=row.account_number,
        holder_name=row.holder_name, currency=row.currency,
        transaction_count=row.transaction_count, has_warnings=row.has_warnings,
    )


def _statement_row_to_schema(row: StatementRow) -> Statement:
    return Statement(
        id=row.id, account_id=row.account_id,
        source_file_name=row.source_file_name,
        period_start=row.period_start, period_end=row.period_end,
        opening_balance=row.opening_balance,
        closing_balance=row.closing_balance,
        extracted_txn_count=row.extracted_txn_count,
        sum_check_debits_pct=row.sum_check_debits_pct,
        sum_check_credits_pct=row.sum_check_credits_pct,
        uploaded_at=row.uploaded_at, uploaded_by=row.uploaded_by,
    )


def _txn_row_to_schema(row: TransactionRow) -> Transaction:
    entities_raw = json.loads(row.entities_json or "{}")
    entities = {k: EntityValue(**v) for k, v in entities_raw.items()}
    return Transaction(
        id=row.id, statement_id=row.statement_id, account_id=row.account_id,
        case_id=row.case_id, row_index=row.row_index, txn_date=row.txn_date,
        amount=row.amount, direction=row.direction, running_balance=row.running_balance,
        raw_description=row.raw_description, entities=entities,
        tags=json.loads(row.tags_json or "[]"),
        confidence=row.confidence,
        flags=json.loads(row.flags_json or "[]"),
        review_status=row.review_status, edit_count=row.edit_count,
    )


# ───── per-case aggregate counts ─────

def _case_counts(session, case_id: str) -> dict:
    from sqlalchemy import func, select
    stmt_count = session.scalar(
        select(func.count(StatementRow.id)).join(AccountRow, StatementRow.account_id == AccountRow.id)
        .join(PersonRow, AccountRow.person_id == PersonRow.id)
        .where(PersonRow.case_id == case_id)
    ) or 0
    txn_count = session.scalar(
        select(func.count(TransactionRow.id)).where(TransactionRow.case_id == case_id)
    ) or 0
    # flags: count transactions with non-empty flags_json
    flag_txns = session.execute(
        select(TransactionRow.flags_json).where(TransactionRow.case_id == case_id)
    ).scalars().all()
    flag_count = sum(len(json.loads(f or "[]")) for f in flag_txns)
    return {"statements": stmt_count, "transactions": txn_count, "flags": flag_count}


# ───── public API ─────

def list_cases() -> list[Case]:
    with get_session() as s:
        rows = s.query(CaseRow).all()
        return [_case_row_to_schema(r, _case_counts(s, r.id)) for r in rows]


def get_case(case_id: str) -> Optional[CaseDetail]:
    with get_session() as s:
        row = s.get(CaseRow, case_id)
        if not row:
            return None
        persons = s.query(PersonRow).filter_by(case_id=case_id).all()
        person_ids = [p.id for p in persons]
        accounts = s.query(AccountRow).filter(AccountRow.person_id.in_(person_ids)).all() if person_ids else []
        return CaseDetail(
            case=_case_row_to_schema(row, _case_counts(s, case_id)),
            persons=[_person_row_to_schema(p) for p in persons],
            accounts=[_account_row_to_schema(a) for a in accounts],
        )


def list_case_transactions(
    case_id: str, account_id: Optional[str] = None, offset: int = 0, limit: int = 100,
) -> Optional[TransactionPage]:
    with get_session() as s:
        if not s.get(CaseRow, case_id):
            return None
        q = s.query(TransactionRow).filter_by(case_id=case_id)
        if account_id:
            q = q.filter_by(account_id=account_id)
        q = q.order_by(TransactionRow.statement_id.asc(), TransactionRow.row_index.asc())
        total = q.count()
        items = q.offset(offset).limit(limit).all()
        return TransactionPage(
            total=total, offset=offset, limit=limit,
            items=[_txn_row_to_schema(r) for r in items],
        )


def get_statement(statement_id: str) -> Optional[Statement]:
    with get_session() as s:
        row = s.get(StatementRow, statement_id)
        return _statement_row_to_schema(row) if row else None


def get_statement_pdf_path(statement_id: str) -> Optional[tuple[str, str]]:
    """Return (absolute_path, filename) for a statement's source PDF, or None."""
    with get_session() as s:
        row = s.get(StatementRow, statement_id)
        if not row or not row.source_file_path:
            return None
        return row.source_file_path, row.source_file_name


def get_transaction(txn_id: str) -> Optional[Transaction]:
    with get_session() as s:
        row = s.get(TransactionRow, txn_id)
        return _txn_row_to_schema(row) if row else None


def _signed(amount: float, direction: str) -> float:
    return float(amount) if direction == "Cr" else -float(amount)


def patch_transaction(txn_id: str, patch: TransactionPatch) -> Optional[Transaction]:
    with get_session() as s:
        row = s.get(TransactionRow, txn_id)
        if not row:
            return None
        now = datetime.utcnow().isoformat(timespec="seconds")
        updates = patch.model_dump(exclude_unset=True)

        # Capture pre-update amount/direction so we can compute a balance delta
        # if either changes. Cascade uses the PDF-display order (row_index
        # ascending) so running balances stay consistent with what the bank
        # printed — some banks print latest-first, others oldest-first.
        pre_amount = float(row.amount)
        pre_direction = row.direction

        for field, new_val in updates.items():
            if field == "entities":
                old_val = row.entities_json
                new_json = {k: v.model_dump() if hasattr(v, "model_dump") else v for k, v in new_val.items()}
                row.entities_json = json.dumps(new_json)
            elif field == "tags":
                old_val = row.tags_json
                row.tags_json = json.dumps(new_val)
            elif field == "amount":
                old_val = str(row.amount)
                row.amount = float(new_val)
            elif field == "direction":
                old_val = row.direction
                row.direction = new_val
            elif field == "txn_date":
                old_val = row.txn_date
                row.txn_date = new_val
            elif field == "review_status":
                old_val = row.review_status
                row.review_status = new_val
            else:
                continue
            s.add(EditEventRow(
                transaction_id=txn_id, actor="unknown",
                field=field, old_value=str(old_val)[:500], new_value=str(new_val)[:500], at=now,
            ))
        row.edit_count += 1

        delta = _signed(row.amount, row.direction) - _signed(pre_amount, pre_direction)
        if delta != 0:
            _shift_balances_from(s, row.statement_id, row.row_index, delta)

        s.commit()
        s.refresh(row)
        return _txn_row_to_schema(row)


def _shift_balances_from(session, statement_id: str, from_row_index: int, delta: float) -> None:
    """Apply `delta` to running_balance on the row at `from_row_index` and
    every row after it (row_index ascending) in the statement. Preserves the
    walk direction the PDF used, so it works whether the statement is printed
    oldest-first or latest-first.
    """
    if delta == 0:
        return
    txns = (
        session.query(TransactionRow)
        .filter(TransactionRow.statement_id == statement_id)
        .filter(TransactionRow.row_index >= from_row_index)
        .all()
    )
    for t in txns:
        t.running_balance = float(t.running_balance) + delta
    stmt = session.get(StatementRow, statement_id)
    if stmt is not None:
        stmt.closing_balance = float(stmt.closing_balance) + delta


def list_transaction_audit(txn_id: str) -> Optional[list[dict]]:
    with get_session() as s:
        if not s.get(TransactionRow, txn_id):
            return None
        events = s.query(EditEventRow).filter_by(transaction_id=txn_id).order_by(EditEventRow.id.asc()).all()
        return [
            {"field": e.field, "old": e.old_value, "new": e.new_value, "at": e.at, "by": e.actor}
            for e in events
        ]


# ───── entity resolution ─────

_ENTITY_STOP = {"upi", "neft", "imps", "rtgs", "pos", "atm", "ecs", "nach",
                 "cheque", "chq", "cash", "by", "to", "the", "ltd", "pvt",
                 "services", "service", "india", "pay", "payment", "inr", "rs"}


def _canonical_key(name: str) -> str:
    """Normalise a counterparty string to a stable matching key.

    Example: "AMZN PAY IN * AMAZON INDIA" -> "amazon india".
    The key is only for clustering — the display name stays whatever the
    user most recently edited or the most-frequent extracted variant.
    """
    import re as _re
    if not name:
        return ""
    s = name.lower()
    s = _re.sub(r"[^a-z0-9\s]", " ", s)
    tokens = [t for t in s.split() if t and t not in _ENTITY_STOP and not t.isdigit() and len(t) > 1]
    # Keep most-signal tokens: longest 3.
    tokens.sort(key=lambda t: (-len(t), t))
    key = " ".join(sorted(tokens[:3]))
    return key


def _entity_row_to_schema(row: EntityRow, stats: Optional[dict] = None) -> Entity:
    stats = stats or {}
    return Entity(
        id=row.id,
        case_id=row.case_id,
        name=row.name,
        canonical_key=row.canonical_key,
        entity_type=row.entity_type,
        pan=row.pan,
        phone=row.phone,
        notes=row.notes,
        linked_person_id=row.linked_person_id,
        aliases=json.loads(row.aliases_json or "[]"),
        created_at=row.created_at,
        auto_created=bool(row.auto_created),
        txn_count=stats.get("txn_count", 0),
        total_dr=round(stats.get("total_dr", 0.0), 2),
        total_cr=round(stats.get("total_cr", 0.0), 2),
    )


def _entity_stats(session, entity_id: str) -> dict:
    from sqlalchemy import select
    links = session.query(TransactionEntityLinkRow).filter_by(entity_id=entity_id).all()
    txn_ids = [l.transaction_id for l in links]
    if not txn_ids:
        return {"txn_count": 0, "total_dr": 0.0, "total_cr": 0.0}
    rows = session.query(TransactionRow).filter(TransactionRow.id.in_(txn_ids)).all()
    total_dr = sum(float(r.amount) for r in rows if r.direction == "Dr")
    total_cr = sum(float(r.amount) for r in rows if r.direction == "Cr")
    return {"txn_count": len(rows), "total_dr": total_dr, "total_cr": total_cr}


def resolve_entities_for_case(case_id: str) -> Optional[dict]:
    """Cluster transactions by canonical counterparty key into entities.
    Idempotent: re-running is safe — we update names/aliases, insert new
    entities for unseen keys, and keep old links in place.
    """
    with get_session() as s:
        if not s.get(CaseRow, case_id):
            return None
        txns = s.query(TransactionRow).filter_by(case_id=case_id).all()

        # group txn IDs by canonical key
        groups: dict[str, dict] = {}
        for r in txns:
            ents = json.loads(r.entities_json or "{}")
            cp = (ents.get("counterparty") or {}).get("value") or ""
            key = _canonical_key(cp)
            if not key:
                continue
            g = groups.setdefault(key, {"txn_ids": [], "names": {}, "aliases": set()})
            g["txn_ids"].append(r.id)
            g["names"][cp] = g["names"].get(cp, 0) + 1
            g["aliases"].add(cp)

        # upsert entities
        existing = {e.canonical_key: e for e in s.query(EntityRow).filter_by(case_id=case_id).all()}
        now = datetime.utcnow().isoformat(timespec="seconds")
        created = 0
        updated = 0

        for key, g in groups.items():
            most_common_name = max(g["names"].items(), key=lambda kv: kv[1])[0]
            aliases = sorted(a for a in g["aliases"] if a != most_common_name)

            ent = existing.get(key)
            if not ent:
                eid = _next_id(s, "e", EntityRow)
                ent = EntityRow(
                    id=eid, case_id=case_id, name=most_common_name, canonical_key=key,
                    entity_type="counterparty", aliases_json=json.dumps(aliases),
                    created_at=now, auto_created=True,
                )
                s.add(ent)
                s.flush()
                created += 1
            else:
                if ent.auto_created:
                    ent.name = most_common_name
                ent.aliases_json = json.dumps(aliases)
                updated += 1

            # ensure a link exists for every txn in the group
            existing_links = {
                l.transaction_id for l in s.query(TransactionEntityLinkRow)
                .filter_by(entity_id=ent.id, role="counterparty").all()
            }
            for tid in g["txn_ids"]:
                if tid not in existing_links:
                    s.add(TransactionEntityLinkRow(
                        transaction_id=tid, entity_id=ent.id, role="counterparty",
                    ))

        s.commit()

        # Second pass — merge auto-created entities whose canonical_keys are
        # substring-equivalent. Catches cases like AMAZON ⊂ AMAZONPAY where
        # token-equality alone leaves them separate.
        merged = _merge_substring_entities(case_id)
        return {
            "entities_created": created,
            "entities_updated": updated,
            "entities_merged": merged,
            "groups": len(groups),
        }


def _merge_substring_entities(case_id: str, min_key_len: int = 5) -> int:
    """Merge `auto_created` entities whose canonical_keys substring-match.
    The entity with more linked transactions wins; the other's name and
    aliases become its aliases, and all its links are rewired.
    Manual entities are never auto-merged.
    Returns the count of merged-away entities.
    """
    with get_session() as s:
        ents = s.query(EntityRow).filter_by(case_id=case_id).all()
        counts = {}
        for e in ents:
            counts[e.id] = s.query(TransactionEntityLinkRow).filter_by(entity_id=e.id).count()
        # Sort by count desc so big entities absorb smaller variants.
        ents.sort(key=lambda e: -counts.get(e.id, 0))
        absorbed: set[str] = set()
        merged = 0

        for i, winner in enumerate(ents):
            if winner.id in absorbed:
                continue
            w_key = (winner.canonical_key or "").replace(" ", "")
            if len(w_key) < min_key_len:
                continue
            winner_aliases = json.loads(winner.aliases_json or "[]")

            for j in range(i + 1, len(ents)):
                loser = ents[j]
                if loser.id in absorbed or not loser.auto_created:
                    continue
                l_key = (loser.canonical_key or "").replace(" ", "")
                if len(l_key) < min_key_len:
                    continue
                # Substring check both directions; prefer longer-substring-contains-shorter
                short, long = (l_key, w_key) if len(l_key) < len(w_key) else (w_key, l_key)
                if short in long:
                    # Rewire links from loser to winner (dedupe)
                    loser_links = s.query(TransactionEntityLinkRow).filter_by(entity_id=loser.id).all()
                    for link in loser_links:
                        existing = s.query(TransactionEntityLinkRow).filter_by(
                            entity_id=winner.id,
                            transaction_id=link.transaction_id,
                            role=link.role,
                        ).first()
                        if existing:
                            s.delete(link)
                        else:
                            link.entity_id = winner.id
                    # Merge names/aliases into winner
                    if loser.name and loser.name != winner.name and loser.name not in winner_aliases:
                        winner_aliases.append(loser.name)
                    for a in json.loads(loser.aliases_json or "[]"):
                        if a and a not in winner_aliases and a != winner.name:
                            winner_aliases.append(a)
                    s.delete(loser)
                    absorbed.add(loser.id)
                    merged += 1

            winner.aliases_json = json.dumps(winner_aliases)

        s.commit()
        return merged


def list_entities(case_id: str) -> Optional[list[Entity]]:
    with get_session() as s:
        if not s.get(CaseRow, case_id):
            return None
        rows = s.query(EntityRow).filter_by(case_id=case_id).all()
        return [_entity_row_to_schema(r, _entity_stats(s, r.id)) for r in rows]


def get_entity(entity_id: str) -> Optional[EntityDetail]:
    with get_session() as s:
        row = s.get(EntityRow, entity_id)
        if not row:
            return None
        links = s.query(TransactionEntityLinkRow).filter_by(entity_id=entity_id).all()
        txn_ids = [l.transaction_id for l in links]
        txns = []
        if txn_ids:
            txn_rows = (
                s.query(TransactionRow)
                .filter(TransactionRow.id.in_(txn_ids))
                .order_by(TransactionRow.txn_date.desc(), TransactionRow.row_index.asc())
                .all()
            )
            txns = [_txn_row_to_schema(r) for r in txn_rows]
        return EntityDetail(
            entity=_entity_row_to_schema(row, _entity_stats(s, entity_id)),
            transactions=txns,
        )


def create_entity(case_id: str, body: EntityCreate) -> Optional[Entity]:
    with get_session() as s:
        if not s.get(CaseRow, case_id):
            return None
        now = datetime.utcnow().isoformat(timespec="seconds")
        eid = _next_id(s, "e", EntityRow)
        row = EntityRow(
            id=eid, case_id=case_id, name=body.name,
            canonical_key=_canonical_key(body.name),
            entity_type=body.entity_type, pan=body.pan, phone=body.phone,
            notes=body.notes, linked_person_id=body.linked_person_id,
            aliases_json="[]", created_at=now, auto_created=False,
        )
        s.add(row)
        s.commit()
        return _entity_row_to_schema(row, {"txn_count": 0, "total_dr": 0.0, "total_cr": 0.0})


def link_transaction_to_entity(txn_id: str, entity_id: str, role: str = "counterparty") -> Optional[bool]:
    with get_session() as s:
        if not s.get(TransactionRow, txn_id) or not s.get(EntityRow, entity_id):
            return None
        existing = s.query(TransactionEntityLinkRow).filter_by(
            transaction_id=txn_id, entity_id=entity_id, role=role,
        ).first()
        if existing:
            return True
        s.add(TransactionEntityLinkRow(transaction_id=txn_id, entity_id=entity_id, role=role))
        s.commit()
        return True


def unlink_transaction_from_entity(txn_id: str, entity_id: str) -> Optional[bool]:
    with get_session() as s:
        links = s.query(TransactionEntityLinkRow).filter_by(
            transaction_id=txn_id, entity_id=entity_id,
        ).all()
        if not links:
            return False
        for l in links:
            s.delete(l)
        s.commit()
        return True


def list_entities_for_transaction(txn_id: str) -> Optional[list[Entity]]:
    with get_session() as s:
        if not s.get(TransactionRow, txn_id):
            return None
        links = s.query(TransactionEntityLinkRow).filter_by(transaction_id=txn_id).all()
        ids = [l.entity_id for l in links]
        if not ids:
            return []
        rows = s.query(EntityRow).filter(EntityRow.id.in_(ids)).all()
        return [_entity_row_to_schema(r, _entity_stats(s, r.id)) for r in rows]


# ───── forensic patterns ─────

def run_patterns_for_case(case_id: str) -> Optional[dict]:
    """Run all forensic pattern detectors over every transaction in the case
    and persist the resulting flags into `transactions.flags_json`.

    Returns a summary {flag_name: count} or None if the case doesn't exist.
    """
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).parent.parent.parent))
    from plugins.bank.patterns import run_all

    with get_session() as s:
        if not s.get(CaseRow, case_id):
            return None
        rows = s.query(TransactionRow).filter_by(case_id=case_id).all()
        pool = [
            {"id": r.id, "txn_date": r.txn_date, "amount": float(r.amount),
             "direction": r.direction, "account_id": r.account_id}
            for r in rows
        ]
        new_flags = run_all(pool)

        counter: dict[str, int] = {}
        for r in rows:
            existing = json.loads(r.flags_json or "[]")
            # Drop any previously-computed pattern flags (our namespace) so
            # reruns are idempotent; keep extraction-stage flags untouched.
            pattern_flags = {"STRUCTURING_SUSPECTED", "VELOCITY_SPIKE", "ROUND_AMOUNT_CLUSTER"}
            preserved = [f for f in existing if f not in pattern_flags]
            added = new_flags.get(r.id, [])
            merged = preserved + added
            r.flags_json = json.dumps(merged)
            for f in added:
                counter[f] = counter.get(f, 0) + 1
        s.commit()
        return counter


# ───── case summary (aggregations) ─────

def case_summary(case_id: str) -> Optional[CaseSummary]:
    """Aggregate all transactions in a case into dashboard-ready numbers.
    Returns None if the case doesn't exist."""
    with get_session() as s:
        if not s.get(CaseRow, case_id):
            return None
        rows = s.query(TransactionRow).filter_by(case_id=case_id).all()

        total_dr = 0.0
        total_cr = 0.0
        flag_count = 0
        reviewed = 0
        unreviewed = 0
        flagged = 0

        monthly: dict[str, dict] = {}
        cp_agg: dict[str, dict] = {}
        cat_agg: dict[str, dict] = {}

        pattern_hits: dict[str, dict] = {}
        for r in rows:
            amt = float(r.amount)
            if r.direction == "Dr":
                total_dr += amt
            else:
                total_cr += amt

            flags = json.loads(r.flags_json or "[]")
            flag_count += len(flags)
            for f in flags:
                p = pattern_hits.setdefault(f, {"count": 0, "samples": []})
                p["count"] += 1
                if len(p["samples"]) < 5:
                    p["samples"].append(r.id)
            if r.review_status == "reviewed":
                reviewed += 1
            elif r.review_status == "flagged":
                flagged += 1
            else:
                unreviewed += 1

            month = (r.txn_date or "")[:7] or "unknown"
            m = monthly.setdefault(month, {"dr": 0.0, "cr": 0.0, "count": 0})
            if r.direction == "Dr":
                m["dr"] += amt
            else:
                m["cr"] += amt
            m["count"] += 1

            entities = json.loads(r.entities_json or "{}")
            cp_name = (entities.get("counterparty") or {}).get("value") or "(unknown)"
            cp = cp_agg.setdefault(cp_name, {"count": 0, "dr": 0.0, "cr": 0.0})
            cp["count"] += 1
            if r.direction == "Dr":
                cp["dr"] += amt
            else:
                cp["cr"] += amt

            cat_name = (entities.get("category") or {}).get("value") or "Other"
            ct = cat_agg.setdefault(cat_name, {"count": 0, "dr": 0.0, "cr": 0.0})
            ct["count"] += 1
            if r.direction == "Dr":
                ct["dr"] += amt
            else:
                ct["cr"] += amt

        monthly_list = [
            MonthlyPoint(month=k, dr_total=round(v["dr"], 2), cr_total=round(v["cr"], 2), count=v["count"])
            for k, v in sorted(monthly.items())
        ]

        top_cp = sorted(cp_agg.items(), key=lambda kv: kv[1]["count"], reverse=True)[:15]
        top_counterparties = [
            TopCounterparty(name=k, count=v["count"], total_dr=round(v["dr"], 2), total_cr=round(v["cr"], 2))
            for k, v in top_cp
        ]

        categories = [
            CategoryBreakdown(category=k, count=v["count"], total_dr=round(v["dr"], 2), total_cr=round(v["cr"], 2))
            for k, v in sorted(cat_agg.items(), key=lambda kv: kv[1]["count"], reverse=True)
        ]

        # Surface every known pattern (including the zero-hit ones) so the UI
        # can show a complete scoreboard — investigators want to see what was
        # checked, not just what fired.
        patterns: list[PatternHit] = []
        for name, meta in PATTERN_META.items():
            hit = pattern_hits.get(name, {"count": 0, "samples": []})
            patterns.append(PatternHit(
                name=name,
                label=meta["label"],
                description=meta["description"],
                severity=meta["severity"],
                count=hit["count"],
                sample_txn_ids=hit["samples"],
            ))
        # Also include any patterns we didn't know about (forward-compat)
        for name, hit in pattern_hits.items():
            if name in PATTERN_META:
                continue
            patterns.append(PatternHit(
                name=name,
                label=name.replace("_", " ").title(),
                description="",
                severity="low",
                count=hit["count"],
                sample_txn_ids=hit["samples"],
            ))
        patterns.sort(key=lambda p: (-p.count, p.name))

        return CaseSummary(
            total_dr=round(total_dr, 2),
            total_cr=round(total_cr, 2),
            net=round(total_cr - total_dr, 2),
            txn_count=len(rows),
            flag_count=flag_count,
            reviewed_count=reviewed,
            unreviewed_count=unreviewed,
            flagged_count=flagged,
            monthly=monthly_list,
            top_counterparties=top_counterparties,
            categories=categories,
            patterns=patterns,
        )


# ───── writes: create case / ingest statement ─────

def _next_id(session, prefix: str, row_class) -> str:
    """Generate next id of the form {prefix}{N} based on existing rows —
    flushes pending inserts first so multiple calls within a single
    transaction don't collide."""
    session.flush()
    n = session.query(row_class).count() + 1
    while session.get(row_class, f"{prefix}{n}") is not None:
        n += 1
    return f"{prefix}{n}"


def create_case(fir_number: str, title: str, officer_name: str) -> Case:
    with get_session() as s:
        now = datetime.utcnow().isoformat(timespec="seconds")
        cid = _next_id(s, "c", CaseRow)
        row = CaseRow(
            id=cid, fir_number=fir_number, title=title, officer_name=officer_name,
            status="active", created_at=now, updated_at=now,
        )
        s.add(row)
        s.commit()
        return _case_row_to_schema(row, {"statements": 0, "transactions": 0, "flags": 0})


def create_person(case_id: str, name: str, pan: Optional[str] = None, phone: Optional[str] = None) -> Optional[Person]:
    with get_session() as s:
        if not s.get(CaseRow, case_id):
            return None
        pid = _next_id(s, "p", PersonRow)
        row = PersonRow(id=pid, case_id=case_id, name=name, aliases_json="[]", pan=pan, phone=phone)
        s.add(row)
        s.commit()
        return _person_row_to_schema(row)


def ingest_statement(
    *, case_id: str, person_id: str, source_file_name: str, source_file_path: Optional[str],
    bank: str, account_type: str, account_number: str, holder_name: str,
    period_start: str, period_end: str, opening_balance: float, closing_balance: float,
    declared_dr: Optional[float], declared_cr: Optional[float],
    parser_txns: list[dict], uploaded_by: str = "unknown",
) -> Optional[Tuple[Statement, list[Transaction]]]:
    """Persist a parsed statement + its transactions. Used by the upload endpoint."""
    with get_session() as s:
        if not s.get(CaseRow, case_id):
            return None
        if not s.get(PersonRow, person_id):
            return None

        # Find or create the account (identified by bank + account_number + person)
        acc = s.query(AccountRow).filter_by(
            person_id=person_id, bank=bank, account_number=account_number,
        ).first()
        if not acc:
            aid = _next_id(s, "a", AccountRow)
            acc = AccountRow(
                id=aid, person_id=person_id, bank=bank, account_type=account_type,
                account_number=account_number, holder_name=holder_name, currency="INR",
                transaction_count=0, has_warnings=False,
            )
            s.add(acc)
            s.flush()

        # Sum check
        sum_dr = sum(t["amount"] for t in parser_txns if t["type"] == "Dr")
        sum_cr = sum(t["amount"] for t in parser_txns if t["type"] == "Cr")
        dr_pct = (sum_dr / declared_dr * 100.0) if declared_dr else 100.0
        cr_pct = (sum_cr / declared_cr * 100.0) if declared_cr else 100.0

        now = datetime.utcnow().isoformat(timespec="seconds")
        sid = _next_id(s, "s", StatementRow)
        stmt = StatementRow(
            id=sid, account_id=acc.id, source_file_name=source_file_name,
            source_file_path=source_file_path,
            period_start=period_start, period_end=period_end,
            opening_balance=opening_balance, closing_balance=closing_balance,
            extracted_txn_count=len(parser_txns),
            sum_check_debits_pct=round(dr_pct, 2), sum_check_credits_pct=round(cr_pct, 2),
            uploaded_at=now, uploaded_by=uploaded_by,
        )
        s.add(stmt)
        s.flush()

        # Transactions
        from app.entity_inference import infer_channel, infer_category, infer_counterparty, iso_date
        running_balance = float(opening_balance)
        for idx, t in enumerate(parser_txns, start=1):
            raw = t.get("description", "")
            channel = infer_channel(raw)
            category = infer_category(raw)
            counterparty = infer_counterparty(raw, channel)
            amount = float(t["amount"])
            direction = t["type"]
            running_balance += amount if direction == "Cr" else -amount
            conf = "high"
            flags: list[str] = []
            if counterparty.startswith("(unknown") or len(counterparty) < 3:
                conf = "low"; flags.append("NEEDS_REVIEW")
            elif channel == "OTHER":
                conf = "medium"
            tid = _next_id(s, "t", TransactionRow)
            s.add(TransactionRow(
                id=tid, statement_id=sid, account_id=acc.id, case_id=case_id,
                row_index=idx, txn_date=iso_date(t.get("date", "")),
                amount=amount, direction=direction, running_balance=round(running_balance, 2),
                raw_description=raw,
                entities_json=json.dumps({
                    "channel":      {"value": channel,      "source": "extracted",     "confidence": 1.0 if channel != "OTHER" else 0.4},
                    "counterparty": {"value": counterparty, "source": "extracted",     "confidence": 0.9 if conf == "high" else 0.5 if conf == "medium" else 0.25},
                    "category":     {"value": category,     "source": "auto_resolved", "confidence": 0.7},
                }),
                tags_json="[]", confidence=conf, flags_json=json.dumps(flags),
                review_status="unreviewed", edit_count=0,
            ))

        # Update account totals
        acc.transaction_count += len(parser_txns)
        if abs(dr_pct - 100) > 0.01 or abs(cr_pct - 100) > 0.01:
            acc.has_warnings = True

        # Update case updated_at
        case = s.get(CaseRow, case_id)
        case.updated_at = now

        s.commit()
        s.refresh(stmt)

        # Return the persisted statement + its transactions
        stmt_schema = _statement_row_to_schema(stmt)
        txns = s.query(TransactionRow).filter_by(statement_id=sid).order_by(TransactionRow.row_index).all()
        out = stmt_schema, [_txn_row_to_schema(t) for t in txns]

    # Run forensic detectors over the whole case now that the new txns are
    # persisted. Patterns often need cross-statement context (e.g., velocity
    # across accounts), so we always run case-level.
    try:
        run_patterns_for_case(case_id)
    except Exception:
        pass
    try:
        resolve_entities_for_case(case_id)
    except Exception:
        pass
    return out


# ───── seed from benchmark (idempotent) ─────

def seed_from_benchmarks() -> None:
    """If the DB is empty, seed the same case/person/account structure the
    export-for-frontend script produces. Idempotent: no-op once seeded.
    """
    with get_session() as s:
        if s.query(CaseRow).count() > 0:
            return
    _do_seed()


def _do_seed() -> None:
    from pathlib import Path as _Path
    import importlib.util, json as _json, sys as _sys
    REPO = _Path(__file__).parent.parent.parent
    spec = importlib.util.spec_from_file_location(
        "export_for_frontend", REPO / "tools" / "export-for-frontend.py"
    )
    if spec is None or spec.loader is None:
        return
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    PDFS = mod.PDFS
    CASES = mod.CASES
    BENCH = REPO / "benchmarks" / "results" / "pdfplumber_text"

    for case_seed in CASES:
        case = create_case(case_seed["fir_number"], case_seed["title"], case_seed["officer_name"])
        # Replace generated id with the seed's id for stable references
        _rename_case(case.id, case_seed["id"])
        case_id = case_seed["id"]

        # Persons
        person_map: dict[str, str] = {}
        for person_seed in case_seed["persons"]:
            p = create_person(case_id=case_id, name=person_seed["name"],
                              pan=person_seed.get("pan"), phone=person_seed.get("phone"))
            if p:
                _rename_person(p.id, person_seed["id"])
                person_map[person_seed["id"]] = person_seed["id"]

        for pdf_name, person_id in case_seed["pdfs"]:
            meta = PDFS.get(pdf_name)
            if not meta:
                continue
            stem = _Path(pdf_name).stem
            json_path = BENCH / f"{stem}.json"
            if not json_path.exists():
                continue
            data = _json.loads(json_path.read_text(encoding="utf-8"))
            parser_txns = data.get("txns", [])
            ingest_statement(
                case_id=case_id, person_id=person_id,
                source_file_name=pdf_name, source_file_path=str((REPO / "data" / "pdf" / pdf_name).resolve()),
                bank=meta["bank"], account_type=meta["account_type"],
                account_number=meta["account_number"], holder_name=meta["holder"],
                period_start=meta["period_start"], period_end=meta["period_end"],
                opening_balance=float(meta.get("opening", 0)),
                closing_balance=float(meta.get("closing", 0)),
                declared_dr=meta.get("declared_dr"), declared_cr=meta.get("declared_cr"),
                parser_txns=parser_txns, uploaded_by="seed",
            )


def _rename_case(old_id: str, new_id: str) -> None:
    """Rename a case id (and cascade to all tables that reference it)."""
    if old_id == new_id:
        return
    with get_session() as s:
        # The SQL is explicit because SQLAlchemy doesn't propagate PK rename.
        from sqlalchemy import text
        s.execute(text("UPDATE cases SET id = :new WHERE id = :old"), {"new": new_id, "old": old_id})
        s.execute(text("UPDATE persons SET case_id = :new WHERE case_id = :old"), {"new": new_id, "old": old_id})
        s.execute(text("UPDATE transactions SET case_id = :new WHERE case_id = :old"), {"new": new_id, "old": old_id})
        s.commit()


def _rename_person(old_id: str, new_id: str) -> None:
    if old_id == new_id:
        return
    with get_session() as s:
        from sqlalchemy import text
        s.execute(text("UPDATE persons SET id = :new WHERE id = :old"), {"new": new_id, "old": old_id})
        s.execute(text("UPDATE accounts SET person_id = :new WHERE person_id = :old"), {"new": new_id, "old": old_id})
        s.commit()


# ───── bootstrap helpers ─────

def init_and_seed(reset: bool = False) -> None:
    init_db(reset=reset)
    seed_from_benchmarks()
    # Detect forensic patterns over every case post-seed. Safe to rerun
    # (detectors are idempotent and we clear our own flag namespace).
    with get_session() as s:
        case_ids = [c.id for c in s.query(CaseRow).all()]
    for cid in case_ids:
        try:
            run_patterns_for_case(cid)
        except Exception:
            pass
        try:
            resolve_entities_for_case(cid)
        except Exception:
            pass


# ───── counts for /api/health ─────

def counts() -> dict:
    with get_session() as s:
        return {
            "cases": s.query(CaseRow).count(),
            "persons": s.query(PersonRow).count(),
            "accounts": s.query(AccountRow).count(),
            "statements": s.query(StatementRow).count(),
            "transactions": s.query(TransactionRow).count(),
        }
