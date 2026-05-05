"""
Phase 5 / Phase 1 enterprise — Jina embeddings with hardware backend abstraction (§8.2).

``EmbeddingBackend`` routes inference through CPU / CUDA / ROCm / XPU / OpenVINO NPU / MPS.
Module-level ``embed`` and ``embed_batch`` preserve the public contract used by the
orchestrator and RQ worker: async APIs, 768 dimensions, thread-pool offload for blocking stacks.

Vector dimension and cosine semantics are unchanged — PostgreSQL pgvector ingestion is unaffected.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import random
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from trimcp.config import cfg

log = logging.getLogger("tri-stack-embeddings")

MODEL_ID = "jinaai/jina-embeddings-v2-base-code"
VECTOR_DIM = 768

# Model encode is not thread-safe across mixed backends — single worker serializes.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="trimcp-embed")

# Lazy singleton selected by ``detect_backend()``.
_backend: EmbeddingBackend | None = None


def _stub_vector(text: str) -> list[float]:
    """Deterministic 768-dim mock — identical inputs → identical vectors (CI / failures)."""
    seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**31)
    rng = random.Random(seed)
    return [rng.uniform(-1.0, 1.0) for _ in range(VECTOR_DIM)]


def _is_rocm() -> bool:
    try:
        import torch

        hip = getattr(torch.version, "hip", None)
        return bool(hip)
    except Exception:
        return False


def _torch_mps_available() -> bool:
    try:
        import torch

        return bool(
            hasattr(torch.backends, "mps")
            and torch.backends.mps.is_available()
            and torch.backends.mps.is_built()
        )
    except Exception:
        return False


def _torch_xpu_available() -> bool:
    try:
        import torch

        return bool(hasattr(torch, "xpu") and torch.xpu.is_available())
    except Exception:
        return False


def _intel_npu_available() -> bool:
    """
    Conservative auto-detect: OpenVINO Runtime exposes an NPU device, or the user
    pre-declares intent via TRIMCP_OPENVINO_MODEL_DIR (export present).
    """
    model_dir = cfg.TRIMCP_OPENVINO_MODEL_DIR
    if model_dir and os.path.isdir(model_dir):
        return any(model_dir_path_has_openvino_xml(model_dir))

    try:
        from openvino import Core

        core = Core()
        devs = [d for d in core.available_devices if "NPU" in d.upper()]
        return bool(devs)
    except Exception:
        return False


def model_dir_path_has_openvino_xml(model_dir: str) -> list[str]:
    """Return basenames of .xml files looks like OpenVINO IR."""
    try:
        names = []
        for root, _, files in os.walk(model_dir):
            for f in files:
                if f.endswith(".xml"):
                    names.append(f)
            break
        return names
    except Exception:
        return []


@lru_cache(maxsize=8)
def _load_sentence_transformer(device: str):
    """Load SentenceTransformer once per logical device string."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        log.warning("sentence_transformers not installed.")
        return None
    try:
        log.info("Loading embedding model %s on device %r", MODEL_ID, device)
        model = SentenceTransformer(MODEL_ID, trust_remote_code=True, device=device)
        log.info("Embedding model ready (device=%r).", device)
        return model
    except Exception as e:
        log.warning("Could not load %s on %r: %s", MODEL_ID, device, e)
        return None


class EmbeddingBackend(ABC):
    """Abstract embedding provider; batch-first API (§8.2)."""

    @abstractmethod
    def _sync_embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Blocking batch encode; length of output must match length of ``texts``."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self._sync_embed_batch, texts)


class CPUBackend(EmbeddingBackend):
    """Baseline torch CPU / SentenceTransformer."""

    def _sync_embed_batch(self, texts: list[str]) -> list[list[float]]:
        model = _load_sentence_transformer("cpu")
        if model is None:
            return [_stub_vector(t) for t in texts]
        try:
            vectors = model.encode(
                texts,
                normalize_embeddings=True,
                batch_size=min(32, len(texts)),
                show_progress_bar=False,
            )
            return [v.tolist() for v in vectors]
        except Exception as e:
            log.error("CPU batch embedding failed: %s", e)
            return [_stub_vector(t) for t in texts]


class CUDABackend(EmbeddingBackend):
    """NVIDIA CUDA — PyTorch CUDA device (non-ROCm wheels)."""

    def _sync_embed_batch(self, texts: list[str]) -> list[list[float]]:
        model = _load_sentence_transformer("cuda")
        if model is None:
            return [_stub_vector(t) for t in texts]
        try:
            vectors = model.encode(
                texts,
                normalize_embeddings=True,
                batch_size=min(32, len(texts)),
                show_progress_bar=False,
            )
            return [v.tolist() for v in vectors]
        except Exception as e:
            log.error("CUDA batch embedding failed: %s", e)
            return [_stub_vector(t) for t in texts]


