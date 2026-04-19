"""Kotak Mahindra Bank narration decoder.

Envelope patterns observed:
  UPI/<merchant>                          UPI txn, merchant is name
  UPI/<biller>/<sub-ref>                  aggregator (GOOGLEPAY/BILLDESK/AMAZONPAY)
  MB:RECEIVED MONEY                       IMPS credit via mobile banking
  MB SENT TO <beneficiary>                IMPS debit via mobile banking
  MB <LABEL>                              generic mobile-banking action
  PCD/<code>/<MERCHANT>                   POS card debit
  NEFT-<UTR>-<REMITTER>                   NEFT inward (wording varies)
  RTGS-<UTR>-<REMITTER>                   RTGS inward
  ATM-CASH WDL <loc>                      ATM withdrawal
  IMPS-<ref>                              IMPS (when narration is blank)

The PDF concatenates a trailing "UPI-<ref>" / "MB-<ref>" / "IMPS-<ref>"
reference column onto the narration. We split it off so it doesn't
pollute the merchant field.
"""
from __future__ import annotations
import re
from . import _shared as S

_TRAIL_REF_RE = re.compile(
    r"\s+(?:UPI|MB|IMPS|NEFT|RTGS)-\d{10,}.*$", re.I)


def _strip_trailing_ref(raw: str) -> tuple[str, str | None]:
    m = _TRAIL_REF_RE.search(raw)
    if not m:
        return raw, None
    ref_m = re.search(r"\d{10,}", m.group(0))
    return raw[: m.start()].strip(), ref_m.group(0) if ref_m else None


def decode(narration: str) -> dict:
    raw0 = (narration or "").strip()
    core, trailing_ref = _strip_trailing_ref(raw0)
    up = core.upper()

    # 1. Universal static events
    hit = S.match_static_event(S.compact(up))
    if hit:
        return S.result(hit[0], hit[1], None, None, trailing_ref, "static",
                        "Kotak Mahindra Bank")

    # 2. MB:RECEIVED MONEY  (IMPS credit)
    if up.startswith("MB:RECEIVED"):
        return S.result("imps", "Incoming Transfer", None, None,
                        trailing_ref, "mb_received", "Kotak Mahindra Bank")

    # 3. MB SENT TO <beneficiary>   — usually IMPS out
    m = re.match(r"^MB\s+SENT\s+TO\s*(?P<benef>.*)$", core, re.I)
    if m:
        benef = S.titlecase(m.group("benef")) if m.group("benef") else None
        return S.result("imps", benef or "Outgoing Transfer", None, None,
                        trailing_ref, "mb_sent_to")

    # 4. MB <other label>   — mobile banking action
    m = re.match(r"^MB\s+(?P<label>.+)$", core, re.I)
    if m:
        label = S.titlecase(m.group("label"))
        return S.result("mobile_banking", label, None, None, trailing_ref,
                        "mb_generic")

    # 5. UPI/<merchant>[/<extra>]
    if up.startswith("UPI/"):
        parts = [p.strip() for p in core.split("/") if p.strip()]
        merchant = S.titlecase(parts[1]) if len(parts) >= 2 else None
        return S.result("upi", merchant, None, None, trailing_ref, "upi")

    # 6. PCD/<code>/<MERCHANT>
    if up.startswith("PCD/"):
        parts = [p.strip() for p in core.split("/") if p.strip()]
        merchant = S.titlecase(parts[2]) if len(parts) >= 3 else (
            S.titlecase(parts[1]) if len(parts) >= 2 else None)
        ref = parts[1] if len(parts) >= 2 and parts[1].isdigit() else trailing_ref
        return S.result("pos", merchant, None, None, ref, "pcd")

    # 7. NEFT / RTGS
    m = re.match(r"^(?P<kind>NEFT|RTGS)[-/](?P<utr>[A-Z0-9]+)[-/]?(?P<rem>.*)$",
                 core, re.I)
    if m:
        return S.result(m.group("kind").lower(), S.titlecase(m.group("rem")),
                        None, None, m.group("utr"), m.group("kind").lower())

    # 8. ATM
    if "ATM" in up and ("CASH" in up or "WDL" in up or "WITHDRAW" in up):
        return S.result("atm_other", "ATM Withdrawal", None, None,
                        trailing_ref, "atm", "Kotak Mahindra Bank")

    # 9. IMPS-only narration (trailing ref was the whole narration)
    if up.startswith("IMPS-"):
        m = re.match(r"^IMPS-(?P<ref>\d+)\s*(?P<narr>.*)$", core, re.I)
        if m:
            narr = m.group("narr")
            return S.result("imps", S.titlecase(narr) if narr else "IMPS Transfer",
                            None, None, m.group("ref"), "imps_bare")

    return S.result("unknown", None, None, None, trailing_ref, "unmatched")
