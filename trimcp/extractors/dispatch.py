"""Extension → async extractor routing (Appendix J.1).

Queue dispatch (§5.4): lane-based priority routing via RQ.
Real-time / API extractions land on ``high_priority``; batch / webhook
processing lands on ``batch_processing``.  The worker dequeues
``high_priority`` first (see ``start_worker.py``).
"""

from __future__ import annotations

import logging
import mimetypes
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rq import Queue

from trimcp.extractors.core import ExtractionResult, empty_skipped
from trimcp.extractors.encryption import maybe_encrypted_skip

log = logging.getLogger(__name__)

# ── Priority queue lane names ──────────────────────────────────────────
HIGH_PRIORITY_QUEUE = "high_priority"
"""Queue lane for user-facing / real-time API calls (default priority > 0)."""

BATCH_QUEUE = "batch_processing"
"""Queue lane for webhooks, bridge resyncs, and bulk ``index_all.py`` runs."""

_DEFAULT_QUEUE = "default"
"""Legacy queue name — retained for backward compatibility with RQ defaults."""


def get_queue_name(priority: int = 0) -> str:
    """Map a numeric priority to a Redis queue lane name.

    * ``priority > 0``  → ``"high_priority"``
    * ``priority == 0`` → ``"batch_processing"``
    """
    return HIGH_PRIORITY_QUEUE if priority > 0 else BATCH_QUEUE


def get_priority_queue(priority: int, connection: Any) -> Queue:
    """Return an RQ ``Queue`` routed to the correct lane for *priority*.

    Thin wrapper so enqueue sites don't have to import RQ themselves.
    ``connection`` must be a *sync* Redis client (``redis.Redis``).
    """
    from rq import Queue

    return Queue(get_queue_name(priority), connection=connection)


Handler = Callable[[bytes], Awaitable[ExtractionResult]]

_REGISTRY: dict[str, Handler] = {}
_MIME_MAP: dict[str, str] = {
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/markdown": "md",
    "text/html": "html",
    "text/csv": "csv",
    "application/json": "json",
    "application/xml": "xml",
    "text/xml": "xml",
    "message/rfc822": "eml",
}

# Lightweight pure-Python magic-byte → MIME mapping (no external deps).
# Covers the formats most likely to be used in spoofing attacks.
_MAGIC_BYTES: list[tuple[bytes, str]] = [
    (b"%PDF", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"PK\x03\x04", "application/zip"),
    (b"PK\x05\x06", "application/zip"),
    (b"<!DOCTYPE html", "text/html"),
    (b"<!doctype html", "text/html"),
    (b"<html", "text/html"),
    (b"<HTML", "text/html"),
    (b"<?xml", "text/xml"),
    (b"{\"", "application/json"),
    (b"[\n", "application/json"),
]


def _magic_mime_from_bytes(blob: bytes) -> str | None:
    """Return a MIME type guessed from the first bytes of *blob*, or None."""
    if not blob:
        return None
    head = blob[:512]
    for magic, mime in _MAGIC_BYTES:
        if head.startswith(magic):
            return mime
    return None


def _is_security_relevant_mismatch(ext_mime: str | None, magic_mime: str | None) -> bool:
    """Return True if the extension-derived MIME and magic-byte MIME disagree
    on a security-relevant boundary (e.g. image vs archive vs executable)."""
    if ext_mime is None or magic_mime is None:
        return False
    ext_family = ext_mime.split("/")[0]
    magic_family = magic_mime.split("/")[0]
    # Zip-based office docs are expected to look like zip
    if ext_mime in ("application/pdf",) and magic_mime == "application/pdf":
        return False
    # Office formats are zip-based; allow zip magic for them
    office_zips = ("application/vnd.openxmlformats", "application/vnd.ms-office")
    if ext_mime.startswith(office_zips) and magic_mime == "application/zip":
        return False
    # Reject: image pretends to be archive/script, or archive pretends to be image
    dangerous = {
        ("image", "application"),
        ("image", "text"),
        ("application", "image"),
        ("text", "image"),
    }
    return (ext_family, magic_family) in dangerous


def register_extension(ext: str, handler: Handler) -> None:
    key = ext.lower().lstrip(".")
    _REGISTRY[key] = handler


def register_mime(mime: str, ext_key: str) -> None:
    _MIME_MAP[mime.lower()] = ext_key.lower().lstrip(".")


def extension_from_filename(filename: str | None) -> str | None:
    if not filename or "." not in filename:
        return None
    return filename.rsplit(".", 1)[-1].lower()


def _resolve_ext(filename: str | None, mime_type: str | None) -> str | None:
    ext = extension_from_filename(filename)
    if ext and ext in _REGISTRY:
        return ext
    if mime_type:
        mt = mime_type.split(";")[0].strip().lower()
        mapped = _MIME_MAP.get(mt)
        if mapped and mapped in _REGISTRY:
            return mapped
    if filename and not ext:
        guessed, _ = mimetypes.guess_type(filename)
        if guessed:
            mt = guessed.lower()
            mapped = _MIME_MAP.get(mt)
            if mapped and mapped in _REGISTRY:
                return mapped
    return ext


_initialized = False


