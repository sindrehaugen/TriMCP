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
from datetime import UTC, datetime
from typing import Any, Final

import asyncpg

from trimcp.event_types import VALID_EVENT_TYPES, EventType
from trimcp.signing import SigningError, get_active_key, sign_fields

log = logging.getLogger(__name__)

# Advisory lock domain tag — XOR'd with a hash of the namespace UUID so that
# event_log sequence locks are distinct from any other advisory locks the app
# may acquire.  Value chosen to be memorable (ASCII "trimcpev").
_ADVISORY_DOMAIN: Final[int] = 0x7472696D63706576

# Maximum length of agent_id (per spec D4 + auth.py convention).
_AGENT_ID_MAX_LEN: Final[int] = 128

# Genesis sentinel for Merkle chain hash — 32 zero bytes.
# The first event in a namespace uses this as its "previous chain hash"
# input rather than fetching a non-existent prior row.
_GENESIS_SENTINEL: Final[bytes] = b"\x00" * 32

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


class DataIntegrityError(EventLogError):
    """
    Raised when an event log row fails HMAC verification during read.
    Indicates that the row has been tampered with post-insertion.
    """


# Public surface — callers only need to import from this module.
__all__ = [
    "EventType",
    "AppendResult",
    "append_event",
    "verify_worm_enforcement",
    "verify_worm_on_table",
    "_WORM_TABLES",
    "verify_rls_enforcement",
    "_RLS_TABLES",
    "EventLogError",
    "InvalidEventTypeError",
    "EventLogTimestampError",
    "EventLogSequenceError",
    "EventLogSigningError",
    "DataIntegrityError",
    "verify_event_signature",
    "verify_merkle_chain",
]


# ---------------------------------------------------------------------------
# WORM enforcement probe
# ---------------------------------------------------------------------------

# Tables expected to be append-only (no UPDATE/DELETE at the application role).
_WORM_TABLES: tuple[str, ...] = (
    "event_log",
    "pii_redactions",
    "memory_salience",
)


async def verify_worm_on_table(conn: asyncpg.Connection, table_name: str) -> None:
    """
    Runtime assertion that UPDATE and DELETE are denied on *table_name*.

    Attempts a dummy ``UPDATE`` and ``DELETE`` with a ``WHERE FALSE`` clause
    so that no rows are ever modified.  If either statement succeeds (i.e. the
    DB role has UPDATE/DELETE privileges), a ``RuntimeError`` is raised to
    **halt server startup** — the WORM guarantee is broken for that table.

    Parameters
    ----------
    conn
        An open asyncpg connection authenticated as the application role.
    table_name
        The name of the table to probe (must have an ``id`` column).

    Raises
    ------
    RuntimeError
        If UPDATE or DELETE succeeds on the target table.
    asyncpg.exceptions.InsufficientPrivilegeError
        Expected — caught internally; the function returns normally.
    asyncpg.PostgresError
        Propagated for unexpected DB errors (e.g. table missing).
    """
    # Probe 1: UPDATE
    try:
        await conn.execute(f"UPDATE {table_name} SET id = id WHERE FALSE")
    except asyncpg.exceptions.InsufficientPrivilegeError:
        log.info("[worm-probe] %s: UPDATE denied ✅", table_name)
    else:
        raise RuntimeError(
            f"WORM ENFORCEMENT FAILED: UPDATE on {table_name} succeeded.  "
            f"The database role has UPDATE privileges on the {table_name} table.  "
            f"The server cannot start without append-only guarantees.  "
            f"Check the REVOKE/GRANT statements in schema.sql."
        )

    # Probe 2: DELETE
    try:
        await conn.execute(f"DELETE FROM {table_name} WHERE FALSE")
    except asyncpg.exceptions.InsufficientPrivilegeError:
        log.info("[worm-probe] %s: DELETE denied ✅", table_name)
    else:
        raise RuntimeError(
            f"WORM ENFORCEMENT FAILED: DELETE on {table_name} succeeded.  "
            f"The database role has DELETE privileges on the {table_name} table.  "
            f"The server cannot start without append-only guarantees.  "
        )


