# syntax=docker/dockerfile:1.6
#
# Build context is expected to be the REPO ROOT (bank-analyser/), not the
# frontend/ subtree, because Railway's default "Root Directory = blank"
# gives us repo-root context. All COPY paths are therefore prefixed with
# `frontend/`. To build locally: `docker build -f frontend/Dockerfile .`
# from the repo root.

# ── build stage ──────────────────────────────────────────────────────────────
FROM node:20-alpine AS build
WORKDIR /app

# Install deps with a deterministic lockfile.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

# Vite reads VITE_* env vars at build time and bakes them into the bundle.
# Railway passes build-args from the service's variables.
ARG VITE_API_URL
ARG VITE_API_KEY
ARG VITE_DEMO_PASSWORD
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_API_KEY=$VITE_API_KEY
ENV VITE_DEMO_PASSWORD=$VITE_DEMO_PASSWORD

COPY frontend/ ./
RUN npm run build


# ── runtime stage ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

# Railway injects $PORT — substitute it into the nginx conf at container start.
COPY frontend/nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

# The nginx image's entrypoint runs envsubst over /etc/nginx/templates/* using
# only the listed vars (avoids mangling `$host`, `$uri`, etc. in the template).
ENV NGINX_ENVSUBST_TEMPLATE_SUFFIX=.template
ENV NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx/conf.d
ENV NGINX_ENVSUBST_FILTER=PORT

# Railway doesn't need EXPOSE to be correct, but it's useful documentation.
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
