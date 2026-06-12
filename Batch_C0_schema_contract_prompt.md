# Batch C0 — Schema & API Contract Freeze (ships to main, pushed)

> **This is NOT a normal gitignored ledger batch.** Its OUTPUT (migration + schema.sql + models + read endpoints) is tracked product code that is committed and **pushed to `main`** so a front-end developer can build against a stable contract. It is a prerequisite for muscles Batches 106/107/110/113/120/121/128/129 — those batches will assume this schema already exists and will add NO migrations of their own.
> **Larger than a normal batch by design:** it is a pure contract freeze (additive DDL + read-only types + read-only endpoints). It introduces ZERO behavior — no writes, no mutations, no business logic. Everything it adds is either additive schema or read-only shape. If you find yourself writing logic that *changes* state, STOP — that belongs in the numbered behavior batch.

1. **One branch = one PR.** Branch `schema/muscles-contract-v1`. Target `main`.
2. **Verify before you act.** Open `nce/schema.sql` and confirm the cited tables/columns exist as described and that the new ones do NOT already exist. Next free migration is `022` — confirm before writing. If anything differs, **STOP and report**.
3. **Additive only.** Every change must be backward-compatible: new nullable columns or columns with defaults, new tables, new read-only endpoints. NO column drops, type changes, renames, or NOT-NULL-without-default on existing tables. A fresh `schema.sql` build and an in-place migration on a populated DB must both succeed.
4. **Match the established idiom.** Reuse the migration pattern from `nce/migrations/021_embedding_aspects.sql`: `CREATE TABLE IF NOT EXISTS` (+ hash partitions where the sibling tables are partitioned), indexes, `ENABLE`+`FORCE ROW LEVEL SECURITY`, `DROP POLICY IF EXISTS`/`CREATE POLICY tenant_isolation_policy ... USING/WITH CHECK (namespace_id = get_nce_namespace())`, grants in a `DO $$ ... pg_roles ... nce_app` block. Mirror EVERY DDL change into `nce/schema.sql` too (migration + schema.sql must agree).
5. **Acceptance gate (all must pass before PR):**
   - `make lint` clean
   - `make typecheck` clean
   - migration applies cleanly on a fresh DB AND on a DB already at `021` (test both)
   - new read endpoints return correctly-shaped empty results (`[]`) against empty tables
   - existing full suite still green
6. **Migrations:** add ONE migration `nce/migrations/022_muscles_schema_contract.sql` containing all DDL below.
7. **WORM/RLS invariants (never violate):** every new tenant table gets `ENABLE`+`FORCE RLS` + the standard `tenant_isolation_policy` + `nce_app` grants, AND is added to the bulk tenant-table RLS loop list in `schema.sql` (~`:1215`) so fresh builds cover it. `event_parents` is append-only — give it the same WORM trigger/REVOKE treatment as `event_log` (no UPDATE/DELETE). No FK from `origin_event_id` to the partitioned `event_log` (store the UUID only).
8. **Secrets:** `NCE_MASTER_KEY` env-only.
9. **Tests:** migration-idempotency + endpoint-shape tests; DB-dependent ones are `@pytest.mark.integration`.
10. **Report format:** files changed, both migration-apply results, endpoint shapes, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `database-architect` (primary), `backend-architect`, `api-documentation`
**Depends on:** none (this is the prerequisite for the muscles sequence)

**Files:**
- `nce/migrations/022_muscles_schema_contract.sql` (new — all DDL)
- `nce/schema.sql` (mirror every DDL change; add new tenant tables to the RLS loop list)
- `nce/models.py` (read-only DTOs + enums)
- `nce/admin_routes.py` + `nce/admin_handlers/` (read-only GET endpoints)
- `tests/test_schema_contract.py` (new), `tests/test_contract_endpoints.py` (new)

---

### Part A — Additive DDL (migration 022 + schema.sql mirror)

**A1. Provenance columns (Batch 106 substrate) — on `memories`, `kg_nodes`, `kg_edges`:**
```sql
ALTER TABLE <t> ADD COLUMN IF NOT EXISTS change_origin TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE <t> ADD CONSTRAINT <t>_change_origin_chk CHECK (change_origin IN
  ('sync','webhook','agent','operator','consolidation','replay','unknown')) NOT VALID;  -- VALIDATE separately if large
ALTER TABLE <t> ADD COLUMN IF NOT EXISTS origin_event_id UUID;  -- no FK (event_log is partitioned/WORM)
```
(Apply to the partitioned parent; it cascades to partitions.)

**A2. Derivation depth (Batch 107 substrate) — on `memories`:**
```sql
ALTER TABLE memories ADD COLUMN IF NOT EXISTS derivation_depth SMALLINT NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_memories_ns_derivation_depth ON memories (namespace_id, derivation_depth);
```

**A3. DLQ triage columns (Batch 121 substrate) — on `dead_letter_queue`:**
```sql
ALTER TABLE dead_letter_queue ADD COLUMN IF NOT EXISTS error_fingerprint TEXT;
ALTER TABLE dead_letter_queue ADD COLUMN IF NOT EXISTS quarantined_until TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_dlq_fingerprint ON dead_letter_queue (error_fingerprint);
```

