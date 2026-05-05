"""
Phase 2.1 — Automated re-embedding migration (Strategy A, dimension-compatible).

Provides deterministic vector math helpers, queue-driven backfill, quality-gate
overlap checks, and *active embedding* resolution so semantic search keeps using the
currently authoritative column while ``embedding_v2`` is filled in the background.

Postgres/asyncpg adapters can wrap this orchestration later; callers pass a ``Store``
that satisfies :class:`ReembeddingStorePort`.
"""
from __future__ import annotations

import asyncio
import hashlib
import math
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, Mapping, Protocol, Sequence


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity with L2 normalization; clamps to [-1, 1] for FP noise."""
    if len(a) != len(b):
        raise ValueError("dimension mismatch")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    raw = dot / (na * nb)
    return max(-1.0, min(1.0, raw))


def neighbor_overlap_fraction(
    old_neighbors: Iterable[str],
    new_neighbors: Iterable[str],
) -> float:
    """
    Jaccard similarity of two neighbour-ID sets (roadmap §2.1 quality gate).

    Interpretation:
        overlap >= threshold (e.g. 0.7) ⇒ gate pass for that sample pair.
        overlap < threshold ⇒ migration commit should be blocked until resolved.
    """
    a = frozenset(old_neighbors)
    b = frozenset(new_neighbors)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def deterministic_unit_embedding(
    text: str,
    *,
    model_version: str,
    dimension: int,
    rotation: Sequence[float] | None = None,
) -> list[float]:
    """
    Deterministic mock embedding: SHA-256–seeded repeatable noise, **L2 = 1**.

    Passing a different ``model_version`` rotates the derivation so vectors differ
    (model bump) but remain stable for identical text (TEST-2.1-01).
    """
    if dimension < 1:
        raise ValueError("dimension must be >= 1")
    vec: list[float] = []
    counter = 0
    while len(vec) < dimension:
        blob = hashlib.sha256(f"{model_version}\0{text}\0{counter}".encode("utf-8")).digest()
        for i in range(0, len(blob) - 1, 2):
            coord = int.from_bytes(blob[i : i + 2], "big") / 65535.0 - 0.5
            vec.append(coord)
            if len(vec) >= dimension:
                break
        counter += 1
    vec = vec[:dimension]
    if rotation is not None:
        if len(rotation) != dimension:
            raise ValueError("rotation length must match dimension")
        vec = [v + r for v, r in zip(vec, rotation)]
    s = math.sqrt(sum(x * x for x in vec))
    if s == 0.0:
        return [1.0 if i == 0 else 0.0 for i in range(dimension)]
    return [x / s for x in vec]


@dataclass(frozen=True)
class MemoryEmbeddingRow:
    memory_id: str
    canonical_text: str
    embedding_v1: list[float]
    embedding_v2: list[float] | None = None
    embedding_v2_target_model_id: str | None = None


class MigrationPhase(str, Enum):
    IDLE = "idle"
    BACKFILLING = "backfilling"
    COMMITTED = "committed"
    ABORTED = "aborted"


class ReembeddingStorePort(Protocol):
    """Abstract store boundary — production uses asyncpg; tests use an in-memory impl."""

    async def pop_pending_ids(self, limit: int) -> list[str]:
        ...

    async def load_row(self, memory_id: str) -> MemoryEmbeddingRow | None:
        ...

    async def write_embedding_v2(
        self,
        memory_id: str,
        *,
        embedding: Sequence[float],
        model_id: str,
    ) -> None:
        ...


class ReembeddingMigrationOrchestrator:
    """
    Drives backlog processing after a target model bump.

    Concurrent **reads** remain valid as long as the store delegates
    ``active_embedding()`` to embedding_v1 until :meth:`commit` is called —
    callers must not erase v1 prematurely.
    """

    def __init__(
        self,
        *,
        store: ReembeddingStorePort,
        embed_fn_v2: "EmbeddingFn",
        target_model_id: str,
        dimension: int,
    ):
        self._store = store
        self.embed_fn_v2 = embed_fn_v2
        self.target_model_id = target_model_id
        self.dimension = dimension
        self.phase = MigrationPhase.BACKFILLING
        self._cv = asyncio.Condition()

    async def process_batch(self, batch_size: int) -> int:
        """Dequeue up to *batch_size* IDs, embed with v2, persist without touching v1."""
        if self.phase != MigrationPhase.BACKFILLING:
            return 0
        ids = await self._store.pop_pending_ids(batch_size)
        if not ids:
            return 0
        for mid in ids:
            row = await self._store.load_row(mid)
            if row is None:
                continue
            vec = self.embed_fn_v2(row.canonical_text, dimension=self.dimension)
            if len(vec) != self.dimension:
                raise ValueError(
                    f"embed_fn_v2 returned dim {len(vec)}, expected {self.dimension}"
                )
            await self._store.write_embedding_v2(
                mid, embedding=vec, model_id=self.target_model_id
            )
        async with self._cv:
            self._cv.notify_all()
        return len(ids)

    def mark_aborted(self) -> None:
        """Align orchestrator state when the store aborts a migration."""
        self.phase = MigrationPhase.ABORTED

    def mark_committed(self) -> None:
        """Call after :meth:`InMemoryReembeddingStore.commit_primary_to_v2`."""
        self.phase = MigrationPhase.COMMITTED


@dataclass
class InMemoryReembeddingStore:
    """
    Test/dev store: dual embeddings + pending queue + explicit commit/abort.

    ``active_embedding`` always returns v1 until :meth:`commit`; then returns v2
    where present else v1.
    """

    _rows: dict[str, MemoryEmbeddingRow]
    _pending: asyncio.Queue[str]
    phase: MigrationPhase = MigrationPhase.IDLE
    _lock: asyncio.Lock = dataclass(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_lock", asyncio.Lock())

    @classmethod
    def from_records(
        cls,
        records: Mapping[str, MemoryEmbeddingRow],
        *,
        initial_pending: Iterable[str],
    ) -> InMemoryReembeddingStore:
        q: asyncio.Queue[str] = asyncio.Queue()
        store = cls(_rows=dict(records), _pending=q, phase=MigrationPhase.BACKFILLING)
        for mid in initial_pending:
            store._pending.put_nowait(mid)
        return store

    def pending_qsize(self) -> int:
        return self._pending.qsize()

    async def pop_pending_ids(self, limit: int) -> list[str]:
        ids: list[str] = []
        for _ in range(limit):
            try:
                ids.append(self._pending.get_nowait())
            except asyncio.QueueEmpty:
                break
        return ids

    async def load_row(self, memory_id: str) -> MemoryEmbeddingRow | None:
        async with self._lock:
            row = self._rows.get(memory_id)
            return row

    async def write_embedding_v2(
        self,
        memory_id: str,
        *,
        embedding: Sequence[float],
        model_id: str,
    ) -> None:
        async with self._lock:
            old = self._rows.get(memory_id)
            if old is None:
                return
            self._rows[memory_id] = MemoryEmbeddingRow(
                memory_id=old.memory_id,
                canonical_text=old.canonical_text,
                embedding_v1=old.embedding_v1,
                embedding_v2=list(embedding),
                embedding_v2_target_model_id=model_id,
            )

    def active_embedding(self, memory_id: str) -> list[float] | None:
        """
        Simulate live search/recall reads against the **authoritative** column.

        Strategy A: ``embedding_v1`` is always the serving vector.  The worker fills
        ``embedding_v2`` in the shadow slot; after :meth:`commit_primary_to_v2`, the
        promoted vectors live in ``embedding_v1`` again — reads never observe a hole.
        """
        row = self._rows.get(memory_id)
        if row is None:
            return None
        return row.embedding_v1

    def commit_primary_to_v2(self) -> None:
        """Atomic logical swap — only after quality gate passes (roadmap §2.1)."""
        if self.phase == MigrationPhase.ABORTED:
            raise RuntimeError("cannot commit an aborted migration")
        for mid, row in list(self._rows.items()):
            if row.embedding_v2 is None:
                continue
            self._rows[mid] = MemoryEmbeddingRow(
                memory_id=row.memory_id,
                canonical_text=row.canonical_text,
                embedding_v1=list(row.embedding_v2),
                embedding_v2=None,
                embedding_v2_target_model_id=None,
            )
        self.phase = MigrationPhase.COMMITTED

    def abort_and_clear_pending_v2(self) -> None:
        """Revert pending v2 fills; restores v1-only rows (TEST-2.1-04 spirit)."""
        self.phase = MigrationPhase.ABORTED
        for mid, row in list(self._rows.items()):
            self._rows[mid] = MemoryEmbeddingRow(
                memory_id=row.memory_id,
                canonical_text=row.canonical_text,
                embedding_v1=row.embedding_v1,
                embedding_v2=None,
                embedding_v2_target_model_id=None,
            )
        while not self._pending.empty():
            try:
                self._pending.get_nowait()
            except asyncio.QueueEmpty:
                break


EmbeddingFn = Callable[..., list[float]]
"""Embedder callable: accepts ``text`` plus optional kwargs (e.g. ``dimension=int``)."""
