# NCE Enterprise Security Guide

This document details the security model, cryptographic controls, and access authorization boundaries implemented in the Neuro Cognitive Engine (NCE).

---

## 1. Authentication Architecture

NCE exposes three distinct communication interfaces, each using an authentication mechanism tailored to its protocol and exposure surface:

```
                  ┌────────────────────────┐
                  │   Client Applications  │
                  └───────────┬────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │ (Stdio Pipe)       │ (HTTP REST)        │ (JSON-RPC)
         ▼                    ▼                    ▼
┌──────────────────┐┌──────────────────┐┌──────────────────┐
│    MCP Stdio     ││    Admin API     ││    A2A Server    │
│  (server.py)     ││ (admin_server.py)││ (a2a_server.py)  │
├──────────────────┤├──────────────────┤├──────────────────┤
│ - NCE_MCP_API_KEY││ - HMAC-SHA256    ││ - Bearer JWT     │
│ - Pin Namespace  ││ - HTTP Basic UI  ││ - A2A Grants     │
│                  ││ - mTLS Option    ││ - mTLS Option    │
└──────────────────┘└──────────────────┘└──────────────────┘
```

| Service Surface | Transport | Primary Security Protocol | Configuration Variables |
| :--- | :--- | :--- | :--- |
| **MCP Stdio Server** | Standard Process Pipes | Symmetric API Key Validation + Namespace Pinning | `NCE_MCP_API_KEY`, `NCE_MCP_NAMESPACE_ID` |
| **Admin REST API & UI** | HTTP / HTTPS | HMAC-SHA256 Signature (API) / HTTP Basic (UI) + mTLS | `NCE_ADMIN_API_KEY`, `NCE_ADMIN_PASSWORD`, `NCE_ADMIN_MTLS_ENABLED` |
| **A2A (Agent-to-Agent)** | HTTP / HTTPS | Asymmetric JWT Bearer Tokens + mTLS + Sharing Grants | `NCE_JWT_SECRET`, `NCE_JWT_PUBLIC_KEY`, `NCE_A2A_MTLS_ENABLED` |

---

## 2. MCP Stdio Authentication & Namespace Pinning

The MCP stdio server (`server.py`) operates as a child process of the client IDE (such as Cursor or Claude Desktop).

### 2a. Configuration Envelope
When running in production, the client environment must inject the security keys into the launch configuration:

```json
{
  "mcpServers": {
    "nce-memory": {
      "command": "python",
      "args": ["/path/to/nce/server.py"],
      "env": {
        "NCE_MCP_API_KEY": "mcp_client_tenant_secret_key_string",
        "NCE_MASTER_KEY": "aes_256_gcm_vault_master_key_material",
        "NCE_MCP_NAMESPACE_ID": "673f8e91-654e-48bd-b7bb-ea392d4f8001"
      }
    }
  }
}
```

### 2b. Namespace Pinning Constraint
* **Tenant Isolation**: By specifying `NCE_MCP_NAMESPACE_ID`, the stdio server locks all incoming requests to that single namespace. Any payload specifying a different `namespace_id` is rejected at the entry dispatcher boundary.
* **Key Validation**: Every incoming tool call must include the correct `mcp_api_key` matching the environment's `NCE_MCP_API_KEY`. If they do not match, the request fails with a JSON-RPC `-32602` error.

---

## 3. HMAC-SHA256 API Authentication (Admin API)

All programmatically triggered HTTP routes exposed on the Admin API (`admin_server.py` on port `8003`) require HMAC-SHA256 request authentication to prevent payload tampering and replay attacks.

### 3a. Header Signature Structure
Requests must supply an `Authorization` header formatted as follows:

```http
Authorization: HMAC-SHA256 <timestamp>:<nonce>:<signature>
```

* **Timestamp**: Epoch time in seconds.
* **Nonce**: A single-use random string (minimum 16 characters).
* **Signature**: Hex-encoded HMAC calculated using `NCE_ADMIN_API_KEY` over the canonical payload string.

### 3b. Signature Calculation Formula
The signature is generated using SHA-256:

