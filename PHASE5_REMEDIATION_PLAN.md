# TriMCP Phase 5 Remediation Plan

> **Created**: 2026-05-09
> **Scope**: Close out remaining Phase 4 kaizen discoveries + resolve all pre-existing test failures to achieve a green test suite.

---

## Executive Summary

Phase 4 closed all 52 original remediation items across 7 batches. This plan covers:
1. **16 open kaizen discoveries** from Phase 3/4 (architecture, ops, security)
2. **27 test failures + 37 errors** that pre-existed before Phase 4 and still block a green CI

**Target state**: `pytest tests/` → 100% pass rate (excluding optional dependency skips like `httpx_mock`).

---

## Part A: Test Failure Remediation (Blocking CI)

### T1. `test_check_admin_hardening.py` — 16 FAILED + 5 ERROR
**Root cause**: Tests import `_check_admin` from `server.py`, but the server module's `check_admin` logic was refactored into `trimcp.auth._validate_scope`. The test suite is testing stale/removed code.

**Files**: `tests/test_check_admin_hardening.py`, `server.py`, `trimcp/auth.py`

**Fix strategy**:
- [ ] Verify whether `server.py:_check_admin` still exists and what it does
- [ ] If removed: update tests to import `trimcp.auth._validate_scope` instead
- [ ] If changed: update test assertions to match new behavior
- [ ] The 5 `TestAdminToolSchemas` errors (`NameError: cfg`) suggest `server.py` has a circular import or module-level `cfg` reference that fails during test collection

**ETA**: ~20 min | **Risk**: Low

---

### T2. `test_mcp_handlers_coverage.py` — 7 FAILED
**Root cause**: Bridge/replay handler validation errors. Tests expect specific error messages/structures that changed during Phase 4 refactors (`delete_snapshot` typed return, `check_health` merge, replay fork validation).

**Files**: `tests/test_mcp_handlers_coverage.py`

**Failed tests**:
- `test_connect_bridge_invalid_provider`
- `test_complete_bridge_auth_validations`
- `test_complete_bridge_auth_webhook_base_validation_errors`
- `test_complete_bridge_auth_state_machine_errors`
- `test_force_resync_sharepoint_bad_resource`
- `test_bridge_status_not_found`
- `test_replay_fork_invalid_parameters`

**Fix strategy**:
- [ ] Run tests individually with `-v --tb=long` to get actual vs expected
- [ ] Update assertions to match post-Phase 4 error messages and return types
- [ ] `test_replay_fork_invalid_parameters` may need updated Pydantic validation error text

**ETA**: ~25 min | **Risk**: Low

---

### T3. `test_quotas.py` — 2 FAILED
**Root cause**: Quota enforcement tests failing. Likely related to missing `TRIMCP_QUOTAS_ENABLED` or `cfg` not being available in test context.

**Files**: `tests/test_quotas.py`

**Failed tests**:
- `test_admin_api_search_returns_429_when_quota_exceeded`
- `test_mcp_call_tool_surfaces_quota_as_32013`

**Fix strategy**:
- [ ] Check if tests need `TRIMCP_QUOTAS_ENABLED=true` env var
- [ ] Verify quota middleware/handler signatures match test mocks

**ETA**: ~15 min | **Risk**: Low

---

### T4. `test_cognitive_orchestrator_rls.py` — 1 FAILED
**Root cause**: `test_inserts_salience_zero_and_logs_event` fails. Possibly related to RLS context reset or `forget_memory` soft-delete behavior.

**Files**: `tests/test_cognitive_orchestrator_rls.py`, `trimcp/orchestrators/cognitive.py`

**Fix strategy**:
- [ ] Run with `--tb=long` to get exact failure
- [ ] Check if `forget_memory` RLS query needs `valid_to IS NULL` filter adjustment

**ETA**: ~10 min | **Risk**: Low

---

### T5. `test_admin_rate_limiting.py` — 1 FAILED
**Root cause**: `test_server_call_tool_translates_rate_limit_error` — rate limit error code/message mismatch.

**Files**: `tests/test_admin_rate_limiting.py`

**Fix strategy**:
- [ ] Check if error code changed from `-32013` to something else
- [ ] Update test assertion to match current error translation

**ETA**: ~10 min | **Risk**: Low

---

### T6. `test_llm_providers.py` — 10 ERROR (missing `httpx_mock`)
**Root cause**: Tests require `pytest-httpx` plugin (`httpx_mock` fixture) which is not installed.

