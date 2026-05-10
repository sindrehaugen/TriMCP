"""J.19 OCR helpers and image OCR (pytesseract)."""

from __future__ import annotations

import asyncio
import io
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from trimcp.extractors.core import Section

log = logging.getLogger(__name__)


async def ocr_pil_image(img: Any, *, lang: str = "eng") -> tuple[str, list[str]]:
    warnings: list[str] = []

    def _run() -> tuple[str, float]:
        import pytesseract

        data = pytesseract.image_to_data(
            img, lang=lang, output_type=pytesseract.Output.DICT
        )
        confs: list[int] = []
        for c in data.get("conf", []):
            try:
                ic = int(float(c))
            except (TypeError, ValueError):
                continue
            if ic >= 0:
                confs.append(ic)
        avg = (sum(confs) / len(confs) / 100.0) if confs else 0.0
        text = (pytesseract.image_to_string(img, lang=lang) or "").strip()
        return text, avg

    try:
        text, avg = await asyncio.to_thread(_run)
    except Exception as e:
        log.warning("ocr_failed: %s", e)
        return "", [f"ocr_failed: {e}"]

    if avg > 0 and avg < 0.30 and text:
        return "", ["ocr_low_confidence: discarded (<30%)"]
    if 0 < avg < 0.60:
        warnings.append(f"ocr_low_confidence: average {avg:.0%}")
    return text, warnings


async def ocr_image_bytes(blob: bytes, *, lang: str = "eng") -> tuple[str, list[str]]:
    def _open():
        from PIL import Image

        im = Image.open(io.BytesIO(blob))
        return im.convert("RGB")

    try:
        img = await asyncio.to_thread(_open)
    except Exception as e:
        log.warning("ocr_image_open_failed: %s", e)
        return "", [f"ocr_image_open_failed: {e}"]
    return await ocr_pil_image(img, lang=lang)


async def ocr_pdf_to_sections(
    blob: bytes, *, lang: str = "eng"
) -> tuple[str, list[Section], list[str]]:
    try:
        from pdf2image import convert_from_bytes
    except ImportError as e:
        return "", [], [f"pdf2image_unavailable: {e}"]

    def _pages():
        return convert_from_bytes(blob, dpi=150)

    try:
        pages = await asyncio.to_thread(_pages)
    except Exception as e:
        log.warning("pdf2image_failed: %s", e)
        return "", [], [f"pdf2image_failed: {e}"]

    all_text: list[str] = []
    sections: list[Section] = []
    warnings: list[str] = []
    order = 0
    for i, pil in enumerate(pages, start=1):
        txt, w = await ocr_pil_image(pil, lang=lang)
        warnings.extend(w)
        if txt.strip():
            sections.append(
                Section(
                    text=txt,
                    structure_path=f"Page {i}",
                    section_type="body",
                    order=order,
                )
            )
            order += 1
            all_text.append(txt)
    return "\n\n".join(all_text), sections, warnings
