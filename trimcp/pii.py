"""
Phase 0.3 — PII Detection and Auto-Redaction Pipeline.
Intercepts payloads before they hit the LLM provider interface and masks sensitive entities.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
from typing import TYPE_CHECKING, cast

from trimcp.assertion import infer_assertion_type  # noqa: F401 — re-export for trimcp.pii API
from trimcp.models import NamespacePIIConfig, PIIEntity, PIIPolicy, PIIProcessResult
from trimcp.signing import encrypt_signing_key, require_master_key

if TYPE_CHECKING:
    pass

log = logging.getLogger("tri-stack-pii")

# Pseudonym tokens: first 16 bytes of HMAC-SHA256 (128 bits), base64url-encoded
# (~22 chars).  Per-namespace key must provide at least 64 bits of key material
# (UTF-8 length ≥ 8).  128-bit collision resistance (2^64 birthday bound) is
# adequate for pseudonyms within a single namespace.
_MIN_PSEUDONYM_SECRET_BYTES = 8

# Simple regex fallback for environments without Presidio installed
_FALLBACK_REGEXES = {
    "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "PHONE": r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "CREDIT_CARD": r"\b(?:\d[ -]*?){13,16}\b",
}


def scan(text: str, config: NamespacePIIConfig) -> list[PIIEntity]:
    """
    Scans the text for PII entities defined in the namespace config.
    Uses Presidio if available, otherwise falls back to basic regex.
    """
    if not config.entity_types:
        return []

    entities: list[PIIEntity] = []

    try:
        try:
            from presidio_analyzer import AnalyzerEngine

            analyzer = AnalyzerEngine()
            results = analyzer.analyze(text=text, entities=config.entity_types, language='en')
            for r in results:
                value = text[r.start : r.end]
                if value not in config.allowlist:
                    entities.append(
                        PIIEntity(
                            start=r.start,
                            end=r.end,
                            entity_type=r.entity_type,
                            value=value,
                            score=r.score,
                        )
                    )
                del value  # Scrub local PII reference immediately after use
        except ImportError:
            # Fallback to regex — wrap each match in a try/finally so the raw
            # match value is never present in a live stack frame if an exception
            # propagates.  Sentry and Python logging capture local variables
            # from traceback frames; keeping ``value`` alive would leak PII into
            # error reports, violating GDPR Art. 25 (data protection by design).
            for entity_type in config.entity_types:
                pattern = _FALLBACK_REGEXES.get(entity_type)
                if not pattern:
                    continue
                for match in re.finditer(pattern, text):
                    value = None  # type: ignore[no-redef]
                    try:
                        value = match.group(0)
                        if value not in config.allowlist:
                            entities.append(
                                PIIEntity(
                                    start=match.start(),
                                    end=match.end(),
                                    entity_type=entity_type,
                                    value=value,
                                    score=0.8,
                                )
                            )
                    except Exception as match_exc:
                        # Scrub the raw match value from the local frame before
                        # the exception is logged.  Log position/type only —
                        # never the matched text.
                        value = None  # overwrite before del to ensure GC sees null
                        del value
                        log.warning(
                            "PII regex match processing failed for entity_type=%r "
                            "at span=(%d, %d); skipping match. err=%s",
                            entity_type,
                            match.start(),
                            match.end(),
                            type(match_exc).__name__,  # type name only, not message
                        )
                        continue
                    finally:
                        # Always delete the local reference so it does not
                        # appear in frame locals if an outer exception unwinds
                        # through this scope.
                        value = None
                        del value

        # Sort entities by start index descending to allow safe string replacement
        entities.sort(key=lambda x: x.start, reverse=True)
        return entities
    except Exception:
        # If scan() fails partway through, clear raw PII values from any
        # entities already created so they never leak into tracebacks.
        for entity in entities:
            entity.clear_raw_value()
        raise


def _pseudonym_hmac_key_material(config: NamespacePIIConfig) -> bytes:
    """Return HMAC key bytes for pseudonym generation."""
    if config.pseudonym_hmac_key is not None:
        key = config.pseudonym_hmac_key.encode("utf-8")
        if len(key) < _MIN_PSEUDONYM_SECRET_BYTES:
            raise ValueError(
                f"pseudonym_hmac_key must be at least {_MIN_PSEUDONYM_SECRET_BYTES} bytes "
                f"when set; got {len(key)}."
            )
        return key
    mk = os.environ.get("TRIMCP_MASTER_KEY", "").strip().encode("utf-8")
    if len(mk) < 32:
        raise ValueError(
            "Pseudonymisation requires TRIMCP_MASTER_KEY (≥32 UTF-8 bytes) or "
            f"a namespace pseudonym_hmac_key (≥{_MIN_PSEUDONYM_SECRET_BYTES} bytes)."
        )
    return mk


def _pseudonym_token_suffix(entity_type: str, value: str, hmac_key: bytes) -> str:
    """
    Deterministic opaque suffix: first 16 bytes of HMAC-SHA256, base64url-encoded.

    Yields ~22 characters (128 bits) vs the previous 64 hex chars (256 bits).
    Collision resistance: 2^64 (birthday bound) — adequate for pseudonyms
    within a single namespace (requires ~4 billion tokens before a collision
    becomes likely).

    Message binds entity type and raw value so types do not collide across categories.
    """
    msg = f"{entity_type}\x00{value}".encode()
    raw = hmac.new(hmac_key, msg, hashlib.sha256).digest()
    # Truncate to 16 bytes (128 bits), encode as base64url without padding.
    return base64.urlsafe_b64encode(raw[:16]).rstrip(b"=").decode("ascii")


def process(text: str, config: NamespacePIIConfig) -> PIIProcessResult:
    """
    Processes the text according to the namespace PII policy.
    """
    entities = scan(text, config)

    if not entities:
        return PIIProcessResult(
            sanitized_text=text, redacted=False, entities_found=[], vault_entries=[]
        )

    if config.policy == PIIPolicy.reject:
        found_types = list(set(e.entity_type for e in entities))
        # Clear raw PII before raising so traceback frames never leak values.
        for entity in entities:
            entity.clear_raw_value()
        raise ValueError(
            f"PII Policy Reject: Found sensitive entities of type(s): {', '.join(found_types)}"
        )

    if config.policy == PIIPolicy.flag:
        # Clear raw PII from entities before returning — the caller may
        # hold the result in memory indefinitely (e.g. audit logs).
        for entity in entities:
            entity.clear_raw_value()
        return PIIProcessResult(
            sanitized_text=text,
            redacted=False,
            entities_found=list(set(e.entity_type for e in entities)),
            vault_entries=[],
        )

    # Redact or Pseudonymise
    sanitized_text = text
    vault_entries = []
    mk = require_master_key() if config.reversible else None
    pseudonym_key: bytes | None = None
    if config.policy == PIIPolicy.pseudonymise:
        pseudonym_key = _pseudonym_hmac_key_material(config)

    try:
        for entity in entities:
            if config.policy == PIIPolicy.pseudonymise:
                digest = _pseudonym_token_suffix(
                    entity.entity_type,
                    entity.value,
                    cast(bytes, pseudonym_key),
                )
                token = f"<{entity.entity_type}_{digest}>"

                if config.reversible:
                    # We reuse encrypt_signing_key as it provides AES-256-GCM encryption
                    encrypted_val = encrypt_signing_key(entity.value.encode('utf-8'), mk)
                    vault_entries.append(
                        {
                            "token": token,
                            "encrypted_value": encrypted_val,
                            "entity_type": entity.entity_type,
                        }
                    )
            else:
                # Standard redact
                token = f"<{entity.entity_type}>"

            # Store the token on the entity for traceability
            entity.token = token

            # Replace in text (safe because we iterate in reverse order of start index)
            sanitized_text = sanitized_text[: entity.start] + token + sanitized_text[entity.end :]

            # Clear the raw PII value now that it has been consumed
            entity.clear_raw_value()
    finally:
        if mk is not None:
            mk.zero()

    return PIIProcessResult(
        sanitized_text=sanitized_text,
        redacted=True,
        entities_found=list(set(e.entity_type for e in entities)),
        vault_entries=vault_entries,
    )