def ensure_registered() -> None:
    """Populate registry on first use to avoid import cycles with email extractors."""
    global _initialized
    if _initialized:
        return
    from trimcp.extractors import (
        adobe_ext,  # noqa: F401
        cad_ext,  # noqa: F401
        diagrams,  # noqa: F401
        email_ext,  # noqa: F401
        pdf_ext,  # noqa: F401
        plaintext,  # noqa: F401
        project_ext,  # noqa: F401
    )
    from trimcp.extractors.office_excel import extract_xls, extract_xlsx
    from trimcp.extractors.office_pptx import extract_ppt, extract_pptx
    from trimcp.extractors.office_word import extract_doc, extract_docx

    register_extension("docx", extract_docx)
    register_extension("doc", extract_doc)
    register_extension("xlsx", extract_xlsx)
    register_extension("xls", extract_xls)
    register_extension("pptx", extract_pptx)
    register_extension("ppt", extract_ppt)
    register_extension("pdf", pdf_ext.extract_pdf)
    register_extension("ai", adobe_ext.extract_ai)
    register_extension("msg", email_ext.extract_msg)
    register_extension("eml", email_ext.extract_eml)
    for ext, fn in [
        ("txt", plaintext.extract_txt),
        ("md", plaintext.extract_markdown),
        ("csv", plaintext.extract_csv),
        ("tsv", plaintext.extract_tsv),
        ("html", plaintext.extract_html),
        ("htm", plaintext.extract_html),
        ("rtf", plaintext.extract_rtf),
        ("json", plaintext.extract_json),
        ("xml", plaintext.extract_xml),
        ("yaml", plaintext.extract_yaml),
        ("yml", plaintext.extract_yaml),
        ("ipynb", plaintext.extract_ipynb),
    ]:
        register_extension(ext, fn)

    register_extension("vsdx", diagrams.extract_vsdx)
    register_extension("drawio", diagrams.extract_drawio)
    register_extension("mermaid", diagrams.extract_mermaid)
    register_extension("mmd", diagrams.extract_mermaid)
    register_extension("psd", adobe_ext.extract_psd)
    register_extension("idml", adobe_ext.extract_idml)
    register_extension("indd", adobe_ext.extract_indd)
    register_extension("dxf", cad_ext.extract_dxf)
    register_extension("dwg", cad_ext.extract_dwg)
    register_extension("rvt", cad_ext.extract_rvt)
    register_extension("skp", cad_ext.extract_skp)
    register_extension("mpp", project_ext.extract_mpp)
    register_extension("pub", project_ext.extract_pub)
    _initialized = True


async def extract_bytes(
    blob: bytes,
    filename: str | None = None,
    mime_type: str | None = None,
) -> ExtractionResult:
    from trimcp.config import cfg
    from trimcp.observability import EXTRACTION_REJECTED_TOO_LARGE_TOTAL, get_tracer

    tracer = get_tracer()

    with tracer.start_as_current_span("extractors.dispatch") as span:
        span.set_attribute("trimcp.filename", filename or "unknown")
        span.set_attribute("trimcp.mime_type", mime_type or "unknown")

        if len(blob) > cfg.TRIMCP_MAX_ATTACHMENT_BYTES:
            EXTRACTION_REJECTED_TOO_LARGE_TOTAL.inc()
            return empty_skipped(
                "dispatch",
                "payload_too_large",
                warnings=[
                    f"blob {len(blob)} B exceeds limit {cfg.TRIMCP_MAX_ATTACHMENT_BYTES} B"
                ],
            )

        ensure_registered()
        ext = _resolve_ext(filename, mime_type)
        if not ext or ext not in _REGISTRY:
            return empty_skipped(
                "dispatch",
                "unsupported_format",
                warnings=[
                    f"unknown or unregistered extension: {ext!r} (file={filename!r})"
                ],
            )

        # Magic-byte cross-check (Item E)
        magic_mime = _magic_mime_from_bytes(blob)
        ext_mime = mimetypes.guess_type(filename or f".{ext}")[0] if ext else None
        if _is_security_relevant_mismatch(ext_mime, magic_mime):
            from trimcp.observability import EXTRACTION_MIME_MISMATCH_TOTAL

            EXTRACTION_MIME_MISMATCH_TOTAL.inc()
            log.warning(
                "MIME mismatch: extension claims %s but magic bytes say %s (file=%s)",
                ext_mime,
                magic_mime,
                filename,
            )
            return empty_skipped(
                "dispatch",
                "mime_mismatch",
                warnings=[
                    f"extension claims {ext_mime} but magic bytes indicate {magic_mime}"
                ],
            )

        span.set_attribute("trimcp.extension", ext)

        enc = maybe_encrypted_skip(blob, filename=filename, extension=ext)
        if enc is not None:
            return enc
        try:
            return await _REGISTRY[ext](blob)
        except Exception as e:
            log.warning("extract_bytes failed ext=%s: %s", ext, e, exc_info=True)
            span.record_exception(e)
            return empty_skipped("dispatch", "extraction_failed", warnings=[str(e)])


async def extract_with_fallback(
    blob: bytes,
    filename: str | None = None,
    mime_type: str | None = None,
) -> ExtractionResult:
    """Same as extract_bytes; name matches Appendix J.9 attachment recursion."""
    return await extract_bytes(blob, filename, mime_type)
