# Deploying LedgerFlow on Railway

Two services from this same repo:

| Service | Subtree used | Builder | Port |
|---|---|---|---|
| **ledgerflow-api**      | `backend/` + `plugins/` | Dockerfile (`backend/Dockerfile`) | `$PORT` → uvicorn |
| **ledgerflow-frontend** | `frontend/` | Dockerfile (`frontend/Dockerfile`) | `$PORT` → nginx |

Both deploy from the same GitHub repo; each Railway service uses its own `railway.json` to point at its Dockerfile. **Both services should keep Root Directory = blank** (repo-root build context) — the backend needs it so `plugins/` is visible, and the Dockerfiles are written to reference their subtrees with explicit `backend/…` / `frontend/…` paths.

---

## 1 — Backend service

### Create the service
- New Railway service → connect this repo
- **Root Directory**: leave blank (repo root). The backend needs `plugins/bank/` which sits beside `backend/`, so Railway must see the whole repo.
- **Builder**: Dockerfile (auto-picked via `backend/railway.json`; in the service UI, Settings → Build → Builder should read "Dockerfile", Dockerfile Path `backend/Dockerfile`). If it's stuck on Nixpacks/Railpack, set it manually here — `railway.json` should win, but the UI override takes precedence if ever set.

### Environment variables
| Name | Required | Notes |
|---|---|---|
| `LEDGERFLOW_API_KEY` | **yes, in prod** | Any hard-to-guess string. Clients must send it in the `X-API-Key` header. If unset, the API is fully open (dev mode). |
| `ALLOWED_ORIGINS`    | yes | Comma-separated list. For a fronted-only deploy: `https://your-frontend.up.railway.app`. Add additional origins comma-separated. |
| `DATABASE_URL`       | optional → recommended | When set, the backend uses Postgres instead of the local SQLite file. On Railway, add a Postgres plugin and reference it as `${{Postgres.DATABASE_URL}}`. Supports both `postgres://` and `postgresql://` forms — we rewrite to the psycopg driver automatically. |
| `LEDGERFLOW_PDF_STORE_DIR` | optional → recommended | Absolute path where uploaded PDFs are archived (content-addressed by sha256). On Railway, mount a **volume** and set this to the mount path (e.g. `/data/pdf_store`). Without a volume, archived PDFs are lost on every redeploy. |
| `LLM_ENABLED`        | no  | Set to `1` to turn on dual-provider LLM extraction. When off (default), only the deterministic regex parser runs. |
| `ANTHROPIC_API_KEY`  | yes, if `LLM_ENABLED=1` | Claude API key. |
| `GOOGLE_API_KEY`     | yes, if `LLM_ENABLED=1` | Gemini API key. (Accepts `GEMINI_API_KEY` as an alias.) |
| `LLM_CLAUDE_MODEL`   | no  | Override Claude model id. Default `claude-sonnet-4-5`. |
| `LLM_GEMINI_MODEL`   | no  | Override default Gemini model id. Default `gemini-2.5-pro`. Ignored when `LLM_GEMINI_MODELS` is set. |
| `LLM_GEMINI_MODELS`  | no  | Comma-separated list of Gemini models to call on every extraction — for head-to-head quality comparison. Example: `gemini-2.5-flash,gemini-2.5-pro`. Each listed model produces its own `llm_attempts` row per upload, so you pay per model. Unset = call only `LLM_GEMINI_MODEL`. |
| `PORT`               | auto | Railway injects. |
| `LEDGERFLOW_RESET_DB`| no  | Set to `1` once to reset+reseed the case store on startup. Does **not** drop `extraction_log`, `extraction_trace`, or `llm_attempts`. |
 minor edit
### Generate an API key
Any 32-byte URL-safe random string is fine:
```
python -c "import secrets; print(secrets.token_urlsafe(32))"
```
Save this — both the frontend service and your internal main API will need it.

### Verify after deploy
```
curl https://<api-service>.up.railway.app/api/health
# → {"status":"ok", ...}

curl -X POST https://<api-service>.up.railway.app/api/extract \
  -H "X-API-Key: <your-key>" \
  -F "file=@statement.pdf"
# → {"bank":{...}, "transactions":[...], ...}

# Encrypted PDF:
curl -X POST https://<api-service>.up.railway.app/api/extract \
  -H "X-API-Key: <your-key>" \
  -F "file=@statement.pdf" \
  -F "password=hunter2"
```

