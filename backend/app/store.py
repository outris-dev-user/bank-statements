"""In-memory store seeded from the benchmark parser output.

Phase 1 stub — not a real database. Replace with SQLite/SQLAlchemy when
we wire persistence. The shape of the store (cases, persons, accounts,
statements, transactions dicts keyed by id) matches what SQLAlchemy
models will look like one layer up.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

from app.schemas import (
    Case, Person, Account, Statement, Transaction, EntityValue,
)

# Paths
BACKEND = Path(__file__).parent.parent
REPO = BACKEND.parent
BENCHMARK_RESULTS = REPO / "benchmarks" / "results" / "pdfplumber_text"


class Store:
    def __init__(self) -> None:
        self.cases: dict[str, Case] = {}
        self.persons: dict[str, Person] = {}
        self.accounts: dict[str, Account] = {}
        self.statements: dict[str, Statement] = {}
        self.transactions: dict[str, Transaction] = {}
        # audit log: per-transaction list of edit events
        self.audit: dict[str, list[dict]] = {}

    # ───── seed from export ─────
    def seed_from_export(self, export_json_path: Optional[Path] = None) -> None:
        """Seed from the realData.ts the export script produces — via a
        sibling JSON the export writes for us.

        For the stub we instead duplicate the seeding logic inline by
        reading the same benchmark JSON files the export-for-frontend
        script uses. That keeps this backend independent of the
        TypeScript file (which is what the frontend consumes).
        """
        # Re-seed: clear
        self.__init__()

        # Import declarations from the export script, which is the SoT for
        # "which PDFs feed which cases with what declared totals".
        import sys
        sys.path.insert(0, str(REPO / "tools"))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "export_for_frontend", REPO / "tools" / "export-for-frontend.py"
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot locate tools/export-for-frontend.py")
        export_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(export_mod)

        PDFS = export_mod.PDFS
        CASES = export_mod.CASES
        iso_date = export_mod.iso_date
        infer_channel = export_mod.infer_channel
        infer_category = export_mod.infer_category
        infer_counterparty = export_mod.infer_counterparty

        for case_seed in CASES:
            case_id = case_seed["id"]
            seen_accounts: dict[tuple, str] = {}
            case_stmt_count = 0
            case_txn_count = 0
            case_flag_count = 0

            for person in case_seed["persons"]:
                pid = person["id"]
                self.persons[pid] = Person(
                    id=pid,
                    case_id=case_id,
                    name=person["name"],
                    aliases=[],
                    pan=person.get("pan"),
                    phone=person.get("phone"),
                )

            for pdf_name, person_id in case_seed["pdfs"]:
                meta = PDFS.get(pdf_name)
                if not meta:
                    continue
                acc_key = (meta["bank"], meta["account_number"], person_id)
                if acc_key not in seen_accounts:
                    acc_id = f"a{len(self.accounts) + 1}"
                    seen_accounts[acc_key] = acc_id
                    self.accounts[acc_id] = Account(
                        id=acc_id,
                        person_id=person_id,
                        bank=meta["bank"],
                        account_type=meta["account_type"],
                        account_number=meta["account_number"],
                        holder_name=meta["holder"],
                        currency="INR",
                    )
                acc_id = seen_accounts[acc_key]

                stem = Path(pdf_name).stem
                json_path = BENCHMARK_RESULTS / f"{stem}.json"
                if not json_path.exists():
                    continue
                data = json.loads(json_path.read_text(encoding="utf-8"))
                parser_txns = data.get("txns", [])

                stmt_id = f"s{len(self.statements) + 1}"
                sum_dr = sum(t["amount"] for t in parser_txns if t["type"] == "Dr")
                sum_cr = sum(t["amount"] for t in parser_txns if t["type"] == "Cr")
                dec_dr = meta["declared_dr"]
                dec_cr = meta["declared_cr"]
                dr_pct = (sum_dr / dec_dr * 100) if dec_dr else 100.0
                cr_pct = (sum_cr / dec_cr * 100) if dec_cr else 100.0

                self.statements[stmt_id] = Statement(
                    id=stmt_id,
                    account_id=acc_id,
                    source_file_name=pdf_name,
                    period_start=meta["period_start"],
                    period_end=meta["period_end"],
                    opening_balance=float(meta.get("opening", 0)),
                    closing_balance=float(meta.get("closing", 0)),
                    extracted_txn_count=len(parser_txns),
                    sum_check_debits_pct=round(dr_pct, 2),
                    sum_check_credits_pct=round(cr_pct, 2),
                    uploaded_at=datetime.utcnow().isoformat(timespec="seconds"),
                    uploaded_by="Saurabh",
                )
                case_stmt_count += 1

                running_balance = float(meta.get("opening", 0))
                for idx, t in enumerate(parser_txns, start=1):
                    raw = t.get("description", "")
                    channel = infer_channel(raw)
                    category = infer_category(raw)
                    counterparty = infer_counterparty(raw, channel)
                    amount = float(t["amount"])
                    direction = t["type"]
                    running_balance += amount if direction == "Cr" else -amount

                    conf: str = "high"
                    flags: list[str] = []
                    if counterparty.startswith("(unknown") or len(counterparty) < 3:
                        conf = "low"
                        flags.append("NEEDS_REVIEW")
                    elif channel == "OTHER":
                        conf = "medium"

                    tid = f"t{len(self.transactions) + 1}"
                    self.transactions[tid] = Transaction(
                        id=tid,
                        statement_id=stmt_id,
                        account_id=acc_id,
                        case_id=case_id,
                        row_index=idx,
                        txn_date=iso_date(t.get("date", "")),
                        amount=amount,
                        direction=direction,
                        running_balance=round(running_balance, 2),
                        raw_description=raw,
                        entities={
                            "channel":      EntityValue(value=channel,      source="extracted",     confidence=1.0 if channel != "OTHER" else 0.4),
                            "counterparty": EntityValue(value=counterparty, source="extracted",     confidence=0.9 if conf == "high" else 0.5 if conf == "medium" else 0.25),
                            "category":     EntityValue(value=category,     source="auto_resolved", confidence=0.7),
                        },
                        tags=[],
                        confidence=conf,
                        flags=flags,
                        review_status="unreviewed",
                        edit_count=0,
                    )
                    case_txn_count += 1
                    case_flag_count += len(flags)

                # update account totals
                acc = self.accounts[acc_id]
                acc.transaction_count += len(parser_txns)
                if dr_pct != 100.0 or cr_pct != 100.0:
                    acc.has_warnings = True

            self.cases[case_id] = Case(
                id=case_id,
                fir_number=case_seed["fir_number"],
                title=case_seed["title"],
                officer_name=case_seed["officer_name"],
                status=case_seed["status"],
                created_at="2026-04-13T10:30:00",
                updated_at=datetime.utcnow().isoformat(timespec="seconds"),
                statement_count=case_stmt_count,
                transaction_count=case_txn_count,
                flag_count=case_flag_count,
            )


# module-level singleton
store = Store()
store.seed_from_export()
