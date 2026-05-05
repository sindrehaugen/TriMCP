"""
Phase 2.2 memory time-travel helpers: parse client-supplied ``as_of`` timestamps.
"""

from __future__ import annotations

from datetime import datetime, timezone


def parse_as_of(raw: str | None) -> datetime | None:
    """
    Parse and validate an ISO 8601 timestamp from an MCP tool or REST body.

    Returns a timezone-aware ``datetime`` (UTC-normalised) or ``None`` when
    ``raw`` is absent, which signals "query the current state".

    Raises ``ValueError`` for:
    - Malformed / non-ISO-8601 strings.
    - Timestamps in the future (time-travel reads *past* state only).
    """
    if raw is None:
        return None
    try:
        # ``fromisoformat`` accepts most ISO 8601 variants in Python 3.11+.
        # The ``Z`` suffix is not valid for ``fromisoformat`` before 3.11,
        # so normalize for Python 3.9/3.10 compatibility.
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise ValueError(
            f"as_of must be a valid ISO 8601 timestamp "
            f"(e.g. '2026-01-15T10:00:00Z'), got: {raw!r}"
        )
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt > datetime.now(timezone.utc):
        raise ValueError(
            "as_of must not be in the future — temporal queries read past state only"
        )
    return dt
