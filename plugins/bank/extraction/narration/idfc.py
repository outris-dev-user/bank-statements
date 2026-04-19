"""IDFC First Bank narration decoder.

Envelope patterns observed (limited sample — expand as more statements arrive):
  UPI/<DR|CR>/<ref>/<merchant>/<bank-code>/<vpa>/<purpose>
  UPI/<DR|CR>/<ref>/<merchant>
  NEFT/<UTR>/<remitter>
  RTGS/<UTR>/<remitter>
  IMPS/<DR|CR>/<ref>/<remitter>

IDFC narrations wrap to multiple visual lines in the PDF but pdfplumber
concatenates them with spaces; we normalise by collapsing whitespace.
"""
from __future__ import annotations
import re
from . import _shared as S


def _slash_parts(raw: str):
    return [p.strip() for p in raw.split("/")]


def decode(narration: str) -> dict:
    raw = re.sub(r"\s+", " ", (narration or "").strip())
    up = raw.upper()

    # 1. Universal static events
    hit = S.match_static_event(S.compact(up))
    if hit:
        return S.result(hit[0], hit[1], None, None, None, "static",
                        "IDFC First Bank")

    parts = _slash_parts(raw)
    head = parts[0].upper() if parts else ""

    # 2. UPI/<DR|CR>/<ref>/<merchant>[/<bank>/<vpa>/<purpose>]
    if head == "UPI" and len(parts) >= 3:
        direction = parts[1].upper() if len(parts) > 1 else None
        ref = parts[2] if len(parts) > 2 else None
        merchant_raw = parts[3] if len(parts) > 3 else None
        bank_tok = parts[4] if len(parts) > 4 else None
        vpa_raw = parts[5] if len(parts) > 5 else None

        merchant = S.titlecase(merchant_raw) if merchant_raw else None
        # If merchant is empty/NA, fall back to VPA local-part
        if (not merchant or merchant.upper() == "NA") and vpa_raw:
            vm = S.VPA_RE.search(vpa_raw)
            if vm:
                merchant = S.titlecase(vm.group("local"))

        bank_name = S.identify_bank(bank_tok) if bank_tok else None
        rule = "upi_dr" if direction == "DR" else "upi_cr" if direction == "CR" else "upi"
        return S.result("upi", merchant, None, None, ref, rule, bank_name)

    # 3. IMPS/<DR|CR>/<ref>/<remitter>
    if head == "IMPS" and len(parts) >= 3:
        ref = parts[2]
        remitter = parts[3] if len(parts) > 3 else None
        return S.result("imps", S.titlecase(remitter), None, None, ref, "imps")

    # 4. NEFT / RTGS
    if head in ("NEFT", "RTGS") and len(parts) >= 2:
        utr = parts[1]
        remitter = parts[2] if len(parts) > 2 else None
        bank_tok = parts[3] if len(parts) > 3 else None
        return S.result(head.lower(), S.titlecase(remitter), None, None, utr,
                        head.lower(),
                        S.identify_bank(bank_tok) if bank_tok else None)

    # 5. ATM withdrawal
    if up.startswith("ATM ") or "ATM WITHDRAWAL" in up:
        return S.result("atm_hdfc", "ATM Withdrawal", None, None, None,
                        "atm_generic", "IDFC First Bank")

    return S.result("unknown", None, None, None, None, "unmatched")
