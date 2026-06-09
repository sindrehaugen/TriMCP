# Dynamics 365 Integration Reference

This document provides a comprehensive technical reference for the Dynamics 365 / Dataverse integration surfaces in the Neuro Cognitive Engine (NCE). These surfaces consist of a set of administrative REST API routes on the admin server and specialized Model Context Protocol (MCP) tools for LLM interaction.

---

## 1. Admin REST API

The administrative REST API endpoints for the Dynamics 365 integration allow monitoring configuration, inspecting active tenant integrations, triggering immediate synchronizations, listing service level agreement (SLA) breaches, and toggling integration state per namespace.

> [!NOTE]
> All admin REST API routes run on the **admin server (port 8003)** and require standard NCE HMAC-SHA256 signature authentication in the `Authorization` header.

### 1.1. Get Configuration
* **Endpoint**: `GET /api/admin/d365/config`
* **Description**: Returns the active Dynamics 365 global configuration parameters. For security reasons, client secrets and webhooks secrets are redacted or returned as boolean flags.
* **Query Parameters**: None
* **Success Response (`200 OK`)**:
  ```json
  {
    "enabled": true,
    "org_url": "https://nce-prod.crm4.dynamics.com",
    "api_version": "9.2",
    "sync_interval_minutes": 60,
    "sync_page_size": 500,
    "high_priority_salience_boost": 2.0,
    "webhook_secret_set": true,
    "empathic_urgency_keywords": "CRITICAL,DOWN,OUTAGE,EXPIRED",
    "empathic_frustration_keywords": "ANNOYED,UPSET,DELAY,UNHAPPY"
  }
  ```

### 1.2. List Integrations
* **Endpoint**: `GET /api/admin/d365/integrations`
* **Description**: Lists registered tenant-scoped Dynamics 365 integration profiles, paginated.
* **Query Parameters**:
  * `page` (integer, optional, default: `1`) — The page index to fetch.
  * `limit` (integer, optional, default: `50`) — The maximum number of entries to return.
* **Success Response (`200 OK`)**:
  ```json
  {
    "total": 1,
    "items": [
      {
        "id": "e813a48e-d95b-4c48-8dfb-f28328c0b299",
        "namespace_id": "a4d3cfbd-2ea1-424a-a035-e1ab89bf3dc1",
        "namespace_slug": "tenant-alpha",
        "org_url": "https://nce-prod.crm4.dynamics.com",
        "status": "ACTIVE",
        "last_sync_at": "2026-06-07T01:30:00Z",
        "last_sync_stats": {
          "incidents": {
            "processed": 42,
            "upserted": 42,
            "errors": 0
          }
        },
        "created_at": "2026-06-06T12:00:00Z",
        "updated_at": "2026-06-07T01:30:00Z",
        "d365_enabled": true
      }
    ]
  }
  ```

### 1.3. Trigger Immediate Sync
* **Endpoint**: `POST /api/admin/d365/sync`
* **Description**: Triggers a synchronous, immediate Dataverse entity sync cycle for a specific namespace.
* **Request Body (`application/json`)**:
  * `namespace_id` (string/UUID, required) — The target tenant namespace UUID.
  * `entity_types` (array of strings, optional) — A list of entities to synchronize (subset of `["accounts", "contacts", "opportunities", "incidents"]`). If omitted, all supported entity types are synchronized.
* **Success Response (`200 OK`)**:
  ```json
  {
    "status": "ok",
    "stats": {
      "accounts": {"processed": 5, "upserted": 5, "errors": 0},
      "contacts": {"processed": 12, "upserted": 12, "errors": 0},
      "opportunities": {"processed": 3, "upserted": 3, "errors": 0},
      "incidents": {"processed": 8, "upserted": 8, "errors": 0}
    }
  }
  ```
* **Error Responses**:
  * `400 Bad Request` — Invalid JSON body structure.
  * `422 Unprocessable Entity` — Missing or malformed `namespace_id`.
  * `504 Gateway Timeout` — The sync duration exceeded the maximum allowed timeout of 300 seconds.

