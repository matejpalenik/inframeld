FROM docker.io/library/python:3.13.18-slim-trixie@sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1 AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY apps/backend/pyproject.toml apps/backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY apps/backend/README.md ./README.md
COPY apps/backend/src ./src
RUN uv sync --locked --no-dev --no-editable

FROM docker.io/library/python:3.13.18-slim-trixie@sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1 AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app apps/backend/src ./src
COPY --chown=app:app apps/backend/migrations ./migrations
COPY --chown=app:app apps/backend/alembic.ini ./alembic.ini

USER app:app

EXPOSE 8000

CMD ["uvicorn", "inframeld_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
