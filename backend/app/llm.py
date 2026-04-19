"""LLM-based bank-statement extraction.

Runs in parallel with the deterministic parser (during the F&F test phase we
call both LLMs on every request, regardless of whether the regex parser
succeeded, so we can compare them against each other and against the regex
output). Each call records prompt + raw response + parsed JSON + token usage
+ latency in the `llm_attempts` table so nothing is lost.

Providers wired: Anthropic Claude, Google Gemini. Both return the same
extraction schema (see `EXTRACTION_SCHEMA_DOC`) so the downstream response
shape is provider-agnostic.

Designed to be safe to import even when neither provider SDK is available —
attempts to call a disabled provider raise inside the helper, the caller
catches and records a `parse_error`, and the request continues.
"""
from __future__ import annotations
import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any


# ────────────────────────── configuration ──────────────────────────

CLAUDE_MODEL = os.environ.get("LLM_CLAUDE_MODEL", "claude-sonnet-4-5")
GEMINI_MODEL = os.environ.get("LLM_GEMINI_MODEL", "gemini-2.5-pro")


def gemini_models() -> list[str]:
    """Which Gemini model(s) to call per extraction. Accepts a comma-separated
    list in `LLM_GEMINI_MODELS` for head-to-head comparison runs (e.g.
    `gemini-2.5-flash,gemini-2.5-pro` fires both every time) — falls back to
    the single `LLM_GEMINI_MODEL` when unset so existing deployments keep
    their current behaviour."""
    raw = os.environ.get("LLM_GEMINI_MODELS", "").strip()
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    return [GEMINI_MODEL]


def primary_provider_preference() -> list[str]:
    """Ordered list of run_all slot keys (or prefixes) to use as the
    "authoritative" LLM when picking which result overlays onto the
    deterministic response. First entry wins if it succeeded; we fall
    through to the next on parse/provider error.

    Configured via `LLM_PRIMARY` env var (comma-separated). Each entry
    matches a run_all slot by prefix:
      - "claude"                  → the Claude result
      - "gemini-2.5-pro"          → the specific Gemini slot
      - "gemini"                  → any Gemini slot
      - "gemini:gemini-2.5-flash" → exact slot match

    Default order keeps current behaviour (Claude primary, Gemini as
    fallback), so a deploy without the env var set doesn't change the
    selection. During the test phase we call every configured model so
    `llm_attempts` always has the full comparison data regardless of
    which one ended up driving the case-store view.
    """
    raw = os.environ.get("LLM_PRIMARY", "").strip()
    if not raw:
        return ["claude", "gemini-2.5-pro", "gemini-2.5-flash", "gemini"]
    return [e.strip() for e in raw.split(",") if e.strip()]


def pick_primary_response(llm_responses: dict[str, dict]) -> tuple[str | None, dict | None]:
    """Pick the primary LLM response from a `{slot: normalised_response}` dict
    using the configured preference order. Returns `(slot_key, response)`.
    If nothing matched (all models errored), returns `(None, None)`.

    Slot keys look like `"claude"` or `"gemini:gemini-2.5-flash"`; we match
    by prefix so `LLM_PRIMARY=gemini` accepts any Gemini variant."""
    for pref in primary_provider_preference():
        for slot, resp in llm_responses.items():
            # Accept exact match or prefix match on the provider portion.
            if slot == pref or slot.startswith(pref) or slot.replace(":", "-").startswith(pref.replace(":", "-")):
                return slot, resp
            # Also try after the colon (e.g. "gemini-2.5-pro" matching
            # "gemini:gemini-2.5-pro").
            if ":" in slot and slot.split(":", 1)[1] == pref:
                return slot, resp
    return None, None


