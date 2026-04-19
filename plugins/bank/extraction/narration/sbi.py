"""State Bank of India narration decoder.

Built from documented SBI narration envelopes (no live sample in tree yet
— rules are conservative; tune once real PDFs arrive).

Envelope patterns:
  TO TRANSFER-INB <narr>-<benef>-<REF>       Internet-banking outward xfer
  BY TRANSFER-INB <narr>-<remitter>-<REF>    Internet-banking inward xfer
  TO TRANSFER-NEFT <UTR>-<REMITTER>          NEFT outward
  BY TRANSFER-NEFT <UTR>-<REMITTER>          NEFT inward
  TO TRANSFER-RTGS <UTR>-<REMITTER>          RTGS outward
  BY TRANSFER-IMPS <REF>-<PAYER/PAYEE>       IMPS
  TO TRANSFER-UPI/<VPA>/<REF>                UPI outward
  BY TRANSFER-UPI/<VPA>/<REF>                UPI inward
  TO ATM WDL-<ATMID>-<LOC>-<CARD>            ATM withdrawal
  TO POS <REF>-<MERCHANT>                    POS card debit
  BY CLEARING-<CHQNO>-<PAYEE>                inward cheque
  BY CASH-<BRANCH>                           cash deposit
  TO CHQ-<CHQNO>-<PAYEE>                     outward cheque
  DEBIT INTEREST / CREDIT INTEREST           interest events
  SB SMS CHRG / SB MAB CHRG                  bank charges
"""
from __future__ import annotations
import re
from . import _shared as S


def decode(narration: str) -> dict:
    raw = (narration or "").strip()
    up = raw.upper()

    # 1. Universal static events (use compact form to tolerate whitespace)
    hit = S.match_static_event(S.compact(up))
    if hit:
        return S.result(hit[0], hit[1], None, None, None, "static", "State Bank of India")

    # 2. Interest / bank charges (SBI-specific wording)
    if "CREDIT INTEREST" in up:
        return S.result("interest_credit", "SBI — Savings Interest",
                        None, None, None, "interest_cr", "State Bank of India")
    if "DEBIT INTEREST" in up:
        return S.result("interest_debit", "SBI — Overdraft Interest",
                        None, None, None, "interest_dr", "State Bank of India")
    if re.search(r"SB\s+(SMS|MAB)\s+CHRG", up):
        return S.result("bank_charge",
                        "SBI — SMS Charges" if "SMS" in up else "SBI — MAB Charges",
                        None, None, None, "sbi_chg")

    # 3. UPI
    m = re.match(
        r"^(?P<dir>TO|BY)\s+TRANSFER-UPI/(?P<vpa>[^/]+)(?:/(?P<ref>\S+))?",
        raw, re.I)
    if m:
        vpa = m.group("vpa")
        ref = m.group("ref")
        vm = S.VPA_RE.search(vpa or "")
        merchant = S.titlecase(vm.group("local")) if vm else S.titlecase(vpa)
        bank = S.identify_bank(vm.group("handle")) if vm else None
        return S.result("upi", merchant, None, None, ref, "upi", bank)

    # 4. IMPS
    m = re.match(
        r"^(?P<dir>TO|BY)\s+TRANSFER-IMPS[/\s-]*(?P<ref>\d+)[-/\s]*(?P<rem>.+)?",
        raw, re.I)
    if m:
        return S.result("imps", S.titlecase(m.group("rem")), None, None,
                        m.group("ref"), "imps")

    # 5. NEFT / RTGS
    m = re.match(
        r"^(?P<dir>TO|BY)\s+TRANSFER-(?P<kind>NEFT|RTGS)[-/\s]*(?P<utr>[A-Z0-9]+)"
        r"[-/\s]*(?P<rem>.+)?", raw, re.I)
    if m:
        return S.result(m.group("kind").lower(),
                        S.titlecase(m.group("rem")) if m.group("rem") else None,
                        None, None, m.group("utr"), m.group("kind").lower())

    # 6. INB (generic internet-banking transfer)
    m = re.match(
        r"^(?P<dir>TO|BY)\s+TRANSFER-INB\s+(?P<narr>.+?)(?:-(?P<ref>\S+))?$",
        raw, re.I)
    if m:
        narr = m.group("narr")
        return S.result("ib_xfer", S.titlecase(narr), None, None,
                        m.group("ref"), "inb", "State Bank of India")

    # 7. ATM withdrawal
    m = re.match(
        r"^TO\s+ATM\s+(?:WDL|WITHDRAWAL)[-/\s]*(?P<atmid>[A-Z0-9]+)?"
        r"[-/\s]*(?P<loc>[A-Z ]+?)(?:[-/\s](?P<card>\d{4,}))?$", raw, re.I)
    if m:
        loc = S.titlecase(m.group("loc"))
        return S.result("atm_other",
                        f"SBI ATM — {loc}" if loc else "SBI ATM Withdrawal",
                        loc, S.card_last4(m.group("card") or ""),
                        m.group("atmid"), "atm", "State Bank of India")

    # 8. POS
    m = re.match(r"^TO\s+POS\s+(?P<ref>\d+)[-/\s]*(?P<merchant>.+)$", raw, re.I)
    if m:
        return S.result("pos", S.titlecase(m.group("merchant")), None, None,
                        m.group("ref"), "pos")

    # 9. Cheque
    m = re.match(r"^BY\s+CLEARING-(?P<chq>\d+)-(?P<payee>.+)$", raw, re.I)
    if m:
        return S.result("cheque_deposit", S.titlecase(m.group("payee")),
                        None, None, m.group("chq"), "cheque_in")
    m = re.match(r"^TO\s+CHQ-?(?P<chq>\d+)[-\s]*(?P<payee>.+)$", raw, re.I)
    if m:
        return S.result("cheque_paid", S.titlecase(m.group("payee")),
                        None, None, m.group("chq"), "cheque_out")

    # 10. Cash deposit
    m = re.match(r"^BY\s+CASH[-\s]*(?P<branch>.+)$", raw, re.I)
    if m:
        branch = S.titlecase(m.group("branch"))
        return S.result("cash_deposit", f"Cash Deposit — {branch}",
                        branch, None, None, "cash")

    return S.result("unknown", None, None, None, None, "unmatched")
