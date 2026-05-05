# TriMCP — Implementation Spec
<!-- MACHINE-READABLE SPEC. Prose minimised. All decisions are binding. -->

---

## METADATA

```yaml
project: TriMCP
repo: https://github.com/sindrehaugen/TriMCP
maintainer: sindrehaugen
distribution: free open-source, self-hosted only
primary_deployment_target: Docker Compose, single machine
spec_version: 2.0
last_updated: 2026-05-05
status: APPROVED — ready for implementation
```

---

## DECISIONS INDEX
<!-- All architectural decisions. Reference by ID throughout spec. -->

| ID | Question | Decision |
|---|---|---|
| D1 | Deployment target | Self-hosted Docker Compose only. No hosted offering. Helm chart is community contribution, not core. |
| D2 | Default LLM provider | `local-cognitive-model` (bundled). Cloud providers opt-in per namespace. |
| D3 | LLM credentials | BYO always. `ref:env/TRIMCP_NS_<slug>_<PROVIDER>_KEY` or `ref:vault/...`. No shared platform key. |
| D4 | Agent identity | `agent_id TEXT NOT NULL DEFAULT 'default'` ships Phase 0.1. Free-text, no FK, no agents table in v1. |
| D5 | Temporal retention | Default 90 days. `null` = infinite. Per-namespace via `namespaces.metadata.temporal_retention_days`. |
| D6 | MinIO LLM payload retention | Matches `temporal_retention_days` by default. Independently overridable via `namespaces.metadata.llm_payload_retention_days`. `0` = no caching, re-execute only. |
| D7 | Bundled model distribution | Separate image `ghcr.io/sindrehaugen/trimcp-cognitive:v1`. Auto-detected via health check on `localhost:11435`. Never bundled in main image. |
| D8 | Point-in-time writes | PERMANENTLY OUT OF SCOPE. Hard rejection at ingest boundary. No exceptions at any version. |
| D9 | Assertion types | Field `assertion_type TEXT` on memories. Values: `fact \| opinion \| preference \| observation`. Default inferred by classifier. Contradiction detection fires only on `fact` vs `fact`. |

---

## GLOBAL CONSTRAINTS

```
[CONSTRAINT] Every write path enforces namespace_id + agent_id scoping.
[CONSTRAINT] Every Saga transaction also writes to event_log atomically. No exceptions.
[CONSTRAINT] event_log has no UPDATE or DELETE grants on any runtime role (WORM).
[CONSTRAINT] valid_from is always set to now() on writes. User-supplied past timestamps rejected with error. [D8]
[CONSTRAINT] All canonical JSON serialisation uses JCS (RFC 8785).
[CONSTRAINT] All LLM calls go through LLMProvider interface. No direct SDK calls outside providers/.
[CONSTRAINT] PII redaction runs before embedding on every store_memory call.
[CONSTRAINT] All high-volume tables declared PARTITION BY RANGE (created_at) from Phase 0.1. Never added retroactively.
```

---

## TECH STACK

```yaml
runtime: Python 3.12+
databases:
  postgres: 16+        # memories, KG, temporal, event_log
  mongodb: 7+          # memory payloads, versions
  redis: 7+            # working cache, pub/sub
  minio: latest        # media, LLM response payloads
queue: RQ + rq-scheduler
vector_index: pgvector (HNSW)
signing: HMAC-SHA256 + JCS (RFC 8785)
pii_scanner: Microsoft Presidio
nli_model: cross-encoder/nli-deberta-v3-small
containerisation: Docker Compose (primary), Helm (community)
```

---

## PHASE OVERVIEW

```
Phase 0 — Foundations      Weeks 1–5    [BLOCKER for all other phases]
Phase 1 — Cognitive Layer  Weeks 6–11   [REQUIRES Phase 0 complete]
Phase 2 — Operational      Weeks 12–19  [REQUIRES Phase 1 complete]
Phase 3 — Ecosystem        Weeks 20–22  [PARALLELISABLE with Phase 2]
```

---

## PHASE 0 — FOUNDATIONS

### 0.1 Multi-Tenant Namespacing + Postgres RLS

```
[GOAL] Namespace isolation from schema up. Multiple agents/teams share one instance safely.
[EFFORT] 2 weeks
[BLOCKS] All phases depend on this.
```

#### SCHEMA

