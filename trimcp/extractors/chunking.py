"""
Structured chunking driven by Section objects (Appendix J.2).

RCA — consumption by chunk_structured:
- Each Section is a hard boundary: chunks never concatenate text from two different
  Section instances. That preserves Excel (one Section per visible sheet), PowerPoint
  (one Section per slide body and a separate Section for speaker notes), Word headings,
  and PDF pages as non-splittable units at the indexing layer.
- Long Sections (e.g. huge pasted text in one cell) may be split into multiple
  StructuredChunk records sharing the same structure_path / source_order and increasing
  part_index; embeddings still cite the same anchor.
- chunk_structured walks sections in ``order`` and applies a character budget per chunk,
  preferring paragraph boundaries (\\n\\n) inside the Section.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from trimcp.extractors.core import Section

__all__ = ["StructuredChunk", "chunk_structured"]


@dataclass
class StructuredChunk:
    text: str
    structure_path: str
    section_type: str
    source_order: int
    part_index: int


def chunk_structured(
    sections: list[Section],
    *,
    max_chars: int = 4000,
    overlap: int = 200,
) -> list[StructuredChunk]:
    """
    Build chunks that never span two Sections.
    Within a Section, split on paragraphs; optional overlap copies tail of previous part.
    """
    if overlap >= max_chars:
        overlap = max(0, max_chars // 8)

    out: list[StructuredChunk] = []
    for sec in sorted(sections, key=lambda s: s.order):
        text = sec.text.strip()
        if not text:
            continue
        parts = _split_section_text(text, max_chars, overlap)
        for i, p in enumerate(parts):
            out.append(
                StructuredChunk(
                    text=p,
                    structure_path=sec.structure_path,
                    section_type=sec.section_type,
                    source_order=sec.order,
                    part_index=i,
                )
            )
    return out


def _split_section_text(text: str, max_chars: int, _overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    paragraphs = re.split(r"\n{2,}", text)
    chunks: list[str] = []
    buf: list[str] = []
    cur_len = 0

    for para in paragraphs:
        sep = 2 if buf else 0
        need = sep + len(para)
        if need > max_chars and not buf:
            for i in range(0, len(para), max_chars):
                chunks.append(para[i : i + max_chars])
            continue
        if cur_len + need <= max_chars:
            buf.append(para)
            cur_len += need
            continue
        if buf:
            chunks.append("\n\n".join(buf))
        buf = []
        cur_len = 0
        if len(para) > max_chars:
            for i in range(0, len(para), max_chars):
                chunks.append(para[i : i + max_chars])
            continue
        buf = [para]
        cur_len = len(para)
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks
