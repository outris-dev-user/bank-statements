#!/usr/bin/env bash
# smoke-test-e2e.sh — bring up backend + frontend and verify the
# LedgerFlow stack boots end-to-end.
#
# Usage:
#   bash tools/smoke-test-e2e.sh           # starts both, pokes, reports, keeps running
#   bash tools/smoke-test-e2e.sh --check   # starts both, pokes, reports, exits
#
# Does NOT install dependencies; run `npm install` and `pip install -e .`
# in frontend/ and backend/ respectively first.

set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_PORT=8000
FRONTEND_PORT=5173
CHECK_ONLY="${1:-}"

cleanup() {
  echo ""
  echo "--- cleaning up ---"
  [[ -n "${BACK_PID:-}" ]] && kill "$BACK_PID" 2>/dev/null || true
  [[ -n "${FRONT_PID:-}" ]] && kill "$FRONT_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT

echo "--- starting backend on :$BACKEND_PORT ---"
cd "$HERE/backend"
python -m uvicorn app.main:app --port "$BACKEND_PORT" --log-level warning >/tmp/ledgerflow-back.log 2>&1 &
BACK_PID=$!
cd "$HERE"

echo "--- waiting for backend ---"
for i in $(seq 1 20); do
  if curl -fs "http://localhost:$BACKEND_PORT/api/health" >/dev/null 2>&1; then
    echo "  backend up"
    break
  fi
  sleep 0.5
  [[ $i -eq 20 ]] && { echo "  backend did NOT come up"; tail /tmp/ledgerflow-back.log; exit 1; }
done

echo ""
echo "--- /api/health ---"
curl -s "http://localhost:$BACKEND_PORT/api/health" | python -m json.tool

echo ""
echo "--- /api/cases (summary) ---"
curl -s "http://localhost:$BACKEND_PORT/api/cases" | python -c "
import json, sys
d = json.load(sys.stdin)
print(f'{len(d)} cases:')
for c in d:
    print(f'  {c[\"fir_number\"]}: {c[\"transaction_count\"]} txns, {c[\"statement_count\"]} statements, {c[\"flag_count\"]} flags')
"

echo ""
echo "--- /api/cases/c1/transactions (first 3) ---"
curl -s "http://localhost:$BACKEND_PORT/api/cases/c1/transactions?limit=3" | python -c "
import json, sys
d = json.load(sys.stdin)
print(f'total={d[\"total\"]}, returned {len(d[\"items\"])}:')
for t in d['items']:
    ct = t['entities'].get('counterparty', {}).get('value', '-')
    print(f'  {t[\"txn_date\"]} {t[\"direction\"]} INR {t[\"amount\"]:>10,.2f}  {ct}')
"

echo ""
echo "--- PATCH /api/transactions/t1 (set category=Salary) ---"
curl -s -X PATCH "http://localhost:$BACKEND_PORT/api/transactions/t1" \
  -H 'content-type: application/json' \
  -d '{"entities": {"category": {"value": "Salary", "source": "user_edited", "confidence": 1.0}}}' \
  | python -c "
import json, sys
t = json.load(sys.stdin)
cat = t['entities'].get('category', {}).get('value', '-')
print(f'  t1 now category={cat}, edit_count={t[\"edit_count\"]}')
"

echo ""
echo "--- /api/transactions/t1/audit ---"
curl -s "http://localhost:$BACKEND_PORT/api/transactions/t1/audit" | python -m json.tool

if [[ "$CHECK_ONLY" == "--check" ]]; then
  echo ""
  echo "--- --check mode: backend passes, not starting frontend ---"
  exit 0
fi

echo ""
echo "--- starting frontend dev server on :$FRONTEND_PORT ---"
cd "$HERE/frontend"
npm run dev >/tmp/ledgerflow-front.log 2>&1 &
FRONT_PID=$!
cd "$HERE"

echo "--- waiting for frontend ---"
for i in $(seq 1 40); do
  if curl -fs "http://localhost:$FRONTEND_PORT/" >/dev/null 2>&1; then
    echo "  frontend up"
    break
  fi
  sleep 0.5
done

echo ""
echo "=========================================="
echo "  LedgerFlow running locally:"
echo "  Backend:  http://localhost:$BACKEND_PORT  (docs at /docs)"
echo "  Frontend: http://localhost:$FRONTEND_PORT"
echo "=========================================="
echo "  Press Ctrl-C to stop both."
echo ""
wait
