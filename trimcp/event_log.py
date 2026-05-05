"""
TriMCP append-only tamper-resistant event log writer (Phase 0.2 / 2.3).

Design contract
---------------

WORM guarantee
    This module has NO UPDATE or DELETE code paths.  All writes are INSERT-only.
    The Postgres role-level enforcement (``REVOKE UPDATE, DELETE ON event_log
    FROM trimcp_app``) is the primary WORM layer; this module is defence-in-depth.

Atomicity with Saga
    ``append_event()`` must be called inside an EXISTING asyncpg transaction
    (the Saga coordinator has already issued BEGIN).  This function never
    commits, rolls back, or opens its own transaction.  A rolled-back Saga
    produces no ``event_log`` entry — atomicity is guaranteed by the shared
    transaction.

Gap-free per-namespace sequence numbers
    ``event_seq`` is monotonically increasing per ``namespace_id`` with no gaps.
    Allocation is serialised via a transaction-scoped advisory lock keyed to the
    namespace UUID (``pg_advisory_xact_lock``).  The lock is released
    automatically on transaction commit/rollback — no manual cleanup needed.

Signature over DB-provided timestamp
    ``occurred_at`` is always set by the DB (``clock_timestamp()`` fetched in a
    preliminary round-trip) so the signature covers the value that is actually
    stored.  This closes the window where a Python-side clock and the DB clock
    diverge.

Point-in-time write rejection (D8)
    ``occurred_at`` is always ``now()`` on the DB.  The ``params`` dict must NOT
    contain a ``valid_from`` field with a past timestamp; this is validated
    before the INSERT.  Raw SQL back-dating is blocked by the DB schema
    (``DEFAULT now()``) and the WORM role grants.

Usage
-----
::

    async with conn.transaction():          # Saga coordinator opens the TX
        # ... other Saga mutations ...
        result = await append_event(
            conn=conn,
            namespace_id=ns_id,
            agent_id="retrieval-agent",
            event_type="store_memory",
            params={"memory_id": str(memory_id), "assertion_type": "fact"},
        )
        # result.event_id, result.event_seq, result.occurred_at are now set.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final, Literal, Optional, get_args

import asyncpg

from trimcp.signing import SigningError, get_active_key, sign_fields

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed event_type values — single source of truth
# ---------------------------------------------------------------------------

EventType = Literal[
    "store_memory",
    "forget_memory",
    "boost_memory",
    "resolve_contradiction",
    "consolidation_run",
    "pii_redaction",
    "snapshot_created",
    "unredact",
]

_VALID_EVENT_TYPES: Final[frozenset[str]] = frozenset(get_args(EventType))

# Advisory lock domain tag — XOR'd with a hash of the namespace UUID so that
# event_log sequence locks are distinct from any other advisory locks the app
# may acquire.  Value chosen to be memorable (ASCII "trimcpev").
_ADVISORY_DOMAIN: Final[int] = 0x7472696D63706576

# Maximum length of agent_id (per spec D4 + auth.py convention).
_AGENT_ID_MAX_LEN: Final[int] = 128

# ---------------------------------------------------------------------------
# Public exceptions
# ---------------------------------------------------------------------------


class EventLogError(Exception):
    """Base class for event log write errors."""


class InvalidEventTypeError(EventLogError):
    """Raised when *event_type* is not in the allowed set."""


class EventLogTimestampError(EventLogError):
    """
    Raised if a backdated ``valid_from`` is detected in *params* (D8).

    The primary enforcement is the DB clock (``clock_timestamp()``); this is
    defence-in-depth at the Python layer.
    """


class EventLogSequenceError(EventLogError):
    """
    Raised when sequence allocation fails unexpectedly.

    Under correct usage (advisory lock held, single-TX model) this should
    never occur.  If it does it indicates a concurrency bug or DB
    misconfiguration.
    """


class EventLogSigningError(EventLogError):
    """Raised when the signing key cannot be loaded or the HMAC step fails."""


# Public surface — callers only need to import from this module.
__all__ = [
    "EventType",
    "AppendResult",
    "append_event",
    "EventLogError",
    "InvalidEventTypeError",
    "EventLogTimestampError",
    "EventLogSequenceError",
    "EventLogSigningError",
]


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AppendResult:
    """Immutable result of a successful ``append_event`` call."""

    event_id: uuid.UUID
    """UUID of the newly created row (same as ``event_log.id``)."""

    event_seq: int
    """Monotonically increasing per-namespace sequence number (no gaps)."""

    occurred_at: datetime
    """DB-authoritative timestamp (``clock_timestamp()`` at insert time, UTC)."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _advisory_lock_key(namespace_id: uuid.UUID) -> int:
    """
    Derive a signed int64 advisory lock key for *namespace_id*.

    Combines a domain tag with the first 8 bytes of
    SHA-256(domain || namespace_bytes) to distribute lock keys across the
    full int64 space and avoid collisions with other advisory lock users.

    Returns a *signed* int64 as required by ``pg_advisory_xact_lock(int8)``.
    """
    digest = hashlib.sha256(
        _ADVISORY_DOMAIN.to_bytes(8, "big") + namespace_id.bytes
    ).digest()
    raw = int.from_bytes(digest[:8], "big")
    # Wrap to signed int64 range.
    if raw >= (1 << 63):
        raw -= 1 << 64
    return raw


