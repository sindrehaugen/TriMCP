"""
MCP tool handlers for time-travel snapshots (§9).

Thin transport adapter — delegates data transformation to
``trimcp.snapshot_serializer`` so the snapshot serialization logic can be
unit-tested independently of the MCP transport layer.

Each handler receives the engine and raw arguments dict, builds a request
object via the serializer, calls the engine, and returns a JSON string
that ``call_tool()`` wraps in ``TextContent``.

Streaming export
────────────────
``stream_snapshot_export()`` is an async generator that yields NDJSON
lines for HTTP streaming.  It uses a server-side asyncpg cursor so the
full export is never materialised in Python heap memory — enabling
GB-scale tenant exports without crashing the orchestrator.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from trimcp.mcp_errors import mcp_handler
from trimcp.orchestrator import TriStackEngine
from trimcp.snapshot_serializer import (
    SNAPSHOT_ARG_KEYS,
    build_compare_states_request,
    build_create_snapshot_request,
    serialize_delete_result,
    serialize_snapshot_list,
    serialize_snapshot_record,
    serialize_state_diff,
)

log = logging.getLogger("trimcp.snapshot_mcp_handlers")

# ── Stream batching constants ─────────────────────────────────────────────
_STREAM_BATCH_SIZE: int = 500  # rows per server-side cursor fetch
_STREAM_PROGRESS_INTERVAL: int = 1000  # emit a progress line every N rows


@mcp_handler
async def handle_create_snapshot(
    engine: TriStackEngine, arguments: dict[str, Any]
) -> str:
    """Create a named point-in-time reference for a namespace."""
    req = build_create_snapshot_request(arguments)
    res = await engine.create_snapshot(req)
    return serialize_snapshot_record(res)


@mcp_handler
async def handle_list_snapshots(
    engine: TriStackEngine, arguments: dict[str, Any]
) -> str:
    """List all snapshots for a namespace."""
    res = await engine.list_snapshots(arguments[SNAPSHOT_ARG_KEYS.NAMESPACE_ID])
    return serialize_snapshot_list(res)


@mcp_handler
async def handle_delete_snapshot(
    engine: TriStackEngine, arguments: dict[str, Any]
) -> str:
    """Delete a point-in-time reference."""
    res = await engine.delete_snapshot(
        snapshot_id=arguments[SNAPSHOT_ARG_KEYS.SNAPSHOT_ID],
        namespace_id=arguments[SNAPSHOT_ARG_KEYS.NAMESPACE_ID],
    )
    return serialize_delete_result(res)


@mcp_handler
async def handle_compare_states(
    engine: TriStackEngine, arguments: dict[str, Any]
) -> str:
    """Diff two temporal views of a namespace."""
    req = build_compare_states_request(arguments)
    res = await engine.compare_states(req)
    return serialize_state_diff(res)


# ── Streaming export ──────────────────────────────────────────────────────
# Used by the admin HTTP server to stream large snapshot exports as NDJSON.
# Avoids buffering the full dataset in RAM by using a server-side cursor.


async def stream_snapshot_export(
    engine: TriStackEngine,
    namespace_id: str,
    *,
    as_of: datetime | None = None,
    snapshot_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Yield NDJSON lines for a namespace's full snapshot export.

    Uses a server-side asyncpg cursor to batch-fetch memories, keeping
    orchestrator RAM usage flat regardless of export size.

    Args:
        engine: The TriStackEngine with connected pg_pool.
        namespace_id: Target namespace UUID as string.
        as_of: Point-in-time for the export (defaults to now).
        snapshot_id: Optional snapshot ID; resolved to ``as_of`` if given.

    Yields:
        NDJSON lines (``{"type": "metadata"|"memory"|"progress"|"complete"}``).
    """
    if not engine.pg_pool:
        yield json.dumps({"type": "error", "message": "Engine not connected"}) + "\n"
        return

    ns_uuid = uuid.UUID(namespace_id)
    export_as_of = as_of or datetime.now(timezone.utc)

    # ── Resolve snapshot_id to as_of ─────────────────────────────────────
    if snapshot_id:
        try:
            snap_uuid = uuid.UUID(snapshot_id)
            async with engine.pg_pool.acquire(timeout=10.0) as conn:
                snap_row = await conn.fetchrow(
                    "SELECT snapshot_at FROM snapshots WHERE id = $1 AND namespace_id = $2",
                    snap_uuid,
                    ns_uuid,
                )
                if snap_row:
                    export_as_of = snap_row["snapshot_at"]
                    log.info(
                        "Snapshot export resolved %s → as_of=%s",
                        snapshot_id,
                        export_as_of.isoformat(),
                    )
                else:
                    yield (
                        json.dumps(
                            {
                                "type": "error",
                                "message": f"Snapshot {snapshot_id} not found",
                            }
                        )
                        + "\n"
                    )
                    return
        except ValueError:
            yield (
                json.dumps(
                    {
                        "type": "error",
                        "message": f"Invalid snapshot_id: {snapshot_id}",
                    }
                )
                + "\n"
            )
            return

    # ── Export header ────────────────────────────────────────────────────
    yield (
        json.dumps(
            {
                "type": "metadata",
                "namespace_id": namespace_id,
                "as_of": export_as_of.isoformat(),
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "format": "trimcp-snapshot-export-v1",
            }
        )
        + "\n"
    )

    # ── Stream memories via server-side cursor ───────────────────────────
    total = 0
    try:
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
            # Count total rows first (lightweight)
            count_row = await conn.fetchrow(
                """
                SELECT COUNT(*)::bigint AS total
                FROM memories
                WHERE namespace_id = $1
                  AND valid_from <= $2
                  AND (valid_to IS NULL OR valid_to > $2)
                """,
                ns_uuid,
                export_as_of,
            )
            total_expected = int(count_row["total"]) if count_row else 0

            # Server-side cursor — never materialises full result set
            async with conn.transaction():
                cursor = conn.cursor(
                    """
                    SELECT
                        m.id AS memory_id,
                        m.namespace_id,
                        m.agent_id,
                        m.payload_ref,
                        m.assertion_type,
                        m.memory_type,
                        m.valid_from,
                        m.pii_redacted,
                        m.derived_from,
                        COALESCE(m.metadata, '{}'::jsonb) AS metadata,
                        (SELECT ms.salience_score
                         FROM memory_salience ms
                         WHERE ms.memory_id = m.id
                           AND ms.namespace_id = m.namespace_id
                         ORDER BY ms.updated_at DESC NULLS LAST
                         LIMIT 1) AS salience
                    FROM memories m
                    WHERE m.namespace_id = $1
                      AND m.valid_from <= $2
                      AND (m.valid_to IS NULL OR m.valid_to > $2)
                    ORDER BY m.valid_from ASC
                    """,
                    ns_uuid,
                    export_as_of,
                )

                async for batch in cursor.fetchmany(_STREAM_BATCH_SIZE):
                    for row in batch:
                        memory = _serialize_memory_row(row)
                        yield (
                            json.dumps(
                                {
                                    "type": "memory",
                                    "memory": memory,
                                }
                            )
                            + "\n"
                        )
                        total += 1

                    # Periodic progress markers
                    if total % _STREAM_PROGRESS_INTERVAL == 0:
                        yield (
                            json.dumps(
                                {
                                    "type": "progress",
                                    "exported": total,
                                    "total_expected": total_expected,
                                }
                            )
                            + "\n"
                        )

    except Exception as exc:
        log.exception("Snapshot export failed at memory %d", total)
        yield (
            json.dumps(
                {
                    "type": "error",
                    "message": f"Export failed after {total} records: {exc}",
                }
            )
            + "\n"
        )
        return

    # ── Completion ───────────────────────────────────────────────────────
    yield (
        json.dumps(
            {
                "type": "complete",
                "exported": total,
                "total_expected": total_expected,
            }
        )
        + "\n"
    )

    log.info(
        "Snapshot export complete ns=%s as_of=%s exported=%d expected=%d",
        namespace_id,
        export_as_of.isoformat(),
        total,
        total_expected,
    )


def _serialize_memory_row(row: Any) -> dict[str, Any]:
    """Convert an asyncpg row to a JSON-safe dict.

    Args:
        row: An asyncpg record or dict-like object from a cursor fetch.

    Returns:
        A plain dict with UUIDs → str, datetimes → ISO strings.
    """
    out: dict[str, Any] = {}
    for k, v in dict(row).items():
        if isinstance(v, uuid.UUID):
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.astimezone(timezone.utc).isoformat() if v else None
        elif k == "metadata" and isinstance(v, str):
            out[k] = json.loads(v)
        else:
            out[k] = v
    return out
