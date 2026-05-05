"""
Phase 0.3 — PII Detection and Auto-Redaction Pipeline.
Intercepts payloads before they hit the LLM provider interface and masks sensitive entities.
"""
from __future__ import annotations

import logging
import re
import hashlib
from typing import TYPE_CHECKING

from trimcp.models import NamespacePIIConfig, PIIPolicy, PIIEntity, PIIProcessResult
from trimcp.signing import encrypt_signing_key, require_master_key

if TYPE_CHECKING:
    import asyncpg

log = logging.getLogger("tri-stack-pii")

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
        from presidio_analyzer import AnalyzerEngine
        analyzer = AnalyzerEngine()
        results = analyzer.analyze(text=text, entities=config.entity_types, language='en')
        for r in results:
            value = text[r.start:r.end]
            if value not in config.allowlist:
                entities.append(PIIEntity(
                    start=r.start,
                    end=r.end,
                    entity_type=r.entity_type,
                    value=value,
                    score=r.score
                ))
    except ImportError:
        # Fallback to regex
        for entity_type in config.entity_types:
            pattern = _FALLBACK_REGEXES.get(entity_type)
            if pattern:
                for match in re.finditer(pattern, text):
                    value = match.group(0)
                    if value not in config.allowlist:
                        entities.append(PIIEntity(
                            start=match.start(),
                            end=match.end(),
                            entity_type=entity_type,
                            value=value,
                            score=0.8
                        ))
    
    # Sort entities by start index descending to allow safe string replacement
    entities.sort(key=lambda x: x.start, reverse=True)
    return entities

def process(text: str, config: NamespacePIIConfig) -> PIIProcessResult:
    """
    Processes the text according to the namespace PII policy.
    """
    entities = scan(text, config)
    
    if not entities:
        return PIIProcessResult(
            sanitized_text=text,
            redacted=False,
            entities_found=[],
            vault_entries=[]
        )

    if config.policy == PIIPolicy.reject:
        found_types = list(set(e.entity_type for e in entities))
        raise ValueError(f"PII Policy Reject: Found sensitive entities of type(s): {', '.join(found_types)}")

    if config.policy == PIIPolicy.flag:
        return PIIProcessResult(
            sanitized_text=text,
            redacted=False,
            entities_found=list(set(e.entity_type for e in entities)),
            vault_entries=[]
        )

    # Redact or Pseudonymise
    sanitized_text = text
    vault_entries = []
    master_key = require_master_key() if config.reversible else ""

    for entity in entities:
        if config.policy == PIIPolicy.pseudonymise:
            # Generate a deterministic but opaque token
            hash_suffix = hashlib.sha256(entity.value.encode()).hexdigest()[:4]
            token = f"<{entity.entity_type}_{hash_suffix}>"
            
            if config.reversible:
                # Encrypt the original value
                # We reuse encrypt_signing_key as it provides AES-256-GCM encryption
                encrypted_val = encrypt_signing_key(entity.value.encode('utf-8'), master_key)
                vault_entries.append({
                    "token": token,
                    "encrypted_value": encrypted_val,
                    "entity_type": entity.entity_type
                })
        else:
            # Standard redact
            token = f"<{entity.entity_type}>"

        # Replace in text (safe because we iterate in reverse order of start index)
        sanitized_text = sanitized_text[:entity.start] + token + sanitized_text[entity.end:]

    return PIIProcessResult(
        sanitized_text=sanitized_text,
        redacted=True,
        entities_found=list(set(e.entity_type for e in entities)),
        vault_entries=vault_entries
    )

def infer_assertion_type(text: str) -> str:
    """Rule-based classifier for [D9] Fact-typing."""
    text_lower = text.lower()
    if any(phrase in text_lower for phrase in ["i think", "i believe", "in my opinion", "seems like"]):
        return "opinion"
    if any(phrase in text_lower for phrase in ["i prefer", "i like", "i love", "i hate", "favorite"]):
        return "preference"
    if any(phrase in text_lower for phrase in ["i saw", "i noticed", "observed", "looks like"]):
        return "observation"
    return "fact"
