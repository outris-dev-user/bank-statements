# Bank Statement Extraction API — Reference

Single endpoint for turning a bank-statement PDF into structured, machine-readable JSON. Stateless: no case binding, no persistence, no session.

**Base URL** — set by your Railway deploy (e.g. `https://ledgerflow-api.up.railway.app`).

---

## Authentication

Every request to `/api/extract` must include an `X-API-Key` header matching the backend's `LEDGERFLOW_API_KEY` env var.

```
X-API-Key: <your-key>
```

`/api/health` bypasses the gate so Railway's probe can hit it. All other `/api/*` paths enforce the key the same way.

---

## `POST /api/extract`

### Request

**Content-Type**: `multipart/form-data`

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | file | yes | PDF file. Extension must be `.pdf`. Must start with the `%PDF-` signature. Max 25 MB. |
| `password` | string | no | Password for encrypted PDFs. Omit or leave blank if unencrypted. |
| `submitted_by` | string | no | Free-text tag stored with the extraction log (e.g. `"internal-api"`, `"rahul-cousin"`). Also accepted as the `X-Submitter` header. |
| `use_llm` | bool | no | Per-request override of the `LLM_ENABLED` env var. Omit to use the server default. `false` skips the LLM entirely (deterministic + decoder only — zero AI cost, much faster, slightly less accurate counterparty naming and no `analysis` block). `true` requires the server to have `LLM_ENABLED=true` and valid API keys; it does not force LLM on if credentials are missing. |
| `llm_providers` | string | no | Comma-separated filter narrowing which LLM slots run for this call. Values are prefix-matched against slot keys (`claude`, `gemini`, or full `gemini-2.5-flash`/`gemini-2.5-pro`). Example: `claude,gemini-2.5-flash` runs only those two. Omit to use the server's default fan-out (`LLM_GEMINI_MODELS` + Claude). |

### Controlling LLM behaviour

Three levers, in order of precedence (per-request beats env):

| Lever | Scope | Values | Purpose |
|---|---|---|---|
| `use_llm` request field | per call | `true` / `false` / omit | Turn the LLM off for a single call (e.g. bulk re-ingest where cost matters). |
| `llm_providers` request field | per call | comma-sep slot prefixes | Narrow the fan-out for this call. |
| `LLM_ENABLED` env var | server | `true` / `false` | Master switch — when off, no call ever triggers the LLM regardless of request fields. |
| `LLM_GEMINI_MODELS` env var | server | comma-sep model IDs | Which Gemini models the server fans out to by default (e.g. `gemini-2.5-flash` for cost, `gemini-2.5-flash,gemini-2.5-pro` for head-to-head comparison). |
| `LLM_PRIMARY` env var | server | comma-sep slot prefixes | Preference order for which provider's output drives the final `transactions` array. Falls through on parse/provider error. |

**Recommended config for internal release:**
- `LLM_ENABLED=true`, `LLM_GEMINI_MODELS=gemini-2.5-flash`, `LLM_PRIMARY=claude,gemini-2.5-flash`.
- Two LLM calls per extraction (Claude + Flash), ~$0.01-0.02/statement. Both opinions retained in the admin `llm_attempts` table for post-hoc analysis. Claude drives the response unless it errors; Flash takes over if it does.

The response always records what actually happened:
- `meta.llm_requested` — `"on"`, `"off"`, or `"default"` (reflects the request field)
- `meta.llm_enabled` — whether the call actually fired
- `meta.llm_providers_filter` — present when `llm_providers` was set
- `meta.source` — `deterministic`, `deterministic+<provider>`, or `llm-<provider>`
- `meta.llm_overlay` — provider + model that produced the final rows (when the overlay path ran)

### Limits