**Files**: `tests/test_llm_providers.py`

**Fix strategy**:
- [ ] `pip install pytest-httpx` in dev dependencies
- [ ] Or add `pytest.importorskip("pytest_httpx")` at top of test file
- [ ] Or move tests to `tests/integration/` with their own requirements

**ETA**: ~5 min | **Risk**: Low

---

### T7. `test_mcp_cache.py` — 20 ERROR (`NameError: name 'cfg' is not defined`)
**Root cause**: `server.py:123` references `cfg` at module level, but importing `server.py` in tests triggers config init before env vars are set. The `TRIMCP_MASTER_KEY` check runs at import time.

**Files**: `tests/test_mcp_cache.py`, `server.py`

**Fix strategy**:
- [ ] Move `server.py` module-level `cfg` access into lazy initialization
- [ ] Or add `if __name__ != "__main__":` guard for import-time side effects
- [ ] Or mock `cfg` before importing server in test conftest
- [ ] This is the same circular import risk that hits any test importing `server.py` directly

**ETA**: ~20 min | **Risk**: Medium

---

## Part B: Architecture & Operations (Kaizen Backlog)

### B1. Backfill `chain_hash` NULL for existing event_log rows
**Priority**: P3 | **Status**: OPEN
- One-off data migration script needed
- All existing rows have `chain_hash = NULL` (Merkle chain was added after table creation)
- Script should compute `chain_hash` by walking `namespace_id + event_seq` order

**ETA**: ~30 min | **Risk**: Medium (data integrity)

---

### B2. Admin HTTP endpoint + Prometheus gauge for Merkle chain verification
**Priority**: P3 | **Status**: OPEN
- Add `/admin/verify-chain/{namespace_id}` endpoint
- Add `trimcp_merkle_chain_verification_total` gauge (0=valid, 1=corrupted)
- Endpoint walks event_log and recomputes chain hashes, returns first mismatched event

**ETA**: ~45 min | **Risk**: Low

---

### B3. Migrate `bridge_mcp_handlers.py` callers to canonical `bridge_repo.save_token()` / `get_token()`
**Priority**: P3 | **Status**: OPEN
- Bridge handlers currently inline SQL or use ad-hoc patterns
- Centralize token persistence through `trimcp.bridges` module
- Reduces duplication and makes token encryption/rotation easier

**ETA**: ~40 min | **Risk**: Low

---

### B4. Schema migration for existing plaintext OAuth tokens in `bridge_subscriptions`
**Priority**: P3 | **Status**: OPEN
- Add `encrypted_token` column
- Backfill by encrypting existing plaintext tokens
- Add deprecation timeline for plaintext column

**ETA**: ~30 min | **Risk**: Medium (credential handling)

---

### B5. Audit XML entity bomb vulnerability in remaining extractors
**Priority**: P3 | **Status**: OPEN
- Check `extractors/dispatch.py` and other extractor modules for `xml.etree.ElementTree` / `lxml` usage
- Ensure `resolve_entities=False` and `no_network=True`
- Add test with billion-laughs-style payload

**ETA**: ~30 min | **Risk**: Medium (security)

---

### B6. Extract `MTLSAuthMiddleware` to shared module and apply to remaining servers
**Priority**: P3 | **Status**: OPEN
- `HMACAuthMiddleware` exists in `trimcp/auth.py`
- mTLS logic exists in `trimcp/a2a.py` but is A2A-specific
- Extract reusable `MTLSAuthMiddleware` to `trimcp/mtls.py`
- Apply to `admin_server.py` and `a2a_server.py`

**ETA**: ~45 min | **Risk**: Low

---

### B7. Traefik `X-Forwarded-Tls-Client-Cert` PEM parsing support
**Priority**: P3 | **Status**: OPEN
- Current code supports Caddy-style headers
- Traefik sends full PEM cert in `X-Forwarded-Tls-Client-Cert`
- Add PEM parsing branch to `parse_client_cert_from_headers()`

**ETA**: ~20 min | **Risk**: Low

---

### B8. Distributed lock for singleton cron jobs
**Priority**: P3 | **Status**: OPEN
- `cron.py` runs `renew_expiring_subscriptions`, `consolidation_tick`, `partition_maintenance`
- Multiple instances race on the same work
- Add Redis-based distributed lock (SET NX EX) with `trimcp:cron:lock:{job_id}`
- Lock TTL should be > job duration + heartbeat