```sql
CREATE TABLE namespaces (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug       TEXT UNIQUE NOT NULL,
  parent_id  UUID REFERENCES namespaces(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata   JSONB NOT NULL DEFAULT '{}'::jsonb
  -- metadata keys consumed by later phases:
  -- temporal_retention_days: int | null          [D5]
  -- llm_payload_retention_days: int | null       [D6]
  -- consolidation.enabled: bool
  -- consolidation.llm_provider: string
  -- consolidation.llm_model: string
  -- consolidation.llm_credentials: string
  -- consolidation.llm_temperature: float
  -- consolidation.decay_sources: bool
  -- pii.entity_types: string[]
  -- pii.policy: redact | pseudonymise | reject | flag
  -- pii.reversible: bool
  -- pii.allowlist: string[]
);

-- PARTITIONING: Applied to ALL high-volume tables from day one.
-- Pattern (repeat for kg_nodes, kg_edges, code_chunks, event_log, contradictions):
CREATE TABLE memories (
  id                  UUID        NOT NULL,
  namespace_id        UUID        NOT NULL REFERENCES namespaces(id),
  agent_id            TEXT        NOT NULL DEFAULT 'default',      -- [D4]
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  memory_type         TEXT        NOT NULL DEFAULT 'episodic',     -- episodic | consolidated | decision | code_chunk
  assertion_type      TEXT        NOT NULL DEFAULT 'fact',         -- [D9] fact | opinion | preference | observation
  payload_ref         TEXT        NOT NULL,                        -- MongoDB document ref
  embedding           vector(768),
  embedding_model_id  UUID,
  derived_from        JSONB,                                       -- source memory IDs for consolidated type
  valid_from          TIMESTAMPTZ NOT NULL DEFAULT now(),          -- [D8] never accept user-supplied past value
  valid_to            TIMESTAMPTZ,                                 -- NULL = current row
  signature           BYTEA       NOT NULL,
  signature_key_id    TEXT        NOT NULL,
  pii_redacted        BOOLEAN     NOT NULL DEFAULT false,
  PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE memories_2026_05 PARTITION OF memories
  FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
-- Nightly job creates next month partition automatically.

-- RLS
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
CREATE POLICY memory_tenant_isolation ON memories
  USING (
    namespace_id = current_setting('trimcp.namespace_id')::uuid
    OR namespace_id IN (
      SELECT id FROM namespaces
      WHERE parent_id = current_setting('trimcp.namespace_id')::uuid
    )
  );

-- Indexes
CREATE INDEX idx_memories_current  ON memories USING hnsw (embedding vector_cosine_ops)
  WHERE valid_to IS NULL;                               -- fast path: current-state semantic search
CREATE INDEX idx_memories_temporal ON memories (namespace_id, valid_from, valid_to);
CREATE INDEX idx_memories_agent    ON memories (namespace_id, agent_id, created_at);

-- Salience stored per (memory, agent) pair to avoid fan-out updates
CREATE TABLE memory_salience (
  memory_id       UUID        NOT NULL,
  agent_id        TEXT        NOT NULL,
  namespace_id    UUID        NOT NULL REFERENCES namespaces(id),
  salience_score  REAL        NOT NULL DEFAULT 1.0,
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  access_count    INTEGER     NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (memory_id, agent_id)
) PARTITION BY RANGE (created_at);
```

#### CODE

```
trimcp/auth.py
  resolve_namespace(request_headers) -> UUID
  set_namespace_context(conn, namespace_id)  # SET LOCAL only — never SET
  validate_agent_id(agent_id: str) -> str    # strip whitespace, max 128 chars

trimcp/orchestrator.py
  All write methods signature: (namespace_id: UUID, agent_id: str, ...)
  Redis key pattern:  "{namespace_slug}:{agent_id}:{key}"
  MinIO path pattern: "{namespace_slug}/{agent_id}/{object}"
```

#### MCP TOOLS — CHANGES

```
store_memory(content, ..., namespace_id?, agent_id?)
semantic_search(query, ..., namespace_id?, agent_id?, as_of?)
graph_search(query, ...,    namespace_id?, agent_id?, as_of?)
get_recent_context(...,     namespace_id?, agent_id?, as_of?)

[ADMIN ONLY]
manage_namespace(command, ...)
  command: create | list | grant | revoke | update_metadata
```

#### ACCEPTANCE CRITERIA

```
[TEST-0.1-01] Two sessions with different namespace_ids cannot read each other via any MCP tool.
[TEST-0.1-02] Parent namespace reads child namespace memories.
[TEST-0.1-03] Connection pool reuse with stale namespace → empty results (SET LOCAL prevents leak).
[TEST-0.1-04] agent_id filter on semantic_search returns only that agent's memories.
[TEST-0.1-05] Omitting agent_id on store_memory stores with agent_id='default'.
[TEST-0.1-06] Nightly job creates next month's partition before month begins.
[TEST-0.1-07] Direct SQL with no session variable set → zero rows returned (RLS, not error).
```

---

### 0.2 Cryptographic Memory Signing

```
[GOAL] HMAC-sign every stored memory. Any retrieval can verify integrity.
[EFFORT] 1 week
[REQUIRES] 0.1 complete
```

#### SCHEMA

```sql
CREATE TABLE signing_keys (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key_id        TEXT UNIQUE NOT NULL,
  encrypted_key BYTEA NOT NULL,     -- AES-256 encrypted at rest
  status        TEXT NOT NULL,      -- active | retired
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  retired_at    TIMESTAMPTZ
);
-- memories.signature + memories.signature_key_id already declared in 0.1.
```

#### SIGNING CONTRACT

```
signature_input = JCS({                    -- JCS = RFC 8785, mandatory
  "namespace_id":   "<uuid>",
  "agent_id":       "<string>",
  "payload_ref":    "<mongo_ref_id>",
  "created_at":     "<ISO8601>",
  "assertion_type": "<string>"
})
signature = HMAC-SHA256(active_signing_key, signature_input)

[CONSTRAINT] Retired keys retained indefinitely. Required for historical verify_memory calls.
[CONSTRAINT] Master key = env var TRIMCP_MASTER_KEY (dev) or KMS (prod). Never stored in DB.
[CONSTRAINT] Server refuses to start if TRIMCP_MASTER_KEY is missing or empty.
```