# USD per 1M tokens — input (prompt) and output (completion). Sourced from
# each provider's public price card. Keep this table honest; the billing
# rollup in the admin API reads straight from here. Unknown models return
# None so we can tell "no data" from "$0.00".
PRICING: dict[str, dict[str, float]] = {
    # Anthropic — https://www.anthropic.com/pricing
    "claude-sonnet-4-5":         {"input": 3.00,  "output": 15.00},
    "claude-sonnet-4-6":         {"input": 3.00,  "output": 15.00},
    "claude-opus-4-5":           {"input": 15.00, "output": 75.00},
    "claude-opus-4-7":           {"input": 15.00, "output": 75.00},
    "claude-haiku-4-5":          {"input": 1.00,  "output": 5.00},
    # Google — https://ai.google.dev/gemini-api/docs/pricing
    # Flash: tiered (<=128k prompt); we use the <=128k rates which apply to
    # bank statements (tens of thousands of tokens).
    "gemini-2.5-flash":          {"input": 0.30,  "output": 2.50},
    "gemini-2.5-pro":            {"input": 1.25,  "output": 10.00},
    "gemini-2.0-flash":          {"input": 0.10,  "output": 0.40},
}


def estimate_cost_usd(model: str | None, prompt_tokens: int | None,
                      completion_tokens: int | None) -> float | None:
    """Compute USD cost for one call from token counts. Returns None when the
    model isn't in the PRICING table (don't silently lie with $0) or when
    token counts are missing (Gemini 429s arrive with nulls — we can't price
    a call that was rejected pre-generation)."""
    if not model:
        return None
    price = PRICING.get(model)
    if price is None:
        # Try a case-insensitive prefix match — providers sometimes append
        # dates ("claude-sonnet-4-5-20260401") to concrete model ids.
        for k, v in PRICING.items():
            if model.lower().startswith(k.lower()):
                price = v
                break
    if price is None:
        return None
    if prompt_tokens is None and completion_tokens is None:
        return None
    pt = prompt_tokens or 0
    ct = completion_tokens or 0
    return round((pt * price["input"] + ct * price["output"]) / 1_000_000, 6)

# Per-provider feature toggles. Read lazily so a redeploy picks up changes.
def claude_enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))

def gemini_enabled() -> bool:
    return bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))

def llm_enabled() -> bool:
    """Master toggle. LLM fallback only runs when this is truthy AND at least
    one provider has a key."""
    if os.environ.get("LLM_ENABLED", "").lower() not in ("1", "true", "yes", "on"):
        return False
    return claude_enabled() or gemini_enabled()


# The raw input to the LLM is the pdfplumber-extracted text. Cap at ~40K chars
# (~10K tokens). Statements longer than that are *extremely* rare; we trim the
# tail rather than skip entirely and flag it for the record.
MAX_TEXT_CHARS = 40_000


# ────────────────────────── schema / prompt ──────────────────────────

EXTRACTION_SCHEMA_DOC = """{
  "bank": {
    "key": "stable snake_case id, e.g. 'axis_savings', 'hdfc_cc'",
    "label": "human bank name, e.g. 'Axis Bank'",
    "account_type": "SA | CA | CC | NRE | NRO | OD | other",
    "fingerprint": "30-60 char substring unique to this bank's header — so a future regex parser can detect this bank",
    "layout_notes": "one-line description of how transaction rows are structured (columns, multi-line vs single, date format)"
  },
  "account": {
    "number_masked": "****1234 (last 4 only, or null)",
    "holder_name": "primary holder, stripped of Mr/Mrs/Shri",
    "joint_holders": ["additional names, empty list if none"],
    "customer_id": "bank's customer id if visible in the header, else null",
    "pan_hint": "PAN if printed on the statement, else null",
    "phone_hint": "mobile number if printed, else null",
    "email_hint": "email address if printed, else null",
    "branch": "branch name / code if visible, else null"
  },
  "period": {"start": "YYYY-MM-DD or null", "end": "YYYY-MM-DD or null"},
  "balance": {"opening": 0.0, "closing": 0.0, "currency": "INR"},
  "transactions": [
    {
      "date": "YYYY-MM-DD",
      "amount": 0.0,
      "direction": "debit | credit",
      "description": "raw narration as printed",
      "counterparty": "real entity name extracted from narration, e.g. 'Amazon' not 'UPI/DR/123456/Amazon/...'",
      "entity_type": "individual | business | bank | government | related_party | self | unknown",
      "channel": "UPI | NEFT | IMPS | RTGS | POS | ATM | ECS | NACH | CHEQUE | CASH | OTHER",
      "category": "Shopping | Food | Transport | Travel | Utility | Telecom | Rent | Salary | Interest | Investment | Insurance | Tax | Transfer | Cash | EMI | Fee | Refund | Medical | Education | Entertainment | Subscription | Other",
      "is_self_transfer": false,
      "notable_reason": "null, OR a one-line reason this txn is worth an investigator's attention (unusual amount, round-number cluster, odd counterparty, balance mismatch, etc.)",
      "balance_after": 0.0,
      "transaction_type": "purchase | transfer_in | transfer_out | salary | refund | fee | interest | emi | cash_withdrawal | cash_deposit | other"
    }
  ],
  "narrative_summary": "2–3 sentence description of the account's typical monthly behaviour: income pattern, major spend categories, anything unusual. Written for an investigator reading one glance.",
  "anomalies": [
    {
      "type": "round_amount_cluster | duplicate_reference | balance_mismatch | large_cash_deposit | structured_transfers | unusual_counterparty | same_day_in_out | sudden_balance_spike | dormant_then_active | high_velocity | other",
      "severity": "high | medium | low",
      "description": "Full sentence explaining what you noticed and why it matters",
      "txn_indices": [0, 3, 12]
    }
  ],
  "risk_level": "high | medium | low",
  "statement_integrity": {
    "looks_complete": true,
    "gaps_noticed": "null, or free text describing any suspicious gaps, renumbered rows, or balance chain breaks"
  },
  "confidence": "high | medium | low",
  "notes": "free text — anything ambiguous, skipped, or worth flagging"
}"""


