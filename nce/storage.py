"""
NCE (Neuro-Cognitive Engine) Object Storage Helper.
Provides secure pre-signed URL generation with strict namespace tenant isolation.
"""

from __future__ import annotations

import logging
import mimetypes
from datetime import timedelta
from uuid import UUID

from minio import Minio

log = logging.getLogger(__name__)

# Maximum allowed expiry for pre-signed URLs (15 minutes)
MAX_EXPIRY_SECONDS = 900


def generate_secure_presigned_url(
    minio_client: Minio,
    bucket_name: str,
    object_name: str,
    method: str = "GET",
    expiry_seconds: int = 900,
    expected_mime: str | None = None,
    current_namespace_id: str | UUID | None = None,
) -> str:
    """
    Generate a secure pre-signed URL for a MinIO object.

    Enforces the following security boundaries:
    1. Tenant Isolation: If current_namespace_id is specified, validates that
       the object_name starts with the prefix "{namespace_id}/".
    2. Expiry Bounding: Restricts expiry to a maximum of 15 minutes (900 seconds).
    3. MIME/Extension Validation: For PUT operations, validates that the extension
       in the object_name is supported by the NCE document dispatcher.
    """
    # 1. Tenant Isolation Check
    if current_namespace_id:
        ns_str = str(current_namespace_id).strip().lower()
        if not object_name.lower().startswith(f"{ns_str}/"):
            log.warning(
                "Access denied: Tenant path mismatch. Namespace %s requested object %s",
                ns_str,
                object_name,
            )
            raise PermissionError("Access denied: Tenant path mismatch.")

    # 2. Expiry Bounding Check
    bounded_expiry = min(max(expiry_seconds, 1), MAX_EXPIRY_SECONDS)
    expires_delta = timedelta(seconds=bounded_expiry)

    # 3. Method and MIME Type Validation
    method_upper = method.upper().strip()
    if method_upper not in ("GET", "PUT"):
        raise ValueError(f"Unsupported HTTP method for pre-signed URL: {method}")

    # Validate file extension if writing (PUT)
    if method_upper == "PUT":
        # Extract extension and validate
        if "." in object_name:
            ext = object_name.rsplit(".", 1)[-1].lower()
        else:
            ext = ""

        # We need to make sure the registry is populated
        from nce.extractors.dispatch import _REGISTRY, ensure_registered

        ensure_registered()

        # If we have an expected MIME, check if it maps to a registry extension
        if expected_mime:
            mime_lower = expected_mime.lower().split(";")[0].strip()
            guessed_ext = mimetypes.guess_extension(mime_lower)
            if guessed_ext:
                ext_key = guessed_ext.lstrip(".")
                if ext_key not in _REGISTRY:
                    raise ValueError(f"Unsupported MIME type for storage upload: {expected_mime}")

        # Standard extension check
        if ext and ext not in _REGISTRY:
            raise ValueError(f"Unsupported file extension for upload: .{ext}")

    # 4. Generate URL via MinIO client
    try:
        if method_upper == "GET":
            # For GET operations, enforce attachment Content-Disposition to prevent inline HTML/XSS
            response_headers = {
                "response-content-type": expected_mime or "application/octet-stream",
                "response-content-disposition": "attachment",
            }
            url = minio_client.presigned_get_object(
                bucket_name,
                object_name,
                expires=expires_delta,
                response_headers=response_headers,
            )
        else:
            # PUT operation
            url = minio_client.presigned_put_object(
                bucket_name,
                object_name,
                expires=expires_delta,
            )
        return url
    except Exception as e:
        log.error("Failed to generate pre-signed URL: %s", e)
        raise RuntimeError(f"Storage service failure: {e}") from e
