1. **One batch = one branch = one commit.** Branch name `batch-119-echo-suppression`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy**.
3. **Modify only the files listed in the batch.** No new modules/deps.
4. **Minimal diff.** Reuse the webhook dedup Redis helpers (`_claim_dedup`/SET NX), the Batch 106 `change_origin`/`origin_event_id` columns, and the existing semantic-vs-deterministic ingestion split. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing webhook/ingestion tests still pass
6. **Migrations:** none (Redis-only echo set + Batch 106 columns).
7. **WORM/RLS invariants (never violate):** echo-suppressed webhooks still apply the deterministic upsert (state convergence); only the semantic-track (episodic memory + Empathic Tensor) is skipped; tenant-scoped.
8. **Secrets:** `NCE_MASTER_KEY` env-only.
9. **DB-dependent tests** are `@pytest.mark.integration`.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `python-pro` (primary), `distributed-tracing`
**Depends on:** Batch 106 (origin columns), Batch 114 (sync cursors)
**Files:** `nce/webhook_receiver/main.py`; `nce/tasks.py` (`process_d365_event`); `nce/vertical_modules/dynamics365/ingestion.py`; `nce/config.py`; `tests/test_echo_suppression.py` (new)
**Goal:** When NCE itself causes an external change (future mutating tools, Batch 129) the resulting webhook must not be re-ingested as fresh signal and re-trigger the agent. Add an echo set so self-caused webhooks are recognized and their semantic re-ingestion suppressed.
**Steps:**
1. Define an echo-record helper: on any NCE-originated outward change, `SET nce:echo:{system}:{entity_id}` in Redis (TTL = `cfg.NCE_ECHO_TTL_S`, default 600; value = `origin_event_id`). (Producers are wired in Batch 129; here provide the helper + the consumer + a test hook to seed an echo.)
2. Webhook ingestion (`main.py`/`tasks.py`): before semantic ingestion, check the echo set; on hit ⇒ tag the ingest `change_origin='webhook'` + `metadata.echo_of=origin_event_id`, SKIP semantic-track ingestion (no new episodic memory, no Empathic Tensor), but STILL apply the deterministic kg upsert so state converges. Increment metric `nce_echo_suppressed_total`.
3. Config: add `NCE_ECHO_TTL_S` (int, default 600, min 1).
**Acceptance:** `tests/test_echo_suppression.py` (`@pytest.mark.integration`): seed an echo for an entity, deliver the matching webhook ⇒ no new episodic memory / no Empathic Tensor record, deterministic edge still upserted, `metadata.echo_of` set, metric incremented; a non-echo webhook ingests normally. `make lint && make typecheck && pytest -m integration tests/test_echo_suppression.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 119 — echo-suppression`, paste the gate output, and wait for review.
