# Bank Statement Extraction — Client Integration Guide

For teams building on top of the bank-statement API. Everything you need to send a PDF in and get structured transactions + enrichment back.

If you want the full field-by-field specification, see [api_reference_bank_statement.md](api_reference_bank_statement.md) — this doc is the integrator's quickstart version.

---

## 1. Connection

**Base URL** (staging → prod, same envelope):
- Staging: `https://ledgerflow-api-staging.up.railway.app`
- Production: `https://ledgerflow-api.up.railway.app`

**Auth** — every request needs the `X-API-Key` header. Because your service runs on the same Railway project, you already have access to the same secret the backend validates against:

```bash
# In your Railway service env vars, reference the shared key:
LEDGERFLOW_API_KEY=${{shared.LEDGERFLOW_API_KEY}}
```

Send it as:
```
X-API-Key: $LEDGERFLOW_API_KEY
```

Missing / wrong key → `401` with `{"detail":"Missing or invalid X-API-Key header."}`.

---

## 2. The one endpoint you care about

### `POST /api/extract`

Stateless. PDF in, structured JSON out. No case binding, no account creation, no session. Use this for every integration — the case/entity APIs are for our internal UI and you don't need them.

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Purpose |
|---|---|---|---|
| `file` | file | yes | PDF, ≤25 MB, must start with `%PDF-` |
| `password` | string | no | If the PDF is encrypted |
| `submitted_by` | string | no | Free-text tag stored in our extraction log (e.g. `"billpay-service"`, `"user-xyz"`). Helps us triage if you flag something. Also accepted as `X-Submitter` header. |
| `use_llm` | bool | no | `false` to skip the LLM (faster, cheaper, slightly less rich). Defaults to server config. |
| `llm_providers` | string | no | Comma-sep filter like `claude,gemini-2.5-flash`. Narrows the fan-out. |

---

## 3. Response — the shape you'll parse

```jsonc
{
  "bank":    {"key": "hdfc_savings", "label": "HDFC Savings", "account_type": "SA"},
  "account": {
    "number_masked": "****8420",
    "holder_name":   "Bilal Khan",
    "customer_id":   "74905945",   // optional — only when statement header has it
    "pan_hint":      null,
    "phone_hint":    "18002026161",
    "email_hint":    "kmb78660@gmail.com",
    "branch":        "ANDHERI EAST",
    "joint_holders": []
  },
  "period":  {"start": "2023-10-01", "end": "2024-03-31"},
  "balance": {"opening": 70622.10, "closing": 128530.10, "currency": "INR"},
  "summary": {
    "transaction_count": 42,
    "total_debit":  312450.00,
    "total_credit": 355800.00,
    "net_change":    43350.00
  },
  "transactions": [
    {
      "date":           "2023-10-01",                 // ISO-8601
      "amount":         1200.00,
      "direction":      "debit",                      // "debit" | "credit"
      "description":    "UPI-SAMEERTASIBULLAKHA-SAMEERKHAN.SK17-1@OKHDFCBANK-HDFC0000146-327302563522-UPI",
      "counterparty":   "Sameertasibullakha",         // cleaned name
      "channel":        "UPI",                        // UPI|NEFT|IMPS|RTGS|POS|ATM|ECS|NACH|CHEQUE|CASH|TRANSFER|OTHER
      "category":       "Transfer",
      "balance_after":  69422.10,

      // Narration-decoder output (deterministic, no AI). null when the
      // per-bank decoder didn't match this narration.
      "card_last4":        null,
      "ref_number":        "327302563522",
      "counterparty_bank": "HDFC Bank",

      // LLM enrichment. null when LLM was off or didn't produce these.
      "entity_type":       "individual",              // individual|business|bank|government|self|unknown
      "is_self_transfer":  false,
      "notable_reason":    null
    }
  ],

  // Statement-level LLM analysis. Whole block absent / nullable when use_llm=false.
  "analysis": {
    "narrative_summary":   "Regular salary-credit savings account with …",
    "anomalies": [
      {"severity": "medium", "category": "unusual_amount",
       "description": "Single UPI debit of ₹35,000 — ~10× typical.",
       "related_row_indices": [2]}
    ],
    "risk_level": "low",                               // "low" | "medium" | "high"
    "statement_integrity": {"balance_chain_ok": true, "notes": []}
  },

  "meta": {
    "filename":   "Acct Statement_XX3584_29042024.pdf",
    "page_count": 3,
    "parser":     "hdfc_savings",                      // null on bank-detection failure
    "text_empty": false,                               // true → scanned/image PDF, transactions[] empty
    "issues":     [],                                  // see §5
    "source":     "deterministic+claude",              // which layers produced the rows
    "llm_requested": "default",                        // "on" | "off" | "default"
    "llm_enabled":   true,                             // did the LLM actually fire?
    "llm_overlay": {"provider": "claude", "model": "claude-sonnet-4-5", "overlaid": 42, "unmatched": 0},
    "decoder_stats": {
      "bank_key": "hdfc_savings", "rows_total": 42, "rows_matched": 40,
      "hit_rate": 0.952,
      "rules_fired": {"upi_modern": 32, "atm": 4, "ib_xfer:cr": 3, "chqdep": 1, "unmatched": 2}
    }
  }
}
```

