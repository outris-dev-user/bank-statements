"""Domain vocabulary for the bank-statement project.

The `core.analysis.entity_classification` module (synced from the crypto
platform) is vocabulary-free — callers supply their own keyword sets.
This file is *our* keyword set: the signals an Indian bank statement
tends to carry.

Keep each list short and precise. Substring match, case-insensitive.
"""
from __future__ import annotations

ENTITY_TYPE_KEYWORDS: dict[str, frozenset[str]] = {
    "merchant": frozenset({
        "amazon", "flipkart", "myntra", "meesho", "ajio", "nykaa",
        "swiggy", "zomato", "zepto", "blinkit", "dunzo",
        "bigbasket", "grofers", "jiomart",
        "bookmyshow", "paytm", "phonepe", "googlepay", "cred",
        "uber", "ola", "rapido", "redbus", "makemytrip", "goibibo", "oyo",
        "netflix", "hotstar", "jiocinema", "sonyliv", "prime",
        "reliance", "airtel", "jio", "bsnl", "vi ", "vodafone",
        "tata", "croma", "reliance digital",
    }),
    "bank": frozenset({
        "hdfc bank", "icici bank", "sbi", "state bank", "axis bank",
        "kotak", "idfc", "bank of baroda", "pnb", "punjab national",
        "yes bank", "indusind", "rbl", "bank of india", "canara bank",
    }),
    "government": frozenset({
        "income tax", "gst", "cgst", "sgst", "igst",
        "government", "govt of india", "reserve bank",
        "employee provident fund", "epfo", "esic",
        "passport", "rto", "municipal", "nagar nigam",
    }),
    "salary": frozenset({
        "salary", "sal credit", "sal-", "payroll",
    }),
    "finance": frozenset({
        "cred", "bajaj finance", "bajaj finserv", "mahindra finance",
        "home loan", "car loan", "personal loan", "emi",
        "credit card", "cc payment", "stock", "zerodha", "groww",
        "upstox", "angel one", "mutual fund", "sip",
    }),
    "utility": frozenset({
        "electricity", "mseb", "bses", "tneb", "kseb",
        "water bill", "gas bill", "mahanagar gas", "indraprastha gas",
        "lpg", "hp gas", "bharat gas",
    }),
}