$$\text{CanonicalString} = \text{timestamp} \mathbin{\Vert} \text{"\n"} \mathbin{\Vert} \text{nonce} \mathbin{\Vert} \text{"\n"} \mathbin{\Vert} \text{HTTP\_Method} \mathbin{\Vert} \text{"\n"} \mathbin{\Vert} \text{Path} \mathbin{\Vert} \text{"\n"} \mathbin{\Vert} \text{SHA256(Request\_Body)}$$

$$\text{Signature} = \text{HMAC-SHA256}(\text{NCE\_ADMIN\_API\_KEY}, \text{CanonicalString})$$

### 3c. Anti-Replay Mitigation
The verification middleware enforces the following validation checks:
1. **Clock Skew Tolerance**: The timestamp is checked against the server clock. If the skew exceeds `NCE_CLOCK_SKEW_TOLERANCE_S` (default: 300 seconds), the request is rejected.
2. **Distributed Nonce Cache**: The nonce is stored in Redis with a TTL matching the clock skew window. If a nonce is presented a second time within this window, the request is rejected immediately.

---

## 4. JWT Bearer Token Authentication (A2A Server)

Autonomously operating agents communicating via the Agent-to-Agent (A2A) server on port `8004` present JWT Bearer tokens to assert identity.

### 4a. Cryptographic Verification Modes
* **Symmetric (HS256)**: For deployments within a single trust boundary, the signature is verified using `NCE_JWT_SECRET` (minimum 32 bytes).
* **Asymmetric (RS256 / ES256)**: For multi-organization agent federations, NCE validates signatures using a public certificate defined in `NCE_JWT_PUBLIC_KEY` (PEM string or local file path). The issuer is configured in `NCE_JWT_ISSUER`.

### 4b. Audience Isolation Policy
To prevent a token issued for one agent network from being reused against the administrative backend, NCE supports distinct audience (`aud`) verification rules:

```bash
# Required in JWT payload for accessing A2A endpoints (/tasks/send)
NCE_A2A_JWT_AUDIENCE=nce_a2a_network

# Required in JWT payload for accessing Admin REST endpoints
NCE_JWT_AUDIENCE=nce_admin_fleet
```

Tokens that present mismatching audiences are rejected with a `-32010` authorization exception.

---

## 5. PostgreSQL Row-Level Security (RLS) Policies

NCE implements tenant isolation directly at the database layer. This ensures that even if application logic fails to filter a query by tenant, PostgreSQL blocks access to unauthorized data.

### 5a. The Fail-Safe Namespace Resolver
Postgres resolves tenant identity using the session settings variable `nce.namespace_id`. This is wrapped by the stable PL/pgSQL function `get_nce_namespace()`:

```sql
CREATE OR REPLACE FUNCTION get_nce_namespace() RETURNS uuid AS $$
DECLARE
    val text;
BEGIN
    val := nullif(trim(current_setting('nce.namespace_id', true)), '');
    IF val IS NULL THEN
        RAISE EXCEPTION 'nce.namespace_id is not set for this transaction';
    END IF;
    BEGIN
        RETURN val::uuid;
    EXCEPTION
        WHEN invalid_text_representation THEN
            RAISE EXCEPTION 'nce.namespace_id is not a valid UUID: %', val;
    END;
END;
$$ LANGUAGE plpgsql STABLE;
```

### 5b. Default Table Policy Pattern
For all 15 tenant-scoped tables (such as `memories`, `kg_nodes`, `kg_edges`, `pii_redactions`, etc.), RLS is enabled and enforced:

```sql
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE memories FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy ON memories
    FOR ALL TO nce_app
    USING (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace())
    WITH CHECK (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace());
```

* **RLS Enforcement Rule**: All SELECT, INSERT, UPDATE, and DELETE operations executed under the standard application role `nce_app` are restricted to the UUID returned by `get_nce_namespace()`.
* **Privileged Role Exception**: The garbage collection role `nce_gc` bypasses RLS using the database-level `BYPASSRLS` attribute. This role is not accessible to application threads.

---

## 6. PII Redaction & AES-256-GCM Vault

To prevent Personal Data / PII leakage into vector databases and external LLM models, NCE executes a PII Redaction pipeline before writing data.

