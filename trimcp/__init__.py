"""
TriMCP — Tri-Stack Memory Server core package.

This package collapses the Saga orchestrator, embedding engine, AST parser,
graph layer, and background garbage collector behind a single import surface.
The MCP stdio entrypoint (`server.py`) lives at the repo root and imports
everything it needs from here.

Public API — stable names the server.py wrapper (and tests) rely on:
"""
from trimcp.orchestrator import TriStackEngine, MemoryPayload, MediaPayload
from trimcp.garbage_collector import run_gc_loop
from trimcp.config import OrchestratorConfig

__all__ = [
    "TriStackEngine",
    "MemoryPayload",
    "MediaPayload",
    "OrchestratorConfig",
    "run_gc_loop",
]

__version__ = "2.0.0"
