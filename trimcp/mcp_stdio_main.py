"""MCP stdio server lifecycle — connect engine, background tasks, stdio transport."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server

from trimcp import TriStackEngine, run_gc_loop
from trimcp.config import assert_admin_override_not_in_production, cfg, redact_secrets_in_text
from trimcp.mcp_stdio_dispatch import execute_call_tool
from trimcp.mcp_stdio_tools import TOOLS

log = logging.getLogger("tri-stack-mcp")


def create_stdio_app(*, engine: TriStackEngine) -> Server:
    """Build the MCP Server with tool handlers bound to ``engine``."""
    app = Server("tri-stack-memory")

    @app.list_tools()
    async def list_tools():
        return TOOLS

    @app.call_tool()
    async def call_tool(name: str, arguments: dict):
        return await execute_call_tool(engine, name, arguments)

    return app


async def run_stdio_server(*, app: Server | None = None, engine: TriStackEngine | None = None) -> None:
    """Connect TriStackEngine, start background loops, and serve MCP over stdio."""
    assert_admin_override_not_in_production()
    
    if engine is None:
        engine = TriStackEngine()

    from trimcp.observability import init_observability

    init_observability()
    log.info("Observability layer initialized.")

    try:
        await engine.connect()
    except Exception as exc:
        log.critical("FATAL: Startup failure: %s", redact_secrets_in_text(str(exc)))
        sys.exit(1)

    log.info("TriStackEngine connected to all database layers.")

    from trimcp.background_task_manager import create_tracked_task

    gc_task = create_tracked_task(run_gc_loop(), name="gc_loop")
    log.info("GC background task started.")

    from trimcp import quotas as _quotas

    quota_flush_task = create_tracked_task(
        _quotas.quota_redis_flush_loop(engine.redis_client, engine.pg_pool),
        name="quota_redis_flush_loop",
    )
    log.info("Quota Redis flush background task started.")

    from trimcp.re_embedder import start_re_embedder

    re_embedder_task = start_re_embedder(engine.pg_pool, engine.mongo_client)
    log.info("Re-embedder background task started.")

    from trimcp.outbox_relay import run_outbox_relay_once

    interval_s = max(1, int(cfg.OUTBOX_RELAY_INTERVAL_SECONDS))

    async def _outbox_relay_loop() -> None:
        while True:
            try:
                delivered = await run_outbox_relay_once(engine.pg_pool)
                if delivered:
                    log.debug("Outbox relay delivered %d event(s).", delivered)
            except Exception:
                log.exception("Outbox relay iteration failed; will retry.")
            await asyncio.sleep(interval_s)

    outbox_relay_task = create_tracked_task(_outbox_relay_loop(), name="outbox_relay_loop")
    log.info("Outbox relay background task started (interval=%ds).", interval_s)

    stdio_app = app or create_stdio_app(engine=engine)
    try:
        async with stdio_server() as (read_stream, write_stream):
            log.info("MCP server listening on stdio.")
            await stdio_app.run(read_stream, write_stream, stdio_app.create_initialization_options())
    finally:
        for task in (gc_task, quota_flush_task, outbox_relay_task, re_embedder_task):
            task.cancel()
        for task in (gc_task, quota_flush_task, outbox_relay_task, re_embedder_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
        await engine.disconnect()
        log.info("Shutdown complete.")
