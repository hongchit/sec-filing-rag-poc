# syntax=docker/dockerfile:1.8
ARG POSTGRES_IMAGE=postgres:18.4-trixie@sha256:3a82e1f56c8f0f5616a11103ac3d47e632c3938698946a7ad26da0df1334744a
FROM ${POSTGRES_IMAGE}

ARG PG_MAJOR=18
ARG PGVECTOR_VERSION=0.8.2
ARG PGVECTOR_SHA256=69f4019389af05dc1c9548deb8628e62878e6e207c03907f2b8af2016472cdaa
ARG PG_TEXTSEARCH_VERSION=1.2.0
ARG PG_TEXTSEARCH_ARM64_SHA256=5e889c5cb0f3ef9125e1cb09fd51a0944ca2bbcea2a08182ff5c048b20a7a8aa
ARG PG_TEXTSEARCH_AMD64_SHA256=f63e1e35f46246f684f3b48fcc3775b9dd07107d6f39dbaaa2da23e515a7d127
ARG TARGETARCH

RUN set -eux; \
    apt-get update; \
    apt-mark hold locales; \
    apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        postgresql-server-dev-"${PG_MAJOR}" \
        unzip; \
    curl -fsSL \
        "https://github.com/pgvector/pgvector/archive/refs/tags/v${PGVECTOR_VERSION}.tar.gz" \
        -o /tmp/pgvector.tar.gz; \
    echo "${PGVECTOR_SHA256}  /tmp/pgvector.tar.gz" | sha256sum -c -; \
    mkdir /tmp/pgvector; \
    tar -xzf /tmp/pgvector.tar.gz --strip-components=1 -C /tmp/pgvector; \
    make -C /tmp/pgvector OPTFLAGS=""; \
    make -C /tmp/pgvector install; \
    case "${TARGETARCH}" in \
      amd64) pg_textsearch_sha="${PG_TEXTSEARCH_AMD64_SHA256}" ;; \
      arm64) pg_textsearch_sha="${PG_TEXTSEARCH_ARM64_SHA256}" ;; \
      *) echo "unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL \
        "https://github.com/timescale/pg_textsearch/releases/download/v${PG_TEXTSEARCH_VERSION}/pg-textsearch-v${PG_TEXTSEARCH_VERSION}-pg${PG_MAJOR}-${TARGETARCH}.zip" \
        -o /tmp/pg_textsearch.zip; \
    echo "${pg_textsearch_sha}  /tmp/pg_textsearch.zip" | sha256sum -c -; \
    unzip -q /tmp/pg_textsearch.zip -d /tmp/pg_textsearch; \
    dpkg -i /tmp/pg_textsearch/*.deb; \
    test -f "/usr/lib/postgresql/${PG_MAJOR}/lib/pg_textsearch.so"; \
    test -f "/usr/share/postgresql/${PG_MAJOR}/extension/pg_textsearch.control"; \
    rm -rf /tmp/pgvector /tmp/pgvector.tar.gz /tmp/pg_textsearch /tmp/pg_textsearch.zip; \
    apt-get remove -y build-essential postgresql-server-dev-"${PG_MAJOR}" unzip; \
    apt-get autoremove -y; \
    apt-mark unhold locales; \
    # Remove the unused default TLS certificate pair before image inspection.
    rm -f /etc/ssl/private/ssl-cert-snakeoil.key /etc/ssl/certs/ssl-cert-snakeoil.pem; \
    rm -rf /var/lib/apt/lists/*

COPY docker/postgres/init-databases.sh /docker-entrypoint-initdb.d/10-init-databases.sh

LABEL org.opencontainers.image.source="https://github.com/hongchit/sec-filing-rag-poc" \
      org.opencontainers.image.title="SEC Filing RAG PostgreSQL" \
      org.opencontainers.image.version="postgres-18.4_pgvector-0.8.2_pg_textsearch-1.2.0" \
      org.opencontainers.image.licenses="PolyForm-Noncommercial-1.0.0"