def _build_signing_fields(
    *,
    event_id: uuid.UUID,
    namespace_id: uuid.UUID,
    agent_id: str,
    event_type: str,
    event_seq: int,
    occurred_at_iso: str,
    params: dict[str, Any],
    parent_event_id: Optional[uuid.UUID],
) -> dict[str, Any]:
    """
    Return the dict of immutable event fields that is signed.

    ``result_summary``, ``llm_payload_uri``, and ``llm_payload_hash`` are
    intentionally excluded — they may be written or updated (by the migration
    role) after the initial INSERT without invalidating the core integrity
    signature.
    """
    fields: dict[str, Any] = {
        "event_id": str(event_id),
        "namespace_id": str(namespace_id),
        "agent_id": agent_id,
        "event_type": event_type,
        "event_seq": event_seq,
        "occurred_at": occurred_at_iso,
        "params": params,
    }
    if parent_event_id is not None:
        fields["parent_event_id"] = str(parent_event_id)
    return fields


def _serialise_jsonb(obj: Any) -> Optional[str]:
    """
    Serialise *obj* to a JSON string for asyncpg ``jsonb`` parameters.

    Returns ``None`` unchanged (maps to SQL NULL).
    Sorts keys for reproducibility; datetime objects serialised via ``str()``.
    """
    if obj is None:
        return None
    return json.dumps(obj, sort_keys=True, default=str)


def _validate_params_no_backdated_timestamp(params: dict[str, Any]) -> None:
    """
    D8 defence-in-depth: reject if *params* contains a ``valid_from`` that
    is in the past relative to now (UTC).

    This does NOT prevent all backdating — the DB clock is authoritative.
    It is a cheap early rejection for clients that mistakenly pass a stale
    timestamp in the params payload.
    """
    vf = params.get("valid_from")
    if vf is None:
        return
    try:
        if isinstance(vf, str):
            from datetime import datetime as _dt

            ts = _dt.fromisoformat(vf.replace("Z", "+00:00"))
            now = _dt.now(timezone.utc)
            if ts < now:
                raise EventLogTimestampError(
                    "D8 violation: params['valid_from'] is a past timestamp "
                    f"({vf!r}).  valid_from must always be now()."
                )
    except (ValueError, TypeError):
        pass  # Non-parseable value — let the DB enforce


# ---------------------------------------------------------------------------
# Core sequence-allocation helpers
# ---------------------------------------------------------------------------


async def _acquire_seq_lock(
    conn: asyncpg.Connection, namespace_id: uuid.UUID
) -> None:
    """
    Acquire a transaction-scoped advisory lock for namespace sequence allocation.

    ``pg_advisory_xact_lock`` blocks until the lock is available and releases
    it automatically when the enclosing transaction ends.  This guarantees that
    only one writer at a time allocates an ``event_seq`` for a given namespace,
    producing a gap-free sequence even under concurrent load.
    """
    lock_key = _advisory_lock_key(namespace_id)
    await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_key)
    log.debug(
        "Advisory seq lock acquired (namespace_id=%s, lock_key=%d).",
        namespace_id,
        lock_key,
    )


async def _next_event_seq(
    conn: asyncpg.Connection, namespace_id: uuid.UUID
) -> int:
    """
    Return ``max(event_seq) + 1`` for *namespace_id*, or ``1`` if no rows exist.

    Must be called AFTER ``_acquire_seq_lock`` and INSIDE a transaction.
    The advisory lock prevents concurrent callers from reading the same max
    before either has inserted, which would cause a duplicate-seq collision.
    """
    row = await conn.fetchrow(
        """
        SELECT COALESCE(MAX(event_seq), 0) + 1 AS next_seq
        FROM   event_log
        WHERE  namespace_id = $1
        """,
        namespace_id,
    )
    # COALESCE means row is never None.
    return int(row["next_seq"])  # type: ignore[index]


