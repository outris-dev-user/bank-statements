# For the crypto team — proposal for sharing platform code

**Audience:** the crypto investigation platform team (`india-le-platform`).
**From:** bank-analyser team (Saurabh).
**Date:** 2026-04-15.
**TL;DR:** We're building a parallel forensic product (bank-statement analysis for LEA) that wants to reuse ~40% of your platform — the case/investigation/graph/UX/signal layers. We propose **physical code sync** initially (no shared package, no monorepo), with a clear contract on what's "platform" (we copy) vs "domain" (we don't touch). This doc proposes that contract and asks for your input.

---

## Why this proposal exists

Two facts:

1. **You've built a great forensic investigation platform.** The Cytoscape canvas, Case/Investigation models, signal framework (TESTED/CLEAR/NOT_TESTED), velocity analyzer, multi-hop exposure analyzer, and Neo4j/NetworkX graph wrappers are all **domain-agnostic**. They work for *any* forensic investigation domain — crypto today, bank statements next, hawala/gold/shell-companies later.

2. **We need them.** We're shipping a bank statement analyser for Indian law-enforcement. Same target user (LEA investigators), same FIR/case workflow, same graph-based investigation paradigm, same need for forensic alerts and human-in-the-loop case management. Building any of that from scratch would be a reinvention.

The natural move is to share code. The question is *how*.

---

## The constraints we have to work around

Two real constraints rule out the obvious "merge into your repo" option:

1. **Bank-analyser must run fully offline on an air-gapped LEA workstation.** No external API calls, no Aura, no Anthropic. SQLite + NetworkX + Ollama + bundled static data. Your platform must run online (constant API access for blockchain data). Same code path, different deployment config.

2. **Bank-analyser is a hackathon/standalone deliverable.** The repo needs to be self-contained without crypto IP visible. Repo permissions and submission cleanliness matter.

So we need *separation* at the repo level but *sharing* at the code level.

---

## Proposed model: physical sync, not a published package (yet)

For the next 3-6 months, we propose **physical file copying with provenance markers**. Not a published `pip install` package. Not git submodules. Just `cp` with a header on each file.

```python
# Copied from india-le-platform/backend/app/analysis/velocity_analyzer.py
# at commit abc1234 on 2026-04-15.
# Sync via tools/sync-from-crypto.sh in the bank-analyser repo.
# If you need to change behaviour, change upstream first if possible.
# Local divergence (if any) documented in bank-analyser/CRYPTO_SYNC.md.
```

**Why this and not a real package?**
- A published `platform-core` package needs API contracts, semver discipline, private registry setup, version coordination on every change — 3-4 weeks of plumbing **before** anyone writes a feature. We can't afford that this quarter.
- Copying is reversible. If divergence is painful in 6 months, *that's* when we extract a real package — by which point we'll know what the API should actually look like.
- It costs you nothing. Your repo stays exactly as it is.

**Why not git submodule?**
- Submodules are operationally clumsy on Windows (and most teams). Hard pin, awkward updates, friction at every clone.

**Why not just clone-and-fork?**
- A fork loses the link upstream. Within weeks the two diverge silently. Provenance markers + a sync script keep the link explicit and check-able.

---

## The contract: what's "platform" (we copy) vs "domain" (we don't touch)

This is the part we need your buy-in on. The clearer this line is, the cheaper sync becomes.

### Platform — copyable, must stay domain-agnostic

A module is **platform** if it has zero blockchain-specific concepts. A useful test: could this code run unchanged on bank transactions, hawala flows, or gold-smuggling networks if you swapped the data source?

| Module | Path in your repo | Why it's platform |
|---|---|---|
| **Models** | `backend/app/models/{case,investigation,entity}.py` | `Case`, `Investigation`, `Entity` — domain-agnostic concepts. Already used the same way for bank as for crypto. |
| **Signal assembler** | `backend/app/analysis/signal_assembler.py` | TESTED/CLEAR/NOT_TESTED convergence framework. Pure logic. |
| **Velocity analyzer** | `backend/app/analysis/velocity_analyzer.py` | Six metrics (fund-through rate, dwell time, regularity, burst score). The math is currency-agnostic. |
| **Pattern detector skeleton** | `backend/app/analysis/pattern_detector.py` (framework only) | The aggregation/scoring scaffold. The 19 crypto-specific patterns themselves are domain. |
| **Multi-hop exposure** | `backend/app/analysis/exposure_analyzer.py` | Graph-distance scoring with risk decay. Works on any entity graph. |
| **Transaction pool / dedup cache** | `backend/app/analysis/transaction_pool.py` | Generic per-investigation cache. |
| **Entity registry framework** | `backend/app/analysis/entity_constants.py` | Keyword-based classification framework. Keywords themselves are domain. |
| **Graph BFS + storage** | `backend/app/services/{graph_service,graph_storage}.py` (BFS + Neo4j wrapper sections) | Graph traversal and Neo4j queries are generic — labels swap, structure doesn't. |
| **Auth + audit trail** | `backend/app/utils/auth.py`, activity_log table | LEA tools all need this. Identical between domains. |
| **Cytoscape canvas + state** | `frontend/src/components/GraphCanvas.tsx`, `frontend/src/stores/*` | Renders nodes and edges; labels are data, not code. |
| **Case management UI** | `frontend/src/components/cases/*`, `CaseSelectionModal.tsx` | Same FIR/case concept across domains. |
| **Node inspector + activity table + investigation report** | `frontend/src/components/NodeInspector/*`, `AutoInvestigateReport.tsx` | Tab structure is generic; tab content is domain-pluggable. |
| **Provider abstractions** | (some exist as `fetchers/`, others to be extracted) | LLM client (litellm), vector store, OCR provider — interfaces stay; implementations swap. |

### Domain — yours, ours, ours-and-yours both, never shared

A module is **domain** if it embeds blockchain-specific concepts (UTXO, on-chain addresses, DEX, mixers, privacy chains) or bank-specific concepts (UPI, NEFT, IFSC, account numbers, FIU-IND). Don't share.

| Crypto-domain (yours, we don't touch) | Bank-domain (ours, you don't touch) |
|---|---|
| `analysis/privacy_chains.py` | `plugins/bank/parsers/*` |
| `analysis/dex_decoder.py` | `plugins/bank/patterns/*` |
| `analysis/protocol_eras.py` | `plugins/bank/enrichment/*` (PEP, FIU-IND) |
| `services/exchange_detector.py` | `plugins/bank/extraction/*` |
| `analysis/mixer_intelligence.py` | `plugins/bank/terminus_detector.py` |
| 19 crypto patterns in `pattern_detector.py` | 6-8 BFSI patterns (smurfing, mule, hawala, …) |
| Blockchain fetchers (EVM, BTC, TRX, …) | pdfplumber + Tesseract + Azure DocIntel adapters |
| Telegram OSINT | News/forum scrapers |

### The grey zone — please flag these

These straddle the line. We'd love your view on each:

- **`exposure_analyzer.py`** — looks platform but currently calls into entity sources (Arkham, GoPlus). If we extract just the algorithm and let domain plugins inject entity sources, it's clean.
- **`counterparty_triage.py`** — top-N counterparty risk ranking. Logic is generic but currently hardcoded to crypto entity types.
- **`investigation_orchestrator.py`** — your 8-step SSE pipeline. Some steps (forward trace, backward trace) are crypto-specific naming but probably generalisable.
- **Frontend `IntelligenceTab.tsx`** — sections like "sanctions screening", "exposure breakdown" are generic; "address profile" is crypto-flavoured. We'd reskin the labels.

---

## What we ask of you

### Three small things that make sync vastly cheaper

1. **Don't sneak crypto-specific concepts into the platform modules listed above.** If you need to add blockchain-specific logic to `velocity_analyzer.py`, please instead inject it via a callback or extract a domain hook. We'll do the same — no bank-specific code in shared modules.

2. **When you change a platform module's interface, ping us.** Not asking for semver discipline (yet). Just a Slack heads-up: "I'm changing the signature of `signal_assembler.assemble()` next week, FYI." We'll re-sync and adjust on our side.

3. **Tag the platform modules in your repo somehow.** A simple `# PLATFORM` comment at the top of platform files, or a `PLATFORM_MODULES.md` listing them. So future contributors know not to drop crypto-specific imports in. We can help write this list.

### One bigger thing (optional, but high-leverage)

If you're willing: **extract the platform modules into a single subdirectory of your repo** (e.g., `india-le-platform/platform/`), separate from the crypto-specific code. Right now they're scattered across `backend/app/analysis/`, `services/`, `models/`, etc.

This isn't extracting a package — they're still in your repo, still your code, no API contract. Just a clearer physical separation. Benefits:
- Our sync script becomes one-line: `cp -r crypto/platform/* bank-analyser/core/`
- Other future domains (hawala, gold, shell-co) get the same easy reuse
- Nothing changes for *you* — you import from the new location, your tests work, your features ship as normal

If this is too disruptive right now, completely understandable — the inline-tag approach in #3 above works too.

---

## What we'll do on our side

1. **Maintain `CRYPTO_SYNC.md`** in our repo — every synced file logged with the upstream commit SHA and date.
2. **Run the sync script monthly** (or on your ping). Document any local divergence in the same file.
3. **Don't commit local edits to synced files** without first asking: "should this go upstream instead?" If yes, we open a PR against your repo.
4. **Keep our domain code (bank parsers, BFSI patterns, etc.) entirely in `plugins/bank/`** — no leakage into `core/`.

---

## A concrete first slice

If you're game, here's what we'd start with. **Two-week aim** — tiny, low-risk:

1. **Week 1, your side:** add a `# PLATFORM` tag (or move into `india-le-platform/platform/`) for these 6 files:
   - `backend/app/models/case.py`
   - `backend/app/models/investigation.py`
   - `backend/app/analysis/signal_assembler.py`
   - `backend/app/analysis/velocity_analyzer.py`
   - `backend/app/analysis/transaction_pool.py`
   - `backend/app/utils/auth.py`

2. **Week 1, our side:** copy those 6 files into our `core/` with provenance headers. Wire them up. Build a tiny smoke test that proves they work in our offline (SQLite + NetworkX) deployment.

3. **Week 2, both sides:** sync session. Walk through what worked and what didn't. Adjust the contract. Then expand to the next batch (graph BFS, exposure analyzer, frontend Cytoscape).

If after two weeks this feels good, we keep going. If it feels painful, we course-correct early before we've committed too far.

---

## What this is *not*

To be explicit about non-asks:

- **We are not asking you to slow down for our needs.** Keep shipping. We sync to your latest, we adjust to your changes.
- **We are not asking you to maintain backwards compatibility.** If you change a signature, we adjust. We're young; we have no users to break.
- **We are not asking for a shared CI pipeline.** Our tests run in our repo; yours in yours.
- **We are not proposing a merger of teams or repos.** Repos stay separate. Your team owns crypto; ours owns bank. Future shared modules — we can talk about co-ownership when we get there.

---

## Open questions for you

1. Does the platform/domain split feel right to you? Are there modules we've miscategorised?
2. Is moving platform modules into a `platform/` subdir feasible, or is the inline tag approach more realistic?
3. Are there platform-level changes you have planned in the next 4-6 weeks that we should know about so we don't sync mid-flight?
4. Would you want bank-analyser to expose a `Person`/`Entity` API back to crypto, so a single case can show "this person has crypto wallets AND bank accounts" cross-references in a unified case view?

We'd love a 30-min conversation this week to walk through this. Pick a slot that works.

— Saurabh (saurabh@outris.com)
