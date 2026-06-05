"""Batch MongoDB reads for ``memory_archive`` collections (FIX-021 / FIX-024).

Replaces N+1 ``find_one`` loops with single ``$in`` queries per hydrate call.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from bson import ObjectId

log = logging.getLogger(__name__)

_MAX_REFS: int = 10_000
_BATCH_SIZE: int = 500
_QUERY_TIMEOUT_MS: int = 5_000
_ALLOWED_FIELDS: frozenset[str] = frozenset({"raw_data", "raw_code"})


def _safe_object_id(key: str) -> ObjectId | None:
    """Parse a hex string into ObjectId; return None if invalid."""
    try:
        return ObjectId(key)
    except Exception:
        return None


def normalize_payload_ref(payload_ref: str | ObjectId | None) -> str | None:
    if payload_ref is None:
        return None
    if isinstance(payload_ref, ObjectId):
        return str(payload_ref)
    return str(payload_ref)


def _normalize_and_validate_refs(
    refs: Iterable[str | ObjectId | None]
) -> list[ObjectId]:
    """Deduplicate, normalize, and validate a sequence of payload refs.

    Raises ValueError if the number of unique refs exceeds _MAX_REFS.
    """
    seen: list[str] = []
    uniq: dict[str, None] = {}
    for ref in refs:
        key = normalize_payload_ref(ref)
        if not key or key in uniq:
            continue
        uniq[key] = None
        seen.append(key)

    if not seen:
        return []
    if len(seen) > _MAX_REFS:
        raise ValueError(f"Too many payload refs: {len(seen)} exceeds limit of {_MAX_REFS}")

    oids: list[ObjectId] = []
    for key in seen:
        oid = _safe_object_id(key)
        if oid is None:
            log.warning(
                "Invalid Mongo payload_ref (prefix=%s): not a valid ObjectId",
                key[:8],
            )
        else:
            oids.append(oid)
    return oids


async def _fetch_field_by_refs(
    collection,
    refs: Iterable[str | ObjectId | None],
    *,
    field: str,
) -> dict[str, str]:
    if field not in _ALLOWED_FIELDS:
        raise ValueError(f"field {field!r} is not allowed. Allowed: {sorted(_ALLOWED_FIELDS)}")

    oids = _normalize_and_validate_refs(refs)
    if not oids:
        return {}

    out: dict[str, str] = {}
    coll_name = getattr(collection, "name", "collection")
    for i in range(0, len(oids), _BATCH_SIZE):
        batch = oids[i : i + _BATCH_SIZE]
        try:
            cursor = collection.find(
                {"_id": {"$in": batch}},
                projection={field: 1},
                max_time_ms=_QUERY_TIMEOUT_MS,
            )
            async for doc in cursor:
                rid = normalize_payload_ref(doc.get("_id"))
                raw = doc.get(field)
                out[rid] = "" if raw is None else str(raw)
        except Exception as exc:
            log.error(
                "Batch Mongo hydrate failed batch=%d/%d (%s): %s",
                i // _BATCH_SIZE + 1,
                (len(oids) + _BATCH_SIZE - 1) // _BATCH_SIZE,
                coll_name,
                type(exc).__name__,
            )

    return out


async def fetch_episodes_raw_by_ref(
    db,
    refs: Iterable[str | ObjectId | None],
    *,
    field: str = "raw_data",
) -> dict[str, str]:
    """Map episode ``_id`` (str) → ``raw_data`` (or *field*) text."""
    return await _fetch_field_by_refs(db.episodes, refs, field=field)


async def fetch_episode_previews_by_ref(
    db,
    refs: Iterable[str | ObjectId | None],
    *,
    max_preview_len: int = 200,
) -> dict[str, str]:
    """Map episode ``_id`` (str) → short preview (summary, else raw_data)."""
    oids = _normalize_and_validate_refs(refs)
    if not oids:
        return {}

    out: dict[str, str] = {}
    coll = db.episodes
    coll_name = getattr(coll, "name", "episodes")
    for i in range(0, len(oids), _BATCH_SIZE):
        batch = oids[i : i + _BATCH_SIZE]
        try:
            cursor = coll.find(
                {"_id": {"$in": batch}},
                projection={"summary": 1, "raw_data": 1},
                max_time_ms=_QUERY_TIMEOUT_MS,
            )
            async for doc in cursor:
                rid = normalize_payload_ref(doc.get("_id"))
                if not rid:
                    continue
                text = doc.get("summary") or doc.get("raw_data")
                out[rid] = ("" if text is None else str(text))[:max_preview_len]
        except Exception as exc:
            log.error(
                "Batch Mongo preview hydrate failed batch=%d/%d (%s): %s",
                i // _BATCH_SIZE + 1,
                (len(oids) + _BATCH_SIZE - 1) // _BATCH_SIZE,
                coll_name,
                type(exc).__name__,
            )

    return out


async def fetch_code_files_raw_by_ref(
    db,
    refs: Iterable[str | ObjectId | None],
    *,
    field: str = "raw_code",
) -> dict[str, str]:
    """Map code_files ``_id`` (str) → ``raw_code`` (or *field*) text."""
    return await _fetch_field_by_refs(db.code_files, refs, field=field)