### Fields that matter for most integrations

**Always populated:**
- `summary.*` — headline numbers (counts, totals, net change)
- `transactions[].date` / `amount` / `direction` / `description` — the core ledger

**Populated when deterministic parser knows the bank:**
- `transactions[].counterparty`, `channel`, `category`, `balance_after`
- `bank.key` is one of `hdfc_cc`, `hdfc_savings`, `idfc`, `icici`, `kotak`, `axis`, `sbi`
- `meta.decoder_stats` — use `hit_rate` as a triage signal (see §6)

**Populated when LLM ran successfully** (depends on `use_llm` + server config):
- `account.customer_id` / `pan_hint` / `phone_hint` / `email_hint` / `branch` / `joint_holders`
- `transactions[].entity_type`, `is_self_transfer`, `notable_reason`
- The whole `analysis` block

---

## 4. Controlling the LLM

Two questions to answer: *do I want LLM enrichment at all*, and *which models*.

**Scope comparison:**

| Scope | Field | Example |
|---|---|---|
| Per-call | request `use_llm` | `false` to skip LLM this one time |
| Per-call | request `llm_providers` | `claude,gemini-2.5-flash` |
| Server-wide | env `LLM_ENABLED` | master kill-switch (on our side) |
| Server-wide | env `LLM_GEMINI_MODELS` | which Gemini variants we fan out to |
| Server-wide | env `LLM_PRIMARY` | whose output drives the final rows |

Per-call fields win, with one caveat: **`use_llm=true` cannot force LLM on if we've set `LLM_ENABLED=false`** (we'd have no API keys to use). It can only *disable* for a specific call.

### When to turn LLM off

