# Phase 5 Remediation Plan — Status

> **Created**: 2026-05-09  
> **Based on**: `PHASE5_REMEDIATION_PLAN.md` + `last work done - phase 5.txt`  
> **Kimi 2.6 stopped**: Mid-way through B6, line ~3021, token-quota exhausted.

---

## Execution Summary

Kimi 2.6 completed test-suite remediation (Part A) fully, then worked through most of Part B before hitting its quota limit. Verified actual file state via Grep — all changes up to mid-B6 are on disk.

**Test baseline after Part A**: 883 passed, 12 skipped, 0 failed.

---

## Part A: Test Failure Remediation — ALL COMPLETE ✅

| Item | Test File | Failures Fixed | Notes |
|------|-----------|---------------|-------|
| T1 | `test_check_admin_hardening.py` | 16 FAILED + 5 ERROR | `_check_admin` import path corrected |
| T2 | `test_mcp_handlers_coverage.py` | 7 FAILED | Post-Phase-4 error message/return-type assertions updated |
| T3 | `test_quotas.py` | 2 FAILED | Quota env var + middleware signature fixed |
| T4 | `test_cognitive_orchestrator_rls.py` | 1 FAILED | `forget_memory` RLS query fixed |
| T5 | `test_admin_rate_limiting.py` | 1 FAILED | Rate-limit error code assertion updated |
| T6 | `test_llm_providers.py` | 10 ERROR | `pytest-httpx` / `importorskip` resolved |
| T7 | `test_mcp_cache.py` | 20 ERROR | `server.py` module-level `cfg` lazy-init fixed |

---

## Part B: Architecture & Operations — STATUS

### COMPLETED ✅

| Item | Description | Files Changed | Tests |
|------|-------------|---------------|-------|
| B5 | XML entity bomb hardening | `trimcp/extractors/plaintext.py` (lxml secure parser), `trimcp/extractors/diagrams.py` (defusedxml), `trimcp/extractors/adobe_ext.py` (defusedxml + EntitiesForbidden) | `tests/test_xml_entity_bomb.py` (9 tests) |
| B7 | Traefik `X-Forwarded-Tls-Client-Cert` PEM parsing | `trimcp/a2a.py`: `_parse_pem_cert()` helper + Traefik branch in `parse_client_cert_from_headers()` | 3 new tests in `tests/test_a2a.py` |
| B15 | Wire OTLP/Jaeger into docker-compose | `docker-compose.yml` (jaeger depends_on for admin, a2a, webhook-receiver), `.env.example` (OTLP vars), `deploy/compose.stack.env` (OTLP vars) | No unit tests needed |
| B1 | Backfill `chain_hash` NULL for existing event_log rows | `scripts/backfill_chain_hash.py` (new one-off migration script, WORM-trigger aware) | `tests/test_backfill_chain_hash.py` (8 tests) |
| B2 | Admin HTTP endpoint + Prometheus gauge for Merkle chain verification | `admin_server.py` (`api_admin_verify_chain` + route `/api/admin/verify-chain/{namespace_id}`), `trimcp/observability.py` (`MERKLE_CHAIN_VALID` Gauge) | `tests/test_admin_verify_chain.py` (5 tests) |
| B3 | Migrate `bridge_mcp_handlers.py` to canonical `bridge_repo.save_token()` / `get_token()` | `trimcp/bridge_mcp_handlers.py` (removed `_bridge_oauth_ciphertext`, `_decrypt_bridge_oauth_if_present`, stale imports; wired `bridge_repo` calls), `tests/test_mcp_handlers_coverage.py` (updated mocks) | All bridge tests pass |
| B4 | Schema migration for existing plaintext OAuth tokens | `scripts/migrate_bridge_tokens.py` (new one-off migration script, detects plaintext/old-format blobs and re-encrypts) | No unit tests; logic covered by script's internal guards |

---

### COMPLETED ✅ (continued)

#### B6: Extract `MTLSAuthMiddleware` to shared module — COMPLETE ✅