### Persistence

Three storage surfaces, two of them survive redeploys only if you wire them up:

| Data | Backed by | Survives redeploy? |
|---|---|---|
| Case store (cases, persons, accounts, statements, transactions, entities) | SQLite file if `DATABASE_URL` unset; Postgres when set | Yes, when `DATABASE_URL` is set to a Railway Postgres. |
| Extraction log (every `/api/extract` call + what we returned) | Same DB as case store | Yes, when `DATABASE_URL` is set. |
| Archived PDFs (raw bytes, keyed by sha256) | Filesystem at `LEDGERFLOW_PDF_STORE_DIR` | Yes, when pointed at a Railway volume mount. Otherwise they're on the ephemeral container disk and lost on redeploy. |

**Recommended production setup** (covers the friends-and-family data collection):
1. Add a **Postgres** service to the Railway project. Copy `${{Postgres.DATABASE_URL}}` into the backend service's `DATABASE_URL` env var.
2. Add a **Volume** to the backend service. Pick a mount path (e.g. `/data`). Set `LEDGERFLOW_PDF_STORE_DIR=/data/pdf_store`.
3. Redeploy.

First deploy after adding these auto-creates every table (incl. `extraction_log`) via `Base.metadata.create_all` on startup. No manual migration step.

**Minimal deploy** (just the stateless extract endpoint):
Skip Postgres + volume. SQLite on ephemeral disk is fine — nothing is retained, but `/api/extract` keeps working.

---

## 2 — Frontend service

### Create the service
- New Railway service → same repo
- **Root Directory**: leave blank (repo root). The Dockerfile copies `frontend/*` explicitly.
- **Builder**: Dockerfile, path `frontend/Dockerfile` (auto-picked via `frontend/railway.json`).

### Environment variables (set as Build Args too)
Vite bakes these into the bundle **at build time**. When you change any of them, Railway redeploys automatically.

| Name | Value |
|---|---|
| `VITE_API_URL`        | `https://<api-service>.up.railway.app` (no trailing slash) |
| `VITE_API_KEY`        | Same key as backend's `LEDGERFLOW_API_KEY`. Note: baked into the bundle, visible via browser devtools. OK for a gated demo — not a real secret. |
| `VITE_DEMO_PASSWORD`  | Any string. Shown the user on the login overlay. Unset = no overlay. |

### Verify after deploy
Hit the frontend URL in a browser → demo password prompt appears. Enter the password → the app loads and talks to the backend with the key attached.

Also:
```
curl https://<frontend-service>.up.railway.app/healthz
# → ok
```

---

## 2b — Extraction log & admin endpoints

Every call to `/api/extract` is recorded (success or failure) in an `extraction_log` table, and valid PDFs (those that pass the `%PDF-` signature check) are archived in the PDF store. Useful for:
- Promoting the API to friends/family and collecting real statements for parser-quality analysis.
- Replaying old PDFs after a parser change to see whether extraction improved.
- Debugging reports — "I uploaded X and got Y" becomes a lookup.

### Optional submitter tag
Callers can mark their submissions so you can filter the log later:
- Form field: `submitted_by=rahul-cousin`, OR
- Header: `X-Submitter: rahul-cousin`

### Admin endpoints
All require the same `X-API-Key` header.

```
# List recent, most-recent-first. Filters optional.
GET /api/admin/extractions?limit=50&offset=0&success=true&bank=hdfc_cc&submitter=rahul-cousin
  → {"total": N, "offset": 0, "limit": 50, "items": [...]}

# Full detail of one extraction (incl. the response JSON we returned).
GET /api/admin/extractions/{extraction_id}
  → {..., "response": {...}}

# Download the archived PDF.
GET /api/admin/extractions/{extraction_id}/pdf
  → application/pdf stream

# Full diagnostic trace: raw pdfplumber text + deterministic parser raw output.
GET /api/admin/extractions/{extraction_id}/trace
  → {..., "pdfplumber_text": "...", "deterministic_raw": [...]}

# Every LLM attempt for this extraction (both Claude and Gemini in dual mode).
GET /api/admin/extractions/{extraction_id}/llm-attempts
  → {"attempts": [...], "agreement": {...}}

# Cross-cutting: browse every LLM call ever made.
GET /api/admin/llm-attempts?provider=claude&bank=axis_savings&has_error=false
  → {"total": N, "items": [...]}
```