SYSTEM_PROMPT = f"""You extract structured data from Indian bank statements.

Return ONLY a JSON object matching this schema, no prose, no code fences:

{EXTRACTION_SCHEMA_DOC}

Rules:
- Dates ISO-8601 YYYY-MM-DD. If you cannot determine year, use the statement period year.
- Amounts are POSITIVE floats. `direction` tells you debit vs credit.
- Skip opening-balance, closing-balance, and summary rows from `transactions`.
- `counterparty` should be the *real* entity (person, merchant, bank) — strip channel
  prefixes (UPI/ NEFT/), reference numbers, bank suffixes (/UTIB, /HDFC0000001). If
  you can't identify an entity, use the cleanest noun phrase from the narration.
- For a name like "MR. SAURABH SETHI" the `holder_name` is "Saurabh Sethi".

Category vs entity_type — keep these ORTHOGONAL:
- `category` is about WHAT the transaction is FOR (why money moved):
  Shopping, Food, Medical, Transport, Rent, Salary, Tax, Transfer, Cash, Fee,
  Interest, EMI, etc. The same counterparty can have different categories on
  different txns (a friend: Rent one month, Other next month).
- `entity_type` is about WHO the counterparty is (a stable property of them):
    - individual     — a named natural person with no business indicators
    - business       — any commercial entity, merchant, corporate
    - bank           — the txn is a bank-internal event (fee, interest, ATM
                       at this bank's own ATM with no merchant behind it)
    - government     — tax, court, municipal, PSU
    - related_party  — a person or non-commercial counterparty that appears
                       repeatedly in non-arm's-length patterns (family,
                       housemate, personal contact). Use judgement — if a
                       person's name appears 5× with varied amounts, this.
    - self           — counterparty is the holder's own account (same name,
                       same bank internal transfer, UPI handle with holder's
                       own initials/phone). Set `is_self_transfer=true`.
    - unknown        — you truly can't tell from the narration
  Pick "Other" in category only when nothing else fits. Do NOT use the
  category enum for entity_type decisions and vice versa.

`is_self_transfer` should be true whenever entity_type="self". Investigators
use this to measure how much money stayed inside the holder's own network.

`notable_reason` should be null for routine transactions. Fill it only when a
human investigator should specifically look at this row — unusual amount for
this holder's pattern, obvious mismatch, suspicious counterparty, structured
amount just under ₹50K, etc. One short line. Empty means "not notable".

Statement-level fields:
- `narrative_summary`: 2–3 sentences. "Salary ~₹80K credited monthly around
  the 5th. ~60% withdrawn via ATM within a week. Recurring POS at Fortis
  Healthcare suggests chronic medical spend. One unusual ₹1.3L cheque debit
  on 19 July is out of character." Investigator reads this first.
- `anomalies`: array of structured findings (see schema). `txn_indices` are
  0-based positions in the `transactions` array you're about to emit. Empty
  array if nothing notable. Be specific — "5 debits between ₹9,000-₹9,999
  within 8 days to same recipient" is useful; "some round numbers" is not.
- `risk_level`: your overall read. "high" if you found anomalies indicating
  possible laundering/fraud signals; "medium" if there are rough edges worth
  review; "low" for clean statements.
- `statement_integrity`: does the statement itself look intact? Broken
  balance chain, gap in row numbers, or re-pasted sections → flag it.
- If the document is not a bank statement or you cannot parse confidently,
  return `{{"transactions": [], "confidence": "low", "notes": "<why>"}}`.
- The `fingerprint` must be a substring that appears verbatim on the first page
  of this bank's statement layout — we use it for future deterministic detection.

Deterministic-assisted mode:
- When the user message contains a `DETERMINISTIC PRE-PARSE` block, those
  transactions were already extracted by our regex parser. Date, amount and
  direction in that block are AUTHORITATIVE — do NOT change them. Your job is
  to fill in the other fields (counterparty, entity_type, channel, category,
  is_self_transfer, notable_reason, transaction_type, balance_after) by
  reading the full statement text for context. Emit the transactions in the
  same order, same count as the pre-parse. If a pre-parsed row looks clearly
  wrong to you (e.g. an opening-balance row leaked in), still emit it, leave
  counterparty/category best-guess, and flag the disagreement in `notes`.
- Use the deterministic `header_hints` (holder_name_guess, account_number_guess,
  period, opening/closing) as starting points — override only when the raw
  statement text clearly shows a better value. Prefer "unknown"/null over
  guessing when you're uncertain.
"""


