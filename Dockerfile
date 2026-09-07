# syntax=docker/dockerfile:1.8
FROM node:24-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim-trixie@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS python-build

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ src/
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.14-slim-trixie@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS runtime

ENV APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    FRONTEND_DIST_PATH=/app/frontend \
    HOME=/tmp \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --home-dir /tmp app

COPY --from=python-build /wheels/ /wheels/
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels sec-filing-rag-poc \
    && rm -rf /wheels

WORKDIR /app
COPY --chown=app:app config/ config/
COPY --chown=app:app evaluation/ evaluation/
COPY --chown=app:app migrations/ migrations/
COPY --chown=app:app workflows/ workflows/
COPY --from=frontend-build --chown=app:app /build/frontend/dist/ frontend/

USER 10001:10001
EXPOSE 8000
CMD ["sec-rag-api"]

LABEL org.opencontainers.image.source="https://github.com/hongchit/sec-filing-rag-poc" \
      org.opencontainers.image.title="SEC Filing RAG" \
      org.opencontainers.image.licenses="PolyForm-Noncommercial-1.0.0"
