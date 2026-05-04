"""Extension → async extractor routing (Appendix J.1)."""
from __future__ import annotations

import logging
import mimetypes
from collections.abc import Awaitable, Callable

from trimcp.extractors.core import empty_skipped, ExtractionResult
from trimcp.extractors.encryption import maybe_encrypted_skip

log = logging.getLogger(__name__)

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
    from trimcp.extractors import adobe_ext  # noqa: F401
    from trimcp.extractors import cad_ext  # noqa: F401
    from trimcp.extractors import diagrams  # noqa: F401
    from trimcp.extractors import email_ext  # noqa: F401
    from trimcp.extractors import pdf_ext  # noqa: F401
    from trimcp.extractors import plaintext  # noqa: F401
    from trimcp.extractors import project_ext  # noqa: F401
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
    ensure_registered()
    ext = _resolve_ext(filename, mime_type)
    if not ext or ext not in _REGISTRY:
        return empty_skipped(
            "dispatch",
            "unsupported_format",
            warnings=[f"unknown or unregistered extension: {ext!r} (file={filename!r})"],
        )
    enc = maybe_encrypted_skip(blob, filename=filename, extension=ext)
    if enc is not None:
        return enc
    try:
        return await _REGISTRY[ext](blob)
    except Exception as e:
        log.warning("extract_bytes failed ext=%s: %s", ext, e, exc_info=True)
        return empty_skipped("dispatch", "extraction_failed", warnings=[str(e)])


async def extract_with_fallback(
    blob: bytes,
    filename: str | None = None,
    mime_type: str | None = None,
) -> ExtractionResult:
    """Same as extract_bytes; name matches Appendix J.9 attachment recursion."""
    return await extract_bytes(blob, filename, mime_type)