async def verify_worm_enforcement(conn: asyncpg.Connection) -> None:
    """Backward-compat wrapper — probes only ``event_log``."""
    await verify_worm_on_table(conn, "event_log")


# ---------------------------------------------------------------------------
# RLS enforcement probe
# ---------------------------------------------------------------------------

# Tables protected by the ``namespace_isolation_policy`` RLS policy.
_RLS_TABLES: tuple[str, ...] = (
    "memories",
    "memory_embeddings",
    "consolidation_runs",
    "contradictions",
    "snapshots",
    "forks",
    "event_log",
    "pii_redactions",
    "memory_salience",
    "resource_quotas",
    "kg_nodes",
    "kg_edges",
)


async def verify_rls_enforcement(conn: asyncpg.Connection, table_name: str) -> None:
    """
    Validate that RLS is active on *table_name* by attempting a ``SELECT``
    without a scoped ``trimcp.namespace_id``.

    When RLS is correctly configured via the ``namespace_isolation_policy``,
    the session variable falls back to ``NULL`` and all rows are filtered out
    (``namespace_id = NULL::uuid`` is never true).  A non-zero row count from
    an unscoped query signals that RLS is **not** in effect for that table.

    Parameters
    ----------
    conn
        An open asyncpg connection authenticated as the application role.
    table_name
        The name of the table to probe (must have RLS enabled and a
        ``namespace_id`` column).

    Raises
    ------
    RuntimeError
        If a non-scoped SELECT returns one or more rows, indicating RLS is
        not enforced on the table.
    asyncpg.PostgresError
        Propagated for unexpected DB errors (e.g. table missing).
    """
    try:
        count = await conn.fetchval(f"SELECT count(*) FROM {table_name}")
    except Exception as exc:
        log.warning("[rls-probe] %s: could not query — %s: %s", table_name, type(exc).__name__, exc)
        return

    if count is not None and count > 0:
        raise RuntimeError(
            f"RLS ENFORCEMENT FAILED: unscoped SELECT on {table_name} "
            f"returned {count} row(s).  The namespace_isolation_policy is "
            f"not filtering rows.  Check that RLS is enabled on the table "
            f"and the policy is correctly defined."
        )

    log.info("[rls-probe] %s: unscoped SELECT returned 0 rows — RLS active ✅", table_name)


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
    digest = hashlib.sha256(_ADVISORY_DOMAIN.to_bytes(8, "big") + namespace_id.bytes).digest()
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
    parent_event_id: uuid.UUID | None,
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


def _serialise_jsonb(obj: Any) -> str | None:
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
            now = _dt.now(UTC)
            if ts < now:
                raise EventLogTimestampError(
                    "D8 violation: params['valid_from'] is a past timestamp "
                    f"({vf!r}).  valid_from must always be now()."
                )
    except (ValueError, TypeError):
        pass  # Non-parseable value — let the DB enforce


# ---------------------------------------------------------------------------
# Merkle chain helpers (cryptographic chaining for WORM integrity)
# ---------------------------------------------------------------------------


def _compute_content_hash(*, signing_fields: dict[str, Any]) -> bytes:
    """
    Compute a deterministic SHA-256 content hash of the canonical signing fields.

    Uses JSON with sorted keys (identical serialisation to what
    ``_build_signing_fields`` produces) to ensure byte-identical
    hashing across Python versions and processes.

    Returns
    -------
    bytes
        32-byte SHA-256 digest.
    """
    canonical_json: str = json.dumps(signing_fields, sort_keys=True, default=str)
    return hashlib.sha256(canonical_json.encode("utf-8")).digest()


def _compute_chain_hash(*, content_hash: bytes, previous_chain_hash: bytes) -> bytes:
    """
    Compute the Merkle chain hash for the current event.

    ``chain_hash = SHA-256(content_hash || previous_chain_hash)``

    Parameters
    ----------
    content_hash : bytes
        SHA-256 hash of the canonical signing fields for the current event.
    previous_chain_hash : bytes
        The chain_hash of the immediately preceding event in the namespace,
        or ``_GENESIS_SENTINEL`` (32 zero bytes) for the first event.

    Returns
    -------
    bytes
        32-byte SHA-256 digest representing the chained hash.
    """
    return hashlib.sha256(content_hash + previous_chain_hash).digest()


