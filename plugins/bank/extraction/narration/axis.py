"""Axis Bank narration decoder.

Built from documented Axis narration envelopes (no live sample in tree yet
— rules are conservative and will be tuned when real PDFs arrive).

Envelope patterns (savings / current):
  UPI/P2A/<ref>/<PAYER>/<VPA>/<purpose>       UPI P2A
  UPI/P2M/<ref>/<MERCHANT>/<VPA>/<purpose>    UPI P2M
  UPI/<ref>/<COUNTERPARTY>/<VPA>/<bank>       legacy UPI
  INB/<ref>/<REMITTER>/<NARR>                 Internet Banking inward
  IMPS/P2A/<ref>/<PAYEE>/<BANK>               IMPS P2A
  NEFT/<utr>/<REMITTER>/<BANK>                NEFT
  RTGS/<utr>/<REMITTER>/<BANK>                RTGS
  ATM-CASH/<loc>/<TERMINAL>                   ATM withdrawal
  POS/<card-last4>/<MERCHANT>/<loc>           POS card debit
  BRN-CLG-CHQ PAID <payee>                    Cheque paid via clearing
  BRN-CLG-CHQ DEPOSIT                         Cheque deposit
  ECS/<ref>/<BILLER>                          ECS debit
  CMS-<ref>-<BILLER>                          Cash Management Services

We look at the head token (first slash-delimited or dash-delimited chunk)
and dispatch.
"""
from __future__ import annotations
import re
from . import _shared as S


def _slash_parts(raw: str):
    return [p.strip() for p in raw.split("/")]


def decode(narration: str) -> dict:
    raw = (narration or "").strip()
    up = raw.upper()

    # 1. Universal static events
    hit = S.match_static_event(S.compact(up))
    if hit:
        return S.result(hit[0], hit[1], None, None, None, "static", "Axis Bank")

    parts = _slash_parts(raw)
    head = parts[0].upper() if parts else ""

    # 2. UPI
    if head == "UPI" and len(parts) >= 3:
        # Try to detect P2A/P2M/P2P flavour
        second = parts[1].upper()
        if second in ("P2A", "P2M", "P2P"):
            ref = parts[2] if len(parts) > 2 else None
            cp = parts[3] if len(parts) > 3 else None
            vpa = parts[4] if len(parts) > 4 else None
            purpose = parts[5] if len(parts) > 5 else None
            merchant = S.titlecase(cp)
            if not merchant and vpa:
                vm = S.VPA_RE.search(vpa)
                if vm: merchant = S.titlecase(vm.group("local"))
            return S.result("upi", merchant, None, None, ref,
                            "upi_" + second.lower())
        # Legacy UPI/<ref>/<cp>/<vpa>/<bank>
        ref = parts[1]
        cp = parts[2] if len(parts) > 2 else None
        vpa = parts[3] if len(parts) > 3 else None
        bank_tok = parts[4] if len(parts) > 4 else None
        merchant = S.titlecase(cp) if cp and cp.upper() != "NA" else None
        if not merchant and vpa:
            vm = S.VPA_RE.search(vpa)
            if vm: merchant = S.titlecase(vm.group("local"))
        return S.result("upi", merchant, None, None, ref, "upi",
                        S.identify_bank(bank_tok) if bank_tok else None)

    # 3. IMPS
    if head == "IMPS" and len(parts) >= 3:
        ref = parts[2]
        cp = parts[3] if len(parts) > 3 else None
        bank_tok = parts[4] if len(parts) > 4 else None
        return S.result("imps", S.titlecase(cp), None, None, ref, "imps",
                        S.identify_bank(bank_tok) if bank_tok else None)

    # 4. NEFT / RTGS
    if head in ("NEFT", "RTGS") and len(parts) >= 2:
        utr = parts[1]
        rem = parts[2] if len(parts) > 2 else None
        bank_tok = parts[3] if len(parts) > 3 else None
        return S.result(head.lower(), S.titlecase(rem), None, None, utr,
                        head.lower(),
                        S.identify_bank(bank_tok) if bank_tok else None)

    # 5. INB/<ref>/<remitter>/<narr>    (internet banking inward)
    if head == "INB" and len(parts) >= 2:
        ref = parts[1]
        rem = parts[2] if len(parts) > 2 else None
        return S.result("ib_xfer",
                        S.titlecase(rem) if rem else "Internet Banking Transfer",
                        None, None, ref, "inb", "Axis Bank")

    # 6. POS / ATM
    m = re.match(r"^POS/(?P<card>\d{4,})/(?P<merchant>[^/]+)(?:/(?P<loc>.+))?$",
                 raw, re.I)
    if m:
        return S.result("pos", S.titlecase(m.group("merchant")),
                        S.titlecase(m.group("loc")) if m.group("loc") else None,
                        S.card_last4(m.group("card")), None, "pos")
    m = re.match(r"^ATM-?CASH[/\s]*(?P<loc>[A-Z ,]+?)(?:[/\s](?P<term>[A-Z0-9]+))?$",
                 raw, re.I)
    if m:
        return S.result("atm_other", "ATM Withdrawal",
                        S.titlecase(m.group("loc")), None,
                        m.group("term") if m.lastgroup else None,
                        "atm", "Axis Bank")

    # 7. BRN-CLG-CHQ (branch clearing cheque)
    m = re.match(r"^BRN-CLG-CHQ\s+(?P<dir>PAID|DEPOSIT)\s*(?P<payee>.*)$",
                 raw, re.I)
    if m:
        direction = m.group("dir").upper()
        payee = S.titlecase(m.group("payee"))
        channel = "cheque_paid" if direction == "PAID" else "cheque_deposit"
        merchant = payee or ("Cheque Paid" if direction == "PAID" else "Cheque Deposit")
        return S.result(channel, merchant, None, None, None, "brn_clg_" + direction.lower())

    # 8. ECS / CMS
    m = re.match(r"^ECS[/-](?P<ref>[A-Z0-9]+)[/-](?P<biller>.+)$", raw, re.I)
    if m:
        return S.result("ecs", S.titlecase(m.group("biller")), None, None,
                        m.group("ref"), "ecs")
    m = re.match(r"^CMS-(?P<ref>[A-Z0-9]+)-(?P<biller>.+)$", raw, re.I)
    if m:
        return S.result("ecs", S.titlecase(m.group("biller")), None, None,
                        m.group("ref"), "cms")

    return S.result("unknown", None, None, None, None, "unmatched")