class ROCmBackend(EmbeddingBackend):
    """AMD ROCm — PyTorch exposes CUDA APIs on ROCm builds."""

    def _sync_embed_batch(self, texts: list[str]) -> list[list[float]]:
        model = _load_sentence_transformer("cuda")
        if model is None:
            return [_stub_vector(t) for t in texts]
        try:
            vectors = model.encode(
                texts,
                normalize_embeddings=True,
                batch_size=min(32, len(texts)),
                show_progress_bar=False,
            )
            return [v.tolist() for v in vectors]
        except Exception as e:
            log.error("ROCm batch embedding failed: %s", e)
            return [_stub_vector(t) for t in texts]


class XPUBackend(EmbeddingBackend):
    """Intel GPU via torch.xpu."""

    def _sync_embed_batch(self, texts: list[str]) -> list[list[float]]:
        model = _load_sentence_transformer("xpu")
        if model is None:
            return [_stub_vector(t) for t in texts]
        try:
            vectors = model.encode(
                texts,
                normalize_embeddings=True,
                batch_size=min(32, len(texts)),
                show_progress_bar=False,
            )
            return [v.tolist() for v in vectors]
        except Exception as e:
            log.error("XPU batch embedding failed: %s", e)
            return [_stub_vector(t) for t in texts]


class MPSBackend(EmbeddingBackend):
    """Apple Silicon MPS."""

    def _sync_embed_batch(self, texts: list[str]) -> list[list[float]]:
        model = _load_sentence_transformer("mps")
        if model is None:
            return [_stub_vector(t) for t in texts]
        try:
            vectors = model.encode(
                texts,
                normalize_embeddings=True,
                batch_size=min(32, len(texts)),
                show_progress_bar=False,
            )
            return [v.tolist() for v in vectors]
        except Exception as e:
            log.error("MPS batch embedding failed: %s", e)
            return [_stub_vector(t) for t in texts]


def _mean_pool(last_hidden_state, attention_mask):
    import torch

    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    summed = torch.sum(last_hidden_state * mask, dim=1)
    counts = torch.clamp(mask.sum(dim=1), min=1e-9)
    return summed / counts


@lru_cache(maxsize=2)
def _load_openvino_npu_bundle(model_dir: str, seq_len: int):
    from optimum.intel import OVModelForFeatureExtraction
    from transformers import AutoTokenizer

    model = OVModelForFeatureExtraction.from_pretrained(model_dir)
    tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)
    return model, tokenizer, seq_len


