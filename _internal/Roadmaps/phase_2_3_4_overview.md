# NCE Phases 2–4: Executive Roadmap Overview

**Status:** Phase 1 complete and merged to main  
**Current Date:** 2026-06-05  
**Last Updated:** 2026-06-05

---

## Phase Architecture Timeline

```
Q2 2026          Q3 2026           Q4 2026           Q1 2027
├─ Phase 1 ✅    ├─ Phase 2 →      ├─ Phase 3 →      ├─ Phase 4
│  Complete     │  12-16w          │  16-20w          │  12-16w
│  (MERGED)     │  (Database,      │  (ATMS, Active   │  (ZK-CTE,
│               │   Forgetting,    │   Learning,      │   Federated
│               │   Causal)        │   GraphQL)       │   Swarms)
│               │                  │                  │
└───────────────┴──────────────────┴──────────────────┴──────────►
                                                    500 Tenants
                                                    Live
```

---

## PHASE 2: Scale & Database Partitioning (1 → 150 Tenants)

**Timeline:** 12–16 weeks | **Target:** p95 read latency < 40ms

### Overview
Scale from single-tenant to 150-tenant architecture using Citus distributed PostgreSQL. Implement scientific memory decay models, causal reasoning, and data provenance tracking. Begin NetBox vertical module ecosystem.

### Key Deliverables

#### Infrastructure
- Regional Nordic cloud integrations (Safespring, Orange Business, Azure Norway East)
- Terraform + Bicep automated provisioning
- Multi-region failover strategy

#### Database Architecture
- **Citus multi-tenant partitioning** with distributed query execution
- **GDPR Cascade Pruning Engine** (vector zero-fills on tenant deletion)
- Shard key strategy: tenant_id hash bucketing
- 5-second completion SLA for tenant purges

#### Cognitive Engines
1. **Status-Weighted Ebbinghaus Forgetting Curves**
   - Formula: $R(t) = e^{-t / S}$
   - Incidents decay in 7 days, config in 30 days, topology in 90 days
   - Confidence scores drive ranking