- **Max file size**: 25 MB
- **Content type**: `application/pdf` (or `application/octet-stream` as a tolerated fallback since many clients don't set MIME explicitly)
- **OCR**: not enabled. Scanned / image PDFs return a 200 with an empty transactions list and a `meta.issues` flag — see below.

### Success response — `200 OK`

```jsonc
{
  "bank":    {"key": "hdfc_savings", "label": "HDFC Savings", "account_type": "SA"},
  "account": {
    "number_masked": "****8420",
    "holder_name":   "Bilal Khan",
    "customer_id":   "74905945",         // optional — from statement header when present
    "pan_hint":      null,               // optional — PAN if printed on statement
    "phone_hint":    "18002026161",      // optional
    "email_hint":    "kmb78660@gmail.com",
    "branch":        "ANDHERI EAST",     // optional
    "joint_holders": []                  // optional — array of names if statement lists them
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
      "date": "2023-10-01",
      "amount": 1200.00,
      "direction": "debit",                         // "debit" | "credit"
      "description": "UPI-SAMEERTASIBULLAKHA-SAMEERKHAN.SK17-1@OKHDFCBANK-HDFC0000146-327302563522-UPI",
      "counterparty": "Sameertasibullakha",         // cleaned merchant/payee
      "channel": "UPI",                             // UPI | NEFT | IMPS | RTGS | POS | ATM | ECS | NACH | CHEQUE | CASH | TRANSFER | OTHER
      "category": "Transfer",
      "balance_after": 69422.10,

      // Narration-decoder output (deterministic, no AI). Present when the
      // per-bank decoder matched the row; `null` otherwise.
      "card_last4":        null,
      "ref_number":        "327302563522",
      "counterparty_bank": "HDFC Bank",

      // LLM-supplied enrichment. Present when the LLM call succeeded and
      // returned these fields for the row; `null` otherwise.
      "entity_type":       "individual",            // individual|business|bank|government|self|unknown
      "is_self_transfer":  false,
      "notable_reason":    null                     // short string if the LLM flagged this row
    }
  ],

  // Statement-level LLM analysis. All fields nullable; present only when
  // an LLM call succeeded on the statement.
  "analysis": {
    "narrative_summary":   "Regular salary-credit savings account with monthly household UPI spends and quarterly tax debits.",
    "anomalies": [
      {"severity": "medium",
       "category": "unusual_amount",
       "description": "Single UPI debit of ₹35,000 — ~10× the typical UPI amount on this account.",
       "related_row_indices": [2]}
    ],
    "risk_level": "low",                            // "low" | "medium" | "high"
    "statement_integrity": {
      "balance_chain_ok": true,
      "notes": []
    }
  },

  "meta": {
    "filename":   "Acct Statement_XX3584_29042024.pdf",
    "page_count": 3,
    "parser":     "hdfc_savings",                   // detected bank key; null on detection failure
    "text_empty": false,                            // true for image-only PDFs
    "issues":     [],                               // see "Non-fatal issues" below
    "source":     "deterministic+claude",           // which layer produced the final rows
    "llm_overlay": {                                // present when an LLM overlaid deterministic rows
      "provider":   "claude",
      "model":      "claude-sonnet-4-5",
      "overlaid":   42,
      "unmatched":  0
    },
    "decoder_stats": {                              // narration-decoder coverage for this statement
      "bank_key":     "hdfc_savings",
      "rows_total":   42,
      "rows_matched": 40,
      "hit_rate":     0.952,
      "rules_fired":  {"upi_modern": 32, "atm": 4, "ib_xfer:cr": 3, "chqdep": 1, "unmatched": 2}
    }
  }
}
```

#### Field notes

- **Dates** are ISO-8601 `YYYY-MM-DD` when parsable, else the raw input string. Period dates derive from the statement header first, then the envelope of the parsed transactions.
- **`balance.opening` / `closing`** are best-effort heuristics over the statement header (`Opening Balance`, `Closing Balance`, `B/F Balance`). Either can be `null` — banks print this inconsistently.
- **`balance_after`** on each transaction is populated by the deterministic parser when it reads the bank's running-balance column (HDFC Savings today), and is otherwise filled from the LLM's output when available. `null` means neither path produced a value.
- **`counterparty`** is the best available name — in order of preference: narration-decoder merchant (for hard-rule matches like ATM, cheques, IB transfers), LLM-supplied counterparty, then a regex fallback on the raw description.
- **`counterparty_bank`** is the *other* bank involved in the transaction (identified via IFSC prefix, 4-letter code, or narration keyword). Useful for building money-flow graphs. Null when not identifiable.
- **`ref_number`** is the bank-side reference (UPI ref, UTR, IMPS ref, cheque number) extracted by the decoder. Not guaranteed unique across banks.
- **`entity_type`**, **`is_self_transfer`**, **`notable_reason`** are LLM-only signals — present when the LLM call succeeded and returned them, else `null`. Treat as hints, not truth.
- **`analysis`** is a statement-level block summarising the whole document. All fields nullable. Anomalies include severity, category, a short description, and a list of row indices to inspect. `risk_level` is a coarse tier, not a score — use it for triage, not for decisions.
- **`bank.key`** is one of `hdfc_cc`, `hdfc_savings`, `idfc`, `icici`, `kotak`, `axis`, `sbi`, or `unknown`. When `unknown`, all parsers are tried and any results merged.
- **`meta.source`** documents which layer produced the final rows: `deterministic` (parser only), `deterministic+<provider>` (LLM overlaid on parser output — the normal successful case), or `llm-<provider>` (parser returned nothing, LLM did the whole extraction).
- **`meta.decoder_stats.hit_rate`** is the fraction of rows the narration decoder could pattern-match. Low hit rate (<0.5) usually means either an unrecognised bank format or a heavily truncated PDF text layer — worth flagging for manual review.

#### Non-fatal issues — `meta.issues[]`

Strings that flag known soft-failures the caller may want to surface. Response is still `200`.

| Issue code | Meaning | Suggested caller action |
|---|---|---|
| `scanned_pdf_no_text_layer` | pdfplumber got no text — PDF is likely a scan / image. `transactions` will be empty. | Ask the sender for a text-layer PDF, or retry once OCR is enabled. |
| `unknown_bank_format` | No bank fingerprint matched. We ran all parsers anyway and merged what we found. | The extraction may still be useful; if transaction count looks off, flag for manual review. |
| `zero_transactions_extracted` | The parser ran but found no rows. The PDF might be a summary-only statement, the wrong document, or a format we don't support yet. | Inspect `description` + `filename` and route to manual triage. |

Multiple issues can appear together. Example: a scanned unknown-bank PDF returns `["scanned_pdf_no_text_layer"]` only (the unknown/zero checks are skipped once `text_empty` is set).

---

## Error responses

Every error uses this envelope:

```jsonc
{
  "detail": {
    "error_code": "INVALID_FILE_TYPE",
    "message":    "Only PDF files are supported.",
    "extra":      {"filename": "statement.docx"}   // optional, varies by code
  }
}
```

The HTTP status code plus the `error_code` are stable; the `message` is human-readable and may be tweaked over time. Internal clients should branch on `error_code`, not on the message text.

### Error catalogue

| Status | `error_code` | When | `extra` |
|--------|--------------|------|---------|
| **400** | `MISSING_FILE`            | The `file` field was not present in the multipart body. | — |
| **400** | `EMPTY_FILE`              | The uploaded file is 0 bytes. | — |
| **401** | (no body — middleware)    | `X-API-Key` header missing or doesn't match. `{"detail":"Missing or invalid X-API-Key header."}` | — |
| **401** | `PDF_PASSWORD_REQUIRED`   | PDF is encrypted and no `password` was provided. | — |
| **401** | `PDF_PASSWORD_INCORRECT`  | Password provided was wrong. | — |
| **413** | `FILE_TOO_LARGE`          | File exceeds 25 MB. | `size_bytes`, `max_bytes` |
| **415** | `INVALID_FILE_TYPE`       | Filename doesn't end in `.pdf`, or Content-Type isn't `application/pdf`. | `filename`, `received_content_type` |
| **415** | `INVALID_PDF_SIGNATURE`   | File bytes don't start with `%PDF-`. Likely someone renamed `.jpg` / `.docx` to `.pdf`. | `first_bytes_hex` |
| **422** | `PDF_UNREADABLE`          | pdfplumber threw while opening. Usually corruption. | `underlying_error` (first 200 chars) |
| **500** | `INTERNAL_ERROR`          | Anything unhandled. Check server logs. | — |

### Example failures

```bash
# Non-PDF file
$ curl -X POST $BASE/api/extract -H "X-API-Key: $KEY" -F "file=@note.txt"
HTTP/1.1 415
{"detail":{"error_code":"INVALID_FILE_TYPE",
           "message":"Only PDF files are supported.",
           "extra":{"filename":"note.txt","expected_extension":".pdf"}}}

# Image renamed to .pdf
$ curl -X POST $BASE/api/extract -H "X-API-Key: $KEY" -F "file=@scan.pdf"
HTTP/1.1 415
{"detail":{"error_code":"INVALID_PDF_SIGNATURE",
           "message":"File does not start with %PDF- — it is not a valid PDF.",
           "extra":{"first_bytes_hex":"ffd8ffe000104a46"}}}

# Scanned PDF (real PDF, but image-only pages)
$ curl -X POST $BASE/api/extract -H "X-API-Key: $KEY" -F "file=@scanned.pdf"
HTTP/1.1 200
{"bank":{"key":"unknown",...},
 "transactions":[],
 "meta":{"text_empty":true,"issues":["scanned_pdf_no_text_layer"],...}}

# Encrypted, wrong password
$ curl -X POST $BASE/api/extract -H "X-API-Key: $KEY" \
    -F "file=@stmt.pdf" -F "password=wrong"
HTTP/1.1 401
{"detail":{"error_code":"PDF_PASSWORD_INCORRECT",
           "message":"Incorrect password for the encrypted PDF."}}

# Big file
$ curl -X POST $BASE/api/extract -H "X-API-Key: $KEY" -F "file=@big.pdf"
HTTP/1.1 413
{"detail":{"error_code":"FILE_TOO_LARGE",
           "message":"File exceeds the 25 MB limit.",
           "extra":{"size_bytes":31457280,"max_bytes":26214400}}}
```

---

## Bank coverage

| Bank key       | Full name                  | Account types | Parser           | Narration decoder |
|----------------|----------------------------|---------------|------------------|-------------------|
| `hdfc_cc`      | HDFC Credit Card           | CC            | Validated        | —                 |
| `hdfc_savings` | HDFC Savings               | SA            | Validated (running balance tracked) | ~95% on live samples (legacy POS/ATW/TPT + modern UPI) |
| `idfc`         | IDFC First Bank            | CA / SA       | Validated        | Validated (UPI/IMPS/NEFT/RTGS envelopes) |
| `icici`        | ICICI Bank                 | CA / SA       | Validated        | ~97% on live samples (BIL/INFT, MMT/IMPS, UPI, CLG, VPS) |
| `kotak`        | Kotak Mahindra             | SA            | Validated        | 100% on live sample (UPI/, MB:, PCD/) |
| `axis`         | Axis Bank                  | CA / SA       | Validated        | Documented envelopes; tuning against live samples pending |
| `sbi`          | State Bank of India        | CA / SA       | Validated        | Documented envelopes; tuning against live samples pending |
| `unknown`      | (fingerprint didn't match) | —             | All parsers tried and merged | `meta.decoder_stats.hit_rate` will be 0.0 |

Adding a new bank = one new parser in [plugins/bank/parsers/](plugins/bank/parsers/) + one fingerprint line in `detect_bank()` + one narration decoder in [plugins/bank/extraction/narration/](plugins/bank/extraction/narration/). Existing banks unaffected.

### Extraction pipeline

For every successful call the backend runs up to four layers and records each in `meta.source`:

1. **Text extraction** — pdfplumber (OCR not enabled; scanned PDFs return empty txns + `scanned_pdf_no_text_layer`).
2. **Deterministic parser** — per-bank regex/table parser produces rows with authoritative date/amount/direction/balance.
3. **Narration decoder** — per-bank regex decoder extracts channel, merchant, card last-4, reference number, counterparty bank from the narration. Zero AI. Contributes to `decoder_stats` and overrides the LLM on unambiguous rules (ATM, cheques, IB transfers, bank-internal events).
4. **LLM enrichment** — Claude + Gemini called in parallel; the configured primary provides entity_type, is_self_transfer, notable_reason per row, and the whole `analysis` block.

Layers 3 and 4 are independent — if the LLM call fails the response still includes decoder output; if the decoder produces nothing the LLM output still flows through. `meta.source` tells you which layers contributed.

---

## Integration checklist (internal main API)

1. Set `LEDGERFLOW_API_KEY` on your service's env, identical to the bank-analyser backend.
2. Send every PDF via `multipart/form-data` with `X-API-Key` attached.
3. On `200`:
   - If `meta.issues` includes `scanned_pdf_no_text_layer` → surface "send a text PDF" message to the user.
   - If `summary.transaction_count === 0` and `meta.issues` is non-empty → route to manual review instead of silently passing through.
4. On `4xx`:
   - Branch on `detail.error_code`. Map to user-facing messages on your side.
   - `401` with no `error_code` means your key is wrong (auth middleware); `401` with an `error_code` is a PDF password issue. Different UX.
5. On `5xx` — retry once with backoff, then escalate.

---

## Health check

```
GET /api/health
→ {"status":"ok","cases":...,"persons":...,"accounts":...,"statements":...,"transactions":...}
```

Unauthenticated on purpose — this is what Railway's probe hits.

---

## Versioning

This API is pre-1.0 and unversioned. Breaking changes will be announced; the response envelope and error-code vocabulary are the contract — individual messages and new optional fields are not.
