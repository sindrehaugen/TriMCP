import asyncio
import gc
import json
import logging
from typing import Any

import asyncpg
from bson import ObjectId

from trimcp import embeddings as _embeddings
from trimcp.background_task_manager import create_tracked_task

log = logging.getLogger(__name__)


def _record_vram_metrics(worker_id: str = "default") -> None:
    """Record CUDA VRAM usage to Prometheus gauges (Item 49).

    Gracefully no-ops when torch is missing or running on CPU.
    Resets the peak memory allocator stat after reading so each
    measurement window is independent.
    """
    try:
        import torch

        if not torch.cuda.is_available():
            return
    except (ImportError, RuntimeError):
        return

    try:
        from trimcp.observability import (
            REEMBEDDER_VRAM_ALLOCATED,
            REEMBEDDER_VRAM_PEAK,
            REEMBEDDER_VRAM_RESERVED,
        )

        allocated = torch.cuda.memory_allocated()
        reserved = torch.cuda.memory_reserved()
        peak = torch.cuda.max_memory_allocated()

        REEMBEDDER_VRAM_ALLOCATED.labels(worker_id=worker_id).set(allocated)
        REEMBEDDER_VRAM_RESERVED.labels(worker_id=worker_id).set(reserved)
        REEMBEDDER_VRAM_PEAK.labels(worker_id=worker_id).set(peak)

        # Reset peak so the next measurement captures a fresh window
        torch.cuda.reset_peak_memory_stats()

        log.debug(
            "VRAM metrics recorded: allocated=%d reserved=%d peak=%d",
            allocated,
            reserved,
            peak,
        )
    except Exception:
        log.debug(
            "VRAM metric recording skipped (metrics not available)", exc_info=True
        )


def _release_embedding_batch_memory(worker_id: str = "default") -> None:
    """Free Python refs and return unused blocks to the CUDA allocator after a batch.

    Also records VRAM usage metrics for Prometheus (Item 49).
    """
    _record_vram_metrics(worker_id=worker_id)
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except (ImportError, RuntimeError):
        pass