#### CODE

```
trimcp/signing.py
  sign(namespace_id, agent_id, payload_ref, created_at, assertion_type) -> (bytes, key_id)
  verify(memory_id, as_of?) -> VerifyResult(valid, reason, signed_at, key_id, payload_hash)
  rotate_key() -> new_key_id
```

#### MCP TOOLS — NEW

```
verify_memory(memory_id, as_of?)
  returns: { valid: bool, reason: str, signed_at: datetime, key_id: str, payload_hash: str }
```

#### ACCEPTANCE CRITERIA

```
[TEST-0.2-01] store → retrieve → verify = valid.
[TEST-0.2-02] MongoDB payload tampered post-store → verify returns valid=false, reason="payload_modified".
[TEST-0.2-03] Post key rotation: old memories verify with retired key, new memories with active key.
[TEST-0.2-04] Missing TRIMCP_MASTER_KEY at startup → server exits with clear error.
[TEST-0.2-05] verify_memory(as_of=T) verifies the version of the memory active at time T.
```

---

### 0.3 PII Detection and Auto-Redaction

```
[GOAL] Detect and redact PII before embedding. Configurable per-namespace policy.
[EFFORT] 2 weeks
[REQUIRES] 0.1 complete
[POSITION IN PIPELINE] after text ingestion → before embedding → before MongoDB write
```

#### PIPELINE

```
incoming_text
  → pii_scan(text, namespace_id)         # Presidio NER
  → policy_decision(entities, namespace) # from namespaces.metadata.pii
  → transform(text, entities, policy)    # redact | pseudonymise | reject | flag
  → [embed + store]
```

#### SCHEMA

```sql
CREATE TABLE pii_redactions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  namespace_id    UUID NOT NULL REFERENCES namespaces(id),
  memory_id       UUID NOT NULL,
  token           TEXT  NOT NULL,      -- e.g. <PERSON_a3f2>
  encrypted_value BYTEA NOT NULL,      -- only written if policy=pseudonymise + reversible=true
  entity_type     TEXT  NOT NULL,      -- PERSON | EMAIL | PHONE | ADDRESS | ID | CUSTOM
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
) PARTITION BY RANGE (created_at);
```

#### CODE

```
trimcp/pii.py
  scan(text, namespace_id) -> list[PIIEntity(start, end, type, score)]
  process(text, namespace_id) -> ProcessResult(text, redacted: bool, entities_found: list[str])
  infer_assertion_type(text) -> str   # rule-based classifier for [D9]
```

#### MCP TOOLS — NEW

```
[ADMIN + ELEVATED PERMISSION ONLY]
unredact_memory(memory_id)
  - Requires namespace pii.reversible=true
  - Requires per-agent elevated permission flag (separate from namespace membership)
  - Every call written to event_log with event_type="unredact"
```

#### ACCEPTANCE CRITERIA

```
[TEST-0.3-01] Email in memory content is redacted before embedding. pgvector stores no original email.
[TEST-0.3-02] policy=reject → store_memory returns error with entity types (not values). Nothing stored.
[TEST-0.3-03] policy=pseudonymise + reversible=true → unredact_memory returns original value.
[TEST-0.3-04] Unauthorised agent calling unredact_memory → permission error.
[TEST-0.3-05] Allowlist regex suppresses Presidio false positive (e.g. git SHA not flagged as ID).
[TEST-0.3-06] Multi-word name detected as single PERSON entity, not individual tokens.
[TEST-0.3-07] PII redacted in all time-travel views. No temporal query path returns unredacted values.
```

---

## PHASE 1 — COGNITIVE LAYER

### 1.1 Ebbinghaus Memory Decay + Salience Scoring

```
[GOAL] Memories fade over time, strengthen on retrieval. Retrieval ranking reflects this.
[EFFORT] 1.5 weeks
[REQUIRES] Phase 0 complete
```

#### MODEL

```
Decay (lazy — computed at retrieval time, not via batch job):
  λ = ln(2) / half_life_days     # half_life default: 30 days, per-namespace config
  s(t) = s_last × exp(−λ × Δt_days)

Reinforcement (on every retrieval):
  s_new = min(1.0, s_current + reinforcement_delta)   # default delta: 0.05

Ranking:
  final_score = cosine_similarity × (α + (1 − α) × salience_score)
  # α default: 0.7. Per-namespace configurable.
  # Salience is tie-breaker, not override: high cosine can still win over high salience.

Per-agent salience: stored in memory_salience table (declared in 0.1).
  Retrieval uses per-agent score if row exists, else global memories.salience_score.
```

#### CODE

```
trimcp/salience.py
  compute_decayed_score(s_last, updated_at, half_life_days) -> float
  reinforce(memory_id, agent_id, namespace_id)               # write-back on retrieval
  ranking_score(cosine_sim, salience, alpha) -> float
```

#### MCP TOOLS — NEW

```
boost_memory(memory_id, factor=0.2)
  - Adds factor to salience for calling agent. Capped at 1.0.

forget_memory(memory_id)
  - Sets salience=0.0 for calling agent.
  - Memory remains in store. Invisible in semantic_search for that agent.
  - Does NOT set valid_to (not a logical delete).
```

