"""HDFC Bank savings-account narration decoder.

Envelope patterns observed:
  POS<card><MERCHANT>POSDEBIT | PO SDEBIT | SDEBIT
  POSREF<card>-<MM/DD><MERCHANT>
  CRVPOS<card>DISCOUNTONFUE            (fuel surcharge reversal)
  ATW-<card>-<terminal>-<LOCATION>     (HDFC ATM withdrawal)
  NWD-<card>-<terminal>-<LOCATION>     (non-HDFC ATM withdrawal)
  <ref>-TPT-<entity>                   (Third Party Transfer, online)
  CHQDEP-MICRCLG-<branch>              (cheque deposit)
  CHQPAID-MICRCTS-[NO-]<payee>         (cheque paid out)
  IBFUNDSTRANSFER<DR|CR>-<account>     (internet-banking transfer)
  IMPS-<ref>-<narr>-<bank>-X           (IMPS send/receive)
  IMPSP2P<ref>#<date><time>-MIR<ref>   (IMPS P2P)
  <CODE>-<PERIOD>-<ref>-MIR<ref>       (ECS / recurring charge)
"""
from __future__ import annotations
import re
from . import _shared as S

_MERCHANT_TAILS = (
    "POSDEBIT", "POSSDEBIT", "POS DEBIT", "POS SDEBIT",
    "SDEBIT", "PO SDEBIT", "POS DEBI T", "POSDE BIT",
)

_POS_RE = re.compile(
    r"^POS(?P<card>\d{6}[X*]{4,8}\d{4})(?P<merchant>.+?)"
    r"(?:PO\s*S?DEBIT|POS\s*DEBIT|SDEBIT)\s*$", re.I)

_POSREF_RE = re.compile(
    r"^POSREF(?P<card>\d{6}[*X]{4,8}\d{4})-(?P<mmdd>\d{2}/\d{2})"
    r"(?P<merchant>.+)$", re.I)

_CRVPOS_RE = re.compile(
    r"^CRVPOS(?P<card>\d{6}[*X]{4,8}\d{4})(?P<tag>.+)$", re.I)

_ATM_RE = re.compile(
    r"^(?P<kind>ATW|NWD)-(?P<card>\d{6}[X*]{4,8}\d{4})-"
    r"(?P<terminal>[A-Z0-9]+)-(?P<location>[A-Z]+?)(?:HDFCBAN.*)?$", re.I)

_TPT_RE = re.compile(r"^(?P<ref>\d{10,})-TPT-(?P<merchant>.+)$", re.I)

_CHQDEP_RE  = re.compile(r"^CHQDEP-MICRCLG-(?P<branch>.+)$", re.I)
_CHQPAID_RE = re.compile(r"^CHQPAID-MICRCTS-(?:NO-)?(?P<payee>.+)$", re.I)

_IB_RE = re.compile(
    r"^IBFUNDSTRANSFER(?P<direction>CR|DR)-(?P<account>\d+)$", re.I)

_IMPS_RE = re.compile(
    r"^IMPS-(?P<ref>\d+)-(?P<narr>.+?)(?:-(?P<bank>[A-Z]{3,5}))?-X\s*.*$", re.I)

_IMPSP2P_RE = re.compile(
    r"^\.?IMPSP2P(?P<ref>\d+)#\d{2}/\d{2}/\d{4}\d*\s*-MIR(?P<mir>\d+).*$", re.I)

_MIR_RE = re.compile(
    r"^(?P<code>[A-Z]{4,})-(?P<period>[A-Z]+-[A-Z]+\d*)-\d+-MIR.*$", re.I)

# Modern HDFC UPI envelope (2022+ statements):
#   UPI-<NAME>-<VPA_LOCAL>@<HANDLE>-<IFSC>-<REF>-<TYPE>
# Example: UPI-SAMEERTASIBULLAKHA-SAMEERKHAN.SK17-1@OKHDFCBANK-HDFC0000146-327302563522-UPI
#
# PDF column cuts truncate narrations at arbitrary points, so we only
# *require* the NAME+VPA_LOCAL heads; everything else is scanned from the
# tail.
_UPI_MODERN_HEAD_RE = re.compile(
    r"^UPI-(?P<name>[A-Z0-9]+)-(?P<rest>.+)$", re.I)