class CognitiveRemoteBackend(EmbeddingBackend):
    """
    OpenAI-compatible ``/v1/embeddings`` against the bundled cognitive image [D2/D7].

    Base URL example: ``http://cognitive:11435`` (no trailing ``/v1`` — it is appended).
    Auth: optional ``TRIMCP_COGNITIVE_API_KEY`` env var sent as ``Bearer`` if non-empty.
    """

    def __init__(self) -> None:
        self._base = (cfg.TRIMCP_COGNITIVE_BASE_URL or "").rstrip("/")
        self._model = (cfg.TRIMCP_COGNITIVE_EMBEDDING_MODEL or "").strip() or None

    def _sync_embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not self._base:
            log.warning("CognitiveRemoteBackend: empty base URL — stubbing.")
            return [_stub_vector(t) for t in texts]
        import httpx

        api_key = cfg.TRIMCP_COGNITIVE_API_KEY
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        url = f"{self._base}/v1/embeddings"
        payload: dict = {"input": texts}
        if self._model:
            payload["model"] = self._model

        try:
            with httpx.Client(timeout=120.0) as client:
                r = client.post(url, json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            log.error("Cognitive embedding HTTP failed: %s", e)
            return [_stub_vector(t) for t in texts]

        rows = data.get("data") if isinstance(data, dict) else None
        if not rows or not isinstance(rows, list):
            log.error("Cognitive embedding response missing data[]: %s", data)
            return [_stub_vector(t) for t in texts]

        # OpenAI-style payloads include ``index``; sort defensively when batched.
        indexed: list[tuple[int, list[float]]] = []
        for item in rows:
            if not isinstance(item, dict):
                log.error("Invalid embedding row from cognitive: %r", item)
                return [_stub_vector(t) for t in texts]
            emb = item.get("embedding")
            if not isinstance(emb, list):
                log.error("Invalid embedding row from cognitive: %r", item)
                return [_stub_vector(t) for t in texts]
            idx = int(item["index"]) if "index" in item else len(indexed)
            indexed.append((idx, [float(x) for x in emb]))
        indexed.sort(key=lambda t: t[0])
        vectors = [v for _, v in indexed]

        if len(vectors) != len(texts):
            log.error(
                "Cognitive embedding count mismatch: got %d expected %d",
                len(vectors),
                len(texts),
            )
            return [_stub_vector(t) for t in texts]

        bad_dims = [len(v) for v in vectors if len(v) != VECTOR_DIM]
        if bad_dims:
            log.warning(
                "Cognitive returned non-%d-dim vectors (dims=%s); PG schema expects %d",
                VECTOR_DIM,
                bad_dims[:5],
                VECTOR_DIM,
            )
        return vectors


class OpenVINONPUBackend(EmbeddingBackend):
    """
    Intel NPU via pre-exported OpenVINO IR (static shapes). Requires TRIMCP_OPENVINO_MODEL_DIR.
    Long texts: truncated to seq_len (export-time bound); full token chunking can be layered later.
    """

    def __init__(self, model_dir: str | None = None):
        self.model_dir = (model_dir or cfg.TRIMCP_OPENVINO_MODEL_DIR or "").strip()
        if not self.model_dir:
            log.warning("OpenVINONPUBackend: TRIMCP_OPENVINO_MODEL_DIR not set — will stub.")

    def _sync_embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not self.model_dir or not os.path.isdir(self.model_dir):
            return [_stub_vector(t) for t in texts]
        seq_len = cfg.TRIMCP_OPENVINO_SEQ_LEN
        try:
            model, tokenizer, _ = _load_openvino_npu_bundle(self.model_dir, seq_len)
        except Exception as e:
            log.error("OpenVINO NPU load failed: %s", e)
            return [_stub_vector(t) for t in texts]

        try:
            import numpy as np
            import torch

            encoded = tokenizer(
                texts,
                padding="max_length",
                truncation=True,
                max_length=seq_len,
                return_tensors="pt",
            )
            # Optimum OV models accept dict of numpy or torch depending on version —
            # convert to numpy for widest compatibility.
            inputs = {k: v.numpy() for k, v in encoded.items()}
            out = model(**inputs)
            last = out.last_hidden_state if hasattr(out, "last_hidden_state") else out[0]
            if not isinstance(last, torch.Tensor):
                last = torch.tensor(last)
            mask = encoded["attention_mask"]
            pooled = _mean_pool(last, mask)
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            return pooled.detach().cpu().numpy().astype(np.float64).tolist()
        except Exception as e:
            log.error("OpenVINO NPU inference failed: %s", e)
            return [_stub_vector(t) for t in texts]


_BACKEND_BUILDERS = {
    "cpu": CPUBackend,
    "cuda": CUDABackend,
    "rocm": ROCmBackend,
    "xpu": XPUBackend,
    "openvino_npu": OpenVINONPUBackend,
    "openvino": OpenVINONPUBackend,
    "mps": MPSBackend,
}


def detect_backend() -> EmbeddingBackend:
    """
    Select backend from TRIMCP_BACKEND or auto-detect (§8.2 / §8.4 parity with Go wizard).

    When ``TRIMCP_COGNITIVE_BASE_URL`` is set and ``TRIMCP_BACKEND`` is unset or unknown,
    embeddings use the bundled cognitive HTTP API [D2/D7] instead of loading SentenceTransformer.
    """
    pref = cfg.TRIMCP_BACKEND
    cognitive_url = (cfg.TRIMCP_COGNITIVE_BASE_URL or "").strip()

    if pref:
        if pref not in _BACKEND_BUILDERS:
            log.warning("Unknown TRIMCP_BACKEND=%r — falling back to auto-detect.", pref)
        else:
            log.info("Embedding backend forced by TRIMCP_BACKEND=%s", pref)
            return _BACKEND_BUILDERS[pref]()

    if cognitive_url:
        log.info(
            "Embedding backend: CognitiveRemoteBackend (%s) [TRIMCP_LLM_PROVIDER=%s]",
            cognitive_url,
            cfg.TRIMCP_LLM_PROVIDER or "local-cognitive-model",
        )
        return CognitiveRemoteBackend()

    try:
        import torch
    except ImportError:
        log.warning("torch not importable — using CPU backend stub path.")
        return CPUBackend()

    if torch.cuda.is_available() and not _is_rocm():
        log.info("Auto-selected CUDABackend (CUDA available, not ROCm).")
        return CUDABackend()
    if _is_rocm() and torch.cuda.is_available():
        log.info("Auto-selected ROCmBackend.")
        return ROCmBackend()
    if _torch_xpu_available():
        log.info("Auto-selected XPUBackend.")
        return XPUBackend()
    if _intel_npu_available():
        log.info("Auto-selected OpenVINONPUBackend.")
        return OpenVINONPUBackend()
    if _torch_mps_available():
        log.info("Auto-selected MPSBackend.")
        return MPSBackend()

    log.info("Auto-selected CPUBackend.")
    return CPUBackend()


def get_backend() -> EmbeddingBackend:
    global _backend
    if _backend is None:
        _backend = detect_backend()
    return _backend


def reset_backend_singleton_for_tests() -> None:
    """Test hook: clear lazy singleton so ``detect_backend`` runs again."""
    global _backend
    _backend = None


# --- Public async API (stable for orchestrator / graph / worker) ---


async def embed(text: str) -> list[float]:
    vecs = await get_backend().embed([text])
    return vecs[0] if vecs else _stub_vector(text)


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Chunked batches at ``cfg.EMBED_BATCH_CHUNK`` so large AST runs yield to the event loop.
    """
    if not texts:
        return []
    backend = get_backend()
    loop = asyncio.get_event_loop()
    results: list[list[float]] = []
    for start in range(0, len(texts), cfg.EMBED_BATCH_CHUNK):
        chunk = texts[start : start + cfg.EMBED_BATCH_CHUNK]
        results.extend(await backend.embed(chunk))
    return results
