import asyncio
import logging
import json
from typing import Any
import asyncpg
from bson import ObjectId

from trimcp.config import cfg
from trimcp import embeddings as _embeddings

log = logging.getLogger(__name__)

async def run_re_embedding_worker(pg_pool: asyncpg.Pool, mongo_client: Any):
    """
    Background worker that processes active embedding migrations.
    Uses keyset pagination to avoid locking the database.
    """
    while True:
        try:
            async with pg_pool.acquire() as conn:
                # Find a running migration
                migration = await conn.fetchrow(
                    """
                    SELECT m.id, m.target_model_id, m.last_memory_id, m.last_node_id, e.name as model_name
                    FROM embedding_migrations m
                    JOIN embedding_models e ON m.target_model_id = e.id
                    WHERE m.status = 'running'
                    ORDER BY m.started_at ASC
                    LIMIT 1
                    """
                )
                
                if not migration:
                    await asyncio.sleep(10)
                    continue

                migration_id = migration["id"]
                target_model_id = migration["target_model_id"]
                last_memory_id = migration["last_memory_id"]
                last_node_id = migration["last_node_id"]
                model_name = migration["model_name"]

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
                    # Hydrate from Mongo
                    db = mongo_client.memory_archive
                    texts_to_embed = []
                    valid_memories = []
                    for row in memories_batch:
                        doc = await db.episodes.find_one({"_id": ObjectId(row["payload_ref"])})
                        if doc and doc.get("raw_data"):
                            # We re-embed the raw_data or summary. 
                            # Since we don't store summary separately in Mongo, we embed raw_data.
                            # In a real scenario, we'd ensure we embed the exact same text.
                            texts_to_embed.append(doc["raw_data"])
                            valid_memories.append(row["id"])
                    
                    if texts_to_embed:
                        # Embed batch
                        # Note: In a real implementation, we'd use the specific model_name
                        # For this MVP, we use the default embedder
                        vectors = await _embeddings.embed_batch(texts_to_embed)
                        
                        # Insert into memory_embeddings
                        async with conn.transaction():
                            for mem_id, vec in zip(valid_memories, vectors):
                                await conn.execute(
                                    """
                                    INSERT INTO memory_embeddings (memory_id, model_id, embedding)
                                    VALUES ($1, $2, $3::vector)
                                    ON CONFLICT DO NOTHING
                                    """,
                                    mem_id, target_model_id, json.dumps(vec)
                                )
                            
                            # Update migration state
                            new_last_id = memories_batch[-1]["id"]
                            await conn.execute(
                                "UPDATE embedding_migrations SET last_memory_id = $1 WHERE id = $2",
                                new_last_id, migration_id
                            )
                    continue # Loop immediately to process next batch

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
                    
                    vectors = await _embeddings.embed_batch(texts_to_embed)
                    
                    async with conn.transaction():
                        for node_id, vec in zip(valid_nodes, vectors):
                            await conn.execute(
                                """
                                INSERT INTO kg_node_embeddings (node_id, model_id, embedding)
                                VALUES ($1, $2, $3::vector)
                                ON CONFLICT DO NOTHING
                                """,
                                node_id, target_model_id, json.dumps(vec)
                            )
                        
                        new_last_id = nodes_batch[-1]["id"]
                        await conn.execute(
                            "UPDATE embedding_migrations SET last_node_id = $1 WHERE id = $2",
                            new_last_id, migration_id
                        )
                    continue

                # If both are done, mark as validating
                await conn.execute(
                    "UPDATE embedding_migrations SET status = 'validating' WHERE id = $1",
                    migration_id
                )
                log.info(f"Migration {migration_id} finished processing. Status set to validating.")

        except Exception as e:
            log.error(f"Re-embedding worker error: {e}")
            await asyncio.sleep(10)

def start_re_embedder(pg_pool, mongo_client):
    asyncio.create_task(run_re_embedding_worker(pg_pool, mongo_client))