def decode(narration: str) -> dict:
    raw = (narration or "").strip()
    compact = S.compact(raw)
    up = compact.upper()

    # 1. Universal static events (interest, TDS, bank charges)
    hit = S.match_static_event(up)
    if hit:
        ch, merch = hit
        if ch == "interest_credit":
            merch = "HDFC Bank — Savings Interest"
        return S.result(ch, merch, None, None, None, "static")

    # 2. POS (two variants) + fuel reversal
    m = _POS_RE.match(compact)
    if m:
        merchant = S.titlecase(S.strip_tails(m.group("merchant"), _MERCHANT_TAILS))
        return S.result("pos", merchant, None, S.card_last4(m.group("card")),
                        None, "pos")
    m = _POSREF_RE.match(compact)
    if m:
        return S.result("pos", S.titlecase(m.group("merchant")), None,
                        S.card_last4(m.group("card")), m.group("mmdd"), "posref")
    m = _CRVPOS_RE.match(compact)
    if m:
        tag = m.group("tag").upper()
        if "FUEL" in tag or "DISCOUNTONFUE" in tag:
            return S.result("fuel_reversal", "Fuel Surcharge Reversal", None,
                            S.card_last4(m.group("card")), None, "crvpos_fuel")
        return S.result("fuel_reversal", S.titlecase(tag), None,
                        S.card_last4(m.group("card")), None, "crvpos_other")

    # 3. ATM
    m = _ATM_RE.match(compact)
    if m:
        kind = m.group("kind").upper()
        loc = S.titlecase(m.group("location"))
        channel = "atm_hdfc" if kind == "ATW" else "atm_other"
        merchant = (f"HDFC Bank ATM — {loc}" if kind == "ATW"
                    else f"Non-HDFC ATM — {loc}")
        return S.result(channel, merchant, loc, S.card_last4(m.group("card")),
                        m.group("terminal"), "atm", "HDFC Bank")

    # 4. TPT (third-party transfer, raw preserves hyphens)
    m = _TPT_RE.match(raw)
    if m:
        return S.result("tpt", S.titlecase(m.group("merchant")), None, None,
                        m.group("ref"), "tpt")

    # 5. Cheque deposit / paid
    m = _CHQDEP_RE.match(raw)
    if m:
        branch = S.titlecase(m.group("branch").replace(",", " "))
        return S.result("cheque_deposit", f"Cheque Deposit — {branch}",
                        branch, None, None, "chqdep")
    m = _CHQPAID_RE.match(raw)
    if m:
        return S.result("cheque_paid", S.titlecase(m.group("payee")),
                        None, None, None, "chqpaid")

    # 6. Internet-banking fund transfer (to/from another HDFC account)
    m = _IB_RE.match(compact)
    if m:
        direction = m.group("direction").upper()
        acct = m.group("account")
        return S.result("ib_xfer", f"HDFC A/c {acct[-4:]}", None, None, acct,
                        "ib_xfer:" + direction.lower(), "HDFC Bank")

    # 7. IMPS
    m = _IMPSP2P_RE.match(raw)
    if m:
        return S.result("imps", "IMPS P2P Transfer", None, None,
                        m.group("mir"), "imps_p2p")
    m = _IMPS_RE.match(raw)
    if m:
        bank = S.identify_bank(m.group("bank")) if m.group("bank") else None
        return S.result("imps", S.titlecase(m.group("narr")), None, None,
                        m.group("ref"), "imps", bank)

    # 8. Recurring ECS / service charge codes
    m = _MIR_RE.match(raw)
    if m:
        return S.result("ecs", f"HDFC — {m.group('code').upper()} charge",
                        None, None, None, "mir_charge")

    # 8b. ACHD / ACHC — NACH (Automated Clearing House) debit / credit.
    #     Used for EMIs, mutual-fund SIPs, utility ECS mandates.
    m = re.match(r"^ACH(?P<dir>[DC])-(?P<umrn>[A-Z0-9]+)-(?P<merchant>.+)$", raw, re.I)
    if m:
        direction = m.group("dir").upper()
        ch = "ecs" if direction == "D" else "ecs_credit"
        return S.result(ch, S.titlecase(m.group("merchant")), None, None,
                        m.group("umrn"), "ach_" + direction.lower())

    # 8c. EMI<numeric>CHQS<numeric>...  — loan-EMI debit (auto-collected)
    m = re.match(r"^EMI(?P<loan>\d+)CHQS\d+.*$", raw, re.I)
    if m:
        return S.result("ecs", "Loan EMI", None, None, m.group("loan"),
                        "emi_chqs", "HDFC Bank")

    # 9. Modern UPI envelope (HDFC 2022+)
    # Head match gives us the name; scan the rest for VPA/IFSC/ref/type.
    m = _UPI_MODERN_HEAD_RE.match(raw.replace(" ", ""))
    if m:
        name = m.group("name")
        rest = m.group("rest")
        # Handle: from @<HANDLE> in VPA (e.g. @OKHDFCBANK → HDFC).
        handle_m = re.search(r"@([A-Z]+)", rest, re.I)
        # IFSC: 4-letter bank code + 0 + 6 alphanumeric
        ifsc_m = S.IFSC_RE.search(rest.upper())
        # Reference: a 10+ digit run
        ref_m = re.search(r"\b(\d{10,})\b", rest)
        bank = None
        if handle_m:
            h = handle_m.group(1).upper()
            # "OKHDFCBANK" → strip leading OK
            if h.startswith("OK"):
                h = h[2:]
            bank = S.identify_bank(h)
        if not bank and ifsc_m:
            bank = S.identify_bank(ifsc_m.group(0))
        return S.result("upi", S.titlecase(name), None, None,
                        ref_m.group(1) if ref_m else None,
                        "upi_modern", bank)

    # 9b. UPI-<NAME> with no further tokens (PDF truncation).
    m = re.match(r"^UPI-(?P<name>[A-Z0-9]+)\s*$", raw.replace(" ", ""), re.I)
    if m:
        return S.result("upi", S.titlecase(m.group("name")), None, None,
                        None, "upi_name_only")

    return S.result("unknown", None, None, None, None, "unmatched")
