FROM python:3.12.13-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36 AS base

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /bin/
WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends bubblewrap \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY migrations ./migrations
COPY researcy ./researcy

RUN chmod -R a+rX /app/.venv /app/researcy /app/migrations /app/alembic.ini

FROM base AS test
RUN uv sync --frozen --no-install-project
COPY tests ./tests
RUN chmod -R a+rX /app/.venv /app/tests
USER 65534:65534

FROM base AS production
USER 65534:65534
EXPOSE 8000
CMD ["uvicorn", "researcy.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