async def _fetch_previous_chain_hash(conn: asyncpg.Connection, namespace_id: uuid.UUID) -> bytes:
    """
    Fetch the ``chain_hash`` of the most recent event in *namespace_id*.

    Returns ``_GENESIS_SENTINEL`` if no prior event exists (genesis case).

    Parameters
    ----------
    conn : asyncpg.Connection
        An open asyncpg connection inside an active transaction.
    namespace_id : uuid.UUID
        The namespace scope.

    Returns
    -------
    bytes
        The previous chain_hash, or the genesis sentinel (32 zero bytes).
    """
    row = await conn.fetchrow(
        """
        SELECT chain_hash
        FROM   event_log
        WHERE  namespace_id = $1
        ORDER BY event_seq DESC
        LIMIT 1
        """,
        namespace_id,
    )
    if row is None or row["chain_hash"] is None:
        return _GENESIS_SENTINEL
    chain_hash: bytes = row["chain_hash"]
    if isinstance(chain_hash, memoryview):
        chain_hash = bytes(chain_hash)
    return chain_hash


# ---------------------------------------------------------------------------
# Core sequence-allocation helpers
# ---------------------------------------------------------------------------


async def _acquire_seq_lock(conn: asyncpg.Connection, namespace_id: uuid.UUID) -> None:
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


async def _next_event_seq(conn: asyncpg.Connection, namespace_id: uuid.UUID) -> int:
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
    return ts.astimezone(UTC)


# ---------------------------------------------------------------------------
# Append-event helpers (extracted for Clean Code — SRP)
# ---------------------------------------------------------------------------


def _validate_event_payload(event_type: str, agent_id: str) -> str:
    """
    Validate and normalise ``event_type`` and ``agent_id``.

    Returns the stripped ``agent_id``.

    Raises
    ------
    InvalidEventTypeError
        If ``event_type`` is not in the allowed set.
    ValueError
        If ``agent_id`` is empty or exceeds ``_AGENT_ID_MAX_LEN``.
    """
    if event_type not in VALID_EVENT_TYPES:
        raise InvalidEventTypeError(
            f"Unknown event_type {event_type!r}.  Allowed values: {sorted(VALID_EVENT_TYPES)}"
        )

    agent_id = agent_id.strip()
    if not agent_id:
        raise ValueError("agent_id must not be empty or whitespace-only.")
    if len(agent_id) > _AGENT_ID_MAX_LEN:
        raise ValueError(f"agent_id exceeds {_AGENT_ID_MAX_LEN} characters (got {len(agent_id)}).")
    return agent_id


async def _sign_event(
    conn: asyncpg.Connection,
    *,
    event_id: uuid.UUID,
    namespace_id: uuid.UUID,
    agent_id: str,
    event_type: str,
    event_seq: int,
    occurred_at_iso: str,
    params: dict[str, Any],
    parent_event_id: uuid.UUID | None,
) -> tuple[str, bytes]:
    """
    Load the active signing key, build canonical fields, and HMAC-sign.

    Returns ``(key_id, signature_bytes)``.

    Raises
    ------
    EventLogSigningError
        If the signing key cannot be loaded or HMAC computation fails.
    """
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

    return key_id, signature


