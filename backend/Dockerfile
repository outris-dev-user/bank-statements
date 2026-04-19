# syntax=docker/dockerfile:1.6
#
# Build context MUST be the repo root (bank-analyser/). Railway's default
# "Root Directory = blank" setting already gives us that. We need to see
# `plugins/` as a sibling of `backend/` because main.py imports
# `plugins.bank.extraction.parser` — that layout is the whole point of the
# plugin separation, and copying it into the container preserves it.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install Python deps first so `docker build` can cache this layer across
# code changes that don't touch requirements.txt.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Now the app + its plugin sibling. `core/` holds shared analysis modules
# (`core.analysis.entity_classification` et al.) that store.py imports at
# runtime when resolving counterparties into entities — if we skip this,
# entity resolution silently fails and the graph shows no entity nodes.
COPY backend /app/backend
COPY plugins /app/plugins
COPY core /app/core

WORKDIR /app/backend

# Railway injects PORT. Default to 8000 for local `docker run`.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
