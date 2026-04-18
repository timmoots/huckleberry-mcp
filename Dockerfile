# syntax=docker/dockerfile:1.7
FROM python:3.14-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

# -----------------------

FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    MCP_TRANSPORT=streamable-http \
    PORT=8080

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/src /app/src
WORKDIR /app

RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home app \
 && chown -R app:app /app
USER app

EXPOSE 8080

CMD ["huckleberry-mcp"]