async def _fetch_db_clock(conn: asyncpg.Connection) -> datetime:
    """
    Return the current DB-side timestamp (``clock_timestamp()``) as UTC-aware.

    Using the DB clock (not the Python process clock) ensures the value we
    sign is byte-identical to what the DB will store in ``occurred_at``.
    """
    ts: datetime = await conn.fetchval("SELECT clock_timestamp()")
    # asyncpg returns a timezone-aware datetime; normalise to UTC.
    return ts.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def append_event(
    *,
    conn: asyncpg.Connection,
    namespace_id: uuid.UUID,
    agent_id: str,
    event_type: str,
    params: dict[str, Any],
    result_summary: Optional[dict[str, Any]] = None,
    parent_event_id: Optional[uuid.UUID] = None,
    llm_payload_uri: Optional[str] = None,
    llm_payload_hash: Optional[bytes] = None,
) -> AppendResult:
    """
    Append one entry to the tamper-resistant ``event_log`` table.

    This function is INSERT-only.  It must be called inside an active asyncpg
    transaction owned by the Saga coordinator.  It never commits or rolls back
    the transaction.

    Sequence
    --------
    1. Validate ``event_type`` and ``agent_id``.
    2. Apply D8 defence-in-depth check on ``params``.
    3. Fetch the DB clock (``clock_timestamp()``) for signing.
    4. Acquire per-namespace advisory lock.
    5. Allocate ``event_seq`` (``MAX + 1`` under the advisory lock).
    6. Load the active signing key from ``signing_keys``.
    7. Compute HMAC-SHA256 over JCS-canonical immutable fields.
    8. INSERT the row and ``RETURN`` the DB-assigned values.

    Parameters
    ----------
    conn : asyncpg.Connection
        Must be participating in an active Saga transaction.
    namespace_id : uuid.UUID
        Tenant namespace.  No implicit default — callers must supply this.
    agent_id : str
        Free-text agent identifier; stripped of leading/trailing whitespace;
        max 128 characters (D4).
    event_type : str
        One of the allowed ``EventType`` literal values.
    params : dict
        JSON-serialisable operation input parameters.  Must not contain
        ``valid_from`` with a past timestamp (D8 check).
    result_summary : dict, optional
        JSON-serialisable operation output summary.  May be ``None`` at insert
        time (written later by the migration role on completion).
    parent_event_id : uuid.UUID, optional
        Causal parent event for provenance chains.
    llm_payload_uri : str, optional
        MinIO path for the LLM prompt/response payload (LLM-driven events).
    llm_payload_hash : bytes, optional
        ``sha256(JCS({prompt, response}))`` — must match the MinIO object when
        provided.  Validated externally; stored as-is here.

    Returns
    -------
    AppendResult
        Frozen dataclass with ``event_id``, ``event_seq``, and ``occurred_at``
        as set by the DB.

    Raises
    ------
    InvalidEventTypeError
        ``event_type`` is not in the allowed set.
    ValueError
        ``agent_id`` fails length/content validation.
    EventLogTimestampError
        ``params['valid_from']`` is a past timestamp (D8 defence-in-depth).
    EventLogSigningError
        Active signing key could not be loaded or the HMAC step failed.
    EventLogSequenceError
        Sequence allocation failed after the advisory lock (bug or DB
        misconfiguration — should never occur under normal operation).
    asyncpg.PostgresError
        Propagated unchanged for DB-level errors (e.g., missing partition,
        FK violation on ``namespace_id``, WORM permission denial).
    """
    # -------------------------------------------------------------------------
    # 1. Validate event_type
    # -------------------------------------------------------------------------
    if event_type not in _VALID_EVENT_TYPES:
        raise InvalidEventTypeError(
            f"Unknown event_type {event_type!r}.  "
            f"Allowed values: {sorted(_VALID_EVENT_TYPES)}"
        )

    # -------------------------------------------------------------------------
    # 2. Validate agent_id
    # -------------------------------------------------------------------------
    agent_id = agent_id.strip()
    if not agent_id:
        raise ValueError("agent_id must not be empty or whitespace-only.")
    if len(agent_id) > _AGENT_ID_MAX_LEN:
        raise ValueError(
            f"agent_id exceeds {_AGENT_ID_MAX_LEN} characters "
            f"(got {len(agent_id)})."
        )

    # -------------------------------------------------------------------------
    # 3. D8 defence-in-depth: reject backdated timestamps in params
    # -------------------------------------------------------------------------
    _validate_params_no_backdated_timestamp(params)

    # -------------------------------------------------------------------------
    # 4. Fetch DB clock (used in signature so it matches stored occurred_at)
    # -------------------------------------------------------------------------
    occurred_at: datetime = await _fetch_db_clock(conn)
    occurred_at_iso: str = occurred_at.isoformat()

    # -------------------------------------------------------------------------
    # 5. Acquire per-namespace advisory lock + allocate event_seq
    # -------------------------------------------------------------------------
    await _acquire_seq_lock(conn, namespace_id)

    try:
        event_seq: int = await _next_event_seq(conn, namespace_id)
    except asyncpg.PostgresError:
        raise
    except Exception as exc:
        raise EventLogSequenceError(
            f"Unexpected error allocating event_seq for namespace {namespace_id}: {exc}"
        ) from exc

    # -------------------------------------------------------------------------
    # 6. Generate event UUID
    # -------------------------------------------------------------------------
    event_id = uuid.uuid4()

    # -------------------------------------------------------------------------
    # 7. Load signing key and compute HMAC-SHA256 over immutable fields
    # -------------------------------------------------------------------------
    try:
        key_id, raw_key = await get_active_key(conn)
    except SigningError as exc:
        raise EventLogSigningError(
            f"Cannot load active signing key for event_log write: {exc}"
        ) from exc

    signing_fields_dict = _build_signing_fields(
        event_id=event_id,
        namespace_id=namespace_id,
        agent_id=agent_id,
        event_type=event_type,
        event_seq=event_seq,
        occurred_at_iso=occurred_at_iso,
        params=params,
        parent_event_id=parent_event_id,
    )

    try:
        signature: bytes = sign_fields(signing_fields_dict, raw_key)
    except Exception as exc:
        raise EventLogSigningError(f"HMAC signing failed: {exc}") from exc

    # -------------------------------------------------------------------------
    # 8. INSERT — pass occurred_at explicitly so the stored value matches what
    #    was signed.  asyncpg maps uuid.UUID → PG UUID natively.
    # -------------------------------------------------------------------------
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO event_log (
                id,
                namespace_id,
                agent_id,
                event_type,
                event_seq,
                occurred_at,
                params,
                result_summary,
                parent_event_id,
                llm_payload_uri,
                llm_payload_hash,
                signature,
                signature_key_id
            ) VALUES (
                $1,         -- id              uuid
                $2,         -- namespace_id    uuid
                $3,         -- agent_id        text
                $4,         -- event_type      text
                $5,         -- event_seq       bigint
                $6,         -- occurred_at     timestamptz
                $7::jsonb,  -- params          jsonb
                $8::jsonb,  -- result_summary  jsonb  (nullable)
                $9,         -- parent_event_id uuid   (nullable)
                $10,        -- llm_payload_uri text   (nullable)
                $11,        -- llm_payload_hash bytea (nullable)
                $12,        -- signature       bytea
                $13         -- signature_key_id text
            )
            RETURNING id, event_seq, occurred_at
            """,
            event_id,
            namespace_id,
            agent_id,
            event_type,
            event_seq,
            occurred_at,
            _serialise_jsonb(params),
            _serialise_jsonb(result_summary),
            parent_event_id,
            llm_payload_uri,
            llm_payload_hash,
            signature,
            key_id,
        )
    except asyncpg.UniqueViolationError as exc:
        # Advisory lock should prevent this; treat as a fatal concurrency bug.
        raise EventLogSequenceError(
            f"Unique violation on (namespace_id, event_seq=({namespace_id}, {event_seq})).  "
            "Advisory lock did not prevent a concurrent allocation — this is a bug."
        ) from exc

    if row is None:
        raise EventLogError(
            "INSERT INTO event_log returned no RETURNING row — unexpected DB behaviour."
        )

    result = AppendResult(
        event_id=row["id"],
        event_seq=row["event_seq"],
        occurred_at=row["occurred_at"].astimezone(timezone.utc),
    )

    log.info(
        "event_log: event_type=%s event_seq=%d namespace=%s agent=%s event_id=%s",
        event_type,
        result.event_seq,
        namespace_id,
        agent_id,
        result.event_id,
    )
    return result