#### ACCEPTANCE CRITERIA

```
[TEST-1.1-01] Salience after N half-lives = 0.5^N ± float tolerance.
[TEST-1.1-02] Retrieving same memory 10× raises salience monotonically.
[TEST-1.1-03] High-salience low-similarity memory ranks above low-salience high-similarity at α=0.7.
[TEST-1.1-04] forget_memory: semantic_search returns zero results for that agent. ID lookup still works.
[TEST-1.1-05] boost_memory: salience cannot exceed 1.0.
[TEST-1.1-06] Agent A boost does not change Agent B's ranking of same memory.
```

---

### 1.2 Sleep Consolidation Engine

```
[GOAL] Nightly LLM job synthesises clusters of related episodic memories into semantic abstractions.
[EFFORT] 3 weeks pipeline + 2–3 weeks bundled model (parallel track)
[REQUIRES] Phase 0 complete, 1.1 complete
[DEFAULT LLM] local-cognitive-model [D2]
```

#### PIPELINE

```
Step 1 — CLUSTER
  Select:  memories since last run with salience_score >= 0.3
  Cluster: HDBSCAN on embeddings, ε per-namespace configurable
  Filter:  min_cluster_size >= 5, mean_salience >= 0.3

Step 2 — SYNTHESISE (per cluster)
  Call:     LLMProvider.complete(messages, schema)
  Validate: confidence >= 0.3
            all supporting_memory_ids exist in input cluster (reject hallucinated IDs)
            valid JSON matching schema
  Route:    if contradicting_memory_ids present → Phase 1.3 pipeline, do NOT store

Step 3 — STORE
  memory_type:    consolidated
  assertion_type: fact
  derived_from:   [source_ids]
  salience:       0.9 (initial)
  KG:             inject entities + relations, edge_type=derived_from, weight=confidence

Step 4 — DECAY SOURCES (if consolidation.decay_sources=true in namespace metadata)
  s_source_new = s_source × 0.85
```

#### LLM PROVIDER INTERFACE

```python
class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, messages: list[Message], schema: dict) -> dict:
        # Returns structured JSON matching schema.
        # Raises LLMProviderError on failure.
        pass

    @abstractmethod
    def model_identifier(self) -> str:
        # Returns "provider/model" string for event_log.
        pass
```

#### SUPPORTED PROVIDERS

```yaml
anthropic:
  models: [claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5]
  structured_output: native JSON schema

openai:
  models: [gpt-5, gpt-4.5-turbo]
  structured_output: native JSON schema

azure_openai:
  models: [gpt-5, gpt-4.5-turbo]
  auth: azure_ad | api_key
  structured_output: native JSON schema

google_gemini:
  models: [gemini-2.0-pro, gemini-2.0-flash]
  structured_output: schema-in-prompt + parsing

deepseek:
  models: [deepseek-v4]
  api: OpenAI-compatible endpoint
  note: preferred for cost-sensitive deployments

moonshot_kimi:
  models: [kimi-2.6]
  note: preferred for large clusters (extended context)

local_cognitive_model:                              # [D2] DEFAULT
  image: ghcr.io/sindrehaugen/trimcp-cognitive:v1  # [D7]
  endpoint: http://localhost:11435/v1
  detection: GET localhost:11435/health at startup
  fallback: if not detected, log warning, skip run

openai_compatible:
  endpoint: custom per namespace
  covers: Ollama, vLLM, LM Studio, any custom deployment
```

#### LLM PAYLOAD CACHING

```
On every LLM call:
  payload     = JCS({ "prompt": messages, "response": llm_response })
  hash        = sha256(payload)
  MinIO key   = "llm-payloads/{namespace_id}/{hash}.json"
  event_log fields: llm_payload_uri, llm_payload_hash

Retention: [D6] matches temporal_retention_days by default.
0 = disable caching (re-execute mode only).
```

#### CONSOLIDATION PROMPT

```
SYSTEM:
You are a memory consolidation engine. Given N related episodic memories,
produce ONE durable semantic abstraction capturing their shared meaning.
Return ONLY valid JSON matching the schema. No preamble. No markdown.

USER:
Memories: {memory_cluster_json}

Return JSON:
{
  "abstraction": "<single factual paragraph, no speculation>",
  "key_entities": ["<entity>"],
  "key_relations": [{"subject":"","predicate":"","object":""}],
  "supporting_memory_ids": ["<IDs from input only — hallucinated IDs cause rejection>"],
  "contradicting_memory_ids": ["<if any inputs conflict>"],
  "confidence": <float 0.0–1.0>
}
If inputs are too disparate, return confidence < 0.3.
```

#### SCHEMA

```sql
CREATE TABLE consolidation_runs (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  namespace_id      UUID NOT NULL REFERENCES namespaces(id),
  agent_id          TEXT NOT NULL DEFAULT 'system',
  started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at       TIMESTAMPTZ,
  status            TEXT NOT NULL,   -- running | success | failed
  clusters_found    INTEGER,
  clusters_accepted INTEGER,
  clusters_rejected INTEGER,
  memories_synth    INTEGER,
  llm_provider      TEXT NOT NULL,
  llm_model         TEXT NOT NULL,
  llm_tokens_used   INTEGER,
  error             TEXT
) PARTITION BY RANGE (started_at);
```