**A4. `processed_outbox_events` (Batch 110 substrate):** `event_id UUID PRIMARY KEY`, `namespace_id UUID NOT NULL REFERENCES namespaces(id)`, `processed_at TIMESTAMPTZ NOT NULL DEFAULT now()`. RLS + grants. Index on `namespace_id`.

**A5. `actor_trust` (Batch 113 substrate):** `namespace_id UUID NOT NULL REFERENCES namespaces(id)`, `actor_id TEXT NOT NULL`, `actor_kind TEXT NOT NULL CHECK (actor_kind IN ('agent','operator'))`, `confirmations INT NOT NULL DEFAULT 0`, `rejections INT NOT NULL DEFAULT 0`, `contradictions_sourced INT NOT NULL DEFAULT 0`, `trust NUMERIC NOT NULL DEFAULT 0.65`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `PRIMARY KEY (namespace_id, actor_id, actor_kind)`. RLS + grants.

**A6. `event_parents` (Batch 120 substrate) — APPEND-ONLY:** `event_id UUID NOT NULL`, `parent_event_id UUID NOT NULL`, `namespace_id UUID NOT NULL REFERENCES namespaces(id)`, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `PRIMARY KEY (event_id, parent_event_id)`. RLS + grants + WORM trigger (no UPDATE/DELETE, reuse `prevent_mutation`). Index on `(parent_event_id)` for reverse lineage and `namespace_id`.

**A7. `action_approval_queue` (Batch 128 substrate):** `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`, `namespace_id UUID NOT NULL REFERENCES namespaces(id)`, `agent_id TEXT NOT NULL`, `action_type TEXT NOT NULL`, `target_system TEXT NOT NULL`, `target_entity_id TEXT`, `proposed_payload JSONB NOT NULL`, `status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','executed','expired'))`, `dry_run_result JSONB`, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `resolved_at TIMESTAMPTZ`, `resolved_by TEXT`. RLS + grants. Indexes on `(namespace_id, status)` and `(namespace_id, created_at)`.

**A8. `action_idempotency` (Batch 129 substrate):** `idempotency_key TEXT NOT NULL`, `namespace_id UUID NOT NULL REFERENCES namespaces(id)`, `action_type TEXT NOT NULL`, `target_entity_id TEXT`, `response_hash BYTEA`, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `PRIMARY KEY (namespace_id, idempotency_key)`. RLS + grants.

(Decay-stats table for Batch 131 is intentionally DEFERRED — not in this freeze.)

### Part B — Contract types (`nce/models.py`), read-only

1. Enums (so the FE can generate matching TS): `ChangeOrigin` (the 7 values), `ApprovalStatus` (5 values), `ActorKind` (agent/operator).
2. Read DTOs (response models only — no write/validation logic beyond field types): `ActorTrustOut`, `ApprovalQueueItemOut`, `ActionIdempotencyOut`, `EventParentOut`. Extend the existing memory/kg read DTOs with optional `change_origin`, `origin_event_id`, `derivation_depth` fields so existing endpoints surface them once populated.

### Part C — Read-only endpoints (admin surface), behind existing admin auth

Add GET-only endpoints returning the Part-B DTOs (data from the now-empty tables ⇒ `[]`). These freeze the API response shapes the FE codes against:
- `GET /api/admin/actor-trust?namespace_id=…` → `list[ActorTrustOut]`
- `GET /api/admin/approval-queue?namespace_id=…&status=…` → `list[ApprovalQueueItemOut]`
- `GET /api/admin/approval-queue/{id}` → `ApprovalQueueItemOut`
No POST/approve/execute here — those are behavior (Batches 113/128/129). Read shapes only.

---

**Acceptance:** `tests/test_schema_contract.py` (`@pytest.mark.integration`): migration 022 applies cleanly on a fresh DB and on a DB seeded at 021; every new tenant table has FORCE RLS + tenant policy; `event_parents` rejects UPDATE/DELETE; new columns exist with correct defaults. `tests/test_contract_endpoints.py`: each GET endpoint returns a correctly-typed empty list/shape under admin auth and 401/403 without it. `make lint && make typecheck && pytest -m integration tests/test_schema_contract.py tests/test_contract_endpoints.py` clean against `make local-up`.

## Final (main-bound — normal PR flow, NOT the ledger tooling):
1. When all gates pass, commit on `schema/muscles-contract-v1`.
2. Open a PR titled `Batch C0 — schema & API contract freeze` targeting `main`; paste both migration-apply results, the endpoint shapes, and gate output.
3. Do NOT run `generate_diff.py`/`trigger_tag_audit.py` (those drive the gitignored RL ledger; this batch is tracked product code). After review + merge to `main`, the front-end can build against the frozen tables, DTOs, and endpoints.
4. Once merged, the muscles behavior batches (106/107/110/113/120/121/128/129) add NO migrations — they wire logic onto this pre-existing schema.

- If any acceptance gate fails and you cannot fix it within this batch's stated scope, **STOP and report** — do not widen scope.
