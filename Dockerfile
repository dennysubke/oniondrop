# syntax=docker/dockerfile:1.7
ARG PYTHON_VERSION=3.12
ARG ONIONSHARE_VERSION=2.6.4

FROM python:${PYTHON_VERSION}-slim-bookworm AS builder
ARG ONIONSHARE_VERSION
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential curl git libffi-dev libsodium-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.txt /build/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/venv/bin/pip install -r /build/requirements.txt \
    && curl -fsSL "https://github.com/onionshare/onionshare/archive/refs/tags/v${ONIONSHARE_VERSION}.tar.gz" -o /tmp/onionshare.tar.gz \
    && mkdir -p /tmp/onionshare \
    && tar -xzf /tmp/onionshare.tar.gz -C /tmp/onionshare --strip-components=1 \
    && /opt/venv/bin/pip install /tmp/onionshare/cli

FROM python:${PYTHON_VERSION}-slim-bookworm
ARG ONIONSHARE_VERSION
LABEL org.opencontainers.image.title="OnionDrop" \
      org.opencontainers.image.description="A self-hosted manager for persistent OnionShare receive services" \
      org.opencontainers.image.version="0.2.0" \
      org.opencontainers.image.licenses="GPL-3.0-or-later" \
      org.opencontainers.image.source="https://github.com/dennysubke/oniondrop"
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ONIONDROP_DATA_DIR=/data \
    ONIONDROP_HOST=0.0.0.0 \
    ONIONDROP_PORT=8080 \
    ONIONDROP_AUTH_MODE=setup \
    ONIONDROP_DEFAULT_LANGUAGE=en \
    ONIONSHARE_VERSION=${ONIONSHARE_VERSION} \
    HOME=/data/home
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates gosu tini tor \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 oniondrop \
    && useradd --uid 1000 --gid 1000 --create-home --home-dir /home/oniondrop oniondrop
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY oniondrop /app/oniondrop
COPY entrypoint.sh /usr/local/bin/oniondrop-entrypoint
RUN chmod +x /usr/local/bin/oniondrop-entrypoint \
    && mkdir -p /data \
    && chown -R oniondrop:oniondrop /data /app
EXPOSE 8080
VOLUME ["/data"]
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/oniondrop-entrypoint"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)" || exit 1
