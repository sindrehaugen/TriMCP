# TriMCP Service Integrations

End-to-end data flow, retry logic, and state management for all supported downstream document bridges:
**SharePoint / OneDrive** (Microsoft Graph), **Google Workspace / Drive**, and **Dropbox**.

For OAuth setup and webhook registration steps, see [bridge_setup_guide.md](bridge_setup_guide.md).
For all environment variables, see [configuration_reference.md](configuration_reference.md).

---

## 1. Architecture Overview

The bridge system uses a **push (webhook) model**: TriMCP registers a subscription with each cloud provider, and the provider delivers change notifications to TriMCP's webhook receiver. Only changed documents are re-indexed — no polling waste.

```mermaid
flowchart TB
  subgraph Providers["Cloud Providers"]
    SP[SharePoint / OneDrive\nMS Graph]
    GD[Google Drive\nGoogle Workspace]
    DB[Dropbox]
  end

  subgraph TriMCP["TriMCP"]
    WR["Webhook Receiver\n(trimcp/webhook_receiver)"]
    BRepo["bridge_repo.py\n(subscription state — Postgres)"]
    BRenew["bridge_renewal.py\n(cron refresh)"]
    Cron["trimcp.cron\n(APScheduler)"]
    TSE["TriStackEngine\n(index_file / store_memory)"]
    RQ["Redis Queue\n(start_worker.py)"]
  end

  subgraph Storage["Data plane"]
    PG[(Postgres)]
    MG[(MongoDB)]
    RD[(Redis)]
  end

  SP -- "Webhook POST /webhooks/graph" --> WR
  GD -- "Webhook POST /webhooks/drive" --> WR
  DB -- "Webhook POST /webhooks/dropbox" --> WR

  WR --> BRepo
  WR --> RQ
  RQ --> TSE
  TSE --> PG
  TSE --> MG
  TSE --> RD

  Cron --> BRenew
  BRenew --> BRepo
  BRenew --> SP
  BRenew --> GD
```

---

## 2. Subscription Lifecycle

Bridge subscriptions have **finite lifetimes** set by each provider:

| Provider | Max subscription lifetime | Renewal approach |
|---|---|---|
| SharePoint / OneDrive | 3 days | Cron job calls `PATCH /v1.0/subscriptions/{id}` before expiry |
| Google Drive | 7 days | Cron job calls `POST .../watch` with new channel ID |
| Dropbox | Permanent | No renewal needed; monitor for app re-authorizations |

The `bridge_renewal.py` cron job runs every `BRIDGE_CRON_INTERVAL_MINUTES` minutes (default 45).
It queries `bridge_subscriptions` for entries expiring within `BRIDGE_RENEWAL_LOOKAHEAD_HOURS` (default 12 h).

```mermaid
sequenceDiagram
  participant CR as trimcp.cron (APScheduler)
  participant BR as bridge_renewal.py
  participant PG as Postgres (bridge_subscriptions)
  participant SP as SharePoint API
  participant GD as Google Drive API

  CR->>BR: renew_expiring_subscriptions()
  BR->>PG: SELECT * WHERE expires_at < now() + 12h
  loop for each expiring subscription
    alt provider == graph
      BR->>SP: PATCH /v1.0/subscriptions/{id}\n  expirationDateTime: now+3d
      SP-->>BR: 200 updated subscription
    else provider == gdrive
      BR->>GD: POST /drive/v3/changes/watch\n  (new channel_id, new token)
      GD-->>BR: 200 new channel
    end
    BR->>PG: UPDATE bridge_subscriptions SET expires_at, subscription_id
  end
```

---

## 3. Incoming Webhook Flow (Per Provider)

### 3a. SharePoint / OneDrive (MS Graph)

```mermaid
sequenceDiagram
  participant MS as Microsoft Graph
  participant WR as Webhook Receiver
  participant PG as Postgres
  participant RQ as Redis Queue

  MS->>WR: POST /webhooks/graph\n  {clientState, value: [{...}]}
  WR->>WR: Validate clientState == GRAPH_CLIENT_STATE
  alt validation failure
    WR-->>MS: 401 Unauthorized
  else validation ok
    WR->>PG: Upsert bridge_subscription cursor
    loop for each changed resource
      WR->>RQ: Enqueue index_file(resource_id, namespace_id)
    end
    WR-->>MS: 202 Accepted
  end
  RQ-->>WR: (background) Worker fetches file\n via Graph API + indexes into TSE
```

