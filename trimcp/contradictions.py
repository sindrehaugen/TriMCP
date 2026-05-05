import json
import logging
from typing import Optional, Any, List
import asyncpg
from datetime import datetime

from pydantic import BaseModel, Field

from trimcp.models import KGNode, KGEdge
from trimcp.providers.factory import get_provider
from trimcp.providers.base import Message, LLMProviderError

log = logging.getLogger(__name__)

class ContradictionSignal(BaseModel):
    source: str
    confidence: float

class ContradictionResult(BaseModel):
    is_contradiction: bool
    confidence: float
    explanation: str

_CONTRADICTION_SYSTEM = (
    "You are a strict logical contradiction detector. "
    "Given an existing memory and a new memory, determine if they contain a direct factual contradiction. "
    "Differences in opinion, preference, or observation are NOT contradictions. "
    "Only flag direct factual conflicts (e.g., 'X works at A' vs 'X works at B'). "
    "Return ONLY valid JSON matching the schema. No preamble. No markdown."
)

def _build_contradiction_messages(existing_text: str, new_text: str) -> List[Message]:
    return [
        Message.system(_CONTRADICTION_SYSTEM),
        Message.user(f"Existing memory: {existing_text}\nNew memory: {new_text}")
    ]

async def detect_contradictions(
    conn: asyncpg.Connection,
    mongo_client: Any,
    namespace_id: str,
    memory_id: str,
    memory_text: str,
    assertion_type: str,
    embedding: list[float],
    agent_id: str,
    triplets: list[KGEdge],
    detection_path: str = "sync",
) -> Optional[dict]:
    """
    Phase 1.3: Contradiction Detection Hook.
    Runs after a memory is inserted.
    Does not fail the insertion.
    """
    if assertion_type != 'fact':
        return None

    # Step 1: Candidate Selection
    # Fetch top-K memories by cosine similarity >= 0.85
    candidates = await conn.fetch(
        """
        SELECT id, payload_ref, 1 - (embedding <=> $1::vector) AS similarity
        FROM memories
        WHERE namespace_id = $2::uuid
          AND memory_type = 'episodic'
          AND assertion_type = 'fact'
          AND id != $3::uuid
          AND 1 - (embedding <=> $1::vector) >= 0.85
        ORDER BY similarity DESC
        LIMIT 3
        """,
        json.dumps(embedding), namespace_id, memory_id
    )

    if not candidates:
        return None

    from bson import ObjectId
    db = mongo_client.memory_archive

    # We will check each candidate
    for candidate in candidates:
        cand_id = str(candidate["id"])
        cand_payload_ref = candidate["payload_ref"]
        
        # Step 2: KG Check
        kg_hit = False
        for t in triplets:
            conflict_edge = await conn.fetchrow(
                """
                SELECT e.payload_ref
                FROM kg_edges e
                JOIN memories m ON e.payload_ref = m.payload_ref
                WHERE e.subject_label = $1
                  AND e.predicate = $2
                  AND e.object_label != $3
                  AND m.id = $4
                LIMIT 1
                """,
                t.subject_label, t.predicate, t.object_label, candidate["id"]
            )
            if conflict_edge:
                kg_hit = True
                break

        signals = []
        if kg_hit:
            signals.append({"source": "kg", "confidence": 0.95})

        # Step 3 & 4: LLM Tiebreaker / NLI Check
        doc = await db.episodes.find_one({"_id": ObjectId(cand_payload_ref)})
        if not doc:
            continue
            
        cand_text = doc.get("raw_data", "")
        if not cand_text:
            continue

        # Fetch LLM Provider config from namespace metadata
        ns_row = await conn.fetchrow("SELECT metadata FROM namespaces WHERE id = $1", namespace_id)
        provider_name = "google/gemini-1.5-pro" # Default
        if ns_row and "consolidation" in ns_row["metadata"]:
            provider_name = ns_row["metadata"]["consolidation"].get("llm_provider", provider_name)

        try:
            provider = get_provider(provider_name)
            messages = _build_contradiction_messages(cand_text, memory_text)
            llm_result = await provider.complete(messages, ContradictionResult)
            
            if llm_result.is_contradiction and llm_result.confidence >= 0.7:
                signals.append({"source": "llm", "confidence": llm_result.confidence})
                
                # Insert contradiction record
                await conn.execute(
                    """
                    INSERT INTO contradictions (
                        namespace_id, memory_a_id, memory_b_id, agent_id,
                        detection_path, signals, confidence, resolution
                    )
                    VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6::jsonb, $7, 'unresolved')
                    """,
                    namespace_id, cand_id, memory_id, agent_id,
                    detection_path, json.dumps(signals), llm_result.confidence
                )
                
                return {
                    "memory_a_id": cand_id,
                    "memory_b_id": memory_id,
                    "confidence": llm_result.confidence,
                    "signals": signals,
                    "explanation": llm_result.explanation
                }
        except Exception as e:
            log.warning(f"Contradiction LLM check failed: {e}")
            # If KG hit but LLM failed, we still log it based on KG
            if kg_hit:
                await conn.execute(
                    """
                    INSERT INTO contradictions (
                        namespace_id, memory_a_id, memory_b_id, agent_id,
                        detection_path, signals, confidence, resolution
                    )
                    VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6::jsonb, $7, 'unresolved')
                    """,
                    namespace_id, cand_id, memory_id, agent_id,
                    detection_path, json.dumps(signals), 0.95
                )
                return {
                    "memory_a_id": cand_id,
                    "memory_b_id": memory_id,
                    "confidence": 0.95,
                    "signals": signals,
                    "explanation": "Detected via Knowledge Graph conflict."
                }

    return None