#### BUNDLED LOCAL MODEL

```yaml
base_model: Qwen-3-14B-Instruct (preferred) or Llama-4-13B-Instruct
quantisation: 4-bit GPTQ
size_on_disk: ~8GB
ram_required: ~10GB
inference: 10–20 tokens/sec CPU
fine_tuning: LoRA / QLoRA
training_data:
  consolidation: 50000 examples (frontier-model labelled)
  contradiction:  100000 pairs (SNLI + MultiNLI + ANLI + synthetics)
quality_benchmarks:
  consolidation_vs_gpt5: ~85% human eval
  contradiction_f1: ~0.89
distribution: separate Docker image [D7]
```

#### MCP TOOLS — NEW

```
[ADMIN ONLY]
trigger_consolidation(namespace_id, since_timestamp?)
consolidation_status(run_id)
```

#### ACCEPTANCE CRITERIA

```
[TEST-1.2-01] 2-topic memory batch → exactly 2 clusters detected.
[TEST-1.2-02] Valid LLM response → stored as memory_type=consolidated.
[TEST-1.2-03] supporting_memory_id not in input → run rejected, nothing stored.
[TEST-1.2-04] contradicting_memory_ids present → routed to contradiction pipeline, no consolidated memory stored.
[TEST-1.2-05] confidence < 0.3 → discarded, nothing stored.
[TEST-1.2-06] decay_sources=true → source memory salience reduced after consolidation.
[TEST-1.2-07] Consolidated memory retrievable by semantic_search on cluster topic.
[TEST-1.2-08] LLM payload written to MinIO. Hash matches event_log.llm_payload_hash.
[TEST-1.2-09] All 7 providers pass smoke test on consolidation fixture.
[TEST-1.2-10] Provider unavailable + no local model → warning logged, run skipped, no crash.
```

---

### 1.3 Contradiction Detection

```
[GOAL] Surface factual conflicts between memories. Background sweep by default.
[EFFORT] 2.5 weeks
[REQUIRES] Phase 0 complete
[DEFAULT MODE] async background sweep
[SCOPE — D9] Only fact vs fact. opinion, preference, observation never flagged.
```

#### DETECTION PIPELINE

```
Step 1 — CANDIDATE SELECTION
  Fetch top-K memories by cosine similarity >= τ (default τ=0.85)
  Filter: candidate.assertion_type='fact' AND incoming.assertion_type='fact'  [D9]
  Exit if zero candidates.

Step 2 — KG CHECK (fast, deterministic, always runs)
  Extract KG triples from incoming memory.
  Check: same (subject, predicate) with different object in existing KG.
  Hit → contradiction_signal { source:"kg", confidence:0.95 }

Step 3 — NLI CHECK (per candidate, top-3 only)
  Model: cross-encoder/nli-deberta-v3-small
  Hit (score >= 0.8) → contradiction_signal { source:"nli", confidence:nli_score }

Step 4 — LLM TIEBREAKER (conditional)
  Trigger: KG and NLI disagree, OR either confidence 0.7–0.85
  Uses: LLMProvider (same multi-provider config as 1.2)
  Cap: 5 LLM calls per sweep (cost control)

Step 5 — RECORD + NOTIFY
  Insert contradictions row.
  Fire SSE event to namespace subscribers.
  If check_contradictions=true on store_memory: include in response payload.
```

#### ASSERTION TYPE INFERENCE (for [D9])

```
Rule-based classifier (no LLM). Applied when assertion_type not provided by caller.
  Contains "I think|I believe|in my opinion"    → opinion
  Contains "I prefer|I like|I want"             → preference
  Past-tense + hedging language                 → observation
  Default                                       → fact
```

#### SCHEMA

```sql
CREATE TABLE contradictions (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  namespace_id   UUID NOT NULL REFERENCES namespaces(id),
  memory_a_id    UUID NOT NULL,
  memory_b_id    UUID NOT NULL,
  agent_id       TEXT NOT NULL DEFAULT 'system',
  detected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  detection_path TEXT NOT NULL,   -- sync | async
  signals        JSONB NOT NULL,  -- [{source, confidence}]
  confidence     REAL NOT NULL,
  resolution     TEXT,            -- unresolved | resolved_a | resolved_b | both_valid
  resolved_at    TIMESTAMPTZ,
  resolved_by    TEXT
) PARTITION BY RANGE (detected_at);
```

#### MCP TOOLS — CHANGES + NEW

```
store_memory(..., check_contradictions: bool = false)
  false (default): async detection, zero latency impact
  true:            sync detection, result in response, debug/test use only

list_contradictions(filter?, resolution?, agent_id?)

resolve_contradiction(id, resolution, note?)
  resolution values: resolved_a | resolved_b | both_valid
```

#### ACCEPTANCE CRITERIA

```
[TEST-1.3-01] Two fact memories with different employers for same person → contradiction detected.
[TEST-1.3-02] Two opinion memories with opposite views → NOT flagged. [D9]
[TEST-1.3-03] Two agreeing fact memories → NOT flagged (false positive guard).
[TEST-1.3-04] check_contradictions=false → store_memory p99 unchanged vs baseline.
[TEST-1.3-05] check_contradictions=true → contradiction in store_memory response.
[TEST-1.3-06] Resolved contradiction not re-flagged on subsequent sweeps.
[TEST-1.3-07] Assertion type classifier correctly infers type for standard test inputs.
[TEST-1.3-08] LLM tiebreaker capped at 5 per sweep regardless of volume.
```