# One-line hints per detected bank — appended to the prompt after the
# deterministic parser identifies the layout. The idea is to surface quirks
# the model would otherwise have to infer from scratch on every call.
# Keep each hint under 3 lines; the whole block is pasted verbatim.
BANK_HINTS: dict[str, str] = {
    "hdfc_savings": (
        "HDFC savings POS narrations concatenate the 16-digit card number "
        "(e.g. `490246XXXXXX2310`) directly against the merchant name and a "
        "trailing `POSDEBIT` / `SDEBIT` suffix. Strip both the card number and "
        "the suffix before extracting counterparty. `ATW-<card>-S1...<LOCATION>` "
        "rows are ATM withdrawals — counterparty is the bank's own ATM at "
        "that location."
    ),
    "hdfc_cc": (
        "HDFC credit card statements use short merchant names with a city/"
        "country suffix. The merchant is the first alpha token; strip any "
        "trailing city name. Interest and late fee rows are bank-level."
    ),
    "icici": (
        "ICICI narrations separate fields with `/`. UPI/IMPS/NEFT rows follow "
        "`<channel>/<ref-number>/<counterparty>/<remarks>`. After stripping "
        "the channel prefix and the numeric ref, the next token is the real "
        "counterparty."
    ),
    "axis_savings": (
        "Axis UPI narrations look like `UPI/DR/<ref>/<counterparty>/<bank-code>"
        "/<remarks>`. After stripping `UPI/DR/` and the 12-digit reference, "
        "the first alpha token is the counterparty."
    ),
    "kotak": (
        "Kotak narrations often carry a `UPI-<handle>@<psp>-<counterparty-"
        "name>-<ref>` shape. The counterparty is the last human-readable "
        "token before the numeric ref."
    ),
    "idfc": (
        "IDFC First uses multi-line transaction blocks — the narration can "
        "wrap onto 2-3 lines. Treat any continuation line that starts without "
        "a date as part of the previous row's description."
    ),
}


