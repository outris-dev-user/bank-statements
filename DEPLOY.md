# Deploying LedgerFlow on Railway

Two services from this same repo:

| Service | Subtree used | Builder | Port |
|---|---|---|---|
| **ledgerflow-api**      | `backend/` (imports `plugins/bank` from repo root) | Nixpacks | `$PORT` → uvicorn |
| **ledgerflow-frontend** | `frontend/` | Dockerfile (`frontend/Dockerfile`) | `$PORT` → nginx |

Both deploy from the same GitHub repo; each Railway service watches a subtree and uses its own `railway.json`.

---

## 1 — Backend service

### Create the service
- New Railway service → connect this repo
- **Root Directory**: leave blank (repo root). The backend needs `plugins/bank/` which sits beside `backend/`, so Railway must see the whole repo.
- Railway auto-discovers `backend/railway.json` — accept.

### Environment variables
| Name | Required | Notes |
|---|---|---|
| `LEDGERFLOW_API_KEY` | **yes, in prod** | Any hard-to-guess string. Clients must send it in the `X-API-Key` header. If unset, the API is fully open (dev mode). |
| `ALLOWED_ORIGINS`    | yes | Comma-separated list. For a fronted-only deploy: `https://your-frontend.up.railway.app`. Add additional origins comma-separated. |
| `PORT`               | auto | Railway injects. |
| `LEDGERFLOW_RESET_DB`| no  | Set to `1` once to reset+reseed SQLite on startup. |

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

### Persistence note
SQLite at `backend/ledgerflow.sqlite` lives on the container filesystem and is **ephemeral** — cleared on each redeploy. `/api/extract` is stateless (writes a tempfile and deletes it), so the API's headline endpoint survives redeploys fine. The other endpoints (cases, statements, graph) will reset on deploy. If you want the case store to persist, mount a Railway volume at `backend/` and move the sqlite file onto it.

---

## 2 — Frontend service

### Create the service
- New Railway service → same repo
- **Root Directory**: leave blank (repo root). The Dockerfile path is relative.
- Railway picks up `frontend/railway.json` which points at `frontend/Dockerfile`.

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
