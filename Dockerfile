# syntax=docker/dockerfile:1.7
# echo-tunes: one small image with Python, yt-dlp and Deno (yt-dlp needs a JavaScript
# runtime to read YouTube). Runs as a non-root user; all state lives in /data.

ARG PYTHON_IMAGE=python:3.13.18-slim-trixie

FROM ghcr.io/astral-sh/uv:0.13.10 AS uv
FROM denoland/deno:bin-2.9.8 AS deno

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src
# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-editable

FROM ${PYTHON_IMAGE}
ARG VERSION=dev
LABEL org.opencontainers.image.title="echo-tunes" \
      org.opencontainers.image.description="Self-hosted Alexa skill that plays YouTube Music on your Echo" \
      org.opencontainers.image.source="https://github.com/denzilrdz/echo-tunes" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}"

COPY --from=deno /deno /usr/local/bin/deno
COPY --from=build /app/.venv /app/.venv
RUN useradd --system --uid 10001 --home-dir /data --no-create-home echotunes \
    && mkdir -p /data && chown echotunes /data

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Fewer malloc arenas: stops glibc from holding on to freed memory across threads.
    MALLOC_ARENA_MAX=2 \
    DENO_DIR=/data/deno \
    XDG_CACHE_HOME=/data/cache \
    ECHO_TUNES_DATA_DIR=/data

USER echotunes
WORKDIR /data
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4).status != 200)"]
ENTRYPOINT ["echo-tunes"]
CMD ["serve"]
