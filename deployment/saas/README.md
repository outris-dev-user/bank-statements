# deployment/saas/

Online multi-tenant deployment. Hosts both crypto and bank plugins as workbench tabs in the unified investigation platform.

**Status:** placeholder. To be built after `core/` is synced from crypto.

## Planned stack

- **Backend:** FastAPI (from crypto's existing app)
- **Database:** Postgres (managed)
- **Graph:** Neo4j Aura
- **Vector:** Qdrant Cloud
- **LLM:** Anthropic Claude via litellm
- **OCR fallback:** Azure Document Intelligence (keys in `azure/`)
- **Auth:** JWT (from crypto)

## Existing assets

- `azure/Deployment-FormRecognizerCreate-*` — Azure Document Intelligence resource metadata. Endpoint and Key 1 stored in `.env` (gitignored).
