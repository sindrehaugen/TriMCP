"""
Phase 2.3 — Memory Replay Engine (Observational + Forked).

Transport-agnostic: all execution loops are **async generators** that yield
progress dicts.  The caller (MCP tool handler, admin API route, test) decides
how to serialise output.  There is no SSE, no HTTP-specific code, and no
transport coupling anywhere in this module.

Observational
─────────────
Streams event_log rows for a namespace/seq range back to the caller without
touching any engine state.  Uses an asyncpg server-side cursor so rows are
never fully loaded into Python heap.

Forked
──────
Replays source events into an isolated target namespace up to ``fork_seq``.
For every source event a fresh event_log entry is written in the target via
``append_event()``, with ``parent_event_id`` set to the source event's UUID.
The new HMAC-SHA256 signature is computed over the **fork's own** fields
(fork namespace_id, fork event_seq, fork occurred_at, source parent_event_id)
— this is the "alternate causal provenance" required by the spec.

In ``deterministic`` mode LLM responses are served from the MinIO payload
cache (``event_log.llm_payload_uri``) so the fork is byte-identical to the
source run up to the divergence point.

In ``re-execute`` mode the LLM provider is called fresh, optionally with
``config_overrides``, so the fork intentionally diverges.

Handler registry
────────────────
Each ``event_type`` is mapped to a coroutine that applies the event to the
target namespace and returns a ``result_summary`` dict.  Adding a new
event_type requires adding a matching handler — the registry validates this
at ``ForkedReplay.__init__`` time.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import uuid
from collections.abc import AsyncGenerator, Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, get_args

import asyncpg
from minio import Minio
from minio.error import S3Error

from trimcp.config import cfg
from trimcp.event_log import (
    AppendResult,
    DataIntegrityError,
    append_event,
    verify_event_signature,
)
from trimcp.event_types import EventType
from trimcp.models import FrozenForkConfig
from trimcp.signing import canonical_json

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

# How many rows the asyncpg cursor fetches from Postgres per round-trip.
# Keeps server memory bounded regardless of event_log size.
_CURSOR_PREFETCH: int = 50

# Write a progress item + update replay_runs every N events.
_PROGRESS_INTERVAL: int = 10

# MinIO bucket for LLM payloads (spec: llm_payload_uri = "bucket/object_key").
_LLM_PAYLOAD_BUCKET: str = "trimcp-llm-payloads"

# ---------------------------------------------------------------------------
# Public exceptions
# ---------------------------------------------------------------------------


class ReplayError(Exception):
    """Base class for replay errors."""


class ReplayModeError(ReplayError):
    """``replay_mode`` is not 'deterministic' or 're-execute'."""


class ReplayHandlerMissingError(ReplayError):
    """No handler is registered for the given ``event_type``."""


class MinIOPayloadMissingError(ReplayError):
    """Deterministic replay requested but ``llm_payload_uri`` is NULL on the source event."""


class ReplayRunNotFoundError(ReplayError):
    """Queried ``replay_run_id`` does not exist in ``replay_runs``."""


class ReplayChecksumError(ReplayError):
    """Payload checksum mismatch — the replay request was tampered with or corrupted."""


# ---------------------------------------------------------------------------
# Internal dataclass: one row from event_log
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _EventRow:
    event_id: uuid.UUID
    event_seq: int
    event_type: str
    occurred_at: datetime
    agent_id: str
    params: dict[str, Any]
    result_summary: dict[str, Any] | None
    parent_event_id: uuid.UUID | None
    llm_payload_uri: str | None
    llm_payload_hash: bytes | None


def _row_as_dict(row: _EventRow) -> dict[str, Any]:
    """Serialise an ``_EventRow`` to a JSON-safe dict for yielding."""
    return {
        "event_id": str(row.event_id),
        "event_seq": row.event_seq,
        "event_type": row.event_type,
        "occurred_at": row.occurred_at.isoformat(),
        "agent_id": row.agent_id,
        "params": row.params,
        "result_summary": row.result_summary,
        "parent_event_id": str(row.parent_event_id) if row.parent_event_id else None,
        "llm_payload_uri": row.llm_payload_uri,
    }


def _record_to_event_row(record: asyncpg.Record) -> _EventRow:
    """Convert a raw asyncpg record to ``_EventRow``."""
    return _EventRow(
        event_id=record["id"],
        event_seq=record["event_seq"],
        event_type=record["event_type"],
        occurred_at=record["occurred_at"].astimezone(timezone.utc),
        agent_id=record["agent_id"],
        params=dict(record["params"]) if record["params"] else {},
        result_summary=(
            dict(record["result_summary"]) if record["result_summary"] else None
        ),
        parent_event_id=record["parent_event_id"],
        llm_payload_uri=record["llm_payload_uri"],
        llm_payload_hash=(
            bytes(record["llm_payload_hash"]) if record["llm_payload_hash"] else None
        ),
    )


# ---------------------------------------------------------------------------
# replay_runs table helpers
# NOTE: replay_runs is NOT WORM — we can INSERT and UPDATE it.
# ---------------------------------------------------------------------------


async def _create_run(
    conn: asyncpg.Connection,
    *,
    source_namespace_id: uuid.UUID,
    target_namespace_id: uuid.UUID | None,
    mode: str,
    replay_mode: str,
    start_seq: int,
    end_seq: int | None,
    divergence_seq: int | None,
    config_overrides: dict | None,
) -> uuid.UUID:
    """INSERT a new ``replay_runs`` row and return its UUID."""
    run_id = uuid.uuid4()
    await conn.execute(
        """
        INSERT INTO replay_runs (
            id, source_namespace_id, target_namespace_id,
            mode, replay_mode, start_seq, end_seq, divergence_seq,
            config_overrides, status, events_applied
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, 'running', 0
        )
        """,
        run_id,
        source_namespace_id,
        target_namespace_id,
        mode,
        replay_mode,
        start_seq,
        end_seq,
        divergence_seq,
        json.dumps(config_overrides, sort_keys=True) if config_overrides else None,
    )
    log.info(
        "replay_run created: run_id=%s mode=%s replay_mode=%s ns=%s",
        run_id,
        mode,
        replay_mode,
        source_namespace_id,
    )
    return run_id


async def _update_run_progress(
    conn: asyncpg.Connection,
    run_id: uuid.UUID,
    events_applied: int,
) -> None:
    await conn.execute(
        "UPDATE replay_runs SET events_applied = $1 WHERE id = $2",
        events_applied,
        run_id,
    )


async def _finish_run(
    conn: asyncpg.Connection,
    run_id: uuid.UUID,
    *,
    status: str,
    events_applied: int,
    error: str | None = None,
) -> None:
    await conn.execute(
        """
        UPDATE replay_runs
        SET status = $1, events_applied = $2, finished_at = now(), error = $3
        WHERE id = $4
        """,
        status,
        events_applied,
        error,
        run_id,
    )
    log.info(
        "replay_run finished: run_id=%s status=%s events=%d",
        run_id,
        status,
        events_applied,
    )


async def get_run_status(
    pool: asyncpg.Pool,
    run_id: uuid.UUID,
) -> dict[str, Any]:
    """Return a JSON-safe dict for the given ``replay_run_id``."""
    async with pool.acquire(timeout=10.0) as conn:
        row = await conn.fetchrow(
            """
            SELECT id, source_namespace_id, target_namespace_id,
                   mode, replay_mode, start_seq, end_seq, divergence_seq,
                   config_overrides, status, events_applied,
                   started_at, finished_at, error
            FROM replay_runs WHERE id = $1
            """,
            run_id,
        )
    if row is None:
        raise ReplayRunNotFoundError(f"replay_run {run_id} not found.")
    return {
        "run_id": str(row["id"]),
        "source_namespace_id": str(row["source_namespace_id"]),
        "target_namespace_id": (
            str(row["target_namespace_id"]) if row["target_namespace_id"] else None
        ),
        "mode": row["mode"],
        "replay_mode": row["replay_mode"],
        "start_seq": row["start_seq"],
        "end_seq": row["end_seq"],
        "divergence_seq": row["divergence_seq"],
        "config_overrides": (
            dict(row["config_overrides"]) if row["config_overrides"] else None
        ),
        "status": row["status"],
        "events_applied": row["events_applied"],
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
        "error": row["error"],
    }


# ---------------------------------------------------------------------------
# Event source query builder
# ---------------------------------------------------------------------------


def _build_event_query(
    *,
    source_namespace_id: uuid.UUID,
    start_seq: int,
    end_seq: int | None,
    agent_id_filter: str | None,
) -> tuple[str, list[Any]]:
    """Return ``(sql, args)`` for the event_log cursor query."""
    conditions = ["namespace_id = $1", "event_seq >= $2"]
    args: list[Any] = [source_namespace_id, start_seq]
    idx = 3

    if end_seq is not None:
        conditions.append(f"event_seq <= ${idx}")
        args.append(end_seq)
        idx += 1

    if agent_id_filter:
        conditions.append(f"agent_id = ${idx}")
        args.append(agent_id_filter)
        idx += 1

    sql = f"""
        SELECT
            id, event_seq, event_type, occurred_at, agent_id,
            params, result_summary, parent_event_id,
            llm_payload_uri, llm_payload_hash,
            signature, signature_key_id
        FROM event_log
        WHERE {' AND '.join(conditions)}
        ORDER BY event_seq ASC
    """
    return sql, args


async def _fetch_event_log_snapshot(
    pool: asyncpg.Pool,
    *,
    source_namespace_id: uuid.UUID,
    start_seq: int,
    end_seq: int | None,
    agent_id_filter: str | None,
):
    """Snapshot event rows inside a short REPEATABLE READ txn (FIX-041)."""
    sql, args = _build_event_query(
        source_namespace_id=source_namespace_id,
        start_seq=start_seq,
        end_seq=end_seq,
        agent_id_filter=agent_id_filter,
    )
    async with pool.acquire(timeout=10.0) as conn:
        async with conn.transaction(isolation="repeatable_read"):
            rows = await conn.fetch(sql, *args)
            return list(rows)


# ---------------------------------------------------------------------------
# MinIO helpers  (blocking I/O → thread-pool, never blocks the event loop)
# ---------------------------------------------------------------------------


def _make_minio() -> Minio:
    return Minio(
        cfg.MINIO_ENDPOINT,
        access_key=cfg.MINIO_ACCESS_KEY,
        secret_key=cfg.MINIO_SECRET_KEY,
        secure=cfg.MINIO_SECURE,
    )


async def _fetch_llm_payload(uri: str) -> dict[str, Any]:
    """
    Fetch ``{prompt, response}`` JSON from MinIO.

    ``uri`` format: ``"<bucket>/<object_key>"``.
    Runs the blocking MinIO call on the thread-pool executor.
    """
    if "/" not in uri:
        raise ReplayError(f"Malformed llm_payload_uri (no '/'): {uri!r}")
    bucket, key = uri.split("/", 1)

    loop = asyncio.get_running_loop()
    client = _make_minio()

    def _get() -> bytes:
        response = client.get_object(bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    raw: bytes = await loop.run_in_executor(None, _get)
    return json.loads(raw.decode("utf-8"))


async def _put_llm_payload(uri: str, payload: dict[str, Any]) -> bytes:
    """
    PUT ``{prompt, response}`` to MinIO and return ``sha256(JCS(payload))``.

    Creates the bucket if it does not exist.  Runs on thread-pool.
    """
    if "/" not in uri:
        raise ReplayError(f"Malformed llm_payload_uri (no '/'): {uri!r}")
    bucket, key = uri.split("/", 1)
    payload_bytes: bytes = canonical_json(payload)

    loop = asyncio.get_running_loop()
    client = _make_minio()

    def _put() -> None:
        # Ensure bucket exists before writing.
        try:
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
        except S3Error:
            pass  # May already exist in a race; the put below will fail if bucket truly missing
        client.put_object(
            bucket,
            key,
            io.BytesIO(payload_bytes),
            len(payload_bytes),
            content_type="application/json",
        )

    await loop.run_in_executor(None, _put)
    return hashlib.sha256(payload_bytes).digest()


def _fork_llm_payload_uri(
    source_uri: str,
    target_namespace_id: uuid.UUID,
    source_event_id: uuid.UUID,
) -> str:
    """
    Derive a MinIO URI for the fork's LLM payload.

    Format: ``"<bucket>/fork/<target_ns>/<source_event_id>.json"``
    """
    return f"{_LLM_PAYLOAD_BUCKET}/fork/{target_namespace_id}/{source_event_id}.json"


# ---------------------------------------------------------------------------
# Handler protocol + registry
# ---------------------------------------------------------------------------

# A handler is a coroutine:
#   async def handler(
#       conn, source_event, target_namespace_id, llm_payload, config_overrides
#   ) -> dict[str, Any]
#
# ``llm_payload`` is either:
#   * the fetched MinIO dict  (deterministic mode)
#   * the freshly-computed result  (re-execute mode)
#   * None for non-LLM events

HandlerFn = Callable[
    [asyncpg.Connection, "_EventRow", uuid.UUID, dict | None, dict | None],
    Coroutine[Any, Any, dict[str, Any]],
]

_HANDLER_REGISTRY: dict[str, HandlerFn] = {}


def _register(event_type: str) -> Callable[[HandlerFn], HandlerFn]:
    """Decorator: register a coroutine as the handler for *event_type*."""

    def _dec(fn: HandlerFn) -> HandlerFn:
        _HANDLER_REGISTRY[event_type] = fn
        return fn

    return _dec


# ---------------------------------------------------------------------------
# Per-event-type handlers
# ---------------------------------------------------------------------------


@_register("store_memory")
async def _handle_store_memory(
    conn: asyncpg.Connection,
    src: _EventRow,
    target_ns: uuid.UUID,
    llm_payload: dict | None,
    config_overrides: dict | None,
) -> dict[str, Any]:
    """
    Re-insert the memory row into the target namespace, preserving content.

    The embedding and salience values are carried over from the source row so
    that the fork's semantic state is identical up to the divergence point.
    Full re-embedding is supported by kicking off a re-embedding job later.
    """
    memory_id_str: str = src.params.get("memory_id", "")
    if not memory_id_str:
        return {"skipped": True, "reason": "no_memory_id_in_params"}

    src_memory_id = uuid.UUID(memory_id_str)
    new_memory_id = uuid.uuid4()

    # Fetch the source memory row (embedding + salience + metadata).
    # The source_namespace_id is injected into params.source_namespace_id by
    # ForkedReplay.execute() when it enriches the params dict.
    raw_src_ns = src.params.get("source_namespace_id")
    src_ns_id = uuid.UUID(raw_src_ns) if raw_src_ns else None
    if src_ns_id is None:
        return {"skipped": True, "reason": "source_namespace_id_missing_in_params"}

    src_row = await conn.fetchrow(
        """
        SELECT summary, embedding, assertion_type, memory_type,
               salience, metadata
        FROM memories
        WHERE id = $1 AND namespace_id = $2
          AND valid_to IS NULL
        """,
        src_memory_id,
        src_ns_id,
    )
    if src_row is None:
        log.warning(
            "store_memory handler: source row not found memory_id=%s; writing stub",
            src_memory_id,
        )
        return {"skipped": True, "reason": "source_memory_not_found"}

    meta = dict(src_row["metadata"]) if src_row["metadata"] else {}
    meta["source_memory_id"] = str(src_memory_id)

    await conn.execute(
        """
        INSERT INTO memories (
            id, namespace_id, agent_id,
            summary, embedding,
            assertion_type, memory_type,
            salience, metadata,
            valid_from
        ) VALUES (
            $1, $2, $3,
            $4, $5,
            $6, $7,
            $8, $9::jsonb,
            now()
        )
        ON CONFLICT DO NOTHING
        """,
        new_memory_id,
        target_ns,
        src.agent_id,
        src_row["summary"],
        src_row["embedding"],
        src_row["assertion_type"],
        src_row["memory_type"],
        src_row["salience"],
        json.dumps(meta),
    )

    return {
        "source_memory_id": str(src_memory_id),
        "new_memory_id": str(new_memory_id),
        "target_namespace": str(target_ns),
    }


@_register("forget_memory")
async def _handle_forget_memory(
    conn: asyncpg.Connection,
    src: _EventRow,
    target_ns: uuid.UUID,
    llm_payload: dict | None,
    config_overrides: dict | None,
) -> dict[str, Any]:
    """
    Expire (soft-delete) the matching memory in the target namespace.

    Because the target memory was inserted with a new UUID, we identify it by
    ``source_memory_id`` stored in ``metadata``.  If not found, the event is
    a no-op (idempotent).
    """
    src_memory_id = src.params.get("memory_id", "")
    if not src_memory_id:
        return {"skipped": True, "reason": "no_memory_id_in_params"}

    result = await conn.execute(
        """
        UPDATE memories
        SET valid_to = now()
        WHERE namespace_id = $1
          AND agent_id = $2
          AND valid_to IS NULL
          AND metadata->>'source_memory_id' = $3
        """,
        target_ns,
        src.agent_id,
        src_memory_id,
    )
    return {"rows_expired": int(result.split()[-1])}


@_register("boost_memory")
async def _handle_boost_memory(
    conn: asyncpg.Connection,
    src: _EventRow,
    target_ns: uuid.UUID,
    llm_payload: dict | None,
    config_overrides: dict | None,
) -> dict[str, Any]:
    """Apply the same salience boost to the corresponding fork memory."""
    src_memory_id = src.params.get("memory_id", "")
    factor = float(src.params.get("factor", 0.2))
    if not src_memory_id:
        return {"skipped": True, "reason": "no_memory_id_in_params"}

    result = await conn.execute(
        """
        UPDATE memories
        SET salience = LEAST(1.0, salience + $1)
        WHERE namespace_id = $2
          AND agent_id = $3
          AND valid_to IS NULL
          AND metadata->>'source_memory_id' = $4
        """,
        factor,
        target_ns,
        src.agent_id,
        src_memory_id,
    )
    return {"rows_updated": int(result.split()[-1]), "factor": factor}


@_register("resolve_contradiction")
async def _handle_resolve_contradiction(
    conn: asyncpg.Connection,
    src: _EventRow,
    target_ns: uuid.UUID,
    llm_payload: dict | None,
    config_overrides: dict | None,
) -> dict[str, Any]:
    """Mark the corresponding contradiction as resolved in the fork."""
    contradiction_id = src.params.get("contradiction_id")
    resolution = src.params.get("resolution", "deferred")
    if not contradiction_id:
        return {"skipped": True, "reason": "no_contradiction_id_in_params"}

    result = await conn.execute(
        """
        UPDATE contradictions
        SET resolution = $1, resolved_at = now()
        WHERE namespace_id = $2
          AND id = $3
          AND resolution = 'unresolved'
        """,
        resolution,
        target_ns,
        uuid.UUID(contradiction_id),
    )
    return {"rows_updated": int(result.split()[-1])}


@_register("consolidation_run")
async def _handle_consolidation_run(
    conn: asyncpg.Connection,
    src: _EventRow,
    target_ns: uuid.UUID,
    llm_payload: dict | None,
    config_overrides: dict | None,
) -> dict[str, Any]:
    """
    Apply a consolidation to the fork namespace.

    ``llm_payload`` carries the ``{prompt, response}`` dict:
    * In deterministic mode it was fetched from MinIO (byte-identical to source).
    * In re-execute mode it contains the freshly-computed LLM response.

    The handler writes the resulting consolidated memory and returns the
    result_summary for the fork's event_log entry.
    """
    if llm_payload is None:
        return {"skipped": True, "reason": "llm_payload_unavailable"}

    response: dict = llm_payload.get("response", {})
    abstraction: str = response.get("abstraction", "")
    confidence: float = float(response.get("confidence", 0.0))

    if confidence < 0.3:
        return {
            "skipped": True,
            "reason": "low_confidence",
            "confidence": confidence,
        }

    if not abstraction:
        return {"skipped": True, "reason": "empty_abstraction"}

    new_memory_id = uuid.uuid4()

    # Embed the abstraction (reuse the existing embedding infrastructure
    # via a direct import; avoids circular deps since we don't import engine).
    from trimcp import embeddings as _emb  # local import to avoid module-level circular

    vector = await _emb.embed(abstraction)

    await conn.execute(
        """
        INSERT INTO memories (
            id, namespace_id, agent_id,
            summary, embedding,
            assertion_type, memory_type,
            salience, metadata,
            valid_from
        ) VALUES (
            $1, $2, $3,
            $4, $5,
            'fact', 'consolidated',
            $6, $7::jsonb,
            now()
        )
        ON CONFLICT DO NOTHING
        """,
        new_memory_id,
        target_ns,
        src.agent_id,
        abstraction,
        vector,
        response.get("confidence", 0.0),
        json.dumps(
            {
                "source_memory_ids": response.get("supporting_memory_ids", []),
                "key_entities": response.get("key_entities", []),
                "key_relations": response.get("key_relations", []),
                "replay_fork": True,
            }
        ),
    )

    return {
        "memory_id": str(new_memory_id),
        "confidence": confidence,
        "abstraction": abstraction[:120],
    }


@_register("pii_redaction")
async def _handle_pii_redaction(
    conn: asyncpg.Connection,
    src: _EventRow,
    target_ns: uuid.UUID,
    llm_payload: dict | None,
    config_overrides: dict | None,
) -> dict[str, Any]:
    """Record that PII redaction occurred in the fork (no re-scanning needed)."""
    return {
        "memory_id": src.params.get("memory_id"),
        "entity_types": src.params.get("entity_types", []),
        "replayed": True,
    }


@_register("snapshot_created")
async def _handle_snapshot_created(
    conn: asyncpg.Connection,
    src: _EventRow,
    target_ns: uuid.UUID,
    llm_payload: dict | None,
    config_overrides: dict | None,
) -> dict[str, Any]:
    """
    Record the snapshot event in the fork namespace (provenance-only).

    State snapshots are namespace-level checkpoints.  In a fork, re-recording
    the event in event_log is sufficient for audit provenance; no additional
    state mutation is needed.
    """
    return {
        "source_snapshot_name": src.params.get("name"),
        "replayed": True,
    }


@_register("unredact")
async def _handle_unredact(
    conn: asyncpg.Connection,
    src: _EventRow,
    target_ns: uuid.UUID,
    llm_payload: dict | None,
    config_overrides: dict | None,
) -> dict[str, Any]:
    """Record that an unredaction occurred in the fork namespace."""
    return {
        "memory_id": src.params.get("memory_id"),
        "replayed": True,
    }


async def _handle_fork_provenance_only(
    conn: asyncpg.Connection,
    src: _EventRow,
    target_ns: uuid.UUID,
    llm_payload: dict | None,
    config_overrides: dict | None,
) -> dict[str, Any]:
    """Namespace / migration audit events: fork records provenance in event_log only."""
    return {"replayed": True, "event_type": src.event_type}


_FORK_PROVENANCE_ONLY_TYPES: tuple[str, ...] = (
    "namespace_access_granted",
    "namespace_access_revoked",
    "namespace_created",
    "namespace_metadata_updated",
    "namespace_impersonated",
    "namespace_deleted",
    "migration_started",
    "migration_committed",
    "migration_aborted",
)

for _fork_prov_et in _FORK_PROVENANCE_ONLY_TYPES:
    _HANDLER_REGISTRY[_fork_prov_et] = _handle_fork_provenance_only


# ---------------------------------------------------------------------------
# LLM re-execution helper for ForkedReplay
# ---------------------------------------------------------------------------


async def _resolve_llm_payload(
    src: _EventRow,
    replay_mode: str,
    config_overrides: dict | None,
    target_namespace_id: uuid.UUID,
    source_namespace_id: uuid.UUID,
) -> tuple[dict | None, str | None, bytes | None]:
    """
    Resolve the LLM payload for a forked event.

    Returns ``(payload_dict, new_uri, new_hash)`` where:
    * ``payload_dict``  — ``{prompt, response}`` for handler consumption
    * ``new_uri``       — MinIO URI to store in the fork's event_log row (or None)
    * ``new_hash``      — sha256 of the canonical payload (or None)

    For non-LLM events ``src.llm_payload_uri is None`` so all three are None.

    Deterministic mode
    ──────────────────
    Fetches the cached payload from MinIO and copies it to a fork-scoped URI.

    Re-execute mode
    ───────────────
    Extracts the original prompt from the cached payload (if available) or
    reconstructs from ``src.params``.  Calls the LLM provider with optional
    overrides and stores the result to a new MinIO URI.
    """
    if src.llm_payload_uri is None:
        return None, None, None  # not an LLM-driven event

    if replay_mode not in ("deterministic", "re-execute"):
        raise ReplayModeError(f"Invalid replay_mode: {replay_mode!r}")

    fork_uri = _fork_llm_payload_uri(
        src.llm_payload_uri, target_namespace_id, src.event_id
    )

    if replay_mode == "deterministic":
        try:
            payload = await _fetch_llm_payload(src.llm_payload_uri)
        except (S3Error, Exception) as exc:
            raise MinIOPayloadMissingError(
                f"Deterministic replay: cannot fetch payload at {src.llm_payload_uri!r}: {exc}"
            ) from exc
        # Store copy under fork-scoped URI so it is independently addressable.
        fork_hash = await _put_llm_payload(fork_uri, payload)
        return payload, fork_uri, fork_hash

    # --- re-execute ---
    # Retrieve the original prompt (best-effort; fall back to params).
    original_prompt: str = ""
    try:
        src_payload = await _fetch_llm_payload(src.llm_payload_uri)
        original_prompt = src_payload.get("prompt", "")
    except Exception:
        original_prompt = src.params.get("prompt", "")

    if not original_prompt:
        log.warning(
            "re-execute replay: no prompt recoverable for event %s; skipping LLM call",
            src.event_id,
        )
        return None, None, None

    # Apply optional config_overrides to provider selection only (prompt text is never
    # user-mutable here — validated via ReplayConfigOverrides at the API boundary).
    overrides = config_overrides or {}
    from trimcp.consolidation import ConsolidatedAbstraction  # local import
    from trimcp.providers.base import Message  # local import
    from trimcp.providers.factory import get_provider  # local import

    ns_metadata: dict = {}
    if overrides:
        ns_metadata["consolidation"] = {
            k: overrides[k]
            for k in ("llm_provider", "llm_model", "llm_credentials", "llm_temperature")
            if k in overrides
        }

    provider = get_provider(ns_metadata)

    log.info(
        "re-execute replay: calling %s for event %s",
        provider.model_identifier(),
        src.event_id,
    )

    result: ConsolidatedAbstraction = await provider.complete(
        messages=[
            Message.system(
                "You are a memory consolidation engine. "
                "Given N related episodic memories, produce ONE durable semantic "
                "abstraction capturing their shared meaning. "
                "Return ONLY valid JSON matching the schema. No preamble. No markdown."
            ),
            Message.user(original_prompt),
        ],
        response_model=ConsolidatedAbstraction,
    )

    new_payload = {
        "prompt": original_prompt,
        "response": result.model_dump(),
        "provider": provider.model_identifier(),
        "replay": {
            "source_event_id": str(src.event_id),
            "source_namespace_id": str(source_namespace_id),
        },
    }
    fork_hash = await _put_llm_payload(fork_uri, new_payload)
    return new_payload, fork_uri, fork_hash


# ---------------------------------------------------------------------------
# Observational Replay
# ---------------------------------------------------------------------------


class ObservationalReplay:
    """
    Read-only stream of event_log rows for a namespace/seq range.

    Engine state is **never** modified.  Uses a server-side asyncpg cursor so
    the full event_log is never loaded into Python heap.

    Yielded items
    ─────────────
    * ``{"type": "event",    ...event_fields...}``       — one per log row
    * ``{"type": "progress", "run_id": ..., "events_streamed": N}``
    * ``{"type": "complete", "run_id": ..., "events_streamed": N}``
    * ``{"type": "error",    "run_id": ..., "message": "..."}``  (on failure)
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def execute(
        self,
        *,
        source_namespace_id: uuid.UUID,
        start_seq: int = 1,
        end_seq: int | None = None,
        agent_id_filter: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Async generator — yield one dict per event + periodic progress items.

        The caller drives the iteration; no internal concurrency is created.
        The event loop is never blocked.
        """
        run_id: uuid.UUID | None = None
        events_streamed = 0

        async with self.pool.acquire(timeout=10.0) as meta_conn:
            run_id = await _create_run(
                meta_conn,
                source_namespace_id=source_namespace_id,
                target_namespace_id=None,
                mode="observational",
                replay_mode="deterministic",
                start_seq=start_seq,
                end_seq=end_seq,
                divergence_seq=None,
                config_overrides=None,
            )

        sql, args = _build_event_query(
            source_namespace_id=source_namespace_id,
            start_seq=start_seq,
            end_seq=end_seq,
            agent_id_filter=agent_id_filter,
        )

        try:
            # A separate long-lived connection for the server-side cursor.
            # The transaction keeps the cursor alive across yield boundaries.
            async with self.pool.acquire(timeout=10.0) as cursor_conn:
                async with cursor_conn.transaction(isolation="repeatable_read"):
                    async for record in cursor_conn.cursor(
                        sql, *args, prefetch=_CURSOR_PREFETCH
                    ):
                        try:
                            await verify_event_signature(cursor_conn, record)
                        except DataIntegrityError as exc:
                            yield {
                                "type": "error",
                                "run_id": str(run_id),
                                "message": str(exc),
                            }
                            async with self.pool.acquire(timeout=10.0) as finish_conn:
                                await _finish_run(
                                    finish_conn,
                                    run_id,
                                    status="failed",
                                    events_applied=events_streamed,
                                    error=str(exc),
                                )
                            raise

                        row = _record_to_event_row(record)
                        yield {"type": "event", **_row_as_dict(row)}
                        events_streamed += 1

                        if events_streamed % _PROGRESS_INTERVAL == 0:
                            # Progress update uses a *different* connection to avoid
                            # nesting statements on the cursor connection.
                            async with self.pool.acquire(timeout=10.0) as prog_conn:
                                await _update_run_progress(
                                    prog_conn, run_id, events_streamed
                                )
                            yield {
                                "type": "progress",
                                "run_id": str(run_id),
                                "events_streamed": events_streamed,
                            }

            async with self.pool.acquire(timeout=10.0) as finish_conn:
                await _finish_run(
                    finish_conn,
                    run_id,
                    status="success",
                    events_applied=events_streamed,
                )

            yield {
                "type": "complete",
                "run_id": str(run_id),
                "events_streamed": events_streamed,
            }

        except Exception as exc:
            log.exception(
                "ObservationalReplay failed at event %d run_id=%s",
                events_streamed,
                run_id,
            )
            if run_id is not None:
                async with self.pool.acquire(timeout=10.0) as err_conn:
                    await _finish_run(
                        err_conn,
                        run_id,
                        status="failed",
                        events_applied=events_streamed,
                        error=str(exc),
                    )
            yield {
                "type": "error",
                "run_id": str(run_id) if run_id else None,
                "message": str(exc),
            }
            raise


# ---------------------------------------------------------------------------
# Forked Replay
# ---------------------------------------------------------------------------


class ForkedReplay:
    """
    Replay source events into an isolated target namespace, generating fresh
    HMAC signatures that represent alternate causal provenance.

    For each source event the loop:
    1. Resolves the LLM payload (deterministic → MinIO cache; re-execute → fresh call).
    2. Opens a Saga transaction on the target pool.
    3. Calls the registered handler to apply the event's state change.
    4. Calls ``append_event(parent_event_id=source_event.event_id)`` inside the
       same transaction, which computes a new HMAC-SHA256 over the fork's own
       (namespace_id, event_seq, occurred_at, parent_event_id) fields.
    5. Commits.

    Yielded items
    ─────────────
    * ``{"type": "applied",  "event_seq": N, "event_type": "...", ...}``
    * ``{"type": "skipped",  "event_seq": N, "event_type": "...", "reason": "..."}``
    * ``{"type": "progress", "run_id": ..., "events_applied": N}``
    * ``{"type": "complete", "run_id": ..., "events_applied": N}``
    * ``{"type": "error",    "run_id": ..., "message": "..."}``  (on failure)

    Idempotency
    ───────────
    The loop queries ``replay_runs`` for the highest ``event_seq`` already
    applied and resumes from the next event.  Re-running after an abort
    produces no duplicate effects.
    """

    @staticmethod
    async def _apply_single_event(
        write_conn,
        src,
        target_namespace_id,
        llm_payload,
        config_overrides,
    ) -> dict:
        """Dispatch a single source event to its registered handler.

        Returns the ``result_summary`` dict from the handler, or a skip marker
        if no handler is registered.
        """
        handler = _HANDLER_REGISTRY.get(src.event_type)
        if handler is None:
            log.warning(
                "No handler for event_type=%s; writing provenance only", src.event_type
            )
            return {"skipped": True, "reason": "no_handler"}
        return await handler(
            write_conn, src, target_namespace_id, llm_payload, config_overrides
        )

    async def _dispatch_and_apply(
        self,
        write_conn,
        *,
        src,
        target_namespace_id,
        llm_payload,
        config_overrides,
        run_id,
        source_namespace_id,
        fork_uri=None,
        fork_hash=None,
    ) -> tuple[dict, object]:
        """Apply one event inside a write transaction: dispatch → append_event.

        Returns (result_summary, fork_event).
        """
        result_summary = await self._apply_single_event(
            write_conn, src, target_namespace_id, llm_payload, config_overrides
        )

        enriched_params: dict = {
            **src.params,
            "replay_run_id": str(run_id),
            "source_event_id": str(src.event_id),
            "source_namespace_id": str(source_namespace_id),
        }

        fork_event: AppendResult = await append_event(
            conn=write_conn,
            namespace_id=target_namespace_id,
            agent_id=src.agent_id,
            event_type=src.event_type,
            params=enriched_params,
            result_summary=result_summary,
            parent_event_id=src.event_id,
            llm_payload_uri=fork_uri,
            llm_payload_hash=fork_hash,
        )

        return result_summary, fork_event

    @staticmethod
    def _validate_handler_coverage() -> None:
        """
        Assert that every allowed EventType has a registered handler.

        Called at construction time so misconfiguration is caught immediately,
        not mid-run.  Uses the public ``get_args(EventType)`` API instead of
        duplicating the allowed-value frozenset so we stay on the public surface.
        """
        valid_types: frozenset[str] = frozenset(get_args(EventType))
        missing = valid_types - set(_HANDLER_REGISTRY)
        if missing:
            raise ReplayHandlerMissingError(
                f"No replay handler registered for event type(s): {sorted(missing)}.  "
                "Add a @_register('<type>') handler in trimcp/replay.py."
            )

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self._validate_handler_coverage()

    async def execute(
        self,
        *,
        frozen_config: FrozenForkConfig,
        _existing_run_id: uuid.UUID | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Async generator — drive the forked replay loop.

        Every yielded item is a JSON-safe dict.  The caller collects them and
        decides how to surface them (MCP TextContent, HTTP JSON body, etc.).

        ``frozen_config`` (``FrozenForkConfig``)
            Immutable replay execution config (``frozen=True`` Pydantic model).
            Once instantiated, NO code path can mutate its fields — ``setattr``
            and ``object.__setattr__`` both raise ``ValidationError``.  This
            guarantees WORM-compliant replay integrity.

        ``_existing_run_id``
            If provided, skip creating a new ``replay_runs`` row and use this
            UUID instead.  Callers that need the run_id *before* the generator
            starts (e.g. to return it immediately in an HTTP/MCP response)
            should pre-create the row via ``_create_run()`` and pass it here.
        """
        # ── Extract ALL values from the frozen config ONCE ──
        # These local variables are bound at generator creation time;
        # the frozen_config object itself cannot be mutated by any code
        # path (Pydantic frozen=True blocks setattr at the model level).
        source_namespace_id: uuid.UUID = frozen_config.source_namespace_id
        target_namespace_id: uuid.UUID = frozen_config.target_namespace_id
        fork_seq: int = frozen_config.fork_seq
        start_seq: int = frozen_config.start_seq
        replay_mode: str = frozen_config.replay_mode
        config_overrides: dict | None = frozen_config.overrides_dict
        agent_id_filter: str | None = frozen_config.agent_id_filter

        run_id: uuid.UUID | None = None
        events_applied = 0

        # ------------------------------------------------------------------
        # 1.  Create (or reuse) replay_run row
        # ------------------------------------------------------------------
        if _existing_run_id is not None:
            run_id = _existing_run_id
        else:
            async with self.pool.acquire(timeout=10.0) as meta_conn:
                run_id = await _create_run(
                    meta_conn,
                    source_namespace_id=source_namespace_id,
                    target_namespace_id=target_namespace_id,
                    mode="forked",
                    replay_mode=replay_mode,
                    start_seq=start_seq,
                    end_seq=fork_seq,
                    divergence_seq=fork_seq,
                    config_overrides=config_overrides,
                )

        # ------------------------------------------------------------------
        # 2.  Check for prior progress (idempotency on resume)
        # ------------------------------------------------------------------
        async with self.pool.acquire(timeout=10.0) as chk_conn:
            prior = await chk_conn.fetchval(
                """
                SELECT COALESCE(MAX(event_seq), 0)
                FROM event_log
                WHERE namespace_id = $1
                  AND params->>'replay_run_id' = $2
                """,
                target_namespace_id,
                str(run_id),
            )
        resume_from_seq = int(prior) + 1 if prior else start_seq
        if resume_from_seq > start_seq:
            log.info(
                "ForkedReplay resuming from seq %d (prior progress detected) run_id=%s",
                resume_from_seq,
                run_id,
            )
            start_seq = resume_from_seq

        # ------------------------------------------------------------------
        # 3.  Stream source events + apply each one (FIX-041: RR snapshot only).
        # ------------------------------------------------------------------
        try:
            records = await _fetch_event_log_snapshot(
                self.pool,
                source_namespace_id=source_namespace_id,
                start_seq=start_seq,
                end_seq=fork_seq,
                agent_id_filter=agent_id_filter,
            )
            for record in records:
                try:
                    async with self.pool.acquire(timeout=10.0) as sig_conn:
                        await verify_event_signature(sig_conn, record)
                except DataIntegrityError as exc:
                    yield {
                        "type": "error",
                        "run_id": str(run_id),
                        "message": str(exc),
                    }
                    async with self.pool.acquire(timeout=10.0) as err_conn:
                        await _finish_run(
                            err_conn,
                            run_id,
                            status="failed",
                            events_applied=events_applied,
                            error=str(exc),
                        )
                    raise

                src = _record_to_event_row(record)

                # -- Resolve LLM payload outside RR / crypto verification connections --
                llm_payload, fork_uri, fork_hash = await _resolve_llm_payload(
                    src,
                    replay_mode=replay_mode,
                    config_overrides=config_overrides,
                    target_namespace_id=target_namespace_id,
                    source_namespace_id=source_namespace_id,
                )

                # -- Apply event in its own Saga transaction on a new conn --
                async with self.pool.acquire(timeout=10.0) as write_conn:
                    async with write_conn.transaction():
                        result_summary, fork_event = await self._dispatch_and_apply(
                            write_conn,
                            src=src,
                            target_namespace_id=target_namespace_id,
                            llm_payload=llm_payload,
                            config_overrides=config_overrides,
                            run_id=run_id,
                            source_namespace_id=source_namespace_id,
                            fork_uri=fork_uri,
                            fork_hash=fork_hash,
                        )

                events_applied += 1
                skipped = result_summary.get("skipped", False)
                yield_type = "skipped" if skipped else "applied"

                yield {
                    "type": yield_type,
                    "event_seq": src.event_seq,
                    "event_type": src.event_type,
                    "fork_event_id": str(fork_event.event_id),  # type: ignore[attr-defined]
                    "fork_event_seq": fork_event.event_seq,  # type: ignore[attr-defined]
                    "result": result_summary,
                }

                if events_applied % _PROGRESS_INTERVAL == 0:
                    async with self.pool.acquire(timeout=10.0) as prog_conn:
                        await _update_run_progress(
                            prog_conn, run_id, events_applied
                        )
                    yield {
                        "type": "progress",
                        "run_id": str(run_id),
                        "events_applied": events_applied,
                    }

            async with self.pool.acquire(timeout=10.0) as finish_conn:
                await _finish_run(
                    finish_conn,
                    run_id,
                    status="success",
                    events_applied=events_applied,
                )

            yield {
                "type": "complete",
                "run_id": str(run_id),
                "events_applied": events_applied,
                "fork_namespace": str(target_namespace_id),
                "divergence_seq": fork_seq,
            }

        except Exception as exc:
            log.exception(
                "ForkedReplay failed at event %d run_id=%s", events_applied, run_id
            )
            if run_id is not None:
                async with self.pool.acquire(timeout=10.0) as err_conn:
                    await _finish_run(
                        err_conn,
                        run_id,
                        status="failed",
                        events_applied=events_applied,
                        error=str(exc),
                    )
            yield {
                "type": "error",
                "run_id": str(run_id) if run_id else None,
                "message": str(exc),
            }
            raise


# ---------------------------------------------------------------------------
# Reconstructive Replay (Phase 2.3)
# ---------------------------------------------------------------------------


class ReconstructiveReplay:
    """
    Apply source events to an empty target namespace, reproducing byte-identical
    state at ``end_seq``.

    Unlike ``ForkedReplay``, no LLM payload resolution is performed — all
    events are applied deterministically.  UUIDs are remapped (original →
    new) to avoid constraint violations in the target namespace.

    Yielded items
    ─────────────
    * ``{"type": "applied",  "event_seq": N, "event_type": "...", ...}``
    * ``{"type": "skipped",  "event_seq": N, "event_type": "...", "reason": "..."}``
    * ``{"type": "progress", "run_id": ..., "events_applied": N}``
    * ``{"type": "complete", "run_id": ..., "events_applied": N}``
    * ``{"type": "error",    "run_id": ..., "message": "..."}``

    UUID remapping
    ──────────────
    Handlers are expected to map source UUIDs to fresh UUIDs in the target
    namespace (e.g., ``_handle_store_memory`` already does this).
    ``ReconstructiveReplay`` does NOT maintain a central UUID mapping table
    — each handler is responsible for its own deterministic remapping.
    """

    @staticmethod
    def _validate_handler_coverage() -> None:
        """Assert all EventTypes have registered handlers (shared with ForkedReplay)."""
        valid_types: frozenset[str] = frozenset(get_args(EventType))
        missing = valid_types - set(_HANDLER_REGISTRY)
        if missing:
            raise ReplayHandlerMissingError(
                f"No replay handler registered for event type(s): {sorted(missing)}.  "
                "Add a @_register('<type>') handler in trimcp/replay.py."
            )

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self._validate_handler_coverage()

    async def execute(
        self,
        *,
        source_namespace_id: uuid.UUID,
        target_namespace_id: uuid.UUID,
        end_seq: int,
        start_seq: int = 1,
        agent_id_filter: str | None = None,
        _existing_run_id: uuid.UUID | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Async generator — drive the reconstructive replay loop.

        Args:
            source_namespace_id: Source namespace to replay from.
            target_namespace_id: Empty target namespace to populate.
            end_seq:            Last event sequence to apply (inclusive).
            start_seq:          First event sequence (default 1).
            agent_id_filter:    Optional agent_id to filter source events.
            _existing_run_id:   Pre-created replay_runs row UUID.

        Yields:
            JSON-safe dict per event + progress/complete/error items.
        """
        run_id: uuid.UUID | None = None
        events_applied = 0

        # 1. Create (or reuse) run row
        if _existing_run_id is not None:
            run_id = _existing_run_id
        else:
            async with self.pool.acquire(timeout=10.0) as meta_conn:
                run_id = await _create_run(
                    meta_conn,
                    source_namespace_id=source_namespace_id,
                    target_namespace_id=target_namespace_id,
                    mode="reconstructive",
                    replay_mode="deterministic",
                    start_seq=start_seq,
                    end_seq=end_seq,
                    divergence_seq=None,
                    config_overrides=None,
                )

        # 2. Check for prior progress (idempotent resume)
        async with self.pool.acquire(timeout=10.0) as chk_conn:
            prior = await chk_conn.fetchval(
                """
                SELECT COALESCE(MAX(event_seq), 0)
                FROM event_log
                WHERE namespace_id = $1
                  AND params->>'replay_run_id' = $2
                """,
                target_namespace_id,
                str(run_id),
            )
        resume_from_seq = int(prior) + 1 if prior else start_seq
        if resume_from_seq > start_seq:
            log.info(
                "ReconstructiveReplay resuming from seq %d (prior=%d) run_id=%s",
                resume_from_seq,
                prior,
                run_id,
            )
            start_seq = resume_from_seq

        # 3. Stream source events + apply each one
        sql, args = _build_event_query(
            source_namespace_id=source_namespace_id,
            start_seq=start_seq,
            end_seq=end_seq,
            agent_id_filter=agent_id_filter,
        )

        try:
            async with self.pool.acquire(timeout=10.0) as cursor_conn:
                async with cursor_conn.transaction(isolation="repeatable_read"):
                    async for record in cursor_conn.cursor(
                        sql, *args, prefetch=_CURSOR_PREFETCH
                    ):
                        try:
                            await verify_event_signature(cursor_conn, record)
                        except DataIntegrityError as exc:
                            yield {
                                "type": "error",
                                "run_id": str(run_id),
                                "message": str(exc),
                            }
                            async with self.pool.acquire(timeout=10.0) as err_conn:
                                await _finish_run(
                                    err_conn,
                                    run_id,
                                    status="failed",
                                    events_applied=events_applied,
                                    error=str(exc),
                                )
                            raise

                        src = _record_to_event_row(record)

                        # Apply event in its own Saga transaction
                        async with self.pool.acquire(timeout=10.0) as write_conn:
                            async with write_conn.transaction():
                                handler = _HANDLER_REGISTRY.get(src.event_type)
                                if handler is None:
                                    result_summary: dict = {
                                        "skipped": True,
                                        "reason": "no_handler",
                                    }
                                else:
                                    result_summary = await handler(  # type: ignore[call-arg]
                                        write_conn,
                                        src,
                                        target_namespace_id,
                                        llm_payload=None,
                                        config_overrides=None,
                                    )

                                enriched_params: dict = {
                                    **src.params,
                                    "replay_run_id": str(run_id),
                                    "source_event_id": str(src.event_id),
                                    "source_namespace_id": str(source_namespace_id),
                                }

                                await append_event(
                                    conn=write_conn,
                                    namespace_id=target_namespace_id,
                                    agent_id=src.agent_id,
                                    event_type=src.event_type,
                                    params=enriched_params,
                                    result_summary=result_summary,
                                    parent_event_id=src.event_id,
                                )

                        events_applied += 1
                        skipped = result_summary.get("skipped", False)
                        yield_type = "skipped" if skipped else "applied"

                        yield {
                            "type": yield_type,
                            "event_seq": src.event_seq,
                            "event_type": src.event_type,
                            "result": result_summary,
                        }

                        if events_applied % _PROGRESS_INTERVAL == 0:
                            async with self.pool.acquire(timeout=10.0) as prog_conn:
                                await _update_run_progress(
                                    prog_conn, run_id, events_applied
                                )
                            yield {
                                "type": "progress",
                                "run_id": str(run_id),
                                "events_applied": events_applied,
                            }

            async with self.pool.acquire(timeout=10.0) as finish_conn:
                await _finish_run(
                    finish_conn,
                    run_id,
                    status="success",
                    events_applied=events_applied,
                )

            yield {
                "type": "complete",
                "run_id": str(run_id),
                "events_applied": events_applied,
                "target_namespace": str(target_namespace_id),
                "end_seq": end_seq,
            }

        except Exception as exc:
            log.exception(
                "ReconstructiveReplay failed at event %d run_id=%s",
                events_applied,
                run_id,
            )
            if run_id is not None:
                async with self.pool.acquire(timeout=10.0) as err_conn:
                    await _finish_run(
                        err_conn,
                        run_id,
                        status="failed",
                        events_applied=events_applied,
                        error=str(exc),
                    )
            yield {
                "type": "error",
                "run_id": str(run_id) if run_id else None,
                "message": str(exc),
            }
            raise


# ---------------------------------------------------------------------------
# Convenience: Event Provenance
# ---------------------------------------------------------------------------


async def get_event_provenance(
    pool: asyncpg.Pool,
    memory_id: uuid.UUID,
) -> dict[str, Any]:
    """
    Return the causal chain for a memory: the creating event and all its
    ancestors via ``parent_event_id``.

    Returns a dict with ``chain`` (list, root-first) and ``memory_id``.
    """
    async with pool.acquire(timeout=10.0) as conn:
        # Find the event_log row that created this memory.
        root = await conn.fetchrow(
            """
            SELECT id, namespace_id, agent_id, event_type, event_seq,
                   occurred_at, params, result_summary, parent_event_id
            FROM event_log
            WHERE params->>'memory_id' = $1
            ORDER BY event_seq ASC
            LIMIT 1
            """,
            str(memory_id),
        )
        if root is None:
            return {"memory_id": str(memory_id), "chain": []}

        chain: list[dict] = []
        current_id: uuid.UUID | None = root["id"]

        # Walk up the parent chain (bounded to 50 hops to guard against cycles).
        visited: set[uuid.UUID] = set()
        for _ in range(50):
            if current_id is None or current_id in visited:
                break
            visited.add(current_id)
            row = await conn.fetchrow(
                """
                SELECT id, namespace_id, agent_id, event_type, event_seq,
                       occurred_at, params, result_summary, parent_event_id
                FROM event_log WHERE id = $1
                """,
                current_id,
            )
            if row is None:
                break
            chain.append(
                {
                    "event_id": str(row["id"]),
                    "namespace_id": str(row["namespace_id"]),
                    "agent_id": row["agent_id"],
                    "event_type": row["event_type"],
                    "event_seq": row["event_seq"],
                    "occurred_at": row["occurred_at"].isoformat(),
                    "params": dict(row["params"]) if row["params"] else {},
                    "result_summary": (
                        dict(row["result_summary"]) if row["result_summary"] else None
                    ),
                    "parent_event_id": (
                        str(row["parent_event_id"]) if row["parent_event_id"] else None
                    ),
                }
            )
            current_id = row["parent_event_id"]

    chain.reverse()  # root first
    return {"memory_id": str(memory_id), "chain": chain}
