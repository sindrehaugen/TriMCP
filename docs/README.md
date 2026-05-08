# TriMCP Feature Guides

This directory contains detailed technical specifications and architectural guides for the core components of the TriMCP Memory Engine.

## Foundation & Security
- [**Multi-Tenancy & Resource Quotas**](multi_tenancy.md): isolation boundaries, Row-Level Security (RLS) enforcement, and the atomic quota engine.
- [**Cryptographic Signing & Integrity**](signing.md): HMAC-SHA256 integrity layer, JCS canonicalization (RFC 8785), and AES-256-GCM key management.
- [**PII Detection & Redaction**](pii.md): Automated PII pipeline (Presidio/Regex), redaction policies, and the reversible pseudonymization vault.

## Cognitive Layer
- [**Cognitive Features (Consolidation & Salience)**](cognitive_layer.md): HDBSCAN-based memory "sleep cycle", Ebbinghaus forgetting curve modeling, and contradiction detection.
- [**LLM Providers & Structured Output**](llm_providers.md): Provider-agnostic engine and mandatory Pydantic V2 schema validation for all cognitive tasks.

## Data Engineering & Simulation
- [**Memory Time Travel**](time_travel.md): Temporal state reconstruction using the WORM event log and `as_of` querying.
- [**Memory Replay Engine**](replay.md): Observational and forked replay modes for simulation and "What-If" analysis with alternate causal provenance.
- [**Agent-to-Agent (A2A) Protocol**](a2a.md): Secure cross-agent memory sharing via cryptographic handshakes and scoped tokens.

## System Operations
- [**Airgapped & Edge Deployment**](airgapped_deployment.md): Local inference stack, OpenVINO NPU hardware acceleration, and offline configuration.
- [**System Migrations & Re-embedding**](migrations.md): "Shadow Column" re-embedding strategies, neighbor overlap quality gates, and schema evolution.

---

### Additional Resources
- [Architecture v1.0 Specification](architecture-v1.md)
- [Bridge Setup Guide](bridge_setup_guide.md)
- [IT Admin Guide](it_admin_guide.md)
- [Quick Start Guide](quick_start.md)
- [Troubleshooting & FAQ](troubleshooting_faq.md)