def build_prompt(
    pdfplumber_text: str,
    bank_hint: str | None = None,
    pre_parsed_txns: list[dict] | None = None,
    header_hints: dict | None = None,
) -> tuple[str, str]:
    """Build the (system, user) prompt pair.

    When `pre_parsed_txns` / `header_hints` are provided (deterministic
    parser succeeded), they're added to the user message as authoritative
    context — the LLM preserves date/amount/direction and fills only the
    enrichment fields. When omitted (unknown bank or scanned-only text),
    the LLM does full extraction from the raw text.
    """
    text = pdfplumber_text or ""
    truncated = len(text) > MAX_TEXT_CHARS
    if truncated:
        text = text[:MAX_TEXT_CHARS] + "\n[...truncated for LLM context window...]"

    sections: list[str] = ["Extract this bank statement."]

    if bank_hint and bank_hint != "unknown":
        sections.append(
            f"Our deterministic regex parser identified this as `{bank_hint}`. "
            f"Use that as the bank.key unless the document clearly contradicts it."
        )
        hint_line = BANK_HINTS.get(bank_hint)
        if hint_line:
            sections.append(f"Bank-specific guidance for `{bank_hint}`:\n{hint_line}")

    if header_hints:
        # Serialise only the fields that are non-null so the model isn't
        # distracted by empty placeholders. Labelled "guesses" so the model
        # knows it's free to correct them with stronger evidence.
        clean_hints = {k: v for k, v in header_hints.items() if v not in (None, "", [])}
        if clean_hints:
            sections.append(
                "DETERMINISTIC HEADER HINTS (best-effort — override only with "
                "strong evidence from the statement text):\n"
                + json.dumps(clean_hints, indent=2, ensure_ascii=False)
            )

    if pre_parsed_txns:
        compact = []
        for t in pre_parsed_txns:
            entry = {
                "date": t.get("date"),
                "amount": t.get("amount"),
                "direction": t.get("direction") or t.get("type"),
                "description": (t.get("description") or "")[:200],
            }
            # Narration decoder output (regex-level, deterministic). When
            # present for a row, the model should treat it as strong prior:
            # use it unless the PDF text clearly contradicts it.
            dec = t.get("decoded") or None
            if dec and dec.get("matched_rule") not in (None, "unmatched", "no_decoder"):
                entry["decoded"] = {
                    k: v for k, v in dec.items()
                    if v not in (None, "") and k != "matched_rule"
                }
            compact.append(entry)
        sections.append(
            f"DETERMINISTIC PRE-PARSE ({len(compact)} transactions — "
            "date/amount/direction are authoritative, DO NOT change them; "
            "emit same order, same count, filling the other fields). "
            "Rows that include a `decoded` block have been pattern-matched "
            "by our regex layer — trust those merchant/channel/card_last4/"
            "ref_number values unless the raw statement text obviously "
            "says otherwise:\n"
            + json.dumps(compact, ensure_ascii=False)
        )

    sections.append(
        f"--- BEGIN STATEMENT TEXT ---\n{text}\n--- END STATEMENT TEXT ---"
    )

    user = "\n\n".join(sections)
    return SYSTEM_PROMPT, user


# ────────────────────────── result dataclass ──────────────────────────

@dataclass
class LLMResult:
    provider: str                         # "claude" | "gemini"
    model: str
    raw_response: str = ""                # full unparsed response text
    parsed: dict[str, Any] | None = None  # parsed JSON, None if parse_error set
    parse_error: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int = 0
    error: str | None = None              # any transport / API error
    prompt_text: str = ""                 # what we sent (system + user concatenated)
    extra: dict[str, Any] = field(default_factory=dict)


# ────────────────────────── JSON extraction helper ──────────────────────────

_CODE_FENCE_RX = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_FIRST_JSON_OBJECT_RX = re.compile(r"\{[\s\S]*\}")


def parse_llm_json(raw: str) -> dict[str, Any]:
    """Parse JSON out of an LLM response that may be wrapped in code fences
    or have leading/trailing prose. Raises ValueError if no JSON found."""
    if not raw:
        raise ValueError("empty response")
    # 1. Strip code fences if present
    m = _CODE_FENCE_RX.search(raw)
    if m:
        candidate = m.group(1).strip()
    else:
        candidate = raw.strip()
    # 2. Try direct parse
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    # 3. Fallback — grab the first {...} block from the full response
    m = _FIRST_JSON_OBJECT_RX.search(raw)
    if not m:
        raise ValueError("no JSON object found in response")
    return json.loads(m.group(0))


# ────────────────────────── provider calls ──────────────────────────

