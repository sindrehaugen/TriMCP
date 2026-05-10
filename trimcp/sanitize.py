"""Shared LLM payload sanitization utilities.

Hardened against prompt injection, XML boundary escaping, and zero-width
character obfuscation.  Used by any module that embeds user-controlled text
into LLM prompts.
"""

from __future__ import annotations

import re


def sanitize_llm_payload(text: str) -> str:
    """Strip zero-width unicode spaces and neutralize XML/HTML tag markers.

    Defences applied (in order):

    1. **Zero-width purge** — removes ``\u200b``, ``\u200c``, ``\u200d``,
       ``\u200e``, ``\u200f``, ``\ufeff`` (commonly used to obfuscate tags).
    2. **Tag stripping** — drops ``<tag>``, ``</tag>``, ``<tag attr="val">``
       via regex (case-insensitive).
    3. **Bracket neutralisation** — converts any remaining ``<`` / ``>`` to
       ``[`` / ``]`` so lone angle brackets cannot form new tags.

    Returns ``""`` for *None* or empty input.
    """
    if not text:
        return ""

    # 1. Purge zero-width unicode spaces and bidirectional text markings
    for bad_char in ("\u200b", "\u200c", "\u200d", "\u200e", "\u200f", "\ufeff"):
        text = text.replace(bad_char, "")

    # 2. Drop XML/HTML-like structures
    sanitized = re.sub(r"<\/?[a-zA-Z][^>]*>", "", text)

    # 3. Neutralize any remaining angle brackets
    sanitized = sanitized.replace("<", "[").replace(">", "]")
    return sanitized
