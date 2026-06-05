# NCE Phase 2 Execution Ledger

## Active Environment State
- **Branch:** `feature/phase-2-scaling`
- **Target Latency Baseline:** p95 read < 40ms
- **Current Task ID:** None

## Architectural Guardrails
- No placeholders (`# TODO`) are permitted in files.
- Math expressions must map directly to clean NumPy/SciPy or native primitives.
- All database migrations must maintain backwards compatibility with Phase 1 schemas.

## Execution Track
- [ ] BATCH-P2-001: Citus Schema Sharding Initializer
- [ ] BATCH-P2-002: Temporal Ebbinghaus Curve Math Engine
- [ ] BATCH-P2-003: Cascade Pruning Vector Zero-Fills
- [ ] BATCH-P2-004: Causal Inference Structural Topology

## Phase 2: Scale & Database Partitioning (1 to 150 Tenants)

**Timeline:** Post-Phase 1 | **Target Latency:** p95 read < 40ms

### Infrastructure & Cloud Integration

#### Regional Nordic Cloud Setup
- [ ] **Safespring OpenStack** integration
  - Establish API credentials and tenant provisioning workflows
  - Network peering with primary data center
- [ ] **Orange Business Services (Norway)** integration
  - Circuit provisioning and BGP failover configuration
  - SLA monitoring with automated alerting
- [ ] **Azure Norway East** deployment
  - AKS cluster provisioning via Bicep
  - Managed PostgreSQL with read replicas

#### Automated Infrastructure Provisioning
- [ ] **Terraform modules** for:
  - PostgreSQL cluster setup with replication
  - Redis cluster with Sentinel failover
  - Kubernetes node group provisioning
  - Network policies and security groups
- [ ] **Bicep templates** for Azure resources
- [ ] **Infrastructure state management** (Terraform Cloud)

### Database Architecture

#### Citus Multi-Tenant Partitioning

- [ ] **BATCH-P2-001: Citus Schema Sharding Initializer**
  - Analyze table sizes and access patterns
  - Determine shard key strategy (tenant_id hash bucketing)
  - Migration: `009_citus_sharding_setup.sql`
    - Convert reference tables: `namespaces`, `roles`, `users`
    - Distribute tables: `memories`, `event_log`, `topology_graph`, `v3_cognitive_ledger`, `signing_keys`
    - Create shard indexes for common query patterns
  - Verify data consistency post-sharding (no orphaned rows)

#### GDPR Cascade Pruning Engine

