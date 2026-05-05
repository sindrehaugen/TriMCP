import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

import asyncpg
from pydantic import BaseModel, Field

from trimcp.config import cfg
from trimcp.providers import LLMProvider, Message, get_provider
from trimcp.signing import get_active_key, sign_fields

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain response model — validated by Pydantic V2 on every LLM call
# ---------------------------------------------------------------------------

class ConsolidatedAbstraction(BaseModel):
    """Structured output schema for the sleep-consolidation LLM call.

    Validated by ``LLMProvider.complete()`` before the caller receives it,
    so callers can trust every field without further checking.

    Fields
    ------
    abstraction:
        Single factual paragraph capturing the cluster's shared meaning.
    key_entities:
        Named entities extracted from the cluster.
    key_relations:
        Subject / predicate / object triples for the KG.
    supporting_memory_ids:
        IDs from the *input* cluster only.  Hallucinated IDs cause rejection
        at the ``ConsolidationWorker`` level (TEST-1.2-03).
    contradicting_memory_ids:
        Present when inputs conflict; triggers Phase 1.3 pipeline instead
        of storing a consolidated memory (TEST-1.2-04).
    confidence:
        Float 0.0–1.0.  Runs with confidence < 0.3 are discarded (TEST-1.2-05).
    """

    abstraction: str
    key_entities: List[str]
    key_relations: List[Dict[str, str]]
    supporting_memory_ids: List[str]
    contradicting_memory_ids: Optional[List[str]] = Field(default_factory=list)
    confidence: float


# ---------------------------------------------------------------------------
# Consolidation prompt helper
# ---------------------------------------------------------------------------

_CONSOLIDATION_SYSTEM = (
    "You are a memory consolidation engine. Given N related episodic memories, "
    "produce ONE durable semantic abstraction capturing their shared meaning. "
    "Return ONLY valid JSON matching the schema. No preamble. No markdown."
)


def _build_consolidation_messages(memory_cluster_json: str) -> List[Message]:
    """Build the message list for the consolidation prompt (per spec §1.2)."""
    return [
        Message.system(_CONSOLIDATION_SYSTEM),
        Message.user(f"Memories: {memory_cluster_json}"),
    ]