**ETA**: ~30 min | **Risk**: Low

---

### B9. Build DLQ admin MCP endpoints and HTTP admin panel
**Priority**: P3 | **Status**: OPEN
- `dead_letter_queue.py` table exists but no admin interface
- Add MCP tools: `list_dlq`, `replay_dlq`, `purge_dlq`
- Add HTTP admin routes for web panel

**ETA**: ~60 min | **Risk**: Low

---

### B10. HTML `<h1>`–`<h3>` header context in chunking pipeline
**Priority**: P3 | **Status**: OPEN
- Semantic chunking currently drops HTML header structure
- Headers provide important document hierarchy
- Add BeautifulSoup-based header extraction to chunker, inject as metadata

**ETA**: ~40 min | **Risk**: Low

---

### B11. Generate OpenAPI/JSONSchema docs from strict Pydantic models
**Priority**: P3 | **Status**: OPEN
- Many API models are Pydantic V2 with strict typing
- Use `fastapi` or `pydantic.json_schema()` to generate docs
- Type remaining `Dict[str, Any]` fields to `TypedDict` or concrete models

**ETA**: ~60 min | **Risk**: Low

---

### B12. Resolve `kg_nodes`/`kg_edges` global vs. RLS policy inconsistency
**Priority**: P4 | **Status**: OPEN
- Tables have `namespace_id` + FKs but no `ENABLE ROW LEVEL SECURITY`
- `_allow_global_sweep` in `graph_query.py` requires cross-tenant traversal
- Decision needed: keep global access (document why) or add RLS with admin bypass

**ETA**: ~20 min (document decision) | **Risk**: Low

---

### B13. Batch deletion strategy for large namespace deletes
**Priority**: P4 | **Status**: OPEN
- Current `DELETE FROM memories WHERE namespace_id = $1` may lock millions of rows
- Use `DELETE ... LIMIT 1000` loop with `pg_advisory_lock`
- Or use PostgreSQL `TRUNCATE` partition strategy for full-namespace wipe

**ETA**: ~45 min | **Risk**: Medium (performance)

---

### B14. mypy type-error systematic cleanup (377 remaining errors)
**Priority**: P4 | **Status**: OPEN
- Run `mypy trimcp/ --ignore-missing-imports` and categorize errors
- Bulk-fix `Missing return type` with `-> None`
- Fix `Incompatible types` in model validators
- Add `py.typed` marker for package typing

**ETA**: ~90 min | **Risk**: Low

---

### B15. Wire OTLP backend (Jaeger/Grafana Tempo) into `docker-compose.yml`
**Priority**: P4 | **Status**: OPEN
- `observability.py` already exports OTLP traces
- Add `jaeger` or `grafana-tempo` service to `docker-compose.yml`
- Configure `TRIMCP_OTEL_EXPORTER_OTLP_ENDPOINT` in `.env.example`

**ETA**: ~20 min | **Risk**: Low

---

### B16. Verify Kubernetes `terminationGracePeriodSeconds` matches A2A drain window
**Priority**: P4 | **Status**: OPEN
- A2A drain logic has a 30s timeout
- K8s deployment manifests need `terminationGracePeriodSeconds >= 35`
- Check `deploy/` and `trimcp-infra/k8s/` for mismatch

**ETA**: ~15 min | **Risk**: Low

---

## Part C: Global Validation Gates (Every Batch)

1. `ruff check trimcp/ tests/` — must pass
2. `pytest tests/ --tb=short` — must be green before marking batch done
3. `python -c "import trimcp"` with `TRIMCP_MASTER_KEY` set — must not crash
4. **Uncle-Bob Self-Review**:
   - [ ] Functions <20 lines when possible
   - [ ] No function does more than one thing
   - [ ] Dependencies point inward
   - [ ] Tests exist before or alongside change

---

## Kill Criteria
- Test fails after 2 fix attempts → halt for RCA
- Schema change breaks existing tests → rollback, add migration step
- Function exceeds 40 lines without extraction → refactor before merging

---

## Summary by Priority

| Priority | Items | Est. Effort |
|----------|-------|-------------|
| T (Tests) | 7 groups, 64 broken tests | ~2h |
| B1–B11 (P3 Architecture) | 11 items | ~6.5h |
| B12–B16 (P4 Ops/CI) | 5 items | ~3h |
| **Total** | **27 items** | **~11.5h** |
