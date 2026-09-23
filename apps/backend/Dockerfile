FROM python:3.13.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY apps/backend/pyproject.toml apps/backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM python:3.13.12-slim AS runtime

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