---

## PHASE 2 — OPERATIONAL MATURITY

### 2.1 Automated Re-Embedding Migration

```
[GOAL] Upgrade embedding models without downtime. Atomic swap after quality gate.
[EFFORT] 2–3 weeks
[REQUIRES] Phase 0 complete
```

#### STRATEGIES

```
Strategy A — dimension-compatible:
  1. ADD COLUMN embedding_v2 vector(N)
  2. Background job fills embedding_v2
  3. Quality gate: sample queries, check result overlap >= 70%
  4. Gate pass → rename columns atomically, rebuild HNSW index

Strategy B — dimension-incompatible:
  1. Create shadow table memories_v2 with new dimension
  2. Background job backfills memories_v2
  3. Validation period: queries union both tables, rank by normalised score
  4. Gate pass → swap primary reference
  5. Old table retained 30 days then dropped
```

#### SCHEMA

```sql
CREATE TABLE embedding_models (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name       TEXT UNIQUE NOT NULL,
  dimension  INTEGER NOT NULL,
  status     TEXT NOT NULL,   -- active | retiring | retired
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  retired_at TIMESTAMPTZ
);
-- memories.embedding_model_id references this table (declared in 0.1).
```

#### MCP TOOLS — NEW (ADMIN ONLY)

```
start_migration(target_model_id)
migration_status(migration_id)
validate_migration(migration_id)
commit_migration(migration_id)
abort_migration(migration_id)
```

#### ACCEPTANCE CRITERIA

```
[TEST-2.1-01] Re-embedded vectors match fresh embed of same text within cosine 0.01.
[TEST-2.1-02] Quality gate blocks swap when overlap < 70%.
[TEST-2.1-03] store_memory during migration writes to both indexes consistently.
[TEST-2.1-04] Abort migration leaves system in original state, no partial index.
```

---

### 2.2 Memory Time Travel

```
[GOAL] Query memory state as-of any past timestamp.
[EFFORT] 2.5 weeks
[REQUIRES] Phase 0 complete (temporal columns already in schema from 0.1)
[CONSTRAINT — D8] READ-ONLY. Past writes hard-rejected.
```

#### TEMPORAL QUERY MODEL

```
Current state (default, fast):
  WHERE valid_to IS NULL
  Index: idx_memories_current (partial HNSW)

Historical as-of (degraded mode):
  WHERE valid_from <= :as_of AND (valid_to IS NULL OR valid_to > :as_of)
  Index: idx_memories_temporal (b-tree)
  Method: HNSW over-fetch (N×3) then post-filter to as_of active rows
  Response flags: historical_query=true
                  recall_warning=true if post-filter discarded > 50% of candidates
  [ACCEPTED TRADE-OFF] Historical semantic search is slower. Documented, not hidden.
```

#### SCHEMA

```sql
-- Temporal columns (valid_from, valid_to) already in memories, kg_nodes, kg_edges from 0.1.

CREATE TABLE snapshots (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  namespace_id UUID NOT NULL REFERENCES namespaces(id),
  agent_id     TEXT NOT NULL,
  name         TEXT,
  snapshot_at  TIMESTAMPTZ NOT NULL,    -- reference timestamp (not a data copy)
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata     JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- MongoDB: memory_versions collection
-- Fields: memory_id, namespace_id, agent_id, payload, superseded_at
-- Written by change stream on memory_payloads updates.
```

#### CODE

```
trimcp/temporal.py
  as_of_query(base_query, as_of: datetime) -> modified_query
  validate_write_timestamp(ts: datetime)   # hard-rejects past values [D8]
```

#### MCP TOOLS — CHANGES + NEW

```
-- Changes: add optional as_of param
semantic_search(..., as_of?: TIMESTAMPTZ)
graph_search(...,    as_of?: TIMESTAMPTZ)
get_recent_context(..., as_of?: TIMESTAMPTZ)
verify_memory(memory_id, as_of?: TIMESTAMPTZ)

-- New
create_snapshot(name?)
list_snapshots(filter?)
compare_states(as_of_a, as_of_b, query)
  returns: { added: [], removed: [], modified: [] }
```

#### ACCEPTANCE CRITERIA

```
[TEST-2.2-01] Store memory → update → query as_of before update → original version returned.
[TEST-2.2-02] Query as_of after update → updated version returned.
[TEST-2.2-03] Snapshot → 100 mutations → query at snapshot_at → state matches pre-mutation snapshot.
[TEST-2.2-04] verify_memory(as_of=T) → signature valid for version active at T.
[TEST-2.2-05] PII redacted in ALL historical views. No temporal path returns unredacted values.
[TEST-2.2-06] Historical query returns recall_warning=true when > 50% candidates filtered.
[TEST-2.2-07] User-supplied valid_from in past → hard error (not warning). [D8]
[TEST-2.2-08] Current-state semantic search p99 unaffected by temporal columns.
[TEST-2.2-09] compare_states returns correct diff for known mutations between two timestamps.
```

---

### 2.3 Memory Replay