async def call_claude(system: str, user: str) -> LLMResult:
    """Call Anthropic Claude. Runs the SDK in a threadpool since the SDK
    is sync-only in some versions."""
    started = time.time()
    result = LLMResult(provider="claude", model=CLAUDE_MODEL, prompt_text=f"{system}\n\n{user}")
    if not claude_enabled():
        result.error = "ANTHROPIC_API_KEY not set"
        return result
    try:
        from anthropic import Anthropic  # type: ignore
    except ImportError as exc:
        result.error = f"anthropic SDK not installed: {exc}"
        return result

    def _invoke() -> Any:
        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        # Prefill-assistant trick: seeding the assistant turn with `{` forces
        # Claude to start its response with a JSON object and resist any
        # preamble prose. We prepend the `{` back onto the raw response
        # below so parse_llm_json sees the full object.
        return client.messages.create(
            model=CLAUDE_MODEL,
            # 16K covers ~200 txns + the new narrative/anomalies/entity_type
            # fields with headroom. Claude truncates cleanly if ever hit, but
            # we'd rather not see that; 8K was tight on 50-txn statements
            # with the extended schema.
            max_tokens=16384,
            system=system,
            messages=[
                {"role": "user", "content": user},
                {"role": "assistant", "content": "{"},
            ],
        )

    try:
        response = await asyncio.to_thread(_invoke)
        result.latency_ms = int((time.time() - started) * 1000)
        # Concatenate text blocks from the content array.
        text_parts: list[str] = []
        for block in getattr(response, "content", []):
            if getattr(block, "type", None) == "text":
                text_parts.append(getattr(block, "text", ""))
        # Prepend the `{` we prefilled — Claude's response starts after it.
        result.raw_response = "{" + "".join(text_parts)
        usage = getattr(response, "usage", None)
        if usage is not None:
            result.prompt_tokens = getattr(usage, "input_tokens", None)
            result.completion_tokens = getattr(usage, "output_tokens", None)
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        result.latency_ms = int((time.time() - started) * 1000)
        return result

    try:
        result.parsed = parse_llm_json(result.raw_response)
    except Exception as exc:
        result.parse_error = f"{type(exc).__name__}: {exc}"
    return result


async def call_gemini(system: str, user: str, model: str | None = None) -> LLMResult:
    """Call Google Gemini via the google-genai SDK.

    `model` overrides the default — useful for running Flash and Pro on the
    same extraction to compare quality head-to-head. Caller is responsible
    for slotting the returned result under a unique key in `run_all`."""
    chosen_model = model or GEMINI_MODEL
    started = time.time()
    result = LLMResult(provider="gemini", model=chosen_model, prompt_text=f"{system}\n\n{user}")
    if not gemini_enabled():
        result.error = "GOOGLE_API_KEY / GEMINI_API_KEY not set"
        return result
    try:
        from google import genai  # type: ignore
        from google.genai import types as genai_types  # type: ignore
    except ImportError as exc:
        result.error = f"google-genai SDK not installed: {exc}"
        return result

    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

    def _invoke() -> Any:
        client = genai.Client(api_key=api_key)
        # Gemini 2.5 has "thinking" enabled by default. Flash lets you
        # turn it off with budget=0 (cheaper + avoids the 311-token
        # truncation we saw earlier). Pro REQUIRES thinking mode and
        # rejects budget=0 with "This model only works in thinking
        # mode" — so only set budget=0 on Flash. Older SDKs lack
        # ThinkingConfig; fall back silently.
        extra: dict[str, Any] = {}
        if "flash" in (chosen_model or "").lower():
            try:
                extra["thinking_config"] = genai_types.ThinkingConfig(thinking_budget=0)
            except AttributeError:
                pass
        return client.models.generate_content(
            model=chosen_model,
            contents=user,
            config=genai_types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                # 8192 cut off mid-JSON on a 50-txn statement. 32K covers
                # ~200 txns comfortably; both Flash and Pro support this.
                max_output_tokens=32768,
                **extra,
            ),
        )

    try:
        response = await asyncio.to_thread(_invoke)
        result.latency_ms = int((time.time() - started) * 1000)
        # google-genai exposes `.text` as the concatenated primary text output
        result.raw_response = getattr(response, "text", "") or ""
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            result.prompt_tokens = getattr(usage, "prompt_token_count", None)
            result.completion_tokens = getattr(usage, "candidates_token_count", None)
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        result.latency_ms = int((time.time() - started) * 1000)
        return result

    try:
        result.parsed = parse_llm_json(result.raw_response)
    except Exception as exc:
        result.parse_error = f"{type(exc).__name__}: {exc}"
    return result


