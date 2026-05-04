# TriMCP Enterprise — Implementation Gaps

Audited against: `TriMCP Enterprise Deployment Plan v2.1`
Audit date: 2026-05-04

---

## Phase 2 — Document Bridge System (largest gap)

The webhook receiver exists but nothing calls it. The entire integration layer between TriMCP and cloud document providers is absent.

### Missing: `trimcp/bridges/` module

The plan (§10.3) specifies a provider-abstraction module with a shared base class and three concrete implementations. Nothing under `trimcp/bridges/` exists at all.

Required structure:
```
trimcp/bridges/
├── __init__.py
├── base.py           # Abstract provider base (OAuth, delta walk, subscription lifecycle)
├── sharepoint.py     # MS Graph API + delta + subscription management
├── gdrive.py         # Google Drive API v3 + changes + watch
└── dropbox.py        # Dropbox API v2 + list_folder/continue + webhook
```

#### SharePoint bridge (§10.3, Appendix H.3)
- OAuth via MSAL (device code or auth code flow)
- MS Graph `/drives/{id}/root/delta` for change enumeration
- Graph subscription creation: `POST /subscriptions` with `clientState` secret
- Subscription expiry: 3 days — renewal cron required (see below)
- Validation handshake: echo `validationToken` query param on subscription creation
- Per-notification fetch: `GET /drives/{driveId}/items/{itemId}/content`
- Delta token persistence in PostgreSQL `bridge_subscriptions` table

#### Google Drive bridge (§10.3, Appendix H.4)
- OAuth via `google-auth` + `google-api-python-client`
- `drive.changes.list` + `pageToken` cursor for change enumeration
- Channel watch: `drive.files.watch` or `drive.changes.watch`
- Subscription expiry: 7 days — renewal required
- Validation: respond to `X-Goog-Resource-State: sync` on first delivery
- Per-notification fetch: `drive.files.get(fileId, fields=..., alt='media')`

#### Dropbox bridge (§10.3, Appendix H.5)
- OAuth via `dropbox` SDK (single OAuth flow, simplest of the three)
- `files/list_folder/continue` with cursor for change enumeration
- Webhook: single app-level endpoint, no per-subscription expiry
- Challenge handshake: respond to `?challenge=` GET on webhook registration
- Signature verification: `X-Dropbox-Signature` HMAC-SHA256

---

### Missing: subscription renewal cron (§10.7, Appendix H.6)

SharePoint subscriptions expire every 3 days; Google Drive every 7 days. Without a renewal job, push delivery silently stops.

Required: an APScheduler (or RQ-scheduled) job that:
1. Queries `bridge_subscriptions` WHERE `expires_at < NOW() + INTERVAL '12 hours'`
2. Calls the provider's renewal API (`PATCH /subscriptions/{id}` for Graph, re-`watch` for Drive)
3. Updates `expires_at` in the DB
4. On failure: marks subscription `DEGRADED` and switches to pull-based delta walk as fallback
5. Force-resyncs any subscriptions that missed events (delta walk from last known cursor)

The cron should run every 30–60 minutes. Appendix H.6 specifies the full failure-mode and idempotency behaviour.

---

### Missing: bridge MCP tools in `server.py` (§10.6, Appendix A)

The following 6 tools are in the plan's tool reference but absent from `server.py` TOOLS list and call_tool dispatcher:

| Tool | Purpose |
|---|---|
| `connect_bridge` | Initiate OAuth for SharePoint / Google Drive / Dropbox |
| `complete_bridge_auth` | Complete OAuth code exchange and create first subscription |
| `list_bridges` | Show connected bridges and their sync status |
| `disconnect_bridge` | Remove a bridge connection and cancel subscriptions |
| `force_resync_bridge` | Trigger a full delta walk for a provider (recovery) |
| `bridge_status` | Detailed status for a specific bridge (cursor age, last event, sub expiry) |

Each tool needs a schema definition in TOOLS and a handler branch in `call_tool`.

---

### Missing: PostgreSQL schema for bridge subscriptions (Appendix H.2)

The `schema.sql` needs an additional table:

```sql
CREATE TABLE IF NOT EXISTS bridge_subscriptions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    provider        TEXT NOT NULL CHECK (provider IN ('sharepoint', 'gdrive', 'dropbox')),
    resource_id     TEXT NOT NULL,        -- drive ID, folder ID, etc.
    subscription_id TEXT,                 -- provider-assigned ID (null for Dropbox)
    cursor          TEXT,                 -- delta token / page token / list_folder cursor
    status          TEXT NOT NULL DEFAULT 'ACTIVE'
                    CHECK (status IN ('REQUESTED','VALIDATING','ACTIVE','DEGRADED','EXPIRED','DISCONNECTED')),
    expires_at      TIMESTAMPTZ,          -- null for Dropbox (no expiry)
    client_state    TEXT,                 -- HMAC secret for Graph; channel token for Drive
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON bridge_subscriptions (user_id, provider);
CREATE INDEX ON bridge_subscriptions (expires_at) WHERE status = 'ACTIVE';
```

---

## Phase 4 — Mode-Aware Shim (incomplete wiring)

### `trimcp-launch` binary stops at Phase 4 Part 1

`trimcp-launch/cmd/trimcp-launch/main.go` reads `mode.txt` and merges `.env`, then logs "Phase 4 Part 1 ready" and exits. It does not launch `server.py`.

The full dispatch logic already exists in `go/launch/` (local.go, multiuser.go, cloud_mode.go, netcheck.go, serverexec.go) but `trimcp-launch/cmd/main.go` never imports or calls it.

