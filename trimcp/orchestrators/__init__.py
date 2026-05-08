"""Domain orchestrators — extracted from TriStackEngine per Clean Code (Uncle Bob) SRP split.

Each orchestrator receives shared connection pools (PG, Mongo, Redis) via constructor
injection.  TriStackEngine creates them during connect() and delegates method calls
through thin pass-through wrappers for backward compatibility.
"""

from trimcp.orchestrators.memory import MemoryOrchestrator

__all__ = ["MemoryOrchestrator"]