**Validation token handshake** (subscription creation only):
When MS Graph sends a `validationToken` query parameter, the receiver echoes it back with `text/plain` within 10 seconds. This is handled automatically by the webhook receiver.

### 3b. Google Drive

```mermaid
sequenceDiagram
  participant GD as Google Drive API
  participant WR as Webhook Receiver
  participant PG as Postgres
  participant RQ as Redis Queue

  GD->>WR: POST /webhooks/drive\n  Headers: X-Goog-Channel-Token, X-Goog-Resource-State
  WR->>WR: Validate X-Goog-Channel-Token == DRIVE_CHANNEL_TOKEN
  alt X-Goog-Resource-State == "sync"
    WR-->>GD: 200 OK  (subscription confirmed, no work)
  else resource changed
    WR->>PG: Upsert bridge cursor
    WR->>RQ: Enqueue index_file(file_id, namespace_id)
    WR-->>GD: 200 OK
  end
```

### 3c. Dropbox

```mermaid
sequenceDiagram
  participant DB as Dropbox API
  participant WR as Webhook Receiver
  participant RQ as Redis Queue

  alt GET verification challenge
    DB->>WR: GET /webhooks/dropbox?challenge=<token>
    WR-->>DB: 200 <token>  (echo the challenge)
  else POST change notification
    DB->>WR: POST /webhooks/dropbox\n  Header: X-Dropbox-Signature\n  Body: {list_folder: {accounts: [...]}}
    WR->>WR: Verify HMAC-SHA256(body, DROPBOX_APP_SECRET)\n  == X-Dropbox-Signature
    alt HMAC mismatch
      WR-->>DB: 403 Forbidden
    else HMAC ok
      loop for each account
        WR->>RQ: Enqueue list_and_index_changes(account_id)
      end
      WR-->>DB: 200 OK
    end
  end
```

---

## 4. Retry Logic & Error Handling

Retries are handled at two layers:

### 4a. Webhook receiver layer (immediate)

The webhook receiver always returns **2xx to the provider immediately** (before the indexing worker runs). This prevents the provider from interpreting an indexing failure as a delivery failure and re-sending the same notification thousands of times.

If the receiver fails to enqueue to Redis (queue full or Redis down), it logs an error and returns `503` — the provider will retry delivery according to its own back-off policy.

### 4b. RQ worker layer (async)

The `index_file` RQ job handles indexing failures with TriMCP's standard retry policy:

| Attempt | Back-off | Behaviour |
|---|---|---|
| 1–`TASK_MAX_RETRIES` | Exponential with full jitter | Retry automatically |
| > `TASK_MAX_RETRIES` | — | Route to `dead_letter_queue` table, emit alert |

**Dead-letter queue**:
Failed jobs land in the `dead_letter_queue` Postgres table with the job payload, error message, and attempt count. Operators can inspect and replay from the admin UI or via the admin API.

---

## 5. State Model

Bridge state is tracked in two Postgres tables:

### `bridge_subscriptions`

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Internal ID |
| `namespace_id` | UUID | Owning namespace (RLS enforced) |
| `provider` | text | `graph`, `gdrive`, `dropbox` |
| `subscription_id` | text | Provider-assigned subscription / channel ID |
| `resource_id` | text | Drive / site / folder being watched |
| `cursor` | text | Change cursor / delta token for incremental fetches |
| `expires_at` | timestamptz | Subscription expiry; NULL for Dropbox (permanent) |
| `status` | text | `active`, `expired`, `error` |
| `access_token` | bytea | Encrypted OAuth token (AES-256-GCM) |
| `refresh_token` | bytea | Encrypted refresh token |

### `bridge_events` (via `event_log`)

Every webhook delivery and indexing action is recorded as a signed event in the WORM `event_log`, providing a tamper-evident audit trail of all bridge activity.

---

## 6. Local Development Without a Public URL

Webhooks require a public HTTPS endpoint. For local development, use a tunneling tool:

```bash
# ngrok example
ngrok http 8003
# Copy the HTTPS URL and set:
export BRIDGE_WEBHOOK_BASE_URL=https://<ngrok-id>.ngrok.io
```

When no `BRIDGE_WEBHOOK_BASE_URL` is set, the webhook receiver is still available but subscription registration will fail. The system falls back to **scheduled pull** mechanisms: the cron job polls for changes instead of waiting for push notifications. This is lower frequency but functionally equivalent for development.