### 1.4. List SLA Breaches
* **Endpoint**: `GET /api/admin/d365/sla-breaches`
* **Description**: Lists signed, read-only audit log events corresponding to SLA breach detections logged in the Write-Once-Read-Many (WORM) `event_log`.
* **Query Parameters**:
  * `namespace_id` (string/UUID, optional) — Filters breach records to a specific namespace.
  * `page` (integer, optional, default: `1`) — Page index.
  * `limit` (integer, optional, default: `50`) — Page limit.
* **Success Response (`200 OK`)**:
  ```json
  {
    "total": 1,
    "items": [
      {
        "id": "7b095efb-86d1-4db5-b3e3-7740529d8b13",
        "namespace_id": "a4d3cfbd-2ea1-424a-a035-e1ab89bf3dc1",
        "agent_id": "d365-sync-agent",
        "event_seq": 884,
        "occurred_at": "2026-06-07T02:00:15Z",
        "params": {
          "ticket_number": "CAS-01824-H7Y2",
          "severity": "High",
          "breach_time": "2026-06-07T01:45:00Z"
        },
        "result_summary": "SLA breach detected for Incident CAS-01824-H7Y2"
      }
    ]
  }
  ```

### 1.5. Namespace Toggle Integration
* **Endpoint**: `POST /api/admin/d365/namespace/{ns_id}/d365-enabled`
* **Description**: Globally enables or disables the Dynamics 365 sync engine integrations for the designated namespace by updating the namespace's metadata fields.
* **Path Parameters**:
  * `ns_id` (string/UUID, required) — The namespace UUID to update.
* **Request Body (`application/json`)**:
  * `enabled` (boolean, required) — The target activation state.
* **Success Response (`200 OK`)**:
  ```json
  {
    "namespace_id": "a4d3cfbd-2ea1-424a-a035-e1ab89bf3dc1",
    "d365_enabled": true
  }
  ```

---

## 2. MCP Tools Registry

To enable automated AI agent workflows to query CRM status and perform operational synchronizations, NCE registers four specialized Dynamics 365 tools within its Model Context Protocol (MCP) registry.

### 2.1. Tool Capabilities Matrix

The MCP tools are governed by structural metadata tags specifying mutation safety, cache eligibility, and privilege constraints.

| Tool Name | Mutation? | Cacheable? | Admin Only? | Description |
|---|:---:|:---:|:---:|---|
| `d365_query_case` | ❌ No |  Yes | ❌ No | Fetches a specific case/incident enriched with graph connections. |
| `d365_sync_now` |  Yes | ❌ No |  Yes | Invokes an immediate entity synchronization cycle. |
| `d365_case_stress_report` | ❌ No |  Yes | ❌ No | Summarizes the emotional stress curve of account-linked incidents. |
| `d365_list_sla_breaches` | ❌ No | ❌ No |  Yes | Returns a list of chronological SLA breach events. |

---

### 2.2. Tool Reference Specification

#### `d365_query_case`
Fetches a single incident entity from Dataverse by its GUID and enriches the output with relevant knowledge graph associations (e.g. `Incident:CAS-XXXXX` connections) stored in NCE.

* **Arguments**:
  * `namespace_id` (string, required) — Tenant namespace UUID.
  * `case_id` (string, required) — The Dataverse `incidentid` GUID.
  * `include_notes` (boolean, optional, default: `true`) — Fetch linked annotations.
  * `include_activities` (boolean, optional, default: `false`) — Fetch linked activity timeline records.
