# deployment/lea-offline/

Single-workstation, fully air-gapped deployment for law-enforcement.

**Hard requirement:** zero external network calls. No telemetry, no model downloads at runtime, no API fallbacks.

**Status:** placeholder. To be built after `core/` is synced from crypto.

## Planned stack

- **Runtime:** Docker Compose (everything bundled) or Electron + embedded Python
- **Database:** SQLite (single file)
- **Graph:** NetworkX (in-memory) or embedded Neo4j
- **Vector:** FAISS (on-disk index, pre-built)
- **LLM:** Ollama (llama3 8B preloaded)
- **OCR:** pdfplumber (digital PDFs) + Tesseract (scanned). No Azure DocIntel.
- **Enrichment data:** PEP/sanctions/FIU-IND lists bundled as static datasets, refreshed manually.
- **Auth:** none (single-user workstation) or local OS account integration.

## Bundling plan

1. Single installer (.exe / .msi for Windows, .deb / .pkg for Linux).
2. Pre-bundled Ollama model (~5GB).
3. Pre-bundled FAISS indices (~few hundred MB).
4. Pre-bundled enrichment datasets (~tens of MB).
5. Bank plugin only — crypto plugin is *not* loaded in this build.

## What gets stripped

- crypto plugin (irrelevant offline)
- Anthropic / OpenAI / Gemini API calls
- Azure Document Intelligence
- Multi-tenant auth, JWT
- Telemetry, error reporting
- Live data fetchers
