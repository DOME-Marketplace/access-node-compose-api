# syntax=docker/dockerfile:1

ARG PYTHON_IMAGE=python:3.13-slim-trixie

# --- Python dependencies and application, installed into /opt/venv ---------
FROM ghcr.io/astral-sh/uv:0.13.6 AS uv

FROM ${PYTHON_IMAGE} AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3 \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY README.md LICENSE ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

# --- Helm, pinned and verified against the published checksum ---------------
FROM debian:trixie-slim AS helm
ARG TARGETARCH
ARG HELM_VERSION=3.22.1
ARG HELM_SHA256_amd64=896cf63684a42a723d61c980369d6e588330927deb13676ca0d85006dd6da0ea
ARG HELM_SHA256_arm64=4c29e286b279d170fa048ddfc3e4e83dcd069ca9c52102766ba672d7149e694d
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN set -eu; \
    case "${TARGETARCH}" in \
      amd64) sha="${HELM_SHA256_amd64}" ;; \
      arm64) sha="${HELM_SHA256_arm64}" ;; \
      *) echo "unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    file="helm-v${HELM_VERSION}-linux-${TARGETARCH}.tar.gz"; \
    curl -fsSL -o "/tmp/${file}" "https://get.helm.sh/${file}"; \
    echo "${sha}  /tmp/${file}" | sha256sum -c -; \
    tar -xzf "/tmp/${file}" -C /tmp; \
    install -m 0755 "/tmp/linux-${TARGETARCH}/helm" /usr/local/bin/helm

# --- Runtime ------------------------------------------------------------------
FROM ${PYTHON_IMAGE}
LABEL org.opencontainers.image.source="https://github.com/DOME-Marketplace/access-node-compose-api" \
      org.opencontainers.image.description="Container image versions of a DOME access-node environment, read from dome-gitops" \
      org.opencontainers.image.licenses="Apache-2.0"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --home-dir /work --no-create-home --shell /usr/sbin/nologin app \
    && install -d -o 10001 -g 10001 /work

COPY --from=helm /usr/local/bin/helm /usr/local/bin/helm
COPY --from=builder /opt/venv /opt/venv

# The root filesystem is expected to be read-only: everything is written under
# /work and /tmp, which must be writable volumes (emptyDir / tmpfs).
ENV PATH=/opt/venv/bin:${PATH} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WORK_DIR=/work \
    HOME=/work \
    HELM_CACHE_HOME=/work/helm/cache \
    HELM_CONFIG_HOME=/work/helm/config \
    HELM_DATA_HOME=/work/helm/data \
    PORT=8080

USER 10001:10001
WORKDIR /work
EXPOSE 8080
ENTRYPOINT ["python", "-m", "access_node_compose_api"]