### LLM extraction — what gets recorded

When `LLM_ENABLED=1`, every `/api/extract` call runs Claude and Gemini concurrently on the pdfplumber text (regardless of whether the deterministic regex parser succeeded). For each call we persist:

1. The raw PDF bytes (keyed by sha256) in the PDF store
2. The pdfplumber text output and the deterministic parser's raw output (`extraction_trace` table)
3. One row per provider per call (`llm_attempts` table), storing the full prompt we sent, the verbatim response we got back, the parsed JSON, token counts, latency, and any errors
4. The final response we returned to the caller (`extraction_log.response_json`)

Nothing is lost. Any single upload can be inspected end-to-end: `GET /api/admin/extractions/{id}/pdf` + `/trace` + `/llm-attempts` gives you the complete audit trail.

Response priority: deterministic (if it found transactions) → Claude → Gemini → empty shape. `response.meta.source` identifies which path produced the final answer.

### Friends-and-family rollout — checklist
- [ ] Postgres + Volume set up on Railway (see Persistence section above).
- [ ] Demo gate on the frontend set to a known password so only invited folks get in.
- [ ] Consent line visible on upload — something like:
      _"By uploading, you agree to share this PDF with Outris for testing purposes. We store the file and the extraction result. Email us to delete."_
- [ ] Send each tester the URL + demo password + their `submitted_by` tag so you can filter their uploads later.


## 3 — Internal-service integration

Your main client-facing API calls the backend like any other internal dependency:

```python
resp = httpx.post(
    f"{LEDGERFLOW_URL}/api/extract",
    headers={"X-API-Key": LEDGERFLOW_API_KEY},
    files={"file": ("stmt.pdf", pdf_bytes, "application/pdf")},
    data={"password": pdf_password} if pdf_password else None,
    timeout=60,
)
resp.raise_for_status()
data = resp.json()
# data["bank"], data["account"], data["period"], data["balance"],
# data["summary"], data["transactions"][...], data["meta"]
```

The key lives as an env var on *both* services (same value). Rotate by generating a new key, setting it on the backend first, then on the main service.

---

## 4 — Response shape reference (`/api/extract`)

```jsonc
{
  "bank":    {"key": "idfc", "label": "IDFC First Bank", "account_type": "CA"},
  "account": {"number_masked": "****0888", "holder_name": "Saurabh Sethi"},
  "period":  {"start": "2026-04-13", "end": "2026-04-13"},   // ISO-8601
  "balance": {"opening": null, "closing": null, "currency": "INR"},
  "summary": {
    "transaction_count": 12,
    "total_debit":  45000.00,
    "total_credit": 20000.00,
    "net_change":  -25000.00
  },
  "transactions": [
    {
      "date": "2026-04-13",          // ISO-8601
      "amount": 25000.00,
      "direction": "debit",          // "debit" | "credit"
      "description": "UPI/DR/840398205126/FPL Tech/UTIB/...",
      "counterparty": "FPL Tech",
      "channel": "UPI",              // UPI, NEFT, IMPS, RTGS, POS, ATM, ECS, NACH, CHEQUE, CASH, OTHER
      "category": "Transfer",
      "balance_after": null          // populated for hdfc_savings; null elsewhere
    }
  ],
  "meta": {
    "filename": "IDFC Apr 2026.PDF",
    "parser": "idfc",                // null when bank detection failed
    "text_empty": false              // true for scanned/image PDFs — no txns extracted
  }
}
```

Password-protected PDF with wrong/missing password → `401 {"detail": "PDF is password-protected. Provide the correct `password` form field."}`.
Missing / invalid `X-API-Key` → `401 {"detail": "Missing or invalid X-API-Key header."}`.