**All tasks done (2026-05-09):**
- `trimcp/mtls.py` — `MTLSAuthMiddleware` with early-exit when `enabled=False` (SRP: middleware owns its own gate)
- `trimcp/a2a_server.py` — Regression fixed: all six cfg params now passed to `Middleware(MTLSAuthMiddleware, ...)`, plus removed unused `A2AMTLSError`/`mtls_enforce` imports
- `trimcp/config.py` — Added `TRIMCP_ADMIN_MTLS_*` config vars (all default-disabled; existing deployments unaffected)
- `admin_server.py` — `MTLSAuthMiddleware` wired into middleware stack, protecting `/api/` prefix
- `tests/test_mtls.py` — 14 tests; 14 pass

**Validation**: `ruff check tests/test_mtls.py` clean; `pytest tests/` → 897 passed, 12 skipped, 0 failed.

---

### COMPLETED ✅ (this session, 2026-05-09)

| Item | Description | Files Changed | Tests |
|------|-------------|---------------|-------|
| B8 | Distributed lock for singleton cron jobs | `trimcp/cron_lock.py` (new), `trimcp/cron.py` (import + lock in 3 tick fns) | `tests/test_cron_lock.py` (5 tests) |
| B12 | kg_nodes/kg_edges global vs RLS — keep `_allow_global_sweep`, documented decision | `trimcp/graph_query.py` (module docstring) | No unit tests needed |
| B16 | K8s grace period — no K8s YAML in repo; fixed docker-compose (35s) + Fargate `stopTimeout:35` | `docker-compose.yml`, `trimcp-infra/aws/modules/fargate-worker/main.tf` | No unit tests needed |
| B13 | Batch namespace deletion — chunked 1000-row CTE DELETEs for large tables | `trimcp/orchestrators/namespace.py` (`_delete_namespace_rows_chunked` + loop for `kg_edges`) | All namespace tests pass |
| B9 | DLQ admin endpoints — `list_dlq`, `replay_dlq`, `purge_dlq` MCP tools + HTTP routes | `trimcp/admin_mcp_handlers.py`, `admin_server.py` | Existing DLQ tests pass |
| B10 | HTML h1-h3 header context — selectolax DOM walk, sections with `structure_path` hierarchy | `trimcp/extractors/plaintext.py` (`_html_sections_from_headings` + updated `extract_html`) | `tests/test_html_heading_extraction.py` (11 tests) |
| B11 | OpenAPI/JSON Schema — `scripts/generate_schemas.py` + `/api/admin/schema` endpoint | `scripts/generate_schemas.py` (new), `admin_server.py` (`api_admin_schema`), `docs/schemas.json` | 913 passing |

### OPEN — NOT STARTED ❌

| Item | Description | ETA | Risk | Priority |
|------|-------------|-----|------|----------|
| B14 | mypy type-error systematic cleanup — 377 remaining errors; bulk-fix `Missing return type → None`, `Incompatible types` in validators, add `py.typed` | ~90 min | Low | P4 |

---

## Execution Order for Next Session

```
Priority order:
1. B6 BUG FIX (mTLS regression — a2a_server.py cfg params + tests)
2. B8 (cron distributed lock — safety)
3. B12 (kg_nodes RLS decision — quick)
4. B16 (K8s grace period — quick)
5. B13 (batch deletes — medium complexity)
6. B9 (DLQ endpoints — larger)
7. B10 (HTML chunking)
8. B11 (OpenAPI docs)
9. B14 (mypy — largest, can be last)
```

---

## Global Validation Gates (Every Batch)

1. `ruff check trimcp/ tests/` — must pass
2. `python -m pytest tests/ --tb=short` — must stay at 0 failures
3. `python -c "import trimcp"` with `TRIMCP_MASTER_KEY` set — must not crash
4. Uncle-Bob self-review: functions < 20 lines, single responsibility, tests alongside change

---

## Kill Criteria

- Test fails after 2 fix attempts → halt for RCA
- Schema change breaks existing tests → rollback, add migration step
- Function exceeds 40 lines without extraction → refactor before merging

---

## Remaining Effort Estimate

| Group | Items | Est. |
|-------|-------|------|
| B6 fix (regression) | 1 | ~25 min |
| B8, B12, B16 (quick wins) | 3 | ~65 min |
| B9, B10, B11, B13 (medium) | 4 | ~3.5 h |
| B14 (mypy bulk) | 1 | ~1.5 h |
| **Total** | **9** | **~5.5 h** |
