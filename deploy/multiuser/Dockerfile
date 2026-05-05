# TriMCP application image (RQ worker + optional webhook command overrides).
# Build from repo root:
#   docker compose -f deploy/multiuser/docker-compose.yml build
#
# Multi-stage: compile wheels without dev headers in final layer; non-root runtime;
# pinned base tag (not :latest). HEALTHCHECK is process-local (config sanity only).

FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir -r requirements.txt -w /wheels


FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt --no-index --find-links=/wheels \
    && rm -rf /wheels \
    && useradd --system --uid 10001 --no-create-home trimcp

COPY trimcp ./trimcp
COPY start_worker.py .
COPY admin_server.py server.py ./
COPY admin ./admin

RUN chown -R trimcp:trimcp /app

USER trimcp

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

HEALTHCHECK --interval=60s --timeout=15s --start-period=90s --retries=3 \
    CMD python -c "from trimcp.config import cfg; cfg.validate()"

CMD ["python", "start_worker.py"]
