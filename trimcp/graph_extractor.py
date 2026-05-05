"""
Phase 0.2 — Graphify Layer: Entity & Relation Extraction
Extracts (subject, predicate, object) triplets from text for Knowledge Graph storage.
Primary backend: spaCy noun-chunk + dependency parsing (zero-shot, no LLM call needed).
Fallback: regex heuristic for environments without spaCy models installed.
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from trimcp.models import KGNode, KGEdge

if TYPE_CHECKING:
    import asyncpg

log = logging.getLogger("tri-stack-graphify")


# --- spaCy backend ---

def _spacy_extract(text: str) -> tuple[list[KGNode], list[KGEdge]]:
    """
    Uses spaCy en_core_web_sm NER + dependency parse.
    Returns (nodes, edges). Raises ImportError if spaCy unavailable.
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
    nodes: list[KGNode] = []
    seen_labels: set[str] = set()
    for ent in doc.ents:
        label = ent.text.strip()
        if label and label not in seen_labels:
            nodes.append(KGNode(
                label=label,
                entity_type=entity_type_map.get(ent.label_, "UNKNOWN"),
                source_text=ent.text,
            ))
            seen_labels.add(label)

    # Also capture noun chunks not caught by NER
    for chunk in doc.noun_chunks:
        label = chunk.root.lemma_.strip()
        if label and label not in seen_labels and len(label) > 2:
            nodes.append(KGNode(label=label, entity_type="CONCEPT", source_text=chunk.text))
            seen_labels.add(label)

    # --- Triplets from dependency parse (SVO extraction) ---
    edges: list[KGEdge] = []
    for token in doc:
        if token.pos_ == "VERB" and token.dep_ in ("ROOT", "relcl", "advcl"):
            subj = next((c for c in token.lefts if c.dep_ in ("nsubj", "nsubjpass")), None)
            obj  = next((c for c in token.rights if c.dep_ in ("dobj", "attr", "prep", "pobj")), None)
            if subj and obj:
                edges.append(KGEdge(
                    subject_label=subj.lemma_,
                    predicate=token.lemma_,
                    object_label=obj.lemma_,
                    confidence=0.85,
                ))

    return nodes, edges


# --- Regex fallback ---

_IS_RELATION = re.compile(
    r"(\b\w[\w\s]{1,30}?\b)\s+(is|are|uses|has|contains|stores|connects to|depends on|runs on)\s+([\w][\w\s]{1,30}?\b)",
    re.IGNORECASE,
)
_KNOWN_TOOLS = {
    "redis", "postgres", "postgresql", "mongodb", "mongo", "docker",
    "python", "fastapi", "mcp", "trimcp", "pgvector", "tree-sitter",
}


def _regex_extract(text: str) -> tuple[list[KGNode], list[KGEdge]]:
    nodes: list[KGNode] = []
    edges: list[KGEdge] = []
    seen: set[str] = set()

    # Detect known tool names
    for word in re.findall(r"\b\w[\w\-]+\b", text):
        lower = word.lower()
        if lower in _KNOWN_TOOLS and lower not in seen:
            nodes.append(KGNode(label=word, entity_type="TOOL", source_text=word))
            seen.add(lower)

    # Extract simple SVO triplets
    for m in _IS_RELATION.finditer(text):
        subj, pred, obj = m.group(1).strip(), m.group(2).strip().lower(), m.group(3).strip()
        edges.append(KGEdge(subject_label=subj, predicate=pred, object_label=obj, confidence=0.6))
        for label in (subj, obj):
            if label.lower() not in seen:
                nodes.append(KGNode(label=label, entity_type="CONCEPT", source_text=label))
                seen.add(label.lower())

    return nodes, edges


# --- Public API ---

def extract(text: str) -> tuple[list[KGNode], list[KGEdge]]:
    """
    Extract entities and triplets from text.
    Tries spaCy first; silently falls back to regex heuristic.
    """
    try:
        nodes, edges = _spacy_extract(text)
        log.debug(f"spaCy extracted {len(nodes)} nodes, {len(edges)} edges.")
        return nodes, edges
    except (ImportError, Exception) as e:
        log.info(f"spaCy unavailable ({e}), using regex fallback.")
        nodes, edges = _regex_extract(text)
        log.debug(f"Regex extracted {len(nodes)} nodes, {len(edges)} edges.")
        return nodes, edges


async def persist_graph(conn: asyncpg.Connection, nodes: list[KGNode], edges: list[KGEdge]) -> None:
    """
    Persist extracted KG nodes and edges to PostgreSQL using raw asyncpg.
    Upserts records to maintain idempotency and updates timestamps/references.
    """
    if nodes:
        await conn.executemany(
            """
            INSERT INTO kg_nodes (label, entity_type, payload_ref, created_at, updated_at)
            VALUES ($1, $2, $3, NOW(), NOW())
            ON CONFLICT (label) DO UPDATE SET 
                updated_at = NOW(),
                payload_ref = COALESCE(EXCLUDED.payload_ref, kg_nodes.payload_ref)
            """,
            [(n.label, n.entity_type, n.payload_ref) for n in nodes]
        )
    
    if edges:
        await conn.executemany(
            """
            INSERT INTO kg_edges (subject_label, predicate, object_label, confidence, payload_ref, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW(), NOW())
            ON CONFLICT (subject_label, predicate, object_label) DO UPDATE SET 
                updated_at = NOW(),
                confidence = GREATEST(kg_edges.confidence, EXCLUDED.confidence),
                payload_ref = COALESCE(EXCLUDED.payload_ref, kg_edges.payload_ref)
            """,
            [(e.subject_label, e.predicate, e.object_label, e.confidence, e.payload_ref) for e in edges]
        )