2. **Causal Inference Layer** (Pearl's do-calculus)
   - Query: "What systems fail if this device goes down?"
   - DAG topology → counterfactual analysis
   - Impact probability calculation

3. **Validation Council Framework**
   - Four validators: source trust, topology consistency, schema compliance, cross-reference
   - Quarantine low-confidence memories
   - Auto-purge after 30 days

4. **Memory Provenance Graph**
   - Track lineage: source → validators → citations
   - Full audit trail per memory
   - "Show source" capability for operators

#### NetBox Vertical Module (Optional)
- Topology Seeder (hourly sync from /api/dcim/)
- Webhook Event Bus (real-time topology updates)
- Entity Resolution Engine (NetBox source-of-truth)
- Three-Dimensional Drift Detection (topology, telemetry, config)
- Journal Semantic Harvester (operator notes → Empathic Tensor)
- Power Topology Graph integration
- Scheduled Consistency Audit Engine (nightly)

### Success Criteria
- ✓ Seamless scaling to **150 concurrent tenants**
- ✓ p95 read latency **< 40ms** under load
- ✓ Nightly consistency audits with **zero false-positive** topology claims
- ✓ GDPR deletion ops complete in **< 5 seconds**

### Estimated Team
- 3–4 senior engineers (database, backend, DevOps)

---

## PHASE 3: Cognitive Agentic Superpowers (150 → 500 Tenants)

**Timeline:** 16–20 weeks | **Target:** Autonomous truth maintenance + counterfactual reasoning

### Overview
Enable agents with advanced autonomous decision-making, predictive analytics, and operator well-being monitoring. Deploy ATMS for automated memory deprecation. Extend NetBox module with rich intelligence features.

### Key Deliverables

#### Advanced Memory Systems
1. **Assumption-Based Truth Maintenance System (ATMS)**
   - Auto-deprecate memories when underlying assumptions are violated
   - Example: "This device is online" invalidates when device goes offline
   - Validate 300+ testing tenants

2. **Counterfactual Chrono-Branching**
   - Query alternative realities: "What if this device had been down at 2 PM?"
   - Branch memory timeline without modifying actual ledger
   - Temporal graph traversal with hypothetical injection

3. **Neuromorphic Spreading Activation**
   - Replace breadth-first walk with spiking neural model
   - Pre-fetch context during high-alert states (severity > 8)
   - Synaptic plasticity: edge weights learn from agent decisions

#### Operator Experience & Burnout Prevention
1. **Longitudinal Operator Stress Tracking**
   - Trend the Empathic Tensor ($\vec{E}$) over time
   - Burnout alerts when frustration > 7.0 for 5+ consecutive shifts
   - Predictive fatigue model

2. **Active Learning Loop**
   - Auto-queue low-confidence memories ($S < 0.65$) for operator micro-confirmation
   - Validate suspect claims before propagation
   - Gamify validation with confidence scoring

3. **Predictive Memory Synthesis**
   - Generate anticipated, probabilistic failure nodes
   - "Alert before the alert" capability
   - Learn from historical patterns + device MTBF

#### NetBox Vertical Module Extensions
- Contacts → Operator Stress Mapping (load-balancing integration)
- Circuit Provider Intelligence (auto-escalation ticket generation)
- GraphQL-Powered Spreading Activation (multi-hop context in single query)
- Predictive MTBF Synthesis (device age + incident history)
- Unregistered Asset Discovery (auto-propose to NetBox)
- **NetBox Cognitive Dashboard Plugin** (PyPI package, live device/rack/site insights)

### Success Criteria
- ✓ ATMS engine deployed, **300 testing tenants** validated
- ✓ Automated memory deprecation working end-to-end
- ✓ NetBox Cognitive Dashboard **adopted by 3+ tenants**
- ✓ Stress tracking prevents **2+ burnout incidents** in 6 months

### Estimated Team
- 4–5 senior engineers (AI/ML, distributed systems, DevOps)

### Key Risks
- ATMS complexity: requires careful assumption modeling
- Operator privacy: stress tracking data must be encrypted at rest
- NetBox plugin adoption: requires strong UX/documentation

---

## PHASE 4: Zero-Knowledge Federated Swarms (500 Tenants)

**Timeline:** 12–16 weeks | **Target:** Cross-tenant learning without PII leakage

### Overview
Deploy differential privacy infrastructure to enable safe cross-tenant learning. Pass rigorous third-party security audits. Reach full-scale federation with 500 enterprise tenants.

### Key Deliverables

#### Differential Privacy & ZK Systems
1. **Zero-Knowledge Collective Telemetry Exchange (ZK-CTE)**
   - Tenants safely pool abstract error signatures
   - Share "Device model X shows pattern Y" without customer names/IPs
   - Implement via homomorphic encryption or secure multi-party computation (MPC)

2. **Differential Privacy Budget ($\epsilon$) Management**
   - Assign privacy budgets to each tenant
   - Track $\epsilon$ consumption per cross-tenant query
   - Refuse queries exceeding remaining budget
   - Implement accounting for cumulative privacy loss

#### Security & Compliance
1. **Third-Party Security Audits**
   - Full pen-testing by accredited firm
   - Regulatory oversight from Norwegian Datatilsynet + EU authorities
   - NIS2 Directive compliance validation

2. **Regulatory Certification**
   - ISO 27001 information security management
   - GDPR Data Processing Agreement (DPA) attestation
   - Norwegian "Normen for informasjonssikkerhet" certification

#### Operations & Monitoring
- Federated monitoring & alerting (cross-tenant anomaly detection)
- Global SLA tracking across 500 tenants
- Automated playbook execution across tenant boundaries

### Success Criteria
- ✓ **Zero PII leakage** validated during auditing
- ✓ **500 active enterprise tenants** seamlessly scaled
- ✓ Cross-tenant anomaly sharing live and functional
- ✓ All regulatory certifications obtained

### Estimated Team
- 3–4 senior engineers (cryptography, security, compliance)

### Key Risks
- Regulatory approval timeline: unpredictable
- Cryptographic performance at scale: requires benchmarking
- Multi-party computation (MPC) complexity: novel in this domain

---

## Cross-Phase Considerations

### Data Integrity & Immutability
- All phases maintain WORM (Write-Once-Read-Many) ledger
- Vector embeddings zero-filled on deletion, never removed
- Audit trail permanently preserved with cryptographic seals

### Tenant Isolation
- **Phase 2:** Citus shard-level isolation + RLS policies
- **Phase 3:** Add operator-level access control + audit logging
- **Phase 4:** Zero-knowledge proofs prevent information leakage

### Performance Targets
- **Phase 1:** Baseline (single-tenant, < 15ms)
- **Phase 2:** p95 < 40ms (150 tenants, distributed)
- **Phase 3:** p95 < 50ms (500 tenants, ATMS overhead)
- **Phase 4:** p95 < 60ms (500 tenants, ZK-CTE overhead)

### Rollback & Rollforward Strategy
- Each phase uses **backwards-compatible migrations**
- Feature flags control new cognitive engines (phase-gated)
- Canary deployments: 10% → 50% → 100% tenant rollout

---

## Resource Allocation Summary

| Phase | Duration | Team Size | Complexity | Budget Est. |
|-------|----------|-----------|-----------|-------------|
| 2 | 12–16w | 3–4 eng | High | $180k–240k |
| 3 | 16–20w | 4–5 eng | Very High | $240k–300k |
| 4 | 12–16w | 3–4 eng | Critical | $200k–280k |
| **Total** | **40–52w** | **10–13 eng** | **—** | **$620k–820k** |

---

## Stakeholder Checkpoints

- **Pre-Phase 2:** Architecture design review, infrastructure cost approval
- **Pre-Phase 3:** ATMS prototype validation, NetBox partner agreement
- **Pre-Phase 4:** Regulatory pre-audit, insurance/liability assessment

---

## Document References

- Detailed Phase 2 execution plan: `_internal/Roadmaps/phase_2_execution_ledger.md`
- Phase 1 completion report: Commit `2a8c789` (merged to main)
- Original roadmap: `Rebranding to NCE and V2-V3 Roadmap 05062026.md`

---

**Next Action:** Schedule Phase 2 kickoff meeting with stakeholders and technical leads.