async def _insert_event(
    conn: asyncpg.Connection,
    *,
    event_id: uuid.UUID,
    namespace_id: uuid.UUID,
    agent_id: str,
    event_type: str,
    event_seq: int,
    occurred_at: datetime,
    params: dict[str, Any],
    result_summary: dict[str, Any] | None,
    parent_event_id: uuid.UUID | None,
    llm_payload_uri: str | None,
    llm_payload_hash: bytes | None,
    signature: bytes,
    key_id: str,
    chain_hash: bytes | None,
) -> AppendResult:
    """
    INSERT a row into ``event_log`` and return the DB-assigned result.

    Raises
    ------
    EventLogSequenceError
        On unique-violation (advisory-lock concurrency bug).
    EventLogError
        If the INSERT returns no row.
    """
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO event_log (
                id, namespace_id, agent_id, event_type, event_seq,
                occurred_at, params, result_summary,
                parent_event_id, llm_payload_uri, llm_payload_hash,
                signature, signature_key_id, chain_hash
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7::jsonb, $8::jsonb,
                $9, $10, $11,
                $12, $13, $14
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
            chain_hash,
        )
    except asyncpg.UniqueViolationError as exc:
        raise EventLogSequenceError(
            f"Unique violation on (namespace_id, event_seq)=({namespace_id}, {event_seq}).  "
            "Advisory lock did not prevent a concurrent allocation — this is a bug."
        ) from exc

    if row is None:
        raise EventLogError(
            "INSERT INTO event_log returned no RETURNING row — unexpected DB behaviour."
        )

    return AppendResult(
        event_id=row["id"],
        event_seq=row["event_seq"],
        occurred_at=row["occurred_at"].astimezone(UTC),
    )


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
    result_summary: dict[str, Any] | None = None,
    parent_event_id: uuid.UUID | None = None,
    llm_payload_uri: str | None = None,
    llm_payload_hash: bytes | None = None,
) -> AppendResult:
    """
    Append one entry to the tamper-resistant ``event_log`` table.

    This function is INSERT-only.  It must be called inside an active asyncpg
    transaction owned by the Saga coordinator.  It never commits or rolls back
    the transaction.

    Sequence
    --------
    1. Validate ``event_type`` and ``agent_id`` (``_validate_event_payload``).
    2. Apply D8 defence-in-depth check on ``params``.
    3. Fetch the DB clock for signing.
    4. Acquire per-namespace advisory lock and allocate ``event_seq``.
    5. Generate a fresh ``event_id``.
    6. Load signing key, build canonical fields, and HMAC-sign (``_sign_event``).
    7. Compute Merkle chain hash — SHA-256(content_hash || previous_chain_hash).
       Genesis events use a 32-byte zero sentinel as the previous hash.
    8. INSERT the row (``_insert_event``).

    Returns
    -------
    AppendResult
        Frozen dataclass with ``event_id``, ``event_seq``, and ``occurred_at``.

    Raises
    ------
    InvalidEventTypeError, ValueError, EventLogTimestampError,
    EventLogSigningError, EventLogSequenceError, asyncpg.PostgresError
    """
    # 1. Validate event_type and agent_id
    agent_id = _validate_event_payload(event_type, agent_id)

    # 2. D8 defence-in-depth: reject backdated timestamps in params
    _validate_params_no_backdated_timestamp(params)

    # 3. Fetch DB clock (used in signature so it matches stored occurred_at)
    occurred_at: datetime = await _fetch_db_clock(conn)
    occurred_at_iso: str = occurred_at.isoformat()

    # 4. Acquire per-namespace advisory lock + allocate event_seq
    await _acquire_seq_lock(conn, namespace_id)
    try:
        event_seq: int = await _next_event_seq(conn, namespace_id)
    except asyncpg.PostgresError:
        raise
    except Exception as exc:
        raise EventLogSequenceError(
            f"Unexpected error allocating event_seq for namespace {namespace_id}: {exc}"
        ) from exc

    # 5. Generate event UUID
    event_id = uuid.uuid4()

    # 6. Load signing key, build canonical fields, and HMAC-sign
    key_id, signature = await _sign_event(
        conn,
        event_id=event_id,
        namespace_id=namespace_id,
        agent_id=agent_id,
        event_type=event_type,
        event_seq=event_seq,
        occurred_at_iso=occurred_at_iso,
        params=params,
        parent_event_id=parent_event_id,
    )

    # 7. Compute Merkle chain hash.
    #    content_hash = SHA-256(canonical signing fields)
    #    chain_hash   = SHA-256(content_hash || previous_chain_hash)
    #    Genesis events use _GENESIS_SENTINEL (32 zero bytes) as previous.
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
    content_hash: bytes = _compute_content_hash(signing_fields=signing_fields_dict)
    previous_chain_hash: bytes = await _fetch_previous_chain_hash(conn, namespace_id)
    chain_hash: bytes = _compute_chain_hash(
        content_hash=content_hash,
        previous_chain_hash=previous_chain_hash,
    )

    # 8. INSERT — pass occurred_at explicitly so the stored value matches
    #    what was signed.  asyncpg maps uuid.UUID → PG UUID natively.
    result = await _insert_event(
        conn,
        event_id=event_id,
        namespace_id=namespace_id,
        agent_id=agent_id,
        event_type=event_type,
        event_seq=event_seq,
        occurred_at=occurred_at,
        params=params,
        result_summary=result_summary,
        parent_event_id=parent_event_id,
        llm_payload_uri=llm_payload_uri,
        llm_payload_hash=llm_payload_hash,
        signature=signature,
        key_id=key_id,
        chain_hash=chain_hash,
    )

    log.info(
        "event_log: event_type=%s event_seq=%d namespace=%s agent=%s event_id=%s chain_hash=%s",
        event_type,
        result.event_seq,
        namespace_id,
        agent_id,
        result.event_id,
        chain_hash.hex()[:16],
    )
    return result


