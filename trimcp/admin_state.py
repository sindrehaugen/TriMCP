"""Shared runtime state for the admin HTTP server (avoids circular imports)."""

from __future__ import annotations

from trimcp.orchestrator import TriStackEngine

engine: TriStackEngine | None = None
