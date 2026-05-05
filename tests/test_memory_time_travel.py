"""
Phase 2.2 — Memory Time Travel (graph_search as_of).

Seeds a synthetic event_log timeline with fixed UTC timestamps, drives
``GraphRAGTraverser.search`` through a fake asyncpg pool whose ``fetch`` implements
the same *reconstruction rules* as ``trimcp/graph_query.py`` (latest event per
memory at cutoff, ``store_memory`` vs ``forget_memory``).

External I/O mocked: Mongo hydrate returns []. Embeddings are deterministic scalars
derived from the query string so anchor choice is stable across runs.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pytest

from trimcp.graph_query import GraphRAGTraverser


# ---------------------------------------------------------------------------
# Deterministic timeline (UTC)
# ---------------------------------------------------------------------------

TZ_UTC = timezone.utc
T0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=TZ_UTC)
T1 = datetime(2026, 1, 1, 10, 15, 0, tzinfo=TZ_UTC)
T2 = datetime(2026, 1, 1, 10, 30, 0, tzinfo=TZ_UTC)
T3 = datetime(2026, 1, 1, 10, 45, 0, tzinfo=TZ_UTC)
T4 = datetime(2026, 1, 1, 11, 0, 0, tzinfo=TZ_UTC)

NS_ID = UUID("00000000-0000-4000-8000-000000000001")
MEM_A = UUID("00000000-0000-4000-8000-0000000000a1")
MEM_B = UUID("00000000-0000-4000-8000-0000000000b1")


def _label_distance(label: str, query: str) -> float:
    """Deterministic pseudo-distance monotonic in label (for ordering)."""
    q = sum(ord(c) for c in query) % 251
    ell = sum(ord(c) for c in label) % 251
    return ((ell + 0.001 * q) % 100) / 100.0


@dataclass
class SeededEvent:
    event_seq: int
    occurred_at: datetime
    event_type: str
    memory_id: UUID
    entities: list[dict[str, str]]
    triplets: list[dict[str, Any]]
    namespace_id: UUID = NS_ID


def _active_store_rows(
    events: list[SeededEvent], namespace_id: UUID, as_of: datetime
) -> dict[UUID, SeededEvent]:
    """Mirror event_log CTE: last event per memory_id with occurred_at <= as_of."""
    filt = [
        e
        for e in events
        if e.namespace_id == namespace_id
        and e.occurred_at <= as_of
        and e.event_type in ("store_memory", "forget_memory")
    ]
    by_mem: dict[UUID, list[SeededEvent]] = defaultdict(list)
    for e in filt:
        by_mem[e.memory_id].append(e)
    active: dict[UUID, SeededEvent] = {}
    for mid, rows in by_mem.items():
        latest = max(rows, key=lambda r: r.event_seq)
        if latest.event_type == "store_memory":
            active[mid] = latest
    return active


class _Acquire:
    def __init__(self, conn: TemporalGraphFakeConn) -> None:
        self._c = conn

    async def __aenter__(self) -> TemporalGraphFakeConn:
        return self._c

    async def __aexit__(self, *_exc: object) -> None:
        return None


class FakePool:
    def __init__(self, conn: TemporalGraphFakeConn) -> None:
        self._conn = conn

    def acquire(self) -> _Acquire:
        return _Acquire(self._conn)


class TemporalGraphFakeConn:
    """
    Handles the three ``fetch`` shapes used when ``as_of`` and ``namespace_id``
    are set in ``GraphRAGTraverser``.
    """

    def __init__(
        self,
        events: list[SeededEvent],
        memories_payload_ref: dict[UUID, str],
        last_query: list[str],
        *,
        embed_probe: dict[str, str],
    ) -> None:
        self._events = events
        self._payload_ref = memories_payload_ref
        self._last_query = last_query
        self._embed_probe = embed_probe

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        self._last_query.append(query)
        q = query.lower()

        active = _active_store_rows(self._events, NS_ID, args[-1])
        as_of = args[-1]
        assert isinstance(as_of, datetime)

        # Anchor search (entities + vector distance)
        if "historical_nodes" in q and "<=>" in q:
            vector_json, top_k, ns_arg, _cutoff = args
            assert UUID(str(ns_arg)) == NS_ID
            _ = vector_json
            # Build distinct labels (stable: sort by label)
            label_to_row: dict[str, tuple[str, UUID]] = {}
            for ev in sorted(active.values(), key=lambda e: (e.memory_id, e.event_seq)):
                for ent in ev.entities:
                    lab = ent["label"]
                    if lab not in label_to_row:
                        label_to_row[lab] = (ent["entity_type"], ev.memory_id)

            probe = self._embed_probe.get("q", "")
            scored: list[tuple[float, str, str, str, UUID]] = []
            for lab, (etype, mid) in sorted(label_to_row.items()):
                dist = _label_distance(lab, probe)
                pref = self._payload_ref.get(mid, "")
                scored.append((dist, lab, etype, pref, mid))
            scored.sort(key=lambda t: t[0])
            rows: list[dict[str, Any]] = []
            for dist, lab, etype, pref, _mid in scored[: int(top_k)]:
                rows.append(
                    {
                        "label": lab,
                        "entity_type": etype,
                        "payload_ref": pref,
                        "distance": dist,
                    }
                )
            return rows

        # BFS edge scan
        if "params->'triplets'" in q and "historical_edges" in q:
            current_label, ns_arg, _cutoff = args
            assert UUID(str(ns_arg)) == NS_ID
            rows = []
            for ev in active.values():
                for tr in ev.triplets:
                    subj = tr["subject_label"]
                    obj = tr["object_label"]
                    if subj != current_label and obj != current_label:
                        continue
                    mid = ev.memory_id
                    rows.append(
                        {
                            "subject_label": subj,
                            "predicate": tr["predicate"],
                            "object_label": obj,
                            "payload_ref": self._payload_ref.get(mid, ""),
                            "decayed_confidence": float(tr.get("confidence", 1.0)),
                        }
                    )
            return rows

        # Visited node hydration
        if "params->'entities'" in q and "any($1::text[])" in q.lower():
            labels_any, ns_arg, _cutoff = args
            assert UUID(str(ns_arg)) == NS_ID
            want = set(labels_any)
            seen_label: dict[str, tuple[str, UUID]] = {}
            for ev in sorted(active.values(), key=lambda e: (e.memory_id, e.event_seq)):
                for ent in ev.entities:
                    lab = ent["label"]
                    if lab in want and lab not in seen_label:
                        seen_label[lab] = (ent["entity_type"], ev.memory_id)

            out = []
            for lab in sorted(seen_label.keys()):
                etype, mid = seen_label[lab]
                out.append(
                    {
                        "label": lab,
                        "entity_type": etype,
                        "payload_ref": self._payload_ref.get(mid, ""),
                    }
                )
            return out

        raise AssertionError(f"Unexpected temporal fetch query: {query!r} args={args!r}")


async def _noop_hydrate(*_a: object, **_k: object) -> list:
    return []


@pytest.fixture
def time_travel_traverser(monkeypatch: pytest.MonkeyPatch):
    events: list[SeededEvent] = [
        SeededEvent(
            1,
            T1,
            "store_memory",
            MEM_A,
            entities=[
                {"label": "Alpha", "entity_type": "CONCEPT"},
                {"label": "Beta", "entity_type": "CONCEPT"},
            ],
            triplets=[
                {
                    "subject_label": "Alpha",
                    "predicate": "relates_to",
                    "object_label": "Beta",
                    "confidence": 0.95,
                }
            ],
        ),
        SeededEvent(
            2,
            T3,
            "store_memory",
            MEM_A,
            entities=[
                {"label": "Gamma", "entity_type": "CONCEPT"},
                {"label": "Delta", "entity_type": "CONCEPT"},
            ],
            triplets=[
                {
                    "subject_label": "Gamma",
                    "predicate": "mentions",
                    "object_label": "Delta",
                    "confidence": 0.8,
                }
            ],
        ),
    ]
    payloads = {MEM_A: "payload_mem_a", MEM_B: "payload_mem_b"}

    last_sql: list[str] = []
    probe_holder: dict[str, str] = {"q": ""}
    conn = TemporalGraphFakeConn(events, payloads, last_sql, embed_probe=probe_holder)
    pool = FakePool(conn)

    async def fake_embed(text: str) -> list[float]:
        probe_holder["q"] = text
        return [0.0, 0.0, float(len(text) % 7)]

    t = GraphRAGTraverser(
        pg_pool=pool, mongo_client=MagicClient(), embedding_fn=fake_embed
    )

    monkeypatch.setattr(t, "_hydrate_sources", _noop_hydrate)
    return t, conn, events


class MagicClient:
    """Minimal motor stand-in (never hit)."""

    memory_archive = None


@pytest.mark.asyncio
async def test_as_of_before_update_sees_original_graph(
    time_travel_traverser: tuple,
) -> None:
    traverser, _conn, _events = time_travel_traverser
    sg = await traverser.search(
        "timeline",
        namespace_id=str(NS_ID),
        max_depth=2,
        anchor_top_k=1,
        as_of=T2,
    )
    labels = {n.label for n in sg.nodes}
    assert labels == {"Alpha", "Beta"}
    preds = {(e.subject, e.predicate, e.obj) for e in sg.edges}
    assert preds == {("Alpha", "relates_to", "Beta")}
    assert sg.anchor in {"Alpha", "Beta"}


@pytest.mark.asyncio
async def test_as_of_after_update_sees_rewritten_memory(
    time_travel_traverser: tuple,
) -> None:
    traverser, _conn, _events = time_travel_traverser
    sg = await traverser.search(
        "timeline",
        namespace_id=str(NS_ID),
        max_depth=2,
        anchor_top_k=1,
        as_of=T4,
    )
    labels = {n.label for n in sg.nodes}
    assert "Alpha" not in labels and "Beta" not in labels
    assert "Gamma" in labels and "Delta" in labels


@pytest.mark.asyncio
async def test_pure_reconstruction_matches_known_historical_snapshots() -> None:
    """
    Cross-check: golden expected node/edge sets from the seed file directly,
    independent of traverser BFS walk (order-insensitive graph identity).
    """

    events: list[SeededEvent] = [
        SeededEvent(
            1,
            T1,
            "store_memory",
            MEM_A,
            [{"label": "Alpha", "entity_type": "CONCEPT"}],
            [
                {
                    "subject_label": "Alpha",
                    "predicate": "p",
                    "object_label": "Beta",
                    "confidence": 1.0,
                }
            ],
        ),
        SeededEvent(2, T2, "forget_memory", MEM_A, [], []),
        SeededEvent(
            3,
            T3,
            "store_memory",
            MEM_B,
            [{"label": "Zeta", "entity_type": "CONCEPT"}],
            [],
        ),
    ]

    snap_t1_5 = _active_store_rows(events, NS_ID, datetime(2026, 1, 1, 10, 20, 0, tzinfo=TZ_UTC))
    assert MEM_A in snap_t1_5 and MEM_B not in snap_t1_5

    snap_after_forget = _active_store_rows(events, NS_ID, T3)
    assert MEM_A not in snap_after_forget and MEM_B in snap_after_forget

    labs_t1_5 = {e["label"] for ev in snap_t1_5.values() for e in ev.entities}
    assert labs_t1_5 == {"Alpha"}

    labs_t4 = {e["label"] for ev in snap_after_forget.values() for e in ev.entities}
    assert labs_t4 == {"Zeta"}


@pytest.mark.asyncio
async def test_as_of_after_forget_yields_no_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the latest event for every memory is forget_memory, anchors are empty."""
    events: list[SeededEvent] = [
        SeededEvent(
            1,
            T1,
            "store_memory",
            MEM_A,
            [{"label": "X", "entity_type": "CONCEPT"}],
            [],
        ),
        SeededEvent(2, T3, "forget_memory", MEM_A, [], []),
    ]
    payloads = {MEM_A: "ref"}
    last_sql: list[str] = []
    probe_holder: dict[str, str] = {"q": ""}
    conn = TemporalGraphFakeConn(events, payloads, last_sql, embed_probe=probe_holder)
    pool = FakePool(conn)

    async def fake_embed(_text: str) -> list[float]:
        return [0.0]

    t = GraphRAGTraverser(
        pg_pool=pool, mongo_client=MagicClient(), embedding_fn=fake_embed
    )
    monkeypatch.setattr(t, "_hydrate_sources", _noop_hydrate)

    sg = await t.search(
        "q",
        namespace_id=str(NS_ID),
        max_depth=2,
        anchor_top_k=1,
        as_of=T4,
    )
    assert sg.anchor == "<none>"
    assert sg.nodes == []
    assert sg.edges == []


