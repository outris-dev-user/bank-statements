"""ICICI Bank narration decoder (current + savings).

Envelope patterns observed:
  BY CASH - <BRANCH>                        cash deposit at branch
  BY CASH-<BRANCH>                          (no space variant)
  BIL/INFT/<ref>/<narr-or-NA>/              internet banking transfer in
  MMT/IMPS/<ref>/<purpose>/<remitter>/<bank> IMPS receive/send
  UPI/<ref>/<purpose>/<vpa>/<bank>          UPI transaction
  CLG/<PAYEE>/BRK <chq-no>                  cheque clearing (debit)
  CLG/<PAYEE> /BRK <chq-no>                 (variant with space)
  NEFT/<UTR>/<REMITTER>/<BANK>              NEFT in/out
  RTGS/<UTR>/<REMITTER>/<BANK>              RTGS in/out
  BIL/BPAY/<ref>/<biller>                   bill payment
  VPS/<ref>/<merchant>                      POS / VISA point of sale

All slash-delimited — so decoder splits on `/` after sniffing the prefix.
"""
from __future__ import annotations
import re
from . import _shared as S


def _cash_branch(raw: str):
    # "BY CASH - BIJOLIA" or "BY CASH-KACHHOLA" or "BY CASH - GULABPURA BAWRI CHOURAHA"
    m = re.match(r"^BY\s+CASH\s*-\s*(?P<branch>.+)$", raw, re.I)
    if not m:
        return None
    branch = S.titlecase(m.group("branch"))
    return S.result("cash_deposit", f"Cash Deposit — {branch}",
                    branch, None, None, "by_cash", "ICICI Bank")


def _slash_parts(raw: str):
    return [p.strip() for p in raw.split("/") if p is not None]


def decode(narration: str) -> dict:
    raw = (narration or "").strip()
    up = raw.upper()

    # 1. Universal static events
    hit = S.match_static_event(S.compact(up))
    if hit:
        return S.result(hit[0], hit[1], None, None, None, "static",
                        "ICICI Bank")

    # 2. Cash deposit at branch
    r = _cash_branch(raw)
    if r:
        return r

    parts = _slash_parts(raw)
    if not parts:
        return S.result("unknown", None, None, None, None, "unmatched")
    head = parts[0].upper()

    # 3. UPI/<ref>/<purpose>/<vpa>/<bank>
    if head == "UPI" and len(parts) >= 3:
        ref = parts[1] if len(parts) > 1 else None
        purpose = parts[2] if len(parts) > 2 else None
        vpa_raw = parts[3] if len(parts) > 3 else None
        bank_tok = parts[4] if len(parts) > 4 else None
        generic_purpose = (not purpose) or purpose.upper() in (
            "NA", "UPI", "") or purpose.upper().startswith("PAYMENT FROM")
        merchant = None
        # Prefer VPA local-part unless slot[2] is a real name
        vpa_m = S.VPA_RE.search(vpa_raw or "") if vpa_raw else None
        if generic_purpose:
            if vpa_m:
                merchant = S.titlecase(vpa_m.group("local"))
            elif vpa_raw:
                merchant = S.titlecase(vpa_raw)
        else:
            merchant = S.titlecase(purpose)
        bank_name = S.identify_bank(bank_tok) if bank_tok else None
        return S.result("upi", merchant, None, None, ref, "upi", bank_name)

    # 4. MMT/IMPS/<ref>/<purpose>/<remitter>/<bank>
    if head == "MMT" and len(parts) >= 3 and parts[1].upper() == "IMPS":
        ref = parts[2]
        purpose = parts[3] if len(parts) > 3 else None
        remitter = parts[4] if len(parts) > 4 else None
        bank_tok = parts[5] if len(parts) > 5 else None
        # Prefer remitter name (real counterparty) over purpose code
        merchant = S.titlecase(remitter) if remitter else S.titlecase(purpose)
        bank_name = S.identify_bank(bank_tok) if bank_tok else None
        return S.result("imps", merchant, None, None, ref, "mmt_imps", bank_name)

    # 5. BIL/INFT/<ref>/<narr>/        (internet-banking inward transfer)
    if head == "BIL" and len(parts) >= 2 and parts[1].upper() == "INFT":
        ref = parts[2] if len(parts) > 2 else None
        narr = parts[3] if len(parts) > 3 else None
        merchant = None
        if narr and narr.upper() not in ("NA", "MIB-", ""):
            merchant = S.titlecase(narr)
        else:
            merchant = "Internet Banking Transfer"
        return S.result("ib_xfer", merchant, None, None, ref, "bil_inft",
                        "ICICI Bank")

    # 6. BIL/BPAY/<ref>/<biller>
    if head == "BIL" and len(parts) >= 2 and parts[1].upper() == "BPAY":
        ref = parts[2] if len(parts) > 2 else None
        biller = parts[3] if len(parts) > 3 else None
        return S.result("bill_pay", S.titlecase(biller), None, None, ref,
                        "bil_bpay")

    # 7. NEFT / RTGS
    if head in ("NEFT", "RTGS") and len(parts) >= 2:
        utr = parts[1]
        remitter = parts[2] if len(parts) > 2 else None
        bank_tok = parts[3] if len(parts) > 3 else None
        bank_name = S.identify_bank(bank_tok) if bank_tok else None
        return S.result(head.lower(), S.titlecase(remitter), None, None, utr,
                        head.lower(), bank_name)

    # 8. CLG/<PAYEE>/BRK <cheque-no>           outgoing cheque clearing
    if head == "CLG":
        # Re-split on whitespace too since "BRK 5181" has a space
        m = re.match(r"^CLG/(?P<payee>[^/]+?)\s*/?\s*BRK\s+(?P<chq>\d+)\s*$",
                     raw, re.I)
        if m:
            return S.result("cheque_paid", S.titlecase(m.group("payee")),
                            None, None, m.group("chq"), "clg_brk")
        # Fallback: just a payee after CLG/
        if len(parts) >= 2:
            return S.result("cheque_paid", S.titlecase(parts[1]),
                            None, None, None, "clg_other")

    # 9. VPS/<ref>/<merchant>      (VISA POS)
    if head == "VPS" and len(parts) >= 3:
        return S.result("pos", S.titlecase(parts[2]), None, None,
                        parts[1], "vps")

    return S.result("unknown", None, None, None, None, "unmatched")
