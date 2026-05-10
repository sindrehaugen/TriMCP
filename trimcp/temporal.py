"""
Phase 2.2 memory time-travel helpers: parse client-supplied ``as_of`` timestamps
and produce parameterised temporal SQL clauses.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trimcp.config import cfg


def parse_as_of(raw: str | None) -> datetime | None:
    """
    Parse and validate an ISO 8601 timestamp from an MCP tool or REST body.

    Returns a timezone-aware ``datetime`` (timezone.utc-normalised) or ``None`` when
    ``raw`` is absent, which signals "query the current state".

    Raises ``ValueError`` for:
    - Malformed / non-ISO-8601 strings.
    - Timestamps in the future (time-travel reads *past* state only).
    - Timestamps older than ``cfg.TRIMCP_MAX_TEMPORAL_LOOKBACK_DAYS``
      (prevents unbounded historical scans of ``event_log``).
    """
    if raw is None:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise ValueError(
            f"as_of must be a valid ISO 8601 timestamp (e.g. '2026-01-15T10:00:00Z'), got: {raw!r}"
        )
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if dt > now:
        raise ValueError(
            "as_of must not be in the future — temporal queries read past state only"
        )
    _enforce_lookback_boundary(dt, now)
    return dt


def _enforce_lookback_boundary(dt: datetime, now: datetime) -> None:
    """Reject *dt* if it exceeds the configured max lookback window.

    Raises ``ValueError`` when the timestamp is older than
    ``cfg.TRIMCP_MAX_TEMPORAL_LOOKBACK_DAYS``.  A value of **0** means
    "no boundary" (operator override for admin maintenance tasks).

    Extracted as a separate function for testability without monkey-patching
    ``parse_as_of``.
    """
    max_days = cfg.TRIMCP_MAX_TEMPORAL_LOOKBACK_DAYS
    if max_days <= 0:
        return
    cutoff = now - timedelta(days=max_days)
    if dt < cutoff:
        raise ValueError(
            f"as_of timestamp {dt.isoformat()} exceeds maximum temporal lookback of "
            f"{max_days} days (earliest allowed: {cutoff.isoformat()}). "
            "Adjust TRIMCP_MAX_TEMPORAL_LOOKBACK_DAYS to increase the window."
        )


def as_of_query(base_query: str, as_of: datetime | None) -> tuple[str, list]:
    """
    Append a parameterised temporal filter to *base_query*.

    When *as_of* is ``None``, queries the current state (``valid_to IS NULL``).
    When *as_of* is provided, restricts to rows valid at that point in time:
    ``valid_from <= as_of AND (valid_to IS NULL OR valid_to > as_of)``.

    Returns ``(sql_clause, param_list)`` suitable for concatenation into a
    pre-existing parameterised query.  The caller is responsible for managing
    ``$N`` parameter index offsets.

    Raises ``ValueError`` if *as_of* is in the future — temporal queries must
    never read non-existent future state (causality boundary enforcement).

    Example::

        clause, params = as_of_query("...", as_of=my_timestamp)
        sql = f"SELECT ... WHERE namespace_id = $1 {clause}"
        full_params = [ns_id] + params
    """
    if as_of is None:
        return "AND valid_to IS NULL", []
    now = datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    if as_of > now:
        raise ValueError(
            "as_of must not be in the future — temporal queries read past state only"
        )
    return (
        "AND valid_from <= $1 AND (valid_to IS NULL OR valid_to > $1)",
        [as_of],
    )


def validate_write_timestamp(ts: datetime | None) -> None:
    """
    Reject writes with timestamps in the future (D8 time-travel integrity).

    Raises ``ValueError`` if *ts* is in the future.
    No-op when *ts* is ``None`` (server assigns ``NOW()``).
    """
    if ts is None:
        return
    now = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if ts > now:
        raise ValueError(f"Write timestamp must not be in the future: {ts.isoformat()}")