```
[GOAL] Event-sourced replay for debug, audit, disaster recovery, and forked experimentation.
[EFFORT] 3 weeks
[REQUIRES] Phase 0 complete, Phase 2.2 complete
```

#### REPLAY MODES

```
observational:   stream events for inspection. Engine state untouched.
reconstructive:  apply events to empty target namespace. State at end_seq reproduced.
forked:          replay to fork_seq, diverge with new ops or config_overrides.
                 Forked namespace is a sandbox. No state leaks back to source.
```

#### COGNITIVE DRIFT

```
replay_mode: "deterministic"
  Fetch cached LLM response from MinIO via event_log.llm_payload_uri.
  Reconstruction is byte-identical to original run.
  Use for: disaster recovery, audit reconstruction.

replay_mode: "re-execute"
  Call LLM fresh with original prompt (or modified prompt via config_overrides).
  State diverges — this is intentional.
  Use for: A/B testing consolidation prompts, testing new models, parameter experiments.

[DEFINITION] Cognitive drift = divergence between deterministic and re-execute replay of same event.
             Drift is a feature in re-execute mode, not a bug.
```

#### SCHEMA

```sql
CREATE TABLE event_log (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  namespace_id     UUID NOT NULL REFERENCES namespaces(id),
  agent_id         TEXT NOT NULL,
  event_type       TEXT NOT NULL,
  -- event_type values:
  -- store_memory | forget_memory | boost_memory | resolve_contradiction
  -- consolidation_run | pii_redaction | snapshot_created | unredact
  event_seq        BIGINT NOT NULL,
  occurred_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  params           JSONB NOT NULL,
  result_summary   JSONB,
  parent_event_id  UUID REFERENCES event_log(id),
  llm_payload_uri  TEXT,            -- MinIO ref for LLM-driven events
  llm_payload_hash BYTEA,           -- sha256 of JCS({prompt, response})
  signature        BYTEA NOT NULL,
  signature_key_id TEXT NOT NULL,
  UNIQUE (namespace_id, event_seq)
) PARTITION BY RANGE (occurred_at);

-- WORM enforcement (applied at migration time, never changed):
REVOKE ALL ON event_log FROM PUBLIC;
GRANT INSERT, SELECT ON event_log TO trimcp_app;
-- UPDATE and DELETE not granted to trimcp_app or any runtime role.
-- Retention enforced by partition DROP via migration role only.

CREATE INDEX idx_event_log_ns_time ON event_log (namespace_id, occurred_at);
CREATE INDEX idx_event_log_ns_seq  ON event_log (namespace_id, event_seq);
CREATE INDEX idx_event_log_parent  ON event_log (parent_event_id)
  WHERE parent_event_id IS NOT NULL;

CREATE TABLE replay_runs (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_namespace_id  UUID NOT NULL REFERENCES namespaces(id),
  target_namespace_id  UUID REFERENCES namespaces(id),
  mode                 TEXT NOT NULL,          -- observational | reconstructive | forked
  replay_mode          TEXT NOT NULL DEFAULT 'deterministic',  -- deterministic | re-execute
  start_seq            BIGINT NOT NULL,
  end_seq              BIGINT,
  divergence_seq       BIGINT,
  config_overrides     JSONB,
  status               TEXT NOT NULL,          -- running | success | failed | aborted
  events_applied       BIGINT NOT NULL DEFAULT 0,
  started_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at          TIMESTAMPTZ,
  error                TEXT
) PARTITION BY RANGE (started_at);
```

#### CODE

```
trimcp/replay.py
  ReplayHandler registry: one handler per event_type.
  Adding new event_type requires adding matching handler. Enforced by registry pattern.
  deterministic_replay(event): fetch MinIO payload, use cached response.
  re_execute_replay(event, config_overrides?): call LLM fresh.

[CONSTRAINT] Every event_log write is inside the same Saga transaction as its mutation.
             Rolled-back mutations produce no event_log entry.
[CONSTRAINT] Replay handlers are idempotent. Aborted replays resume from last committed event_seq.
```

#### RETENTION — [D5] [D6]

```
event_log rows:      90 days default. null = infinite. [D5]
MinIO LLM payloads:  matches temporal_retention_days. 0 = no caching. [D6]
Partition drop:      nightly job, migration role only (WORM-safe).
```

#### MCP TOOLS — NEW (ADMIN + ELEVATED PERMISSION)

```
replay_observe(namespace_id, start_seq, end_seq?, filter?)   → SSE stream
replay_reconstruct(source_namespace_id, target_namespace_id, end_seq)
replay_fork(source_namespace_id, target_namespace_id, fork_seq, config_overrides?, replay_mode?)
replay_status(replay_run_id)
get_event_provenance(memory_id)
  → causal tree: memory → creating event → parent events → source memories
```

#### ACCEPTANCE CRITERIA

```
[TEST-2.3-01] Replay same event log twice into two empty namespaces → states byte-identical.
[TEST-2.3-02] Abort at event N, re-run from N → no duplicate effects (idempotency).
[TEST-2.3-03] Fork: mutations in fork do not appear in source namespace.
[TEST-2.3-04] get_event_provenance on consolidated memory returns full causal chain to source events.
[TEST-2.3-05] trimcp_app role: UPDATE/DELETE on event_log → permission denied.
[TEST-2.3-06] N mutations → event_log has exactly N entries, no sequence gaps, all signatures valid.
[TEST-2.3-07] re-execute mode with different prompt → state diverges from deterministic replay of same events.
[TEST-2.3-08] event_log.llm_payload_hash = sha256 of MinIO object content.
```

