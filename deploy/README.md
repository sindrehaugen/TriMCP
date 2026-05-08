# TriMCP deployment guide

Operational defaults for TriMCP v1.0 assume **self-hosted Docker Compose** on one machine unless your team chooses otherwise.

---

## D1 — Default path: repository-root `docker-compose.yml`

**Quick start (zero-copy):**

```bash
docker compose up -d --build
```

This loads committed **`deploy/compose.stack.env`**, handles automated PostgreSQL schema initialization (extensions + RLS), bundles required spaCy models, and starts:

| Service | Role |
|---------|------|
| **postgres** | pgvector/pg16 — memories, graph, quotas, A2A grants, event log |
| **mongodb** | Episodic payloads / code archive |
| **redis** | RQ queue + cache |
| **minio** | Media + replay payload cache (host **9002** / **9003**) |
| **cognitive** | Embeddings sidecar [D7] (**11435**) |
| **worker** | RQ consumer — async `index_code_file`, bridge jobs |
| **cron** | APScheduler — bridge renewal + **ReembeddingWorker** sweeps |
| **admin** | **Starlette** Admin UI + REST (**8003**) — health `/api/health` |
| **a2a** | A2A JSON-RPC / agent card (**8004**) |
| **webhook-receiver** | FastAPI bridge webhooks (**8080**) |
| **caddy** | **:80** — `/webhooks/*` → receiver; **/** → admin |

**MCP (stdio)** is not inside Compose (IDE attaches to a local process). Run on the host with the same logical config as **`.env.example`** (127.0.0.1 URLs). Example:

```bash
set PG_DSN=postgresql://mcp_user:mcp_password@127.0.0.1:5432/memory_meta
set MONGO_URI=mongodb://127.0.0.1:27017
set REDIS_URL=redis://127.0.0.1:6379/0
set MINIO_ENDPOINT=127.0.0.1:9002
python server.py
```

Optional: create a project **`.env`** for Compose **interpolation** only (`POSTGRES_PASSWORD`, port overrides, `TRIMCP_A2A_PUBLIC_URL`). Application env for containers comes from **`deploy/compose.stack.env`**.

---

## Configuration files

| File | Purpose |
|------|---------|
| **`deploy/compose.stack.env`** | Container defaults (service DNS names, dev secrets) — **review before production** |
| **`deploy/compose.stack.env.generated`** | **Generated only** (e.g. `python scripts/bootstrap-compose-secrets.py`) — holds populated secrets. **Do not commit this file to VCS**; add to `.gitignore` locally if your workflow creates it. Rotate any secret that was ever committed by mistake. |
| **`.env.example`** | Documented template for **host** MCP + production notes |
| **`deploy/multiuser/docker-compose.yml`** | Alternate layout; prefer root compose for v1.0 |
| **`Caddyfile`** (repo root) | Edge routing for v1.0 stack |

The multiuser compose file publishes MinIO on host **9000** (API) and **9001** (console) by default, while the root compose uses **9002** and **9003**—set **`MINIO_ENDPOINT`** (and optional `MINIO_API_PORT` / `MINIO_CONSOLE_PORT`) to match whichever stack you run.

---

## D2 / D7 — Cognitive model

- Image **`ghcr.io/sindrehaugen/trimcp-cognitive:v1`** on **11435**.
- Stack sets **`TRIMCP_COGNITIVE_BASE_URL=http://cognitive:11435`** for in-network services.

---

## Operations

- **Backups**: volumes `pg_data`, `mongo_data`, `redis_data`, `minio_data`, `caddy_*` + rotate secrets in **`deploy/compose.stack.env`**.
- **Consolidation**: `trimcp/cron.py` runs `ConsolidationWorker` on an interval for namespaces whose metadata sets `consolidation.enabled=true`. Use the MCP `trigger_consolidation` tool for ad-hoc runs.

---

## Native installers (`trimcp-launch` shim)

The **mode-aware MCP stdio shim** is built from `go/cmd/trimcp-launch/` (Enterprise Deployment Plan section 6.4). Release automation is **`.github/workflows/release.yml`** (runs on annotated tags `v*`).

### Build outputs (CI expectations)

| Platform | Artifact | Shim path inside package |
|----------|----------|---------------------------|
| **Windows (Inno)** | `build/windows/Output/TriMCP-Setup.exe` | `{app}\trimcp-launch.exe` — Start Menu shortcut and post-install run target (`TriMCP-Setup.iss`) |
| **Windows (WiX)** | `build/windows/TriMCP.msi` | `%ProgramFiles%\TriMCP\trimcp-launch.exe` (`TriMCP.wxs`). MSI ships shim + `Patch-IDEConfig.ps1` / `Write-UserConfig.ps1`; use **Inno** for embedded Python + full app tree (`trimcp`, `admin`, compose files, wheels). |
| **macOS** | `build/macos/TriMCP-universal.dmg` | `TriMCP.app/Contents/MacOS/TriMCP` — binary is the universal `build/macos/trimcp-launch` copied into bundle (`build/macos/build-dmg.sh`) |

### Preconditions

- **Windows:** `dotnet tool install --global wix` (CI step) consumes `TrimcpLaunchExe Source="trimcp-launch.exe"` relative to `build/windows/`. Inno compiles `TriMCP-Setup.iss` with working directory **`build/windows/`** so relative `..\..\` repo paths resolve to the project root.

- **macOS:** Produce `build/macos/trimcp-launch` (universal binary via `lipo`) before `./build/macos/build-dmg.sh`; script copies it as the bundle executable named `TriMCP` per `Info.plist`.

### Verification checklist (release engineering)

1. Tag push triggers **`TriMCP Enterprise Release`** workflow; confirm `trimcp-launch.exe` build step exits 0.
2. **Inno artifact:** Inspect `{app}` — `trimcp-launch.exe` present; `%APPDATA%\TriMCP\mode.txt` / `.env` written by Pascal `CurStepChanged` (`ssPostInstall`).
3. **MSI artifact:** `msiexec /i TriMCP.msi MODE=local` (or silent equivalent) — `trimcp-launch.exe` and `scripts\*.ps1` under install root.
4. **DMG:** `codesign --verify --deep` on `.app` when signing identities are set (`APPLE_*` secrets).
5. **Optional:** Smoke-run shim from installed location with expected `TRIMCP_*` env (see `.env.example`).

---

## Architecture

**docs/architecture-v1.md** — runtime topology, temporal queries, A2A, workers.

**docs/architecture-phase-0-1-0-2.md** — namespaces, signing.
