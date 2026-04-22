"""
Phase 2 — Graphify Layer: Entity & Relation Extraction
Extracts (subject, predicate, object) triplets from text for Knowledge Graph storage.
Primary backend: spaCy noun-chunk + dependency parsing (zero-shot, no LLM call needed).
Fallback: regex heuristic for environments without spaCy models installed.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

log = logging.getLogger("tri-stack-graphify")


@dataclass
class Entity:
    label: str          # e.g. "TriMCP", "Redis"
    entity_type: str    # e.g. "CONCEPT", "TOOL", "PERSON", "ORG", "UNKNOWN"
    source_text: str    # original span text


@dataclass
class Triplet:
    subject: str
    predicate: str
    obj: str            # 'object' is a Python builtin — avoid shadowing
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)


# --- spaCy backend ---

def _spacy_extract(text: str) -> tuple[list[Entity], list[Triplet]]:
    """
    Uses spaCy en_core_web_sm NER + dependency parse.
    Returns (entities, triplets). Raises ImportError if spaCy unavailable.
    """
    import spacy  # noqa: PLC0415

    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        raise ImportError("spaCy model 'en_core_web_sm' not installed. Run: python -m spacy download en_core_web_sm")

    doc = nlp(text[:4096])  # cap to prevent runaway on huge payloads

    # --- Entities from NER ---
    entity_type_map = {
        "ORG": "ORG", "PRODUCT": "TOOL", "PERSON": "PERSON",
        "GPE": "PLACE", "LOC": "PLACE", "WORK_OF_ART": "CONCEPT",
        "LANGUAGE": "CONCEPT", "LAW": "CONCEPT",
    }
    entities: list[Entity] = []
    seen_labels: set[str] = set()
    for ent in doc.ents:
        label = ent.text.strip()
        if label and label not in seen_labels:
            entities.append(Entity(
                label=label,
                entity_type=entity_type_map.get(ent.label_, "UNKNOWN"),
                source_text=ent.text,
            ))
            seen_labels.add(label)

    # Also capture noun chunks not caught by NER
    for chunk in doc.noun_chunks:
        label = chunk.root.lemma_.strip()
        if label and label not in seen_labels and len(label) > 2:
            entities.append(Entity(label=label, entity_type="CONCEPT", source_text=chunk.text))
            seen_labels.add(label)

    # --- Triplets from dependency parse (SVO extraction) ---
    triplets: list[Triplet] = []
    for token in doc:
        if token.pos_ == "VERB" and token.dep_ in ("ROOT", "relcl", "advcl"):
            subj = next((c for c in token.lefts if c.dep_ in ("nsubj", "nsubjpass")), None)
            obj  = next((c for c in token.rights if c.dep_ in ("dobj", "attr", "prep", "pobj")), None)
            if subj and obj:
                triplets.append(Triplet(
                    subject=subj.lemma_,
                    predicate=token.lemma_,
                    obj=obj.lemma_,
                    confidence=0.85,
                ))

    return entities, triplets


# --- Regex fallback ---

_IS_RELATION = re.compile(
    r"(\b\w[\w\s]{1,30}?\b)\s+(is|are|uses|has|contains|stores|connects to|depends on|runs on)\s+([\w][\w\s]{1,30}?\b)",
    re.IGNORECASE,
)
_KNOWN_TOOLS = {
    "redis", "postgres", "postgresql", "mongodb", "mongo", "docker",
    "python", "fastapi", "mcp", "trimcp", "pgvector", "tree-sitter",
}


def _regex_extract(text: str) -> tuple[list[Entity], list[Triplet]]:
    entities: list[Entity] = []
    triplets: list[Triplet] = []
    seen: set[str] = set()

    # Detect known tool names
    for word in re.findall(r"\b\w[\w\-]+\b", text):
        lower = word.lower()
        if lower in _KNOWN_TOOLS and lower not in seen:
            entities.append(Entity(label=word, entity_type="TOOL", source_text=word))
            seen.add(lower)

    # Extract simple SVO triplets
    for m in _IS_RELATION.finditer(text):
        subj, pred, obj = m.group(1).strip(), m.group(2).strip().lower(), m.group(3).strip()
        triplets.append(Triplet(subject=subj, predicate=pred, obj=obj, confidence=0.6))
        for label in (subj, obj):
            if label.lower() not in seen:
                entities.append(Entity(label=label, entity_type="CONCEPT", source_text=label))
                seen.add(label.lower())

    return entities, triplets


# --- Public API ---

def extract(text: str) -> tuple[list[Entity], list[Triplet]]:
    """
    Extract entities and triplets from text.
    Tries spaCy first; silently falls back to regex heuristic.
    """
    try:
        entities, triplets = _spacy_extract(text)
        log.debug(f"spaCy extracted {len(entities)} entities, {len(triplets)} triplets.")
        return entities, triplets
    except (ImportError, Exception) as e:
        log.info(f"spaCy unavailable ({e}), using regex fallback.")
        entities, triplets = _regex_extract(text)
        log.debug(f"Regex extracted {len(entities)} entities, {len(triplets)} triplets.")
        return entities, triplets
