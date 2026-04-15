# core/

Domain-agnostic platform code, **synced from the crypto investigation platform**.

Nothing in here is bank-specific. Anything bank-specific belongs in `plugins/bank/`.

See [../CRYPTO_SYNC.md](../CRYPTO_SYNC.md) for the sync ledger.
See [../docs/for-crypto-team.md](../docs/for-crypto-team.md) for the contract that defines what counts as "platform" vs "domain".

## Layout

```
core/
├── models/      # Case, Investigation, Entity, Person, Transaction, Signal
├── analysis/    # signal_assembler, velocity_analyzer, pattern_framework, exposure
├── graph/       # neo4j_store + networkx_store (offline fallback)
├── ui/          # GraphCanvas, NodeInspector, stores, Case management
└── auth/        # JWT (online deployment only)
```

## Status

Empty skeleton. No files synced yet — this happens after the crypto team aligns on the contract in `docs/for-crypto-team.md`.
