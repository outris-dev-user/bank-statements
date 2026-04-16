# LedgerFlow backend

FastAPI service that hosts `plugins/bank/` parsers and exposes a REST API to the `frontend/`.

**Status:** Phase 1 **stub**. In-memory state seeded from the benchmark parser output. Read + PATCH only; POST (upload/create case) is intentionally not wired yet — [STATUS.md](../STATUS.md) explains when it gets wired.

## Run

```bash
cd backend
pip install -e .
# or:  pip install fastapi "uvicorn[standard]" pydantic pdfplumber python-multipart

uvicorn app.main:app --reload --port 8000
```

OpenAPI docs: http://localhost:8000/docs

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | sanity check + counts |
| GET | `/api/cases` | list cases |
| GET | `/api/cases/{id}` | case + persons + accounts |
| GET | `/api/cases/{id}/transactions` | paginated transactions (optional `?account_id=`) |
| GET | `/api/statements/{id}` | one statement |
| PATCH | `/api/transactions/{id}` | edit entities / tags / amount / date / review_status |
| GET | `/api/transactions/{id}/audit` | list of edit events |

## Shape of the store

```
Case → Person → Account → Statement → Transaction
                                           └─ entities: Dict[str, EntityValue]
                                           └─ tags, flags, audit
```

Seeded at import from the benchmark's parser JSON (see `app/store.py`). Same seeding logic as `tools/export-for-frontend.py` — both point at `benchmarks/results/pdfplumber_text/*.json`.

## How the frontend switches from static realData to live API

1. Create `frontend/src/app/lib/api.ts` exporting the same names the facade in `frontend/src/app/data/index.ts` currently exports.
2. Flip the one line in `data/index.ts` from `./realData` to `./lib/api`.
3. Components don't change — they still import `mockCases`, `mockPersons`, etc. from `../data`.

That refactor is intentionally not done yet. We do it once the backend is persisting real state (not just a seeded stub), so the switch is meaningful.

## What's NOT here

- Persistence. In-memory dict, lost on reload. SQLite next.
- Upload pipeline. POST `/api/cases/{id}/statements` is missing — when wired, it'll call `plugins.bank.extraction.parser.parse_text` and add a new Statement row.
- Auth. Any caller is treated as user `unknown` in audit. JWT integration uses `core/auth/jwt.py` when we get there.
- Real sync-check, forensic patterns, etc. Phase 2.

## Tests

None yet. Basic smoke test:
```bash
uvicorn app.main:app --port 8000 &
curl http://localhost:8000/api/health
curl http://localhost:8000/api/cases
curl http://localhost:8000/api/cases/c1 | head
curl 'http://localhost:8000/api/cases/c1/transactions?limit=3'
```

Expected: health returns `{"status":"ok","cases":2,"persons":4,"accounts":5,"statements":9,"transactions":858}`.
