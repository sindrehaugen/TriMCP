# TriMCP Enterprise — Implementation Status & Residual Gaps

**Reference:** `TriMCP Enterprise Deployment Plan v2.1`  
**Last updated:** 2026-05-04 (documentation refresh against the current tree)

This file tracks **what is done** and **what still needs attention**, not obsolete “everything is missing” language from earlier audits.

---

## Implemented (no longer tracked as gaps)

The following items were previously listed as gaps; they now exist in the repository.

| Area | Where it lives |
|------|----------------|
| Document bridge providers (SharePoint / Google Drive / Dropbox) | `trimcp/bridges/` (`base.py`, `sharepoint.py`, `gdrive.py`, `dropbox.py`) |
| Webhook receiver + validation + RQ enqueue | `trimcp/webhook_receiver/main.py` |
| Bridge MCP tools (6 tools) | `server.py` TOOLS + `call_tool` branches; handlers in `trimcp/bridge_mcp_handlers.py` |
| `bridge_subscriptions` PostgreSQL schema | `trimcp/schema.sql` |
| Subscription renewal logic (Graph / Drive expiry, degraded state, etc.) | `trimcp/bridge_renewal.py` |
| APScheduler driver for renewal | `trimcp/cron.py` (`python -m trimcp.cron`) |
| Mode-aware launcher (Local / Multi-User / Cloud) | `go/launch/run.go`; entrypoint `trimcp-launch/cmd/trimcp-launch/main.go` → `launch.Run` |
| Local mode: Docker probe + compose | `go/launch/local.go` (`docker info`, `docker compose up -d --wait`; prefers `docker-compose.local.yml` then `docker-compose.yml`) |
| Cloud mode: MSAL token refresh + TLS probe to Postgres | `go/launch/cloud_mode.go` + `go/auth/` |
| Multi-User TCP checks | `go/launch/multiuser.go` + `go/launch/netcheck.go` |
| Multi-User-ish stack at repo root | `docker-compose.yml`: redis, postgres (`pgvector/pgvector:pg16`), mongodb, minio, worker, webhook-receiver, caddy; root `Caddyfile` proxies `/webhooks/*` → receiver |
| Local-only stack bound to localhost | `docker-compose.local.yml` (no caddy/webhook/worker services) |
| Build-from-source on-prem compose | `deploy/multiuser/docker-compose.yml` + `deploy/multiuser/Dockerfile` + `deploy/multiuser/env.example` (Caddy mounts `../../Caddyfile`) |

---

## Residual gaps & verification items

### 1. Bridge renewal scheduler not wired into default worker/container

**Status:** Renewal code and `trimcp/cron.py` exist, but **`start_worker.py` only starts an RQ worker** — it does not start the APScheduler renewal loop.

**Impact:** Push subscriptions for SharePoint / Google Drive can expire unless operators run renewal separately.

**Remediation options:** Add a compose service (`bridge-cron`) running `python -m trimcp.cron`; or embed renewal as a lightweight background task (e.g. thread/async alongside worker — design choice); document the requirement clearly in README until automated.

---

### 2. Root `docker-compose.yml` — resolved for source builds

**Status:** Repo-root **`docker-compose.yml`** now uses **`build`** (`deploy/multiuser/Dockerfile`) for **`worker`** and **`webhook-receiver`**, plus pinned data-plane images and the **`cognitive`** sidecar [D2/D7].

**Residual:** Operators who prefer pre-published images can still retag local builds or mirror `ghcr.io/sindrehaugen/trimcp-cognitive:v1` offline.

---

### 3. Phase 5 — Installer build pipeline (still unverified)

Build artefacts exist (`build/windows/TriMCP-Setup.iss`, `build/windows/TriMCP.wxs`, `build/macos/build-dmg.sh`) but **end-to-end verification against the wizard spec (§6.2–§7.3) is outstanding**.

Checks to perform when someone owns this:

- **Inno (`TriMCP-Setup.iss`):** Mode branching, Docker check (Local), server field (Multi-User), cloud OAuth UX, silent install flags, Claude/Cursor config patches, Task Scheduler for Local.
- **WiX (`TriMCP.wxs`):** Public properties (`MODE`, `SERVERADDR`, `TENANT`, `BRIDGES`, `BACKEND`).
- **macOS (`build-dmg.sh`):** Universal binary, codesign/notarize/staple, Claude config patching.

---

### 4. Connective health checks — spot-audit optional

Net checks exist (`netcheck.go`, Docker probe in Local, TLS probe in Cloud). A focused QA pass could confirm UX messages and timeouts match §6.4 for all failure modes — **not “missing wiring”**, but **confirmation**.

---

## Effort estimate (residual only)

| Item | Estimate |
|------|-----------|
| Wire `trimcp.cron` into Compose / prod story + README | ~0.5 day |
| Root compose: documented build path or Makefile | ~0.25 day |
| Installer wizard verification / fixes | 1–2 days |
| §6.4 health-check UX QA | ~0.25 day |
| **Total remaining (rough)** | **~2–3 days** (plus installer depth) |

Bridge feature code paths called out in the old audit are implemented; remaining work is **operations integration**, **compose ergonomics**, and **installer/signing verification**.
