"""
Intel NPU — static-shape OpenVINO export for jinaai/jina-embeddings-v2-base-code (§8.3).

Call this from the installer or a one-shot admin script after the Hugging Face snapshot
is available locally. This module does not download weights by itself unless you call
`export_jina_to_openvino_npu` with `local_files_only=False` and allow hub access.

Export output is loaded at runtime by `OpenVINONPUBackend` via `TRIMCP_OPENVINO_MODEL_DIR`.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("tri-stack-openvino-export")

DEFAULT_MODEL_ID = "jinaai/jina-embeddings-v2-base-code"


def export_jina_to_openvino_npu(
    output_dir: str | Path,
    *,
    model_id_or_path: str = DEFAULT_MODEL_ID,
    batch_size: int = 1,
    sequence_length: int = 512,
    compile_for_npu: bool = False,
    local_files_only: bool = False,
) -> Path:
    """
    Export the code-embedding model to OpenVINO IR with fixed batch × sequence shapes
    required by Intel NPU (static graphs only).

    Mirrors §8.3:
      1. ``OVModelForFeatureExtraction.from_pretrained(..., export=True, compile=False)``
      2. ``model.reshape(batch_size=batch_size, sequence_length=sequence_length)``
      3. Optional ``compile()`` then ``save_pretrained(output_dir)``

    Parameters
    ----------
    output_dir:
        Directory to write IR + tokenizer artifacts (e.g. ./jina-openvino-npu).
    model_id_or_path:
        Hugging Face hub id or local snapshot path.
    batch_size:
        Static batch dimension (installer typically uses 1).
    sequence_length:
        Fixed token length; inference truncates/pads to this bound.
    compile_for_npu:
        When True, runs OpenVINO ``compile()`` after reshape.
    local_files_only:
        When True, ``from_pretrained`` never hits the hub (offline / air-gapped).

    Returns
    -------
    Path
        Resolved output directory.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from optimum.intel import OVModelForFeatureExtraction
    except ImportError as e:
        raise RuntimeError(
            "openvino_npu_export requires optimum with Intel OpenVINO support. "
            "Install e.g. pip install 'optimum[openvino-intel]' openvino"
        ) from e

    log.info(
        "OpenVINO NPU export: model=%r out=%s batch=%s seq=%s local_only=%s",
        model_id_or_path,
        output_dir,
        batch_size,
        sequence_length,
        local_files_only,
    )

    model = OVModelForFeatureExtraction.from_pretrained(
        model_id_or_path,
        export=True,
        compile=False,
        local_files_only=local_files_only,
    )

    model.reshape(batch_size=batch_size, sequence_length=sequence_length)

    if compile_for_npu:
        model.compile()

    model.save_pretrained(output_dir)

    try:
        from transformers import AutoTokenizer

        tok = AutoTokenizer.from_pretrained(
            model_id_or_path,
            local_files_only=local_files_only,
            trust_remote_code=True,
        )
        tok.save_pretrained(output_dir)
    except Exception as e:
        log.warning("Tokenizer save_pretrained failed (export may still be usable): %s", e)

    manifest = output_dir / "trimcp_openvino_export_manifest.txt"
    manifest.write_text(
        "\n".join(
            [
                f"model_source={model_id_or_path}",
                f"batch_size={batch_size}",
                f"sequence_length={sequence_length}",
                f"compile_for_npu={compile_for_npu}",
                f"local_files_only={local_files_only}",
                "exporter=trimcp.openvino_npu_export.export_jina_to_openvino_npu",
            ]
        ),
        encoding="utf-8",
    )

    log.info("OpenVINO export finished: %s", output_dir)
    return output_dir
