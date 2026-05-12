# TriMCP Documentation Index

Technical specifications, architectural guides, and operational references for TriMCP v1.0.

---

## Getting Started

- [**Developer Onboarding**](developer_onboarding.md): Local Quad-DB setup, pytest execution, codebase map, and contribution invariants.
- [**Quick Start Guide**](quick_start.md): Fastest path from zero to a working MCP server.
- [**Usage Modes**](usage_modes.md): MCP/LLM stdio (JSON-RPC 2.0) vs. Admin REST API — wire-level payload examples for both.

---

## Architecture & Database

- [**Architecture v1.0 Specification**](architecture-v1.md): Runtime topology, temporal engine, A2A protocol, cognitive workers, GraphRAG pipeline (§7.1), partitioning tradeoffs, and MCP tool surface.
- [**Database Architecture**](database_architecture.md): Connection pools (asyncpg, Motor, Redis, MinIO), `scoped_pg_session` pattern, Saga cross-DB write path, GraphRAG hydration pipeline, WORM event log design, and module map.

---

## Configuration & Operations

- [**Configuration Reference**](configuration_reference.md): Authoritative reference for every environment variable, server launch command, and runtime flag (~70 variables across 20 sections).
- [**IT Admin Guide**](it_admin_guide.md): Operational procedures for production deployments.
- [**Airgapped & Edge Deployment**](airgapped_deployment.md): Local inference stack, OpenVINO NPU hardware acceleration, and offline configuration.
- [**Troubleshooting & FAQ**](troubleshooting_faq.md): Common errors and their resolutions.

---

## Security

- [**Enterprise Security Guide**](enterprise_security.md): mTLS client certificates, JWT/SSO integration, HMAC API authentication, signing key management, RLS enforcement, and production security checklist.
- [**Cryptographic Signing & Integrity**](signing.md): HMAC-SHA256 integrity layer, JCS canonicalization (RFC 8785), and AES-256-GCM key management.
- [**Multi-Tenancy & Resource Quotas**](multi_tenancy.md): isolation boundaries, Row-Level Security (RLS) enforcement, and the atomic quota engine.
- [**PII Detection & Redaction**](pii.md): Automated PII pipeline (Presidio/Regex), redaction policies, and the reversible pseudonymization vault.

---

## Integrations

- [**Service Integrations**](service_integrations.md): SharePoint/OneDrive, Google Drive, and Dropbox webhook flows, subscription lifecycle, retry logic, and dead-letter queue behavior.
- [**Bridge Setup Guide**](bridge_setup_guide.md): OAuth registration and webhook endpoint configuration for all three providers.
- [**Agent-to-Agent (A2A) Protocol**](a2a.md): Secure cross-agent memory sharing via cryptographic handshakes and scoped tokens.

---

## Cognitive Layer

- [**Cognitive Features (Consolidation & Salience)**](cognitive_layer.md): HDBSCAN-based memory "sleep cycle", Ebbinghaus forgetting curve modeling, and contradiction detection.
- [**LLM Providers & Structured Output**](llm_providers.md): Provider-agnostic engine and mandatory Pydantic V2 schema validation for all cognitive tasks.

---

## Data Engineering & Simulation

- [**Memory Time Travel**](time_travel.md): Temporal state reconstruction using the WORM event log and `as_of` querying.
- [**Memory Replay Engine**](replay.md): Observational and forked replay modes for simulation and "What-If" analysis with alternate causal provenance.
- [**System Migrations & Re-embedding**](migrations.md): "Shadow Column" re-embedding strategies, neighbor overlap quality gates, and schema evolution.