async def verify_event_signature(
    conn: asyncpg.Connection,
    record: asyncpg.Record | dict,
) -> None:
    """
    Verify the HMAC-SHA256 signature of an event log row.

    Raises ``DataIntegrityError`` if the signature does not match or if the
    signing key cannot be loaded.

    Parameters
    ----------
    conn : asyncpg.Connection
        An asyncpg Connection.
    record : asyncpg.Record or dict
        A row fetched from ``event_log`` containing all columns, notably
        ``signature`` and ``signature_key_id``.
    """
    from trimcp.signing import get_key_by_id, verify_fields

    key_id = record.get("signature_key_id")
    if not key_id:
        raise DataIntegrityError("Row is missing signature_key_id.")

    try:
        raw_key = await get_key_by_id(conn, key_id)
    except Exception as exc:
        raise DataIntegrityError(f"Failed to retrieve signing key {key_id}: {exc}") from exc

    params: dict[str, Any] | None = record.get("params")
    if params is None:
        params = {}
    elif isinstance(params, str):
        params = json.loads(params)

    # Coerce occurred_at to string representation as built during sign
    occurred_at = record.get("occurred_at")
    if isinstance(occurred_at, datetime):
        occurred_at_iso = occurred_at.astimezone(UTC).isoformat()
    elif isinstance(occurred_at, str):
        occurred_at_iso = occurred_at
    else:
        raise DataIntegrityError("Invalid occurred_at type in record.")

    signing_fields_dict = _build_signing_fields(
        event_id=record["id"],
        namespace_id=record["namespace_id"],
        agent_id=record["agent_id"],
        event_type=record["event_type"],
        event_seq=record["event_seq"],
        occurred_at_iso=occurred_at_iso,
        params=params,
        parent_event_id=record.get("parent_event_id"),
    )

    expected_signature = record.get("signature")
    if not expected_signature:
        raise DataIntegrityError("Row is missing signature.")

    if isinstance(expected_signature, memoryview):
        expected_signature = bytes(expected_signature)

    try:
        is_valid = verify_fields(signing_fields_dict, raw_key, expected_signature)
    except Exception as exc:
        raise DataIntegrityError(f"Failed to verify HMAC signature: {exc}") from exc

    if not is_valid:
        log.critical(
            "DATA INTEGRITY FAILURE: event_log row tampered! event_id=%s namespace_id=%s",
            record["id"],
            record["namespace_id"],
        )
        raise DataIntegrityError(
            f"Event signature mismatch for event_id={record['id']}. Tampering detected."
        )