class ConsolidationWorker:
    def __init__(self, pool: asyncpg.Pool, provider: LLMProvider):
        self.pool = pool
        self.provider = provider

    async def run_consolidation(self, namespace_id: UUID):
        log.info(f"Running consolidation for namespace {namespace_id}")
        
        # 1. Create a consolidation run record and fetch memories (short transaction)
        async with self.pool.acquire() as conn:
            run_id = await conn.fetchval(
                "INSERT INTO consolidation_runs (namespace_id) VALUES ($1) RETURNING id",
                namespace_id
            )
            
            try:
                memories = await conn.fetch(
                    "SELECT id, payload_ref, embedding::text FROM memories WHERE namespace_id = $1 AND memory_type = 'episodic' LIMIT 1000",
                    namespace_id
                )
            except Exception as e:
                log.exception("Failed to fetch memories for consolidation")
                await conn.execute("UPDATE consolidation_runs SET status = 'failed', error_message = $2, completed_at = now() WHERE id = $1", run_id, str(e))
                raise

        if not memories:
            log.info("No memories found to consolidate.")
            async with self.pool.acquire() as conn:
                await conn.execute("UPDATE consolidation_runs SET status = 'completed', completed_at = now() WHERE id = $1", run_id)
            return

        try:
            # Parse embeddings
            import numpy as np
            from sklearn.cluster import HDBSCAN
            
            valid_memories = []
            embeddings = []
            for m in memories:
                if m['embedding']:
                    # parse vector string '[0.1, 0.2, ...]'
                    emb_list = json.loads(m['embedding'])
                    embeddings.append(emb_list)
                    valid_memories.append(m)
                    
            if len(embeddings) < 2:
                log.info("Not enough embeddings to cluster.")
                async with self.pool.acquire() as conn:
                    await conn.execute("UPDATE consolidation_runs SET status = 'completed', completed_at = now() WHERE id = $1", run_id)
                return

            # 3. Cluster using HDBSCAN (offloaded to thread pool to avoid blocking event loop)
            X = np.array(embeddings)
            clusterer = HDBSCAN(min_cluster_size=2)
            labels = await asyncio.to_thread(clusterer.fit_predict, X)
            
            clusters = {}
            for idx, label in enumerate(labels):
                if label == -1:
                    continue # noise
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(valid_memories[idx])
                
            abstractions_created = 0
            
            # 4. For each cluster, call LLM to consolidate (no DB transaction held open here)
            for label, cluster_mems in clusters.items():
                mem_ids  = [str(m['id']) for m in cluster_mems]
                payloads = [m['payload_ref'] for m in cluster_mems]

                messages = _build_consolidation_messages(json.dumps(payloads))
                
                try:
                    # complete() returns a validated ConsolidatedAbstraction or
                    # raises LLMProviderError / LLMValidationError.
                    abstraction: ConsolidatedAbstraction = await self.provider.complete(
                        messages,
                        ConsolidatedAbstraction,
                    )
                except Exception as e:
                    log.error("LLM provider error for cluster %s: %s", label, e)
                    continue

                # TEST-1.2-05: discard low-confidence runs.
                if abstraction.confidence < 0.3:
                    log.info(
                        "Cluster %s discarded: confidence %.2f < 0.3",
                        label, abstraction.confidence,
                    )
                    continue

                # TEST-1.2-03: reject hallucinated supporting_memory_ids.
                input_ids = set(mem_ids)
                bad_ids   = [
                    mid for mid in abstraction.supporting_memory_ids
                    if mid not in input_ids
                ]
                if bad_ids:
                    log.warning(
                        "Cluster %s rejected: hallucinated supporting_memory_ids %s",
                        label, bad_ids,
                    )
                    continue

                # TEST-1.2-04: contradictions → Phase 1.3, do NOT store here.
                if abstraction.contradicting_memory_ids:
                    log.info(
                        "Cluster %s routed to contradiction pipeline: %s",
                        label, abstraction.contradicting_memory_ids,
                    )
                    continue
                
                # 5. Store result back into memories (short transaction per cluster)
                try:
                    async with self.pool.acquire() as conn:
                        async with conn.transaction():
                            # Get active signing key
                            key_id, raw_key = await get_active_key(conn)
                            
                            new_mem_id = await conn.fetchval(
                                """
                                INSERT INTO memories (namespace_id, memory_type, assertion_type, payload_ref, derived_from)
                                VALUES ($1, 'semantic', 'abstraction', $2, $3)
                                RETURNING id
                                """,
                                namespace_id, abstraction.abstraction, json.dumps(mem_ids)
                            )
                            
                            # Store event log
                            event_params = abstraction.model_dump()
                            event_params["source_memories"] = mem_ids
                            
                            # Get next seq
                            seq = await conn.fetchval("SELECT COALESCE(MAX(event_seq), 0) + 1 FROM event_log WHERE namespace_id = $1", namespace_id)
                            
                            # Sign event
                            fields_to_sign = {
                                "namespace_id": str(namespace_id),
                                "agent_id": "system",
                                "event_type": "consolidation",
                                "event_seq": seq,
                                "params": event_params
                            }
                            signature = sign_fields(fields_to_sign, raw_key)
                            
                            await conn.execute(
                                """
                                INSERT INTO event_log (namespace_id, agent_id, event_type, event_seq, params, signature, signature_key_id)
                                VALUES ($1, 'system', 'consolidation', $2, $3, $4, $5)
                                """,
                                namespace_id, seq, json.dumps(event_params), signature, key_id
                            )
                            
                            # Store in KG
                            for entity in abstraction.key_entities:
                                await conn.execute(
                                    "INSERT INTO kg_nodes (label, entity_type) VALUES ($1, 'Entity') ON CONFLICT (label) DO NOTHING",
                                    entity
                                )
                                
                            for rel in abstraction.key_relations:
                                subj = rel.get("subject")
                                pred = rel.get("predicate")
                                obj = rel.get("object")
                                if subj and pred and obj:
                                    await conn.execute(
                                        "INSERT INTO kg_edges (subject_label, predicate, object_label, confidence) VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING",
                                        subj, pred, obj, abstraction.confidence
                                    )
                                    
                            abstractions_created += 1
                            
                            # 6. Handle decay logic
                            if cfg.CONSOLIDATION_DECAY_SOURCES:
                                # Decrease salience of source memories
                                for mem_id in mem_ids:
                                    await conn.execute(
                                        """
                                        INSERT INTO memory_salience (memory_id, agent_id, namespace_id, salience_score)
                                        VALUES ($1, 'system', $2, 0.5)
                                        ON CONFLICT (memory_id, agent_id) DO UPDATE SET salience_score = memory_salience.salience_score * 0.5
                                        """,
                                        UUID(mem_id), namespace_id
                                    )
                except Exception as e:
                    log.error("Database error storing cluster %s: %s", label, e)
                    continue

            # Update run status
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE consolidation_runs 
                    SET status = 'completed', completed_at = now(), events_processed = $2, clusters_formed = $3, abstractions_created = $4
                    WHERE id = $1
                    """,
                    run_id, len(valid_memories), len(clusters), abstractions_created
                )
            
        except Exception as e:
            log.exception("Consolidation failed")
            async with self.pool.acquire() as conn:
                await conn.execute("UPDATE consolidation_runs SET status = 'failed', error_message = $2, completed_at = now() WHERE id = $1", run_id, str(e))
            raise

