"""J.17 — Project files: .mpp (optional MPXJ sidecar), .pub (LibreOffice → docx)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from trimcp.extractors import pdf_ext
from trimcp.extractors.core import ExtractionResult, Section, empty_skipped
from trimcp.extractors.libreoffice import libreoffice_convert
from trimcp.extractors.office_word import extract_docx

log = logging.getLogger(__name__)


def _extract_mpp_sync(blob: bytes) -> ExtractionResult:
    warnings: list[str] = []
    cmd = os.environ.get("TRIMCP_MPXJ_EXTRACTOR", "").strip()
    if not cmd:
        return empty_skipped(
            "mpp",
            "mpp_extractor_not_configured",
            warnings=[
                "MS Project .mpp requires a sidecar: set TRIMCP_MPXJ_EXTRACTOR to a CLI "
                "that writes JSON to stdout. The input path is passed in env TRIMCP_MPP_INPUT.",
            ],
        )
    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mpp", delete=False) as tf:
            tf.write(blob)
            path = Path(tf.name)
        try:
            argv = shlex.split(cmd, posix=os.name != "nt")
        except ValueError as e:
            return empty_skipped("mpp", "mpp_bad_command", warnings=[str(e)])
        if not argv:
            return empty_skipped(
                "mpp", "mpp_bad_command", warnings=["TRIMCP_MPXJ_EXTRACTOR expanded to empty argv"]
            )
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "TRIMCP_MPP_INPUT": str(path)},
        )
        if proc.returncode != 0:
            return empty_skipped(
                "mpp",
                "mpp_sidecar_failed",
                warnings=[(proc.stderr or proc.stdout or f"exit {proc.returncode}")[:500]],
            )
        raw = (proc.stdout or "").strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return empty_skipped("mpp", "mpp_json_invalid", warnings=[str(e), raw[:200]])

        sections: list[Section] = []
        order = 0
        tasks = data.get("tasks") if isinstance(data, dict) else None
        if isinstance(tasks, list):
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                name = str(t.get("name") or t.get("Name") or "").strip()
                if not name:
                    continue
                lvl = t.get("outlineLevel", t.get("outline_level", 0))
                prefix = f"Task[{lvl}]: "
                sections.append(
                    Section(
                        text=f"{prefix}{name}",
                        structure_path=f"MPP task {order + 1}",
                        section_type="project",
                        order=order,
                    )
                )
                order += 1
        notes = data.get("notes") if isinstance(data, dict) else None
        if isinstance(notes, list):
            for n in notes:
                if isinstance(n, str) and n.strip():
                    sections.append(
                        Section(
                            text=n.strip(),
                            structure_path=f"MPP note {order + 1}",
                            section_type="note",
                            order=order,
                        )
                    )
                    order += 1

        full = "\n".join(s.text for s in sections)
        if not full.strip():
            warnings.append("mpp_sidecar_empty_tasks")
        return ExtractionResult(
            method="mpp",
            text=full,
            sections=sections
            or [Section(text="(no tasks)", structure_path="MPP", section_type="project", order=0)],
            metadata={"task_sections": len(sections)},
            warnings=warnings,
        )
    except subprocess.TimeoutExpired:
        return empty_skipped("mpp", "mpp_sidecar_timeout", warnings=["MPXJ extractor timed out"])
    except FileNotFoundError as e:
        return empty_skipped("mpp", "mpp_executable_missing", warnings=[str(e)])
    except Exception as e:
        log.warning("mpp_extract_failed: %s", e, exc_info=True)
        return empty_skipped("mpp", "extraction_failed", warnings=[str(e)])
    finally:
        if path and path.is_file():
            try:
                path.unlink()
            except OSError:
                pass


async def extract_mpp(blob: bytes) -> ExtractionResult:
    return await asyncio.to_thread(_extract_mpp_sync, blob)


async def extract_pub(blob: bytes) -> ExtractionResult:
    warnings: list[str] = []
    try:
        docx_bytes = await asyncio.to_thread(libreoffice_convert, blob, ".pub", "docx")
    except Exception as e:
        return empty_skipped("pub", "libreoffice_exception", warnings=[str(e)])

    if not docx_bytes:
        # Publisher sometimes converts better to PDF for text
        try:
            pdf_bytes = await asyncio.to_thread(libreoffice_convert, blob, ".pub", "pdf")
        except Exception as e:
            warnings.append(f"pub_pdf_fallback:{e}")
            pdf_bytes = None
        if pdf_bytes:
            try:
                return await pdf_ext.extract_pdf(pdf_bytes)
            except Exception as e:
                return empty_skipped("pub", "pdf_fallback_failed", warnings=[str(e)])
        return empty_skipped(
            "pub",
            "libreoffice_conversion_failed",
            warnings=warnings
            + [
                "Install LibreOffice and ensure soffice is on PATH (or set TRIMCP_SOFFICE).",
            ],
        )

    try:
        inner = await extract_docx(docx_bytes)
    except Exception as e:
        return empty_skipped("pub", "docx_parse_failed", warnings=[str(e)])

    warnings.extend(inner.warnings)
    meta = dict(inner.metadata)
    meta["source_format"] = "pub_via_libreoffice_docx"
    return ExtractionResult(
        method="pub",
        text=inner.text,
        sections=inner.sections,
        metadata=meta,
        warnings=warnings,
    )
