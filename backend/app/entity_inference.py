"""Entity inference helpers — turn a raw OCR description into channel,
category, counterparty tokens. Mirrors the ones in
`tools/export-for-frontend.py`. Kept in sync by copy; both are simple.

In Phase 2 these will be replaced by the classification hooks from
`core/analysis/entity_classification.py` (synced from crypto).
"""
from __future__ import annotations
import re
from datetime import datetime

CHANNEL_RX = re.compile(r"\b(UPI|NEFT|IMPS|RTGS|POS|ATM|ECS|NACH|CHEQUE|CHQ|CASH)\b", re.I)
CATEGORY_KEYWORDS = [
    ("salary",   ["SALARY", "SAL CREDIT", "SAL-"]),
    ("rewards",  ["CASHBACK", "REWARD", "REFERRAL"]),
    ("finance",  ["CRED", "CREDIT CARD", "LOAN", "EMI", "INTEREST"]),
    ("shopping", ["AMAZON", "FLIPKART", "SWIGGY", "ZOMATO", "MYNTRA", "MEESHO"]),
    ("food",     ["RESTAURANT", "HOTEL", "ZEPTO", "BLINKIT", "CAFE"]),
    ("rent",     ["RENT", "LANDLORD"]),
    ("transfer", ["UPI", "NEFT", "IMPS", "RTGS", "IFT"]),
    ("cash",     ["ATM", "CASH"]),
    ("charges",  ["FEE", "CHG", "CHARGE", "GST"]),
]


def iso_date(ddmmyyyy: str) -> str:
    try:
        return datetime.strptime(ddmmyyyy, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return ddmmyyyy


def infer_channel(description: str) -> str:
    m = CHANNEL_RX.search(description)
    return m.group(1).upper() if m else "OTHER"


def infer_category(description: str) -> str:
    up = description.upper()
    for cat, keys in CATEGORY_KEYWORDS:
        if any(k in up for k in keys):
            return cat.title()
    return "Other"


def infer_counterparty(description: str, channel: str = "OTHER") -> str:
    text = re.sub(r"^(UPI|NEFT|IMPS|RTGS|POS|ATM)[-/\s]*", "", description, flags=re.I)
    text = re.sub(r"[-/]\d{6,}.*$", "", text)
    text = re.sub(r"-\d{4}-\d{10,}", "", text)
    tokens = re.split(r"[-/@]", text.strip(), maxsplit=1)
    head = tokens[0].strip() if tokens else text.strip()
    return (head[:50] or "(unknown)")