async def run_re_embedding_worker(pg_pool: asyncpg.Pool, mongo_client: Any):
    """
    Background worker that processes active embedding migrations.
    Uses keyset pagination to avoid locking the database.
    """
    while True:
        try:
            async with pg_pool.acquire(timeout=10.0) as conn:
                # Find a running migration
                migration = await conn.fetchrow("""
                    SELECT m.id, m.target_model_id, m.last_memory_id, m.last_node_id, e.name as model_name
                    FROM embedding_migrations m
                    JOIN embedding_models e ON m.target_model_id = e.id
                    WHERE m.status = 'running'
                    ORDER BY m.started_at ASC
                    LIMIT 1
                    """)

                if not migration:
                    await asyncio.sleep(10)
                    continue

                migration_id = migration["id"]
                target_model_id = migration["target_model_id"]
                last_memory_id = migration["last_memory_id"]
                last_node_id = migration["last_node_id"]
                migration["model_name"]

                # Process memories
                # We use keyset pagination on memories.id
                memories_query = """
                    SELECT id, payload_ref 
                    FROM memories 
                    WHERE id > $1
                    ORDER BY id ASC
                    LIMIT 100
                """
                if not last_memory_id:
                    memories_query = """
                        SELECT id, payload_ref 
                        FROM memories 
                        ORDER BY id ASC
                        LIMIT 100
                    """
                    memories_batch = await conn.fetch(memories_query)
                else:
                    memories_batch = await conn.fetch(memories_query, last_memory_id)

                if memories_batch:
                    # Hydrate from Mongo using optimized bulk lookup
                    db = mongo_client.memory_archive
                    texts_to_embed = []
                    valid_memories = []

                    # Map valid ObjectIds to their original memories
                    ref_to_row = {}
                    oids = []
                    for row in memories_batch:
                        ref = row.get("payload_ref")
                        if ref:
                            try:
                                oid = ObjectId(ref)
                                oids.append(oid)
                                ref_to_row[oid] = row
                            except Exception:
                                log.warning(
                                    "Skipping invalid ObjectId payload_ref in re-embedder: %s",
                                    ref,
                                )

                    if oids:
                        docs = {}
                        cursor = db.episodes.find(
                            {"_id": {"$in": oids}}, {"raw_data": 1}
                        )
                        async for doc in cursor:
                            docs[doc["_id"]] = doc

                        # Process in order to align properly
                        for oid in oids:
                            doc = docs.get(oid)
                            if doc and doc.get("raw_data"):
                                texts_to_embed.append(doc["raw_data"])
                                valid_memories.append(ref_to_row[oid]["id"])

                    if texts_to_embed:
                        # Embed batch
                        # Note: In a real implementation, we'd use the specific model_name
                        # For this MVP, we use the default embedder
                        batch = await _embeddings.embed_batch(texts_to_embed)
                        vectors = batch

                        # Insert into memory_embeddings
                        async with conn.transaction():
                            for mem_id, vec in zip(valid_memories, vectors):
                                await conn.execute(
                                    """
                                    INSERT INTO memory_embeddings (memory_id, model_id, embedding)
                                    VALUES ($1, $2, $3::vector)
                                    ON CONFLICT DO NOTHING
                                    """,
                                    mem_id,
                                    target_model_id,
                                    json.dumps(vec),
                                )

                            # Update migration state
                            new_last_id = memories_batch[-1]["id"]
                            await conn.execute(
                                "UPDATE embedding_migrations SET last_memory_id = $1 WHERE id = $2",
                                new_last_id,
                                migration_id,
                            )

                        del batch
                        del vectors
                        del texts_to_embed
                        _release_embedding_batch_memory()
                    continue  # Loop immediately to process next batch

                # If memories are done, process kg_nodes
                nodes_query = """
                    SELECT id, label 
                    FROM kg_nodes 
                    WHERE id > $1
                    ORDER BY id ASC
                    LIMIT 100
                """
                if not last_node_id:
                    nodes_query = """
                        SELECT id, label 
                        FROM kg_nodes 
                        ORDER BY id ASC
                        LIMIT 100
                    """
                    nodes_batch = await conn.fetch(nodes_query)
                else:
                    nodes_batch = await conn.fetch(nodes_query, last_node_id)

                if nodes_batch:
                    texts_to_embed = [row["label"] for row in nodes_batch]
                    valid_nodes = [row["id"] for row in nodes_batch]

                    batch = await _embeddings.embed_batch(texts_to_embed)
                    vectors = batch

                    async with conn.transaction():
                        for node_id, vec in zip(valid_nodes, vectors):
                            await conn.execute(
                                """
                                INSERT INTO kg_node_embeddings (node_id, model_id, embedding)
                                VALUES ($1, $2, $3::vector)
                                ON CONFLICT DO NOTHING
                                """,
                                node_id,
                                target_model_id,
                                json.dumps(vec),
                            )

                        new_last_id = nodes_batch[-1]["id"]
                        await conn.execute(
                            "UPDATE embedding_migrations SET last_node_id = $1 WHERE id = $2",
                            new_last_id,
                            migration_id,
                        )

                    del batch
                    del vectors
                    del texts_to_embed
                    _release_embedding_batch_memory()
                    continue

                # If both are done, mark as validating
                await conn.execute(
                    "UPDATE embedding_migrations SET status = 'validating' WHERE id = $1",
                    migration_id,
                )
                log.info(
                    "Migration %s finished processing. Status set to validating.",
                    migration_id,
                )

        except Exception as e:
            log.error("Re-embedding worker error: %s", e)
            await asyncio.sleep(10)


def start_re_embedder(pg_pool, mongo_client):
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(create_tracked_task(run_re_embedding_worker(pg_pool, mongo_client), name="re_embedding_worker"))
    except RuntimeError:
        # No running loop; this is called at startup in synchronous context
        # Schedule it for execution when the loop is running
        asyncio.create_task(create_tracked_task(run_re_embedding_worker(pg_pool, mongo_client), name="re_embedding_worker"))