```
Incoming Text: "Contact Alice at alice@example.com"
       │
       ▼
[ Presidio Analyzer / Regex Engine ]
       │
       ├─► Redacts Email -> "Contact Alice at <EMAIL_1>"
       │
       └─► Extracts PII: Value="alice@example.com", Type="EMAIL"
             │
             ▼
       [ Encrypt with NCE_MASTER_KEY ]
       (AES-256-GCM, unique 12-byte IV)
             │
             ▼
       [ Write to pii_redactions ]
       Columns: namespace_id, memory_id, token, encrypted_value
```

### 6a. Cryptographic Vault Storage
* **Encryption standard**: PII entities are encrypted using AES-256-GCM.
* **Key Derivation**: The encryption key is derived from the environment variable `NCE_MASTER_KEY` (minimum 32 random bytes).
* **Storage Target**: The encrypted byte array, along with the replacement token (e.g. `<EMAIL_1>`), the entity type, and the referencing memory UUID are inserted into the `pii_redactions` table.

### 6b. Reversible Unredaction
Authorized administrative users can retrieve original values using the `unredact_memory` tool:
1. The requester must supply the `admin_api_key`.
2. The query is executed inside a `scoped_pg_session`, ensuring RLS limits lookup to the requester's namespace.
3. The cipher text is retrieved and decrypted using `NCE_MASTER_KEY` before returning the plain text to the authenticated supervisor.

---

## 7. Agent-to-Agent (A2A) Scope Enforcement

Cross-tenant data sharing is controlled through the `a2a_grants` table, which holds structured access rules.

### 7a. Structuring A2A Grants
An A2A grant specifies the owner namespace, target consumer namespace, validation timeframe, and resource scopes:

```json
{
  "grant_id": "87f0b21e-d124-4bca-89a3-fa349d3c8003",
  "owner_namespace_id": "673f8e91-654e-48bd-b7bb-ea392d4f8001",
  "consumer_namespace_id": "921a4f02-98ab-4cc1-94ef-67efab109f02",
  "scopes": [
    {
      "resource_type": "subgraph",
      "resource_id": "alice_network",
      "permissions": ["read"]
    },
    {
      "resource_type": "memory",
      "resource_id": "67f0b982-f12a-4cbd-b2bb-de882d9f8210",
      "permissions": ["read"]
    }
  ],
  "expires_at": "2026-07-07T00:00:00Z"
}
```

### 7b. Token Verification Mechanics
1. **Creation**: When a sharing grant is created, the system generates a random token and stores its SHA-256 hash in `token_hash`. The raw token is returned once to the caller.
2. **Access request**: When a consumer agent queries data via `/tasks/send` or `a2a_query_shared`, it supplies the raw token.
3. **Validation**: NCE hashes the token using SHA-256 and queries `a2a_grants` for a matching hash:
   * The status must be `'active'`.
   * The current time must be prior to `expires_at`.
   * The requested query parameters must match the permissions defined in the `scopes` JSONB array.
4. **Enforcement**: If valid, the target resources are retrieved under the owner's namespace using the owner's session context before returning them to the consumer agent.

---

## 8. Cryptographic Keys & Secrets Security Checklist

This checklist defines the storage and rotation rules for system secrets:

| Secret Name | Purpose | Minimum Length | Storage Recommendation | Rotation Procedure |
| :--- | :--- | :--- | :--- | :--- |
| `NCE_MASTER_KEY` | Encrypts PII vault data and oauth bridge credentials at rest. | 32 bytes | Enterprise Key Management System (KMS) or vault. | Offline re-encryption script of `pii_redactions` and `bridge_subscriptions` tables. |
| `NCE_MCP_API_KEY` | Authenticates incoming IDE tool calls in stdio transport. | 64 characters | Client user configuration file (encrypted at rest by OS). | Generate new token, update environment configuration, and restart client. |
| `NCE_ADMIN_API_KEY` | Authenticates incoming Admin REST requests via HMAC. | 64 characters | Secrets management system (KMS). | Update environment variable on NCE and client, followed by rolling restart. |
| `NCE_JWT_SECRET` | Signs HS256 tokens for A2A communication. | 32 bytes | Secrets management system (KMS). | Update environment configuration and restart NCE instances. |
| `NCE_JWT_PUBLIC_KEY` | Verifies RS256/ES256 tokens from external SSO / OIDC. | 4096-bit RSA / P-256 EC | Stored as environment PEM string or local file path. | Update public key file, trigger rolling deployment without downtime. |