# --- parse_as_of (trimcp.temporal — MCP / REST boundary) ---


@pytest.fixture
def _patch_temporal_wall_clock(monkeypatch: pytest.MonkeyPatch) -> datetime:
    """Pinned wall clock so 'future' timestamps are controllable."""
    import trimcp.temporal as temporal_mod

    fixed = datetime(2026, 5, 5, 12, 0, 0, tzinfo=TZ_UTC)

    class _DT(datetime):  # type: ignore[misc, valid-type]
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            if tz is None or tz == TZ_UTC:
                return fixed
            return fixed.astimezone(tz)

    monkeypatch.setattr(temporal_mod, "datetime", _DT)
    return fixed


def test_parse_as_of_none_returns_none() -> None:
    from trimcp.temporal import parse_as_of

    assert parse_as_of(None) is None


def test_parse_as_of_accepts_naive_iso_as_utc(_patch_temporal_wall_clock: datetime) -> None:
    from trimcp.temporal import parse_as_of

    dt = parse_as_of("2026-03-01T10:15:30")
    assert dt == datetime(2026, 3, 1, 10, 15, 30, tzinfo=TZ_UTC)


def test_parse_as_of_accepts_z_suffix(_patch_temporal_wall_clock: datetime) -> None:
    from trimcp.temporal import parse_as_of

    dt = parse_as_of("2026-03-01T10:15:30Z")
    assert dt.tzinfo is not None


def test_parse_as_of_rejects_future(_patch_temporal_wall_clock: datetime) -> None:
    from trimcp.temporal import parse_as_of

    with pytest.raises(ValueError, match="future"):
        parse_as_of("2026-06-01T00:00:00Z")


def test_parse_as_of_rejects_bad_format(_patch_temporal_wall_clock: datetime) -> None:
    from trimcp.temporal import parse_as_of

    with pytest.raises(ValueError, match="ISO 8601"):
        parse_as_of("not-a-timestamp")
