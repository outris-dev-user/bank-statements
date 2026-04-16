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

| Field      | Type   | Required | Notes |
|------------|--------|----------|-------|
| `file`     | file   | yes      | PDF file. Extension must be `.pdf`. Must start with the `%PDF-` signature. Max 25 MB. |
| `password` | string | no       | Password for encrypted PDFs. Omit or leave blank if unencrypted. |

### Limits

- **Max file size**: 25 MB
- **Content type**: `application/pdf` (or `application/octet-stream` as a tolerated fallback since many clients don't set MIME explicitly)
- **OCR**: not enabled. Scanned / image PDFs return a 200 with an empty transactions list and a `meta.issues` flag — see below.

### Success response — `200 OK`

```jsonc
{
  "bank":    {"key": "idfc", "label": "IDFC First Bank", "account_type": "CA"},
  "account": {"number_masked": "****0888", "holder_name": "Saurabh Sethi"},
  "period":  {"start": "2026-04-13", "end": "2026-04-13"},   // ISO-8601
  "balance": {"opening": 1154791.51, "closing": 1129791.51, "currency": "INR"},
  "summary": {
    "transaction_count": 1,
    "total_debit":  25000.00,
    "total_credit":     0.00,
    "net_change":  -25000.00
  },
  "transactions": [
    {
      "date": "2026-04-13",                 // ISO-8601
      "amount": 25000.00,
      "direction": "debit",                 // "debit" | "credit"
      "description": "UPI/DR/840398205126/FPL Tech/UTIB/getonec/UPIInte",
      "counterparty": "FPL Tech",
      "channel": "UPI",                     // UPI | NEFT | IMPS | RTGS | POS | ATM | ECS | NACH | CHEQUE | CASH | OTHER
      "category": "Transfer",
      "balance_after": null                 // populated for hdfc_savings today; null elsewhere
    }
  ],
  "meta": {
    "filename": "IDFC Apr 2026.PDF",
    "page_count": 1,
    "parser": "idfc",                       // null when bank detection failed
    "text_empty": false,                    // true for image-PDFs
    "issues": []                            // see "Non-fatal issues" below
  }
}
```

#### Field notes

- **Dates** are ISO-8601 `YYYY-MM-DD` when parsable, else the raw input string. Period dates derive from the statement header first, then the envelope of the parsed transactions.
- **`balance.opening` / `closing`** are best-effort heuristics over the statement header (`Opening Balance`, `Closing Balance`, `B/F Balance`). Either can be `null` — banks print this inconsistently.
- **`balance_after`** on each transaction is present only for **HDFC Savings** today (its parser tracks running balance). Other parsers don't emit it, so the field is `null`.
- **`counterparty`** is an inference from the raw description. UPI/NEFT/IMPS narrations are stripped of channel + direction prefixes and ref numbers. Not guaranteed to be a real-world entity; use it as a hint, not as truth.
- **`bank.key`** is one of `hdfc_cc`, `hdfc_savings`, `idfc`, `icici`, `kotak`, or `unknown`. When `unknown`, all parsers are tried and any results merged.

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

| Bank key       | Full name                | Account types  | Parser confidence |
|----------------|--------------------------|----------------|-------------------|
| `hdfc_cc`      | HDFC Credit Card         | CC             | Validated on benchmark corpus |
| `hdfc_savings` | HDFC Savings             | SA             | Validated — running balance tracked |
| `idfc`         | IDFC First Bank          | CA / SA        | Validated |
| `icici`        | ICICI Bank               | CA             | Validated |
| `kotak`        | Kotak Mahindra           | SA             | Validated |
| `unknown`      | (fingerprint didn't match) | —            | All parsers tried and merged |

Adding a new bank = one new parser in [plugins/bank/parsers/](plugins/bank/parsers/) + one fingerprint line in `detect_bank()`. Existing banks unaffected.

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