* **Output Payload (Stringified JSON)**:
  ```json
  {
    "case": {
      "incidentid": "92f3ac21-b01a-4d7a-b9c1-4ab6cda291b5",
      "ticketnumber": "CAS-01824-H7Y2",
      "title": "Database connection failures under heavy load",
      "description": "The client reports timeout errors during transaction commits.",
      "prioritycode": 1,
      "statuscode": 1,
      "_customerid_value": "bc110a23-df42-e11a-8fc3-b4cd1e220a88",
      "_ownerid_value": "f8a002bc-b82b-422a-88cd-1122ab00ee33"
    },
    "notes": [
      {
        "annotationid": "ab708fde-e112-4cba-bc2b-1188cd22aa01",
        "notetext": "Suspect connection pool exhaustion in the backend service.",
        "subject": "Diagnostic Note",
        "createdon": "2026-06-07T01:10:00Z"
      }
    ],
    "activities": [],
    "graph_context": [
      {
        "subject_label": "Incident:CAS-01824-H7Y2",
        "predicate": "HAS_NOTE",
        "object_label": "Annotation:ab708fde-e112-4cba-bc2b-1188cd22aa01",
        "confidence": 0.98
      }
    ]
  }
  ```

#### `d365_sync_now`
Triggers an immediate, synchronous Dataverse entities sync workflow for the designated tenant namespace.

* **Arguments**:
  * `namespace_id` (string, required) — Tenant namespace UUID.
  * `entity_types` (array of strings, optional) — Specific entities to synchronize (subset of `["accounts", "contacts", "opportunities", "incidents"]`).
* **Output Payload (Stringified JSON)**:
  ```json
  {
    "status": "completed",
    "stats": {
      "incidents": {
        "processed": 1,
        "upserted": 1,
        "errors": 0
      }
    }
  }
  ```

#### `d365_case_stress_report`
Generates an empathic stress and frustration trend report by querying the `v3_cognitive_ledger` table. It retrieves case-linked annotation memories within a historical lookback window, extracts their Empathic Tensors, and evaluates client stress/burnout alerts.

* **Arguments**:
  * `namespace_id` (string, required) — Tenant namespace UUID.
  * `account_name` (string, required) — Target account name (matched via Graph relationships).
  * `lookback_days` (integer, optional, default: `30`) — Lookback duration in days.
* **Output Payload (Stringified JSON)**:
  ```json
  {
    "account_name": "Acme Corp",
    "incident_count": 3,
    "lookback_days": 30,
    "note_readings": 5,
    "frustration_trend": [2.5, 4.0, 7.2, 8.5, 9.1],
    "avg_frustration": 6.26,
    "burnout_alert": true,
    "burnout_threshold": 7.0
  }
  ```

#### `d365_list_sla_breaches`
Lists Dynamics 365 SLA breach events logged chronological under the event type `d365_sla_breach` in the WORM event log.

* **Arguments**:
  * `namespace_id` (string, required) — Tenant namespace UUID.
  * `since` (string, required) — ISO-8601 datetime threshold.
  * `limit` (integer, optional, default: `50`, maximum: `500`) — Maximum records to retrieve.
* **Output Payload (Stringified JSON)**:
  ```json
  {
    "namespace_id": "a4d3cfbd-2ea1-424a-a035-e1ab89bf3dc1",
    "since": "2026-06-06T00:00:00Z",
    "count": 1,
    "breaches": [
      {
        "event_id": "7b095efb-86d1-4db5-b3e3-7740529d8b13",
        "agent_id": "d365-sync-agent",
        "params": {
          "ticket_number": "CAS-01824-H7Y2",
          "severity": "High",
          "breach_time": "2026-06-07T01:45:00Z"
        },
        "created_at": "2026-06-07T02:00:15Z"
      }
    ]
  }
  ```

---

## 3. Test Suite & Registry Verification

The structural integrity and categorization boundaries of the MCP registry are validated by the NCE test suite (specifically `tests/test_tool_registry.py`). 

Following the integration of the Dynamics 365 vertical module, the registry metrics satisfy these constraints:
* **Total Registered Tools**: **58**
* **Mutation-capable Tools**: **28** (including `d365_sync_now`)
* **Admin-only privilege Tools**: **7** (including `d365_sync_now` and `d365_list_sla_breaches`)