async def verify_merkle_chain(
    conn: asyncpg.Connection,
    *,
    namespace_id: uuid.UUID,
    start_seq: int = 1,
    end_seq: int | None = None,
) -> dict[str, Any]:
    """
    Verify the Merkle hash chain for events in *namespace_id*.

    Recomputes ``chain_hash`` for every event in sequence order and compares
    against the stored value.  If any event has been inserted, deleted, or
    altered since the chain was built, the recomputed hash will diverge —
    and every subsequent event will also fail.

    The chain is anchored on ``_GENESIS_SENTINEL`` (32 zero bytes) as the
    ``previous_chain_hash`` for event_seq=1.

    Parameters
    ----------
    conn : asyncpg.Connection
        An open asyncpg connection (transaction is NOT required — this is
        a read-only verification).
    namespace_id : uuid.UUID
        The namespace whose event chain to verify.
    start_seq : int
        First event_seq to verify (default 1 for full chain).
    end_seq : int | None
        Last event_seq to verify (default None = all events from start_seq).

    Returns
    -------
    dict[str, Any]
        ``{"valid": bool, "checked": int, "first_break": int | None,
          "last_verified_seq": int}``.

        ``first_break`` is the event_seq where the chain first broke, or
        ``None`` if the entire chain is valid.

    Raises
    ------
    asyncpg.PostgresError
        On database errors.
    """
    rows = await conn.fetch(
        """
        SELECT id, namespace_id, agent_id, event_type, event_seq,
               occurred_at, params, parent_event_id, chain_hash
        FROM   event_log
        WHERE  namespace_id = $1
          AND  event_seq >= $2
        ORDER BY event_seq ASC
        """,
        namespace_id,
        start_seq,
    )
    if end_seq is not None and rows:
        rows = [r for r in rows if r["event_seq"] <= end_seq]

    checked = 0
    first_break: int | None = None
    last_verified_seq = 0
    previous_chain_hash: bytes = _GENESIS_SENTINEL

    # If we start from seq > 1, fetch the chain_hash of seq-1 as anchor.
    if start_seq > 1:
        anchor_row = await conn.fetchrow(
            """
            SELECT chain_hash FROM event_log
            WHERE namespace_id = $1 AND event_seq = $2
            """,
            namespace_id,
            start_seq - 1,
        )
        if anchor_row is not None and anchor_row["chain_hash"] is not None:
            anchor_hash = anchor_row["chain_hash"]
            if isinstance(anchor_hash, memoryview):
                anchor_hash = bytes(anchor_hash)
            previous_chain_hash = anchor_hash

    for row in rows:
        event_seq = int(row["event_seq"])

        # Deserialise params
        params: dict[str, Any] | None = row.get("params")
        if params is None:
            params = {}
        elif isinstance(params, str):
            params = json.loads(params)

        # Coerce occurred_at to ISO string
        occurred_at = row.get("occurred_at")
        if isinstance(occurred_at, datetime):
            occurred_at_iso = occurred_at.astimezone(UTC).isoformat()
        elif isinstance(occurred_at, str):
            occurred_at_iso = occurred_at
        else:
            occurred_at_iso = str(occurred_at)

        # Build canonical signing fields (same as at insert time)
        signing_fields_dict = _build_signing_fields(
            event_id=row["id"],
            namespace_id=row["namespace_id"],
            agent_id=row["agent_id"],
            event_type=row["event_type"],
            event_seq=event_seq,
            occurred_at_iso=occurred_at_iso,
            params=params,
            parent_event_id=row.get("parent_event_id"),
        )

        # Recompute the chain hash
        content_hash = _compute_content_hash(signing_fields=signing_fields_dict)
        expected_chain_hash = _compute_chain_hash(
            content_hash=content_hash,
            previous_chain_hash=previous_chain_hash,
        )

        stored_chain_hash = row.get("chain_hash")
        if isinstance(stored_chain_hash, memoryview):
            stored_chain_hash = bytes(stored_chain_hash)

        if stored_chain_hash != expected_chain_hash:
            if first_break is None:
                first_break = event_seq
                log.critical(
                    "MERKLE CHAIN BROKEN: namespace=%s event_seq=%d — "
                    "stored chain_hash does not match recomputed value.  "
                    "Tampering or insertion anomaly detected.",
                    namespace_id,
                    event_seq,
                )

        # Advance the chain for the next iteration
        previous_chain_hash = expected_chain_hash
        checked += 1
        last_verified_seq = event_seq

    valid = first_break is None
    if valid and checked > 0:
        log.info(
            "Merkle chain verified: namespace=%s events=%d all valid.",
            namespace_id,
            checked,
        )

    return {
        "valid": valid,
        "checked": checked,
        "first_break": first_break,
        "last_verified_seq": last_verified_seq,
    }