Send `use_llm=false` when:
- You only need the transactions array, not the `analysis` block
- You're re-ingesting a PDF you've already extracted (deterministic output is stable across calls — LLM isn't)
- Latency matters more than enrichment quality (deterministic + decoder returns in ~1s; LLM adds ~5-15s)
- You're bulk-processing and cost dominates

### What you lose with `use_llm=false`

| Gone | Still there |
|---|---|
| `analysis` block (narrative, anomalies, risk_level) | `summary.*` and all numeric fields |
| `transactions[].entity_type`, `is_self_transfer`, `notable_reason` | `transactions[].counterparty`, `channel`, `category` |
| `account.customer_id` / `pan_hint` / etc. | `account.number_masked`, `holder_name` |
| Unknown-bank fallback extraction | Everything for known banks (hit rate ≥95% on the 7 we cover) |

For a simple "show transactions" UI, `use_llm=false` is almost always the right call.

---

## 5. Error handling

All errors share one envelope:

```json
{"detail": {"error_code": "INVALID_FILE_TYPE",
            "message":    "Only PDF files are supported.",
            "extra":      {"filename": "statement.docx"}}}
```

**Branch on `error_code`, not on `message`** — the code is the contract.

| HTTP | `error_code` | What to do |
|---|---|---|
| 400 | `MISSING_FILE` / `EMPTY_FILE` | Client bug; don't retry |
| 401 | (no body — auth middleware) | Wrong / missing `X-API-Key` |
| 401 | `PDF_PASSWORD_REQUIRED` | Ask user for password; resubmit with `password=` |
| 401 | `PDF_PASSWORD_INCORRECT` | Ask user to retype; resubmit |
| 413 | `FILE_TOO_LARGE` | Tell user 25 MB max; ask them to split or shrink |
| 415 | `INVALID_FILE_TYPE` / `INVALID_PDF_SIGNATURE` | File isn't a PDF — reject on your side |
| 422 | `PDF_UNREADABLE` | Corrupt PDF; surface "file appears damaged" to user |
| 500 | `INTERNAL_ERROR` | Retry once with backoff; if still failing, escalate (ping `saurabh@outris.com` with the `extraction_id` from our logs if you know it) |

### Non-fatal issues (HTTP 200, check `meta.issues[]`)

| Issue code | What happened | What to do |
|---|---|---|
| `scanned_pdf_no_text_layer` | PDF is image-only, no extractable text | Ask user for a text-layer PDF (OCR is not yet enabled) |
| `unknown_bank_format` | We couldn't detect the bank | Extraction may still work — check `summary.transaction_count` and `meta.decoder_stats.hit_rate` |
| `zero_transactions_extracted` | Parsers ran but got nothing | Probably wrong document type or format we don't support — route to manual review |

Multiple issues can appear together. A scanned unknown-bank PDF typically returns `["scanned_pdf_no_text_layer"]` alone (downstream checks are short-circuited).

---

## 6. Trust signals — how confident should you be in a given response?

The API doesn't return a single "confidence" number. Instead we expose the raw signals so you can decide per-use-case:

| Signal | Where | How to read it |
|---|---|---|
| Bank detection | `meta.parser` | `null` → we guessed; trust numerics less, trust `counterparty` much less |
| Decoder hit rate | `meta.decoder_stats.hit_rate` | `≥0.9` great · `0.5-0.9` partial · `<0.5` likely a new narration format we haven't seen |
| Balance reconciliation | `balance.opening` / `closing` vs `summary.net_change` | Should match within rounding — if they don't, the parser missed rows |
| LLM overlay | `meta.source` | `deterministic+<provider>` = normal · `llm-<provider>` = parser failed, LLM did whole extraction (lower reliability) |
| Statement integrity | `analysis.statement_integrity.balance_chain_ok` | When `false`, check `notes[]` — the LLM found a gap |

**Rule of thumb for "should I auto-accept this?":**
- `meta.parser != null` AND `meta.decoder_stats.hit_rate ≥ 0.9` AND balance reconciles → auto-accept
- Anything else → route to manual review lane

---

## 7. Working examples

### cURL
```bash
BASE=https://ledgerflow-api-staging.up.railway.app
KEY=$LEDGERFLOW_API_KEY

# Default (LLM on per server config)
curl -X POST $BASE/api/extract \
  -H "X-API-Key: $KEY" \
  -F "file=@statement.pdf" \
  -F "submitted_by=billpay-service"

# No LLM — deterministic + decoder only
curl -X POST $BASE/api/extract \
  -H "X-API-Key: $KEY" \
  -F "file=@statement.pdf" \
  -F "use_llm=false"

# Override provider fan-out for this call
curl -X POST $BASE/api/extract \
  -H "X-API-Key: $KEY" \
  -F "file=@statement.pdf" \
  -F "llm_providers=claude,gemini-2.5-flash"

# Encrypted PDF
curl -X POST $BASE/api/extract \
  -H "X-API-Key: $KEY" \
  -F "file=@stmt.pdf" \
  -F "password=customer-dob-ddmmyyyy"
```

### Python (requests)
```python
import os, requests

BASE = "https://ledgerflow-api-staging.up.railway.app"
HEADERS = {"X-API-Key": os.environ["LEDGERFLOW_API_KEY"]}

def extract(path: str, use_llm: bool = True) -> dict:
    with open(path, "rb") as f:
        r = requests.post(
            f"{BASE}/api/extract",
            headers=HEADERS,
            files={"file": (os.path.basename(path), f, "application/pdf")},
            data={"submitted_by": "billpay-service",
                  "use_llm": "true" if use_llm else "false"},
            timeout=60,
        )
    r.raise_for_status()
    return r.json()

result = extract("data/statement.pdf", use_llm=False)
print(result["summary"]["transaction_count"], "transactions")
for t in result["transactions"][:5]:
    print(t["date"], t["direction"], t["amount"], "→", t["counterparty"])
```

### Node.js (fetch + FormData)
```js
import fs from 'node:fs';

const BASE = 'https://ledgerflow-api-staging.up.railway.app';

async function extract(path, { useLlm = true } = {}) {
  const fd = new FormData();
  fd.set('file', new Blob([fs.readFileSync(path)], { type: 'application/pdf' }),
         path.split('/').pop());
  fd.set('submitted_by', 'billpay-service');
  fd.set('use_llm', String(useLlm));

  const r = await fetch(`${BASE}/api/extract`, {
    method: 'POST',
    headers: { 'X-API-Key': process.env.LEDGERFLOW_API_KEY },
    body: fd,
  });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}
```

---

## 8. What we keep on our side

Every call — success or failure — is recorded on our side. **You don't need to keep PDFs or raw responses** unless your own compliance requires it:

| Thing | Where | Retention |
|---|---|---|
| Your PDF bytes | Content-addressed PDF store (sha256-keyed, dedup across all callers) | Indefinite (cheap to keep) |
| Request metadata | `extraction_log` table (timestamp, filename, size, hash, submitter tag, client IP, user-agent, success flag) | Indefinite |
| Full response JSON | `extraction_log.response` | Indefinite |
| pdfplumber raw text + deterministic parse | `extraction_trace` table | Indefinite |
| Each LLM call (prompt, raw response, parsed, errors, tokens, cost) | `llm_attempts` table | Indefinite |

This means you can replay any past extraction by passing us the `extraction_id` we logged (ask Saurabh for a read-only lookup endpoint if you need one). It also means we can use your traffic to improve decoder coverage over time (see §9).

### Sharing a PDF with Saurabh for debugging

If a specific extraction is wrong, give us the `filename` + approximate timestamp + the `extraction_id` (it's not in the response today — you can fish it out of `/api/admin/extractions` if you have admin access, or just send the PDF over directly).

---

## 9. How extraction quality will improve over time

We run a four-layer pipeline per statement:

1. **Text extraction** — pdfplumber on text-layer PDFs (OCR for scans is coming).
2. **Deterministic parser** — per-bank regex table parser gives authoritative date / amount / direction / balance.
3. **Narration decoder** — per-bank regex decoder gives channel / merchant / card_last4 / ref_number / counterparty_bank from the narration text. Zero AI.
4. **LLM enrichment** — Claude + Gemini in parallel produce entity_type, is_self_transfer, notable_reason, and the statement-level analysis block.

The narration decoder (layer 3) is hand-written today from patterns we've mined by hand (HDFC's `POS<card><merchant>POSDEBIT`, ICICI's `MMT/IMPS/<ref>/…`, Kotak's `UPI/<name>`, etc.). When your users send us a PDF containing a narration envelope we *haven't* seen before, the decoder returns `matched_rule: "unmatched"` for those rows and the LLM fills the gap. We then use the LLM consensus across those unmatched rows as ground truth to propose new regex rules — so coverage grows over time without you having to do anything.

Practically: `meta.decoder_stats.hit_rate` on a novel bank / format might start at 0.2 and climb to 0.9+ as we onboard its envelopes. Your integration doesn't need to change — just trust the signal.

---

## 10. Limits and expectations

- **File size:** 25 MB hard cap
- **Pages:** no hard cap, but >100 pages + LLM enabled can take 30+ seconds
- **Concurrency:** not rate-limited today (use sensibly; ping us before a bulk run)
- **Idempotency:** none. Same PDF sent twice = two `extraction_log` rows. Response is content-stable for the deterministic layers; LLM output has mild run-to-run variation (it's an LLM).
- **Latency (p50):**
  - `use_llm=false` → ~1-3 seconds
  - `use_llm=true` with one LLM → ~5-10 seconds
  - `use_llm=true` with two LLMs (default) → ~8-15 seconds (they run in parallel)
- **SLA:** none promised today — we're pre-1.0. Expect occasional cold-start delays after redeploys (~10 s first call).

---

## 11. Things that aren't in the response yet (roadmap)

- **Image / scanned-PDF support** — today returns `scanned_pdf_no_text_layer` with empty transactions. OCR path is being benchmarked against Document AI, Azure Document Intelligence, and vision LLMs.
- **Single confidence score** — we return raw signals (see §6). Let us know if a rolled-up score would simplify your UI and we'll add it.
- **Offline / no-LLM deployment** — under way, same codebase, flag-controlled.
- **Automatic rule-mining from unmatched narrations** — the feedback loop that turns your traffic into new decoder rules (see §9). The infrastructure is there; the cron job is queued.

---

## 12. Who to ping

- **Integration questions / API behaviour:** Saurabh (saurabh@outris.com)
- **Production incidents (HTTP 5xx spike, total outage):** same — set up a pager alert on your side that watches for `5xx` rate on `/api/extract` and pings Slack + email
- **Request for new bank coverage:** send us 3-5 sample PDFs + a short note. Turnaround is usually ~1 day for a new bank with clean text layer

---

## 13. Version

Pre-1.0, unversioned. The response envelope and `error_code` vocabulary are the contract — individual `message` strings and new *optional* fields are not. We'll announce breaking changes with at least one week of warning.
