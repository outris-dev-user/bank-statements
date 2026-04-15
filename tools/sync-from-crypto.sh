#!/usr/bin/env bash
# sync-from-crypto.sh — pulls platform code from the crypto repo into core/
#
# Usage:
#   ./tools/sync-from-crypto.sh           # interactive: show diff for each, prompt to overwrite
#   ./tools/sync-from-crypto.sh --check   # dry-run — print what would change
#   ./tools/sync-from-crypto.sh --force   # overwrite without asking
#
# Run monthly, or when crypto announces a relevant change.
# Updates CRYPTO_SYNC.md with the synced commit SHA.
#
# This is a placeholder. Implement once core/ has its first synced files
# and the boundary has been locked with the crypto team — see
# docs/for-crypto-team.md for the contract.

set -euo pipefail

CRYPTO_REPO="${CRYPTO_REPO:-D:/OneDrive - Outris/Outris/Product/git-repo/crypto/crypto/india-le-platform}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! -d "$CRYPTO_REPO" ]]; then
  echo "ERROR: crypto repo not found at $CRYPTO_REPO"
  echo "Set CRYPTO_REPO env var to override."
  exit 1
fi

echo "Crypto repo:   $CRYPTO_REPO"
echo "Bank repo:     $HERE"
echo
echo "Not implemented yet — see CRYPTO_SYNC.md for the planned file mapping."
echo "First implementation should:"
echo "  1. Read the file mapping from CRYPTO_SYNC.md (the 'What we plan to copy' table)"
echo "  2. For each row: diff upstream vs local; in --check mode just print, otherwise prompt"
echo "  3. Apply the standard sync header to each newly-copied file"
echo "  4. Append a row to CRYPTO_SYNC.md sync-log with date and crypto commit SHA"
exit 0
