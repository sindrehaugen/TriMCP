# TriMCP Infrastructure — Source of Truth

Authoritative Compose and proxy configuration live **in the repository root** (not under `Instructions/`). This page summarizes how to run the stacks.

## Local mode (quad-DB only, localhost binds)

Prefer:

```bash
docker compose -f docker-compose.local.yml up -d
```

- Postgres: **`pgvector/pgvector:pg16`** (`memory_meta` database).
- Ports are bound to **127.0.0.1** only (see `docker-compose.local.yml`).
- **No** Caddy, webhook receiver, or worker service in this file — intended for laptop / Local mode (`trimcp-launch` starts `server.py` and `start_worker.py` on the host).

Env vars for Python processes should match `.env.example` / your installer-generated `.env` (`PG_DSN`, `REDIS_URL`, `MONGO_URI`, MinIO keys, etc.).

## Multi-user / demo full stack (7 services)

Root file:

```bash
docker compose -f docker-compose.yml up -d
```

Includes: Redis, Postgres (pgvector **pg16**), MongoDB, MinIO (API/console mapped to host **9002/9003**), **worker**, **webhook-receiver**, **Caddy**.

- Reverse proxy uses the root **`Caddyfile`** (routes **`/webhooks/*`** → `webhook-receiver:8080`).
- `worker` / `webhook-receiver` use image names **`trimcp-worker`** and **`trimcp-webhooks`** — build or pull those images before relying on this file; see **`deploy/multiuser/`** below for building from source.

## Build-from-source stack (recommended for on‑prem images)

From the repo root:

```bash
docker compose -f deploy/multiuser/docker-compose.yml --env-file deploy/multiuser/env.example build
docker compose -f deploy/multiuser/docker-compose.yml --env-file deploy/multiuser/env.example up -d
```

Uses **`deploy/multiuser/Dockerfile`**, **`deploy/multiuser/env.example`**, and mounts **`../../Caddyfile`** for Caddy.

## Bridge subscription renewal (production note)

Renewal scheduling is implemented in **`trimcp/cron.py`** (`python -m trimcp.cron`). It is **not** started by **`start_worker.py`**. For long-running SharePoint / Google Drive push subscriptions, plan a separate container or systemd unit for the cron process until it is wired into the default worker/compose flow.

## Bootstrap secrets and version control

`scripts/bootstrap-compose-secrets.py` can emit **`deploy/compose.stack.env.generated`** with real passwords and keys. Treat that file like any secrets artifact: **never commit it to Git** (or any VCS). Use the committed templates (`deploy/compose.stack.env`, `.env.example`) for structure only; inject production values via CI secrets, a password manager, or host-only env files.