Required wiring in `main.go`:
```go
// After mode + env are validated:
runner, err := launch.New(mode, merged, logger, notifier)
if err != nil { ... }
os.Exit(runner.Run())
```

`go/launch/run.go` already has a `Run()` entry point — it just needs to be called.

### Missing: connectivity health checks in shim

Per §6.4, the shim must:
- **Local mode**: check Docker Desktop is running before `docker compose up`; show a plain-language dialog if not
- **Multi-User mode**: TCP connectivity check to Postgres host before launching `server.py`; show "VPN connected?" dialog on failure
- **Cloud mode**: refresh OAuth token if expired (MSAL device code); TLS connectivity check to managed Postgres endpoint

`go/launch/netcheck.go` exists but whether all three paths are wired to it needs verification.

---

## Docker Compose — Multi-User/Production Services Missing

The current `docker-compose.yml` is a **4-service dev stack** (redis, postgres, mongodb, minio). The plan's §4.2 specifies a **7-service Multi-User production stack**.

Missing services:

```yaml
  worker:
    image: trimcp-worker:latest
    restart: always
    depends_on: [postgres, mongodb, redis, minio]
    env_file: .env

  webhook-receiver:
    image: trimcp-webhooks:latest
    restart: always
    depends_on: [redis]
    env_file: .env
    ports: ["8080:8080"]

  caddy:
    image: caddy:2
    restart: always
    ports: ["443:443", "80:80"]
    volumes:
      - "./Caddyfile:/etc/caddy/Caddyfile"
      - "caddy_data:/data"
    depends_on: [webhook-receiver]
```

A `Caddyfile` is also needed to reverse-proxy `/webhooks/*` to the receiver and auto-provision TLS via Let's Encrypt.

The plan also calls for a **separate `docker-compose.local.yml`** bound to `127.0.0.1` only (Local mode), distinct from the Multi-User compose.

---

## Phase 5 — Installer Build Pipeline (verification needed)

Build artefacts exist (`build/windows/TriMCP-Setup.iss`, `build/windows/TriMCP.wxs`, `build/macos/build-dmg.sh`) but have not been verified for completeness against the wizard spec.

### Inno Setup (`TriMCP-Setup.iss`) — check against §6.2 wizard screens

Required screens and branching:
- Screen 1: Welcome
- Screen 2: Mode selection (Local / Office Shared / Cloud) — **three distinct paths**
- Screen 3a (Local): Docker Desktop check with download link if absent
- Screen 3b (Multi-User): Server address input field
- Screen 3c (Cloud): "Sign in with Microsoft" OAuth button (device code flow)
- Screen 4: Hardware acceleration — detected hardware shown; recommended backend pre-selected
- Screen 5: Document bridges (optional checkboxes: SharePoint, Google Drive, Dropbox)
- Screen 6: Progress with friendly status message
- Screen 7: Finish — "Launch Claude Desktop now" checkbox

Also verify:
- Silent install support: `/SILENT /MODE=cloud /TENANT=company.onmicrosoft.com`
- Writes `%APPDATA%\TriMCP\mode.txt` and `.env` from correct template
- Patches `%APPDATA%\Claude\claude_desktop_config.json` and `~/.cursor/mcp.json` if Cursor detected
- Registers Task Scheduler entry for Local mode (Docker stack auto-start at login)

### WiX (`TriMCP.wxs`) — check against §7.2

Required public properties for GPO/Intune silent deploy:
- `MODE` (local / multiuser / cloud)
- `SERVERADDR`
- `TENANT`
- `BRIDGES` (comma-separated: sharepoint,gdrive,dropbox)
- `BACKEND` (cpu / cuda / rocm / openvino_npu / mps)

### macOS DMG (`build-dmg.sh`) — check against §7.3

Must include:
- Universal binary (Intel + Apple Silicon via `lipo`)
- `codesign --deep --options runtime` with Developer ID Application cert
- `xcrun notarytool submit ... --wait` step
- `xcrun stapler staple` for offline Gatekeeper
- Post-install script that patches `~/Library/Application Support/Claude/claude_desktop_config.json`

---

## Minor gaps

### `webhook_receiver/main.py` — missing Redis enqueue

The webhook receiver validates signatures correctly but the POST handlers return `{"status": "ok"}` without enqueuing a processing job into Redis/RQ. In production it should:
```python
from redis import Redis
from rq import Queue
rq = Queue(connection=Redis(...))
rq.enqueue("trimcp.tasks.process_bridge_event", provider="sharepoint", payload=payload)
```

### `docker-compose.yml` — outdated pgvector image

Uses `ankane/pgvector:v0.5.1` (community image, unmaintained). The plan's §4.2 and Appendix G specify `pgvector/pgvector:pg16` (the official image).

### `trimcp-launch` — no OAuth helper for Cloud mode

`go/auth/cloud.go` and `go/auth/msal_cache.go` exist in `go/auth/` but `trimcp-launch` does not import them. Cloud mode identity resolution (MSAL device code flow, token caching) is not wired into the new shim binary.

---

## Effort estimate for remaining work

| Item | Days |
|---|---|
| `trimcp/bridges/` — SharePoint | 2 |
| `trimcp/bridges/` — Google Drive | 1.5 |
| `trimcp/bridges/` — Dropbox | 1.5 |
| Subscription renewal cron | 0.5 |
| Bridge MCP tools + schema | 1 |
| Webhook receiver Redis enqueue | 0.25 |
| docker-compose Multi-User + Caddyfile | 0.5 |
| trimcp-launch: wire go/launch dispatch | 0.5 |
| trimcp-launch: OAuth helper for Cloud mode | 1 |
| Installer wizard verification / fixes | 1–2 |
| **Total remaining** | **~10–11 days** |
