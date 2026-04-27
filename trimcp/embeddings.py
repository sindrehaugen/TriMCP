"""
Phase 5 — Jina Embeddings
Wraps jinaai/jina-embeddings-v2-base-code (768-dim, code-optimized) via sentence-transformers.
Model is loaded once at module level; inference is offloaded to a thread pool so the
async event loop is never blocked.
Falls back to the deterministic hash-based stub when the model is unavailable (CI / low-RAM).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import random
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from trimcp.config import cfg

log = logging.getLogger("tri-stack-embeddings")

MODEL_ID = "jinaai/jina-embeddings-v2-base-code"
VECTOR_DIM = 768
# One worker — model is not thread-safe; serialise inference
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jina-embed")


# --- Model loader (cached — loaded once per process) ---

@lru_cache(maxsize=1)
def _load_model():
    """Load model synchronously. Called from the executor thread on first use."""
    try:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        log.info(f"Loading embedding model: {MODEL_ID}")
        model = SentenceTransformer(MODEL_ID, trust_remote_code=True)
        log.info("Embedding model ready.")
        return model
    except Exception as e:
        log.warning(f"Could not load {MODEL_ID}: {e}. Using hash stub.")
        return None


def _stub_vector(text: str) -> list[float]:
    """Deterministic 768-dim mock — identical text → identical vector."""
    seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**31)
    rng = random.Random(seed)
    return [rng.uniform(-1.0, 1.0) for _ in range(VECTOR_DIM)]


def _sync_embed(text: str) -> list[float]:
    """Blocking encode — runs inside the executor thread."""
    log.debug("Embedding start: %r...", text[:50])
    model = _load_model()
    if model is None:
        log.debug("No model, using stub for %r", text[:20])
        return _stub_vector(text)
    try:
        log.debug("Model encode starting...")
        vector = model.encode(text, normalize_embeddings=True)
        log.debug("Model encode finished.")
        return vector.tolist()
    except Exception as e:
        log.error(f"Embedding inference failed: {e}. Falling back to stub.")
        return _stub_vector(text)


async def embed(text: str) -> list[float]:
    """
    Async entry point. Offloads blocking model inference to the thread executor
    so the event loop stays responsive during embedding.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _sync_embed, text)


def _sync_batch(texts: list[str]) -> list[list[float]]:
    """Blocking batch encode — runs inside the executor thread."""
    model = _load_model()
    if model is None:
        return [_stub_vector(t) for t in texts]
    try:
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]
    except Exception as e:
        log.error(f"Batch embedding failed: {e}. Falling back to stub.")
        return [_stub_vector(t) for t in texts]


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Batch encode — more efficient than N individual calls for code indexing.
    Chunked into cfg.EMBED_BATCH_CHUNK groups at the Python level so a file with
    thousands of AST nodes cannot exhaust memory by holding every input string
    and every output tensor simultaneously. Between chunks control returns to
    the event loop, so other saga steps aren't starved during a large index.
    """
    if not texts:
        return []
    loop = asyncio.get_event_loop()
    results: list[list[float]] = []
    for start in range(0, len(texts), cfg.EMBED_BATCH_CHUNK):
        chunk = texts[start:start + cfg.EMBED_BATCH_CHUNK]
        chunk_vectors = await loop.run_in_executor(_executor, _sync_batch, chunk)
        results.extend(chunk_vectors)
    return results