- [ ] **BATCH-P2-003: Cascade Pruning Vector Zero-Fills**
  - Implement `cascade_delete_tenant()` stored procedure
  - On tenant deletion:
    1. Zero-fill all HNSW vector embeddings (don't delete — preserve ledger immutability)
    2. Nullify sensitive text columns (`value`, `raw_pii_content`, `plaintext_secret`)
    3. Mark deletion in audit log with cryptographic signature
    4. Execute on distributed shards in parallel
  - Test with 50-tenant purge scenario (< 5 second duration requirement)
  - Validate no orphaned vectors remain via consistency check

### Cognitive Engines (Core)

#### Status-Weighted Ebbinghaus Forgetting Curves

- [ ] **BATCH-P2-002: Temporal Ebbinghaus Curve Math Engine**
  - Implement in new module: `nce/temporal_decay.py`
  - Formula: $R(t) = e^{-t / S}$ where:
    - $R(t)$ = retention probability at time $t$ (days)
    - $S$ = stability (domain-specific constant)
      - **Incidents:** $S = 7$ (decay to 37% confidence in 7 days)
      - **Config drift:** $S = 30$ (decay to 37% confidence in 30 days)
      - **Topology edges:** $S = 90$ (decay to 37% confidence in 90 days)
  - Background job: `calculate_retention_scores()` runs hourly
    - Materialize retention view: `memory_retention_scores`
    - Query: `SELECT memory_id, retention_prob FROM memory_retention_scores WHERE retention_prob < 0.65`
  - Web API: `GET /api/v1/memories/{id}?include_decay=true` returns `confidence_score`
  - Tests:
    - Create incident → verify $R(7) \approx 0.37$
    - Create config → verify $R(30) \approx 0.37$
    - Verify scores are used in ranking: high-$R$ results first

#### Causal Inference Layer

- [ ] **BATCH-P2-004: Causal Inference Structural Topology**
  - Implement Pearl's do-calculus in new module: `nce/causal_inference.py`
  - Build Directed Acyclic Graph (DAG) from topology edges
    - Nodes: systems, services, devices
    - Edges: "depends_on", "connected_to", "host_application"
  - API: `POST /api/v1/causal-query`
    ```json
    {
      "intervention": "host_device_failure(device_id=switch_01)",
      "query": "downstream_services_impacted()"
    }
    ```
  - Response calculates:
    1. Direct descendants in graph
    2. Confounding paths (shared dependencies)
    3. Impact probability ($P(impact | intervention)$)
  - Integrate with Active Learning: flag low-confidence causal claims

#### Validation Council Framework

- [ ] **Epistemic Quarantine Validation Council**
  - Four validators:
    1. **Source Trust:** Verify data came from trusted ingestion adapter
    2. **Topology Consistency:** Check topology edges match NetBox graph
    3. **Schema Compliance:** Validate row structure matches column types
    4. **Cross-Reference Verification:** Check external links resolve
  - Implementation: `nce/validation_council.py`
    - Each validator is a callable: `validator(memory: CognitiveMemory) → ValidationVerdict`
    - Verdict: `{is_valid: bool, confidence: float, reason: str}`
    - Memory is "Quarantined" if any validator confidence < 0.8
  - API: `GET /api/v1/memories/{id}/quarantine-status`
  - Cleanup job: Auto-purge quarantined memories > 30 days old

#### Memory Provenance Graph

- [ ] **Memory Provenance Ledger Table** (migration: `010_memory_provenance_ledger.sql`)
  - Schema:
    ```sql
    CREATE TABLE memory_provenance (
      id UUID PRIMARY KEY,
      memory_id UUID REFERENCES memories(id) ON DELETE CASCADE,
      origin_source TEXT,            -- e.g., "netbox_webhook", "syslog_stream"
      origin_timestamp TIMESTAMPTZ,
      validation_chain JSONB,        -- [{validator: "...", verdict: {...}}, ...]
      citation_graph JSONB,          -- {upstream_memory_ids: [...]}
      created_at TIMESTAMPTZ DEFAULT now()
    );
    CREATE INDEX idx_provenance_memory_id ON memory_provenance(memory_id);
    ```
  - Populate on memory write: append validator verdicts to `validation_chain`
  - Query: `GET /api/v1/memories/{id}/provenance` returns full chain
  - Use case: Operator can click "show source" → see which webhook event triggered this memory

### NetBox Vertical Module (Optional but Recommended)

#### NetBox Topology Seeder

- [ ] **NetBox REST API Sync**
  - Endpoint: `/api/dcim/devices/?limit=0` (all devices)
  - Create `nce/vertical_modules/netbox/topology_seeder.py`
  - Scheduled job (hourly):
    ```python
    def sync_netbox_devices():
      devices = netbox_api.dcim.devices.all()
      for device in devices:
        create_or_update_topology_node(
          external_id=device.id,
          node_type="device",
          name=device.name,
          decay_coefficient=0.001
        )
    ```
  - Populate edges from `/api/dcim/cables/` (device-to-device connections)
  - Implement in migration: `011_netbox_topology_sync.sql`
  - Validation: Verify graph has no disconnected islands (unless explicitly quarantined)

#### NetBox Webhook Event Bus

- [ ] **Webhook Listener** on NCE side
  - Endpoint: `POST /api/v1/webhooks/netbox`
  - NetBox webhook config: `POST /api/webhooks/webhooks/` (admin panel)
    - URL: `https://nce.example.com/api/v1/webhooks/netbox`
    - Events: `device_create`, `device_update`, `device_delete`, `cable_create`, `cable_delete`
  - Handler: Route to Dual-Track pipeline
    - Deterministic: Update topology graph edges
    - Semantic: Extract semantic changes (e.g., "device moved to different rack" → re-run spreading activation)
  - Trigger Cascade Pruning when device is marked "decommissioned"

#### NetBox Entity Resolution Engine

- [ ] Replace regex-based entity resolution
  - Query NetBox API: `GET /api/dcim/devices/?name__ic={hostname}`
  - Fallback to regex only if API returns 0 results
  - Cache resolved entities for 1 hour (Redis)

#### Three-Dimensional Drift Detection

- [ ] **Dimensions:** topology, telemetry, config contexts
  - Scheduled job (nightly):
    1. Fetch live topology from event_log (last 24h)
    2. Fetch cached topology from NetBox snapshot (last sync)
    3. Fetch config context from NetBox: `GET /api/dcim/devices/{id}/config-context/`
    4. Compute diff: `(live_topology XOR cached_topology)`
    5. Alert if **unexpected** changes detected (e.g., missing device, new cable)
  - Implementation: `nce/vertical_modules/netbox/drift_detector.py`

#### Journal Semantic Harvester

- [ ] **Operator Notes → Empathic Tensor**
  - NetBox API: `GET /api/dcim/devices/{id}/comments/`
  - NLP extraction:
    - "Device X is flaky" → frustration signal
    - "Recently replaced device Y" → topology confidence reset
    - "High load" → arousal signal
  - Feed into VAD/NASA-TLX calculation

#### Power Topology Graph

- [ ] **PDU Integration**
  - NetBox: `GET /api/dcim/power-distributions/`
  - Create graph edges: `device POWERED_BY pdu_outlet`
  - Use in Spreading Activation: "if PDU fails, mark all devices as potentially offline"

#### Scheduled Consistency Audit Engine

- [ ] **Nightly Audit Job** (midnight UTC)
  ```python
  def nightly_consistency_audit():
    # 1. Fetch all topology claims from event_log
    nce_claims = get_topology_edges(last_24h=True)
    
    # 2. Fetch source-of-truth from NetBox
    netbox_truth = netbox_api.dcim.cables.all()
    
    # 3. Compare and alert on divergence
    false_positives = nce_claims - netbox_truth
    false_negatives = netbox_truth - nce_claims
    
    if len(false_positives) > 0:
      alert(f"WARNING: {len(false_positives)} topology claims not in NetBox")
    
    # 4. Log to audit table
    log_audit_run(nce_claims, netbox_truth, divergences=false_positives)
  ```
  - Success criteria: Zero false-positive claims reaching WORM ledger

### Testing & Validation

- [ ] Load test: 150 concurrent tenants, p95 read latency < 40ms
  - Use `locust` or `k6` to simulate read load
  - Measure: kNN vector search, topology graph traversal, memory provenance lookups
- [ ] Chaos engineering: Kill 1 Citus worker → verify auto-failover
- [ ] GDPR deletion drill: Purge 10 tenants in parallel → verify < 5s completion
- [ ] Consistency audit: Run nightly for 1 week → zero false positives

### Success Criteria
- ✓ Seamless scaling to **150 concurrent tenants**
- ✓ p95 read latency **< 40ms** under load
- ✓ Nightly consistency audits with **zero false-positive** topology claims
- ✓ GDPR deletion ops complete in **< 5 seconds** per tenant
- ✓ All Phase 1 schemas remain backwards compatible

### Estimated Effort
- **Duration:** 12–16 weeks
- **Complexity:** High (distributed systems, multi-tenant partitioning)
- **Team Size:** 3–4 senior engineers (database, backend, DevOps)

---

## Status Tracking

| Task ID | Description | Owner | Status | ETA |
|---------|-------------|-------|--------|-----|
| BATCH-P2-001 | Citus Sharding Initializer | [To Assign] | Not Started | Week 2 |
| BATCH-P2-002 | Ebbinghaus Curve Math | [To Assign] | Not Started | Week 3 |
| BATCH-P2-003 | Cascade Pruning Engine | [To Assign] | Not Started | Week 4 |
| BATCH-P2-004 | Causal Inference Layer | [To Assign] | Not Started | Week 5 |
| BATCH-P2-NX-001 | NetBox Seeder | [To Assign] | Not Started | Week 6 |
| BATCH-P2-NX-002 | Webhook Bus | [To Assign] | Not Started | Week 7 |
| BATCH-P2-LOAD | Load Testing & Validation | [To Assign] | Not Started | Week 14 |

---

## Review & Approval

- [ ] Technical Lead: Code review + architecture sign-off
- [ ] Product Manager: Scope + timeline agreement
- [ ] Security Lead: Data partitioning strategy audit
- [ ] Operations: Infrastructure + deployment readiness

---

**Last Updated:** 2026-06-05  
**Phase 1 Status:** ✅ Complete (merged to main)  
**Phase 2 Status:** 🟡 Planning (this document)