async def run_all(
    text: str,
    bank_hint: str | None = None,
    pre_parsed_txns: list[dict] | None = None,
    header_hints: dict | None = None,
) -> dict[str, LLMResult]:
    """Call Claude + every configured Gemini model concurrently on the same
    prompt. Returns a `{slot_key: LLMResult}` dict where slot_key is one of
    `"claude"` or `"gemini:<model>"` — keys are unique so repeated Gemini
    calls (Flash vs Pro comparison runs) don't collide.

    When deterministic context (`pre_parsed_txns` / `header_hints`) is
    provided, it's woven into the user prompt — the model uses it as
    authoritative anchors for date/amount/direction and focuses effort on
    the enrichment fields. Without it, the model does full extraction.

    Providers without keys return with an `error` set; the dict always
    contains at least "claude", so downstream code can iterate without
    branching.
    """
    system, user = build_prompt(
        text, bank_hint=bank_hint,
        pre_parsed_txns=pre_parsed_txns,
        header_hints=header_hints,
    )
    tasks: dict[str, Any] = {"claude": call_claude(system, user)}
    for gm in gemini_models():
        tasks[f"gemini:{gm}"] = call_gemini(system, user, model=gm)
    results = await asyncio.gather(*tasks.values(), return_exceptions=False)
    return dict(zip(tasks.keys(), results))


# ────────────────────────── normalisation ──────────────────────────

def normalise_llm_response(parsed: dict[str, Any], source_filename: str) -> dict[str, Any]:
    """Shape an LLM's parsed JSON into the `/api/extract` response envelope.
    Missing sections are filled with nulls / empty lists so the caller can
    treat this indistinguishably from a deterministic response.
    """
    bank = parsed.get("bank") or {}
    account = parsed.get("account") or {}
    period = parsed.get("period") or {}
    balance = parsed.get("balance") or {}
    transactions = parsed.get("transactions") or []

    # Compute summary from transactions if the LLM didn't.
    debits = [float(t.get("amount") or 0) for t in transactions if str(t.get("direction", "")).lower() == "debit"]
    credits = [float(t.get("amount") or 0) for t in transactions if str(t.get("direction", "")).lower() == "credit"]
    total_debit = round(sum(debits), 2)
    total_credit = round(sum(credits), 2)

    return {
        "bank": {
            "key": bank.get("key") or "unknown",
            "label": bank.get("label") or "Unknown",
            "account_type": bank.get("account_type"),
            "fingerprint": bank.get("fingerprint"),
            "layout_notes": bank.get("layout_notes"),
        },
        "account": {
            "number_masked": account.get("number_masked"),
            "holder_name": account.get("holder_name"),
            "joint_holders": account.get("joint_holders") or [],
            "customer_id": account.get("customer_id"),
            "pan_hint": account.get("pan_hint"),
            "phone_hint": account.get("phone_hint"),
            "email_hint": account.get("email_hint"),
            "branch": account.get("branch"),
        },
        "period": {
            "start": period.get("start"),
            "end": period.get("end"),
        },
        "balance": {
            "opening": balance.get("opening"),
            "closing": balance.get("closing"),
            "currency": balance.get("currency") or "INR",
        },
        "summary": {
            "transaction_count": len(transactions),
            "total_debit": total_debit,
            "total_credit": total_credit,
            "net_change": round(total_credit - total_debit, 2),
        },
        "transactions": transactions,
        "analysis": {
            "narrative_summary": parsed.get("narrative_summary"),
            "anomalies": parsed.get("anomalies") or [],
            "risk_level": parsed.get("risk_level"),
            "statement_integrity": parsed.get("statement_integrity"),
        },
        "meta": {
            "filename": source_filename,
            "parser": None,
            "text_empty": False,
            "issues": [],
            "confidence": parsed.get("confidence"),
            "notes": parsed.get("notes"),
        },
    }
