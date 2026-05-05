"""
TriMCP cryptographic signing infrastructure (Phase 0.2).

Every stored memory and every event_log row is signed with HMAC-SHA256 over
the JCS-canonicalised (RFC 8785) key fields of that record.  The signature
allows any retrieval to verify integrity and detect post-write tampering.

Key storage
-----------
Signing keys live in the ``signing_keys`` Postgres table as AES-256-GCM
encrypted blobs.  The AES encryption key (master key) comes from the
``TRIMCP_MASTER_KEY`` environment variable in dev, or a KMS-backed secret in
production.

Server bootstrap
----------------
Call ``require_master_key()`` at startup (before the asyncpg pool is used).
It raises ``MasterKeyMissingError`` if ``TRIMCP_MASTER_KEY`` is absent or
empty — the server must not start without it.

Active-key caching
------------------
``get_active_key()`` maintains a module-level in-process cache (5-minute TTL)
so the ``signing_keys`` table is not hit on every write.  The cache is
invalidated automatically on ``rotate_key()``.

Thread/async safety
-------------------
All public ``async`` functions accept an ``asyncpg.Connection`` and must be
called inside an active transaction when the caller requires atomicity.
The in-memory key cache is not locked; for the single-threaded asyncio event
loop that is the normal deployment model this is safe.  For multi-threaded
deployments (e.g. thread-pool workers) the caller must hold its own lock
around ``get_active_key`` / ``rotate_key`` pairs.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

import asyncpg

try:
    import jcs as _jcs_lib  # RFC 8785 — preferred

    def canonical_json(data: dict[str, Any]) -> bytes:  # noqa: D401
        """Return the RFC 8785-canonical JSON encoding of *data*."""
        return _jcs_lib.canonicalize(data)

except ImportError:  # pragma: no cover – jcs is in requirements.txt; handle gracefully
    import json as _json

    def canonical_json(data: dict[str, Any]) -> bytes:  # type: ignore[misc]
        """
        Fallback RFC 8785-compatible canonical JSON.

        Covers the TriMCP signing payload (UUIDs, ISO-8601 strings, integers).
        Full ECMAScript number serialisation divergence is not triggered
        because signing inputs never contain bare floats.
        """
        return _json.dumps(
            data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")


from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_MASTER_KEY_ENV: str = "TRIMCP_MASTER_KEY"
_NONCE_SIZE: int = 12           # 96-bit nonce for AES-256-GCM
_KEY_CACHE_TTL_S: float = 300.0  # 5 minutes


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SigningError(Exception):
    """Base class for all signing-related errors."""


class MasterKeyMissingError(SigningError):
    """Raised at startup when ``TRIMCP_MASTER_KEY`` is absent or empty."""


class NoActiveSigningKeyError(SigningError):
    """Raised when no row with ``status='active'`` exists in ``signing_keys``."""


class SigningKeyDecryptionError(SigningError):
    """Raised when AES-GCM decryption fails (wrong master key or corrupted blob)."""


# ---------------------------------------------------------------------------
# In-memory key cache
# ---------------------------------------------------------------------------


@dataclass
class _CachedKey:
    key_id: str
    raw_key: bytes
    expires_at: float  # time.monotonic() deadline


_key_cache: _CachedKey | None = None


# ---------------------------------------------------------------------------
# AES-256-GCM helpers
# ---------------------------------------------------------------------------


def _derive_aes_key(master_key_text: str) -> bytes:
    """
    Derive a 32-byte AES key from *master_key_text* via SHA-256.

    In production the master key itself should already be 32 cryptographically
    random bytes (hex-encoded or base64).  This derivation step ensures that
    an arbitrary-length env var is safely reduced to a fixed-size key.
    """
    return hashlib.sha256(master_key_text.encode("utf-8")).digest()


def encrypt_signing_key(raw_key: bytes, master_key_text: str) -> bytes:
    """
    AES-256-GCM encrypt *raw_key* with the master key.

    Wire format: ``nonce (12 bytes) || ciphertext+tag``.

    This function is exposed for the key-rotation CLI; callers should not
    store the returned bytes anywhere other than ``signing_keys.encrypted_key``.
    """
    aes_key = _derive_aes_key(master_key_text)
    nonce = os.urandom(_NONCE_SIZE)
    ciphertext_and_tag = AESGCM(aes_key).encrypt(nonce, raw_key, None)
    return nonce + ciphertext_and_tag


def decrypt_signing_key(encrypted_key: bytes, master_key_text: str) -> bytes:
    """
    Decrypt a blob produced by ``encrypt_signing_key``.

    Raises ``SigningKeyDecryptionError`` on authentication failure (wrong
    master key, truncated blob, or data corruption).
    """
    if len(encrypted_key) < _NONCE_SIZE + 16:  # GCM tag is 16 bytes
        raise SigningKeyDecryptionError(
            "encrypted_key blob is too short to be valid "
            f"(got {len(encrypted_key)} bytes, expected ≥{_NONCE_SIZE + 16})."
        )
    aes_key = _derive_aes_key(master_key_text)
    nonce = encrypted_key[:_NONCE_SIZE]
    ct_and_tag = encrypted_key[_NONCE_SIZE:]
    try:
        return AESGCM(aes_key).decrypt(nonce, ct_and_tag, None)
    except Exception as exc:
        raise SigningKeyDecryptionError(
            "AES-GCM authentication failed.  This means either the master key "
            "is wrong or the signing key blob has been corrupted."
        ) from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def require_master_key() -> str:
    """
    Return ``TRIMCP_MASTER_KEY`` or raise ``MasterKeyMissingError``.

    Call once at server startup before any signing operation is attempted.
    The returned value is the raw env-var string; callers should not persist it
    beyond the immediate need.
    """
    mk = os.environ.get(_MASTER_KEY_ENV, "").strip()
    if not mk:
        raise MasterKeyMissingError(
            f"Environment variable {_MASTER_KEY_ENV!r} is missing or empty.  "
            "The TriMCP server cannot start without a signing master key.  "
            "Set TRIMCP_MASTER_KEY to a secret string of ≥32 random characters."
        )
    return mk


async def get_active_key(
    conn: asyncpg.Connection,
) -> tuple[str, bytes]:
    """
    Return ``(key_id, raw_signing_key)`` for the current active key.

    Checks the module-level TTL cache first.  On a cache miss the active key
    is fetched from ``signing_keys``, decrypted, and cached.

    Parameters
    ----------
    conn:
        An ``asyncpg.Connection``.  Need not be inside a transaction.

    Raises
    ------
    MasterKeyMissingError
        If ``TRIMCP_MASTER_KEY`` is absent.
    NoActiveSigningKeyError
        If no ``status='active'`` row exists in ``signing_keys``.
    SigningKeyDecryptionError
        If the stored key blob cannot be decrypted with the master key.
    """
    global _key_cache

    now = time.monotonic()
    if _key_cache is not None and _key_cache.expires_at > now:
        return _key_cache.key_id, _key_cache.raw_key

    master_key = require_master_key()

    row = await conn.fetchrow(
        """
        SELECT key_id, encrypted_key
        FROM   signing_keys
        WHERE  status = 'active'
        ORDER  BY created_at DESC
        LIMIT  1
        """
    )
    if row is None:
        raise NoActiveSigningKeyError(
            "No active signing key exists in signing_keys.  "
            "Run the key-rotation initialisation to create the first key."
        )

    raw_key = decrypt_signing_key(bytes(row["encrypted_key"]), master_key)
    _key_cache = _CachedKey(
        key_id=row["key_id"],
        raw_key=raw_key,
        expires_at=now + _KEY_CACHE_TTL_S,
    )
    log.debug("Signing key cache refreshed (key_id=%s).", row["key_id"])
    return _key_cache.key_id, _key_cache.raw_key


def sign_fields(fields: dict[str, Any], raw_signing_key: bytes) -> bytes:
    """
    Return HMAC-SHA256 over the JCS-canonical encoding of *fields*.

    *fields* must be a dict whose values are JSON-serialisable (strings,
    integers, nested dicts, None).  The signature is computed over the UTF-8
    bytes of the canonical JSON representation.
    """
    canonical_bytes = canonical_json(fields)
    return hmac.new(raw_signing_key, canonical_bytes, hashlib.sha256).digest()


def verify_fields(
    fields: dict[str, Any],
    raw_signing_key: bytes,
    expected_signature: bytes,
) -> bool:
    """
    Return ``True`` iff the HMAC-SHA256 of *fields* matches *expected_signature*.

    Uses ``hmac.compare_digest`` for constant-time comparison.
    """
    computed = sign_fields(fields, raw_signing_key)
    return hmac.compare_digest(computed, expected_signature)


async def rotate_key(conn: asyncpg.Connection) -> str:
    """
    Generate and persist a new active signing key, retiring all current ones.

    Runs inside a DB transaction.  On success the in-memory cache is
    invalidated so the next ``get_active_key`` call loads the new key.

    Returns
    -------
    str
        The ``key_id`` of the newly created key.

    Raises
    ------
    MasterKeyMissingError
        If ``TRIMCP_MASTER_KEY`` is absent.
    asyncpg.PostgresError
        Propagated unchanged on DB failure.
    """
    global _key_cache

    master_key = require_master_key()
    new_raw_key = os.urandom(32)                         # 256-bit HMAC key
    new_key_id = f"sk-{uuid.uuid4().hex[:16]}"
    encrypted_blob = encrypt_signing_key(new_raw_key, master_key)

    async with conn.transaction():
        await conn.execute(
            """
            UPDATE signing_keys
            SET    status = 'retired',
                   retired_at = now()
            WHERE  status = 'active'
            """
        )
        await conn.execute(
            """
            INSERT INTO signing_keys (key_id, encrypted_key, status)
            VALUES ($1, $2, 'active')
            """,
            new_key_id,
            encrypted_blob,
        )

    # Invalidate cache — next call to get_active_key will reload from DB.
    _key_cache = None
    log.info("Signing key rotated.  New key_id=%s.", new_key_id)
    return new_key_id
