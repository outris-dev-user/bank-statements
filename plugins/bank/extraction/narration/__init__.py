"""Bank-narration decoder package.

Structure:
  _shared.py       shared primitives (card/VPA/bank-code parsers, text cleanup)
  hdfc_savings.py  HDFC savings envelope
  icici.py         ICICI current/savings envelope
  idfc.py          IDFC First Bank envelope

Public API:
  decode(bank_key, narration) -> dict
    returns {channel, merchant, location, card_last4, ref_number,
             counterparty_bank, matched_rule}
"""
from __future__ import annotations
from . import _shared, hdfc_savings, icici, idfc

_DECODERS = {
    "hdfc_savings": hdfc_savings.decode,
    "icici":        icici.decode,
    "idfc":         idfc.decode,
}


def decode(bank_key: str, narration: str) -> dict:
    fn = _DECODERS.get(bank_key)
    if fn is None:
        return _shared.result("unknown", None, None, None, None,
                              "no_decoder")
    return fn(narration)


__all__ = ["decode"]
