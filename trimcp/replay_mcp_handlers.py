"""
MCP tool handlers for event replay operations (§10). Extracted from server.py:call_tool().
Follows the same pattern as bridge_mcp_handlers.py — each handler receives the engine
and raw arguments dict, and returns a JSON string that call_tool() wraps in TextContent.

Note: Admin authorization (_check_admin) is handled by call_tool() as a cross-cutting
concern — handlers focus purely on domain logic.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from trimcp.background_task_manager import create_tracked_task
from trimcp.mcp_errors import mcp_handler
from trimcp.orchestrator import TriStackEngine

log = logging.getLogger("trimcp.replay_mcp_handlers")


@mcp_handler
async def handle_replay_observe(
    engine: TriStackEngine, arguments: dict[str, Any]
) -> str:
    """[ADMIN] Observational replay — reads event log and replays events."""
    from trimcp.replay import ObservationalReplay

    replay = ObservationalReplay(pool=engine.pg_pool)
    lines: list[str] = []
    count = 0
    async for item in replay.execute(
        source_namespace_id=uuid.UUID(arguments["namespace_id"]),
        start_seq=int(arguments.get("start_seq", 1)),
        end_seq=int(arguments["end_seq"]) if "end_seq" in arguments else None,
        agent_id_filter=arguments.get("agent_id_filter"),
    ):
        lines.append(json.dumps(item))
        if item.get("type") == "event":
            count += 1
            if count >= int(arguments.get("max_events", 500)):
                lines.append(
                    json.dumps({"type": "truncated", "reason": "max_events_reached"})
                )
                break
    return "\n".join(lines)


@mcp_handler
async def handle_replay_fork(engine: TriStackEngine, arguments: dict[str, Any]) -> str:
    """[ADMIN] Forked replay — creates a new namespace from a fork point."""
    from pydantic import ValidationError

    from trimcp.models import FrozenForkConfig, ReplayForkRequest
    from trimcp.replay import ForkedReplay, _create_run

    try:
        fork_req = ReplayForkRequest.model_validate(
            {
                "source_namespace_id": arguments["source_namespace_id"],
                "target_namespace_id": arguments["target_namespace_id"],
                "fork_seq": int(arguments["fork_seq"]),
                "start_seq": int(arguments.get("start_seq", 1)),
                "replay_mode": arguments.get("replay_mode", "deterministic"),
                "config_overrides": arguments.get("config_overrides"),
                "agent_id_filter": arguments.get("agent_id_filter"),
                "expected_sha256": arguments["expected_sha256"],
            }
        )
    except (ValidationError, KeyError) as exc:
        raise ValueError(f"Invalid replay_fork parameters: {exc}") from exc

    # ── Build the frozen execution config (immutable after this point) ──
    frozen_config = FrozenForkConfig.from_request(fork_req)

    async with engine.pg_pool.acquire(timeout=10.0) as pre_conn:
        fork_run_id = await _create_run(
            pre_conn,
            source_namespace_id=frozen_config.source_namespace_id,
            target_namespace_id=frozen_config.target_namespace_id,
            mode="forked",
            replay_mode=frozen_config.replay_mode,
            start_seq=frozen_config.start_seq,
            end_seq=frozen_config.fork_seq,
            divergence_seq=frozen_config.fork_seq,
            config_overrides=frozen_config.overrides_dict,
        )

    replay = ForkedReplay(pool=engine.pg_pool)

    async def _run_fork():
        try:
            async for _ in replay.execute(
                frozen_config=frozen_config,
                _existing_run_id=fork_run_id,
            ):
                pass
        except Exception:
            log.exception("Replay failed")

    await create_tracked_task(_run_fork(), name=f"fork-{fork_run_id}")
    return json.dumps({"status": "started", "run_id": str(fork_run_id)})


@mcp_handler
async def handle_replay_reconstruct(
    engine: TriStackEngine, arguments: dict[str, Any]
) -> str:
    """[ADMIN] Reconstructive replay — reproduces byte-identical state at end_seq."""
    from trimcp.replay import ReconstructiveReplay, _create_run

    src_ns = uuid.UUID(arguments["source_namespace_id"])
    tgt_ns = uuid.UUID(arguments["target_namespace_id"])
    end_seq = int(arguments["end_seq"])
    start_seq = int(arguments.get("start_seq", 1))
    agent_filter = arguments.get("agent_id_filter")

    async with engine.pg_pool.acquire(timeout=10.0) as pre_conn:
        run_id = await _create_run(
            pre_conn,
            source_namespace_id=src_ns,
            target_namespace_id=tgt_ns,
            mode="reconstructive",
            replay_mode="deterministic",
            start_seq=start_seq,
            end_seq=end_seq,
            divergence_seq=None,
            config_overrides=None,
        )

    replay = ReconstructiveReplay(pool=engine.pg_pool)

    async def _run():
        try:
            async for _ in replay.execute(
                source_namespace_id=src_ns,
                target_namespace_id=tgt_ns,
                end_seq=end_seq,
                start_seq=start_seq,
                agent_id_filter=agent_filter,
                _existing_run_id=run_id,
            ):
                pass
        except Exception:
            log.exception("Reconstructive replay failed")

    await create_tracked_task(_run(), name=f"reconstruct-{run_id}")
    return json.dumps({"status": "started", "run_id": str(run_id)})


@mcp_handler
async def handle_replay_status(
    engine: TriStackEngine, arguments: dict[str, Any]
) -> str:
    """[ADMIN] Check the status of a replay run."""
    from trimcp.replay import get_run_status

    status = await get_run_status(engine.pg_pool, uuid.UUID(arguments["run_id"]))
    return json.dumps(status)


@mcp_handler
async def handle_get_event_provenance(
    engine: TriStackEngine, arguments: dict[str, Any]
) -> str:
    """Get the full provenance chain for a memory."""
    from trimcp.replay import get_event_provenance

    provenance = await get_event_provenance(
        engine.pg_pool, uuid.UUID(arguments["memory_id"])
    )
    return json.dumps(provenance)
