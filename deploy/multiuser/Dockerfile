# TriMCP application image (worker + webhook-receiver) for Multi-User docker-compose.
# Build from repository root: docker compose -f deploy/multiuser/docker-compose.yml build
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
	&& apt-get install -y --no-install-recommends build-essential git \
	&& rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY trimcp ./trimcp
COPY start_worker.py .

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Default CMD is worker; compose overrides for webhook-receiver.
CMD ["python", "start_worker.py"]
