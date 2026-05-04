"""LibreOffice headless conversion (J.4, J.6, J.8, J.22 local mode)."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


def _resolve_soffice() -> str:
    exe = os.environ.get("TRIMCP_SOFFICE", "soffice")
    if shutil.which(exe):
        return exe
    if os.name == "nt":
        for candidate in (
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ):
            if os.path.isfile(candidate):
                return candidate
    return exe


def libreoffice_convert(
    blob: bytes,
    source_ext: str,
    target_ext: str,
    *,
    timeout: int = 180,
) -> bytes | None:
    """
    Convert document bytes via `soffice --headless --convert-to`.
    Returns None on failure (partial extraction elsewhere should log and continue).
    """
    ext = source_ext if source_ext.startswith(".") else f".{source_ext}"
    target = target_ext.lstrip(".")
    soffice = _resolve_soffice()
    try:
        with tempfile.TemporaryDirectory(prefix="trimcp_lo_") as d:
            td = Path(d)
            src = td / f"source{ext}"
            src.write_bytes(blob)
            cmd = [
                soffice,
                "--headless",
                "--norestore",
                "--nolockcheck",
                "--nodefault",
                "--nofirststartwizard",
                "--convert-to",
                target,
                "--outdir",
                str(td),
                str(src),
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                text=False,
            )
            if proc.returncode != 0:
                log.warning(
                    "libreoffice_failed rc=%s stderr=%s",
                    proc.returncode,
                    (proc.stderr or b"")[:500],
                )
                return None
            # LO names output: source.docx from source.doc
            out = td / f"source.{target}"
            if not out.is_file():
                for p in td.iterdir():
                    if p.suffix.lower() == f".{target}" and p.name != src.name:
                        out = p
                        break
            if not out.is_file():
                log.warning("libreoffice_no_output %s", list(td.iterdir()))
                return None
            return out.read_bytes()
    except FileNotFoundError:
        log.warning("libreoffice_not_found: %s", soffice)
        return None
    except subprocess.TimeoutExpired:
        log.warning("libreoffice_timeout")
        return None
    except Exception as e:
        log.warning("libreoffice_error: %s", e)
        return None
