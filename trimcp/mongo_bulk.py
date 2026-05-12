"""Batch MongoDB reads for ``memory_archive`` collections (FIX-021 / FIX-024).

Replaces N+1 ``find_one`` loops with single ``$in`` queries per hydrate call.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from bson import ObjectId

log = logging.getLogger(__name__)


def normalize_payload_ref(payload_ref: str | ObjectId | None) -> str:
    if payload_ref is None:
        return ""
    if isinstance(payload_ref, ObjectId):
        return str(payload_ref)
    return str(payload_ref)


async def _fetch_field_by_refs(
    collection,
    refs: Iterable[str | ObjectId | None],
    *,
    field: str,
) -> dict[str, str]:
    seen: list[str] = []
    uniq: dict[str, None] = {}
    for ref in refs:
        key = normalize_payload_ref(ref)
        if not key or key in uniq:
            continue
        uniq[key] = None
        seen.append(key)

    if not seen:
        return {}

    oids: list[ObjectId] = []
    for key in seen:
        try:
            oids.append(ObjectId(key))
        except Exception as exc:
            log.warning("Invalid Mongo payload_ref=%s: %s", key, exc)

    if not oids:
        return {}

    out: dict[str, str] = {}
    try:
        cursor = collection.find({"_id": {"$in": oids}}, projection={field: 1})
        async for doc in cursor:
            rid = normalize_payload_ref(doc.get("_id"))
            raw = doc.get(field)
            out[rid] = "" if raw is None else str(raw)
    except Exception as exc:
        coll_name = getattr(collection, "name", "collection")
        log.warning("Batch Mongo hydrate failed (%s): %s", coll_name, exc)

    return out


async def fetch_episodes_raw_by_ref(
    db,
    refs: Iterable[str | ObjectId | None],
    *,
    field: str = "raw_data",
) -> dict[str, str]:
    """Map episode ``_id`` (str) → ``raw_data`` (or *field*) text."""
    return await _fetch_field_by_refs(db.episodes, refs, field=field)


async def fetch_code_files_raw_by_ref(
    db,
    refs: Iterable[str | ObjectId | None],
    *,
    field: str = "raw_code",
) -> dict[str, str]:
    """Map code_files ``_id`` (str) → ``raw_code`` (or *field*) text."""
    return await _fetch_field_by_refs(db.code_files, refs, field=field)
