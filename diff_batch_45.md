# Diff Reference for Batch 45

```diff
diff --git a/nce/envelope.py b/nce/envelope.py
new file mode 100644
index 0000000..3a6bc3a
--- /dev/null
+++ b/nce/envelope.py
@@ -0,0 +1,194 @@
+"""
+NCE envelope-encryption subsystem (Part II.4 — Provable Forgetting).
+
+Data Encryption Key (DEK) lifecycle for per-memory (or per-subject) content
+encryption.  The raw content that fans out to MongoDB ``episodes.raw_data`` is
+encrypted under a 256-bit DEK; that DEK is itself **wrapped** (envelope-encrypted)
+under the environment master key and stored alongside the memory row
+(``memories.wrapped_dek`` + ``memories.dek_key_id``).
+
+Crypto reuse
+------------
+This module deliberately does **not** roll its own key-wrapping crypto.  It
+reuses the audited AES-256-GCM envelope already implemented in
+:mod:`nce.signing`:
+
+* :func:`nce.signing.encrypt_signing_key` wraps the raw DEK under the master key
+  (Argon2id or PBKDF2 @ 600K KDF, per-blob random salt + nonce, versioned wire
+  format ``TC3/TC4``).
+* :func:`nce.signing.decrypt_signing_key` unwraps it (auto-detecting the wire
+  format; raises :class:`~nce.signing.SigningKeyDecryptionError` on a wrong key
+  or corrupted blob).
+* :class:`nce.signing.SecureKeyBuffer` holds the transient plaintext DEK and
+  zeroes it on context exit.
+
+The DEK itself is used for **data** encryption (the memory payload) via plain
+AES-256-GCM with a fresh per-call nonce; the wire format is
+``b'TCDEK\\x01' || nonce (12) || ciphertext+tag``.
+
+Provable-forgetting property
+-----------------------------
+Destroying the wrapped DEK (zeroing the ``memories.wrapped_dek`` column) renders
+the corresponding ``episodes.raw_data`` ciphertext permanently undecryptable —
+the master key alone cannot recover the plaintext.  Wiring the read paths and
+``shred_memory`` op is Batch 46; this batch ships only the subsystem + schema.
+
+``NCE_MASTER_KEY`` is environment-only (see :func:`nce.signing.require_master_key`)
+and is never read from or written to any database/settings table.
+"""
+
+from __future__ import annotations
+
+import os
+import uuid
+
+from cryptography.hazmat.primitives.ciphers.aead import AESGCM
+
+from nce.signing import (
+    MasterKey,
+    SecureKeyBuffer,
+    SigningError,
+    decrypt_signing_key,
+    encrypt_signing_key,
+)
+
+# ---------------------------------------------------------------------------
+# Module-level constants
+# ---------------------------------------------------------------------------
+
+# AES-256 → 32-byte DEK.
+_DEK_SIZE: int = 32
+# 96-bit nonce for AES-256-GCM payload encryption (matches signing._NONCE_SIZE).
+_NONCE_SIZE: int = 12
+# Wire-format prefix for DEK-encrypted payloads.  Distinguishes payload
+# ciphertext (this module) from key-wrapping blobs (TC2/TC3/TC4 in signing.py).
+_DEK_PAYLOAD_PREFIX: bytes = b"TCDEK\x01"
+
+
+# ---------------------------------------------------------------------------
+# Exceptions
+# ---------------------------------------------------------------------------
+
+
+class EnvelopeError(SigningError):
+    """Base class for envelope-encryption errors."""
+
+
+class DEKDecryptionError(EnvelopeError):
+    """Raised when AES-256-GCM payload decryption fails (wrong DEK or corruption)."""
+
+
+# ---------------------------------------------------------------------------
+# DEK lifecycle
+# ---------------------------------------------------------------------------
+
+
+def generate_dek() -> bytes:
+    """
+    Generate a fresh 256-bit Data Encryption Key.
+
+    Returns a 32-byte CSPRNG key suitable for AES-256-GCM.  Callers should wrap
+    the returned bytes in a :class:`~nce.signing.SecureKeyBuffer` so the
+    plaintext DEK is zeroed once it has been wrapped under the master key.
+    """
+    return os.urandom(_DEK_SIZE)
+
+
+def new_dek_key_id() -> str:
+    """
+    Return a fresh opaque identifier for a DEK, stored in ``memories.dek_key_id``.
+
+    The id carries no key material — it is an audit/correlation handle so a
+    deletion receipt can name which DEK was destroyed without revealing it.
+    """
+    return f"dek-{uuid.uuid4().hex}"
+
+
+def wrap_dek(dek: bytes, master_key: MasterKey) -> bytes:
+    """
+    Wrap (envelope-encrypt) a raw *dek* under the master key.
+
+    Reuses :func:`nce.signing.encrypt_signing_key` — the same AES-256-GCM
+    envelope (Argon2id/PBKDF2 KDF, per-blob salt + nonce, versioned wire format)
+    that protects signing keys.  The returned bytes are what is stored in
+    ``memories.wrapped_dek``.
+
+    Raises :class:`ValueError` if *dek* is not exactly 32 bytes, or if
+    *master_key* has been zeroed.
+    """
+    if len(dek) != _DEK_SIZE:
+        raise ValueError(f"DEK must be exactly {_DEK_SIZE} bytes; got {len(dek)}.")
+    return encrypt_signing_key(dek, master_key)
+
+
+def unwrap_dek(wrapped_dek: bytes, master_key: MasterKey) -> bytes:
+    """
+    Unwrap a *wrapped_dek* produced by :func:`wrap_dek`.
+
+    Reuses :func:`nce.signing.decrypt_signing_key`, which auto-detects the wire
+    format and raises :class:`~nce.signing.SigningKeyDecryptionError` on a wrong
+    master key or corrupted blob.  Callers should immediately wrap the returned
+    bytes in a :class:`~nce.signing.SecureKeyBuffer`.
+
+    Raises :class:`~nce.signing.SigningKeyDecryptionError` on authentication
+    failure.
+    """
+    return decrypt_signing_key(wrapped_dek, master_key)
+
+
+# ---------------------------------------------------------------------------
+# Payload encryption under a DEK
+# ---------------------------------------------------------------------------
+
+
+def encrypt_with_dek(plaintext: bytes, dek: bytes) -> bytes:
+    """
+    AES-256-GCM encrypt *plaintext* under a raw 32-byte *dek*.
+
+    Wire format: ``b'TCDEK\\x01' || nonce (12) || ciphertext+tag``.  A fresh
+    random nonce is generated per call.
+
+    Raises :class:`ValueError` if *dek* is not exactly 32 bytes.
+    """
+    if len(dek) != _DEK_SIZE:
+        raise ValueError(f"DEK must be exactly {_DEK_SIZE} bytes; got {len(dek)}.")
+    nonce = os.urandom(_NONCE_SIZE)
+    # Wrap the DEK in SecureKeyBuffer so it is zeroed the moment encryption
+    # completes — the raw key must not linger past this scope.
+    with SecureKeyBuffer(dek) as dek_buf:
+        ciphertext_and_tag = AESGCM(bytes(dek_buf)).encrypt(nonce, plaintext, None)
+    return _DEK_PAYLOAD_PREFIX + nonce + ciphertext_and_tag
+
+
+def decrypt_with_dek(blob: bytes, dek: bytes) -> bytes:
+    """
+    Decrypt a *blob* produced by :func:`encrypt_with_dek` under a raw *dek*.
+
+    Raises :class:`DEKDecryptionError` on authentication failure (wrong DEK,
+    truncated/corrupted blob, or a missing/incorrect wire-format prefix).
+    """
+    if len(dek) != _DEK_SIZE:
+        raise ValueError(f"DEK must be exactly {_DEK_SIZE} bytes; got {len(dek)}.")
+    if not blob.startswith(_DEK_PAYLOAD_PREFIX):
+        raise DEKDecryptionError(
+            "payload blob is missing the expected DEK wire-format prefix "
+            "(not produced by encrypt_with_dek, or corrupted)."
+        )
+    tail = blob[len(_DEK_PAYLOAD_PREFIX) :]
+    if len(tail) < _NONCE_SIZE + 16:
+        raise DEKDecryptionError(f"payload blob is too short to be valid (got {len(blob)} bytes).")
+    nonce = tail[:_NONCE_SIZE]
+    ct_and_tag = tail[_NONCE_SIZE:]
+    # Wrap the DEK in SecureKeyBuffer — zeroed the moment decryption completes,
+    # success or failure.
+    try:
+        with SecureKeyBuffer(dek) as dek_buf:
+            return AESGCM(bytes(dek_buf)).decrypt(nonce, ct_and_tag, None)
+    except DEKDecryptionError:
+        raise
+    except Exception as exc:
+        raise DEKDecryptionError(
+            "AES-GCM authentication failed.  The DEK is wrong or the ciphertext "
+            "has been corrupted (or the DEK was destroyed — content is "
+            "cryptographically unrecoverable)."
+        ) from exc
diff --git a/nce/migrations/018_memories_envelope_dek.sql b/nce/migrations/018_memories_envelope_dek.sql
new file mode 100644
index 0000000..688c70c
--- /dev/null
+++ b/nce/migrations/018_memories_envelope_dek.sql
@@ -0,0 +1,16 @@
+-- 018_memories_envelope_dek.sql
+-- Part II.4 (Provable Forgetting) — envelope-encryption DEK columns on memories.
+-- Adds the wrapped Data Encryption Key (envelope-encrypted under NCE_MASTER_KEY
+-- via nce.envelope.wrap_dek) and an opaque DEK identifier.  Destroying
+-- wrapped_dek renders the corresponding episodes.raw_data ciphertext
+-- permanently undecryptable.  Read-path/raw_data encryption wiring is Batch 46.
+-- ============================================================================
+
+ALTER TABLE memories ADD COLUMN IF NOT EXISTS wrapped_dek BYTEA;
+ALTER TABLE memories ADD COLUMN IF NOT EXISTS dek_key_id TEXT;
+
+COMMENT ON COLUMN memories.wrapped_dek IS
+'AES-256-GCM-wrapped Data Encryption Key (envelope-encrypted under NCE_MASTER_KEY). NULL until the memory payload is encrypted (Batch 46). Zeroing this column crypto-shreds episodes.raw_data.';
+
+COMMENT ON COLUMN memories.dek_key_id IS
+'Opaque identifier (no key material) for the wrapped DEK, used in deletion receipts and audit events.';
diff --git a/nce/schema.sql b/nce/schema.sql
index 0c962d0..3dbb455 100644
--- a/nce/schema.sql
+++ b/nce/schema.sql
@@ -88,6 +88,14 @@ CREATE TABLE IF NOT EXISTS memories_default PARTITION OF memories DEFAULT;
 
 ALTER TABLE memories ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
 
+-- Migration 018 (Part II.4 Provable Forgetting): envelope-encryption DEK columns.
+-- wrapped_dek holds the AES-256-GCM-wrapped Data Encryption Key (envelope-encrypted
+-- under NCE_MASTER_KEY via nce.envelope.wrap_dek); dek_key_id is an opaque, key-free
+-- identifier used in deletion receipts/audit events.  Zeroing wrapped_dek crypto-shreds
+-- the corresponding episodes.raw_data ciphertext.  Read-path wiring lands in Batch 46.
+ALTER TABLE memories ADD COLUMN IF NOT EXISTS wrapped_dek BYTEA;
+ALTER TABLE memories ADD COLUMN IF NOT EXISTS dek_key_id TEXT;
+
 -- Data Migration from legacy tables
 DO $$
 DECLARE
diff --git a/tests/test_envelope_dek.py b/tests/test_envelope_dek.py
new file mode 100644
index 0000000..3892ae3
--- /dev/null
+++ b/tests/test_envelope_dek.py
@@ -0,0 +1,123 @@
+"""Unit tests for the envelope-encryption DEK lifecycle (nce/envelope.py).
+
+Pure-unit (no Docker/DB): exercises generate -> wrap -> unwrap round-trips,
+payload encryption under the DEK, and failure on a wrong master key / wrong DEK.
+"""
+
+from __future__ import annotations
+
+import pytest
+from nce.envelope import (
+    _DEK_PAYLOAD_PREFIX,
+    _DEK_SIZE,
+    DEKDecryptionError,
+    decrypt_with_dek,
+    encrypt_with_dek,
+    generate_dek,
+    new_dek_key_id,
+    unwrap_dek,
+    wrap_dek,
+)
+from nce.signing import MasterKey, SigningKeyDecryptionError
+
+
+def test_generate_dek_is_32_bytes_and_random():
+    a = generate_dek()
+    b = generate_dek()
+    assert len(a) == _DEK_SIZE == 32
+    assert len(b) == 32
+    assert a != b  # CSPRNG — collision probability is negligible
+
+
+def test_new_dek_key_id_is_unique_and_carries_no_key_material():
+    id1 = new_dek_key_id()
+    id2 = new_dek_key_id()
+    assert id1 != id2
+    assert id1.startswith("dek-")
+
+
+def test_wrap_unwrap_round_trips():
+    mk = MasterKey(b"m" * 32)
+    dek = generate_dek()
+    wrapped = wrap_dek(dek, mk)
+    # Wrapped blob must not equal the plaintext DEK (it is actually encrypted).
+    assert wrapped != dek
+    assert len(wrapped) > _DEK_SIZE
+    unwrapped = unwrap_dek(wrapped, mk)
+    assert unwrapped == dek
+    mk.zero()
+
+
+def test_wrap_is_nondeterministic_per_blob_nonce_salt():
+    mk = MasterKey(b"m" * 32)
+    dek = generate_dek()
+    w1 = wrap_dek(dek, mk)
+    w2 = wrap_dek(dek, mk)
+    # Per-blob random salt + nonce => identical DEK wraps to different blobs.
+    assert w1 != w2
+    # Both still unwrap to the same DEK.
+    assert unwrap_dek(w1, mk) == unwrap_dek(w2, mk) == dek
+    mk.zero()
+
+
+def test_unwrap_with_wrong_master_key_fails():
+    mk = MasterKey(b"m" * 32)
+    wrong = MasterKey(b"x" * 32)
+    dek = generate_dek()
+    wrapped = wrap_dek(dek, mk)
+    with pytest.raises(SigningKeyDecryptionError):
+        unwrap_dek(wrapped, wrong)
+    mk.zero()
+    wrong.zero()
+
+
+def test_wrap_rejects_wrong_size_dek():
+    mk = MasterKey(b"m" * 32)
+    with pytest.raises(ValueError, match="DEK must be exactly 32 bytes"):
+        wrap_dek(b"too-short", mk)
+    mk.zero()
+
+
+def test_payload_encrypt_decrypt_round_trips_under_dek():
+    dek = generate_dek()
+    plaintext = b"the raw memory content that fans out to episodes.raw_data"
+    blob = encrypt_with_dek(plaintext, dek)
+    assert blob.startswith(_DEK_PAYLOAD_PREFIX)
+    assert plaintext not in blob  # actually encrypted
+    assert decrypt_with_dek(blob, dek) == plaintext
+
+
+def test_payload_decrypt_with_wrong_dek_fails():
+    dek = generate_dek()
+    other_dek = generate_dek()
+    blob = encrypt_with_dek(b"secret", dek)
+    with pytest.raises(DEKDecryptionError):
+        decrypt_with_dek(blob, other_dek)
+
+
+def test_destroyed_dek_makes_ciphertext_undecryptable():
+    """Provable-forgetting property: without the DEK the ciphertext is unrecoverable.
+
+    Wrapping under the master key + losing the wrapped DEK means even the master
+    key cannot recover the plaintext — only a DEK that round-trips can.
+    """
+    mk = MasterKey(b"m" * 32)
+    dek = generate_dek()
+    wrapped = wrap_dek(dek, mk)
+    blob = encrypt_with_dek(b"forget me", dek)
+
+    # Simulate DEK destruction: the only path back to the DEK is the wrapped
+    # blob; a *different* (replacement) DEK cannot decrypt the old ciphertext.
+    replacement = generate_dek()
+    with pytest.raises(DEKDecryptionError):
+        decrypt_with_dek(blob, replacement)
+
+    # Sanity: the legitimately unwrapped DEK still decrypts.
+    assert decrypt_with_dek(blob, unwrap_dek(wrapped, mk)) == b"forget me"
+    mk.zero()
+
+
+def test_payload_decrypt_rejects_missing_prefix():
+    dek = generate_dek()
+    with pytest.raises(DEKDecryptionError, match="prefix"):
+        decrypt_with_dek(b"no-prefix-here-garbage-bytes", dek)
```