---

## PHASE 3 — ECOSYSTEM

### 3.1 A2A Protocol Surface

```
[GOAL] Expose TriMCP as an A2A-compatible agent service alongside MCP.
[EFFORT] 3 weeks
[REQUIRES] Phase 0 complete
[PARALLELISABLE] Can run alongside Phase 2
```

#### ARCHITECTURE

```
New server: trimcp/a2a_server.py  (parallel to sse_server.py)
Routes to same TriStackEngine. No engine changes required.
Auth: A2A bearer tokens → namespace_id (same resolution as MCP).
```

#### ENDPOINTS

```
GET  /.well-known/agent-card
POST /tasks/send
GET  /tasks/{task_id}
POST /tasks/{task_id}/cancel
GET  /tasks/{task_id}/stream       # SSE for long-running tasks
```

#### A2A SKILLS MAP

```
A2A skill name                 → MCP tool
recall_relevant_context        → semantic_search + graph_search
archive_session                → store_memory (batch)
find_related_decisions         → graph_search (memory_type=decision filter)
verify_memory_integrity        → verify_memory
get_cognitive_state            → get_recent_context
```

#### ACCEPTANCE CRITERIA

```
[TEST-3.1-01] Agent card at /.well-known/agent-card is valid A2A spec JSON.
[TEST-3.1-02] Task via A2A produces same engine state as equivalent MCP tool call.
[TEST-3.1-03] Invalid bearer token rejected at same boundary as MCP auth.
[TEST-3.1-04] Long-running task streams progress via SSE.
[TEST-3.1-05] A2A reference client smoke test passes.
```

---

## OBSERVABILITY

```
[REQUIRED] All phases. Exposed on /metrics (Prometheus).

Metrics:
  trimcp_ingest_total{namespace, agent, status}
  trimcp_salience_p50_p99{namespace}
  trimcp_consolidation_runs_total{namespace, status, provider, model}
  trimcp_consolidation_tokens{namespace, provider}
  trimcp_contradiction_total{namespace, detection_path, resolution}
  trimcp_signature_verify_total{namespace, result}
  trimcp_pii_redactions_total{namespace, entity_type}
  trimcp_migration_progress{migration_id, strategy}
  trimcp_event_log_rows{namespace}
  trimcp_temporal_storage_bytes{namespace}

Tracing (OpenTelemetry):
  Trace context through every Saga write.
  Spans: ingest → pii_scan → embed → mongo_write → pg_write → redis_set → event_log_write
```

---

## DOCUMENTATION

```
docs/multi_tenancy.md        namespace model, RLS, grants, agent_id
docs/signing.md              JCS spec, key rotation, verify_memory
docs/pii.md                  entity types, policies, reversibility, allowlists
docs/cognitive_layer.md      decay model, consolidation pipeline, contradiction detection
docs/llm_providers.md        all 7 providers, config schema, benchmarks, credential patterns
docs/airgapped_deployment.md bundled cognitive model, offline embedding, local-only config
docs/time_travel.md          as-of queries, snapshots, compare_states, pgvector trade-offs
docs/replay.md               event sourcing, 3 modes, cognitive drift, retention config
docs/a2a.md                  agent card, skills map, auth
docs/migrations.md           re-embedding runbook, partition management
README.md                    architecture diagram, 5-min quickstart, provider config table
```

---

## TIMELINE

```
Week  1–2:   Phase 0.1   Multi-tenant + RLS + agent_id + partitioning
Week  3:     Phase 0.2   Cryptographic signing (JCS)
Week  4–5:   Phase 0.3   PII redaction pipeline
Week  6:     Phase 1.1   Ebbinghaus decay + salience
Week  7–9:   Phase 1.2   Sleep consolidation + LLM provider interface
             [PARALLEL]  Bundled model fine-tuning (separate ML track)
Week 10–11:  Phase 1.3   Contradiction detection
Week 12–13:  Phase 2.1   Re-embedding migration
Week 14–16:  Phase 2.2   Memory time travel
Week 17–19:  Phase 2.3   Memory replay + event log
Week 20–22:  Phase 3.1   A2A protocol
```

---

## WHAT THIS DELIVERS

```
TriMCP v1.0 is the only free open-source memory engine for AI agents that:

1. COGNITIVE       Memories decay, consolidate, and strengthen over time.
                   Active knowledge management, not passive storage.

2. VERIFIABLE      Every memory HMAC-signed. Append-only tamper-resistant event log.
                   Full causal provenance traceable to root events.

3. TEMPORAL        Any past state queryable as-of any moment.
                   Full replay: observational, reconstructive, forked.
                   Cognitive drift (forked + re-execute) = safe prompt A/B testing on real data.

4. HONEST          Contradictions in the knowledge graph detected and surfaced proactively.
                   System tells agents when their worldview is inconsistent.

5. INTEROPERABLE   MCP + A2A. Works with any agent framework.

6. LOCAL-FIRST     Full cognitive features with zero external dependencies.
                   Bundled fine-tuned model. No API keys required.
```
