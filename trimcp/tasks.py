"""
Phase 6: Async Background Tasks
Handles heavy processing (AST parsing + Jina vectorization) outside the MCP loop.
Uses RQ (Redis Queue) for reliable task distribution.
"""
import logging
import asyncio
import hashlib
import json
from datetime import datetime
from typing import Optional

from trimcp.orchestrator import TriStackEngine, MemoryPayload
from trimcp import embeddings as _embeddings
from trimcp.ast_parser import parse_file

log = logging.getLogger("tri-stack-tasks")

def run_async(coro):
    """Helper to run async code in sync RQ worker context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

def process_code_indexing(filepath: str, raw_code: str, language: str, user_id: Optional[str] = None):
    """
    Worker task: Performs the actual heavy lifting of indexing.
    user_id=None: shared corpus (enterprise default). Otherwise private to that user.
    """
    log.info("[Worker] Starting indexing for %s", filepath)
    
    engine = TriStackEngine()
    
    async def _index():
        await engine.connect()
        inserted_mongo_id = None
        db = engine.mongo_client.memory_archive
        collection = db.code_files
        try:
            file_hash = hashlib.md5(raw_code.encode()).hexdigest()
            
            # STEP 1: Episodic Commit (MongoDB)
            doc: dict = {
                "filepath": filepath,
                "language": language,
                "file_hash": file_hash,
                "raw_code": raw_code,
                "ingested_at": datetime.utcnow(),
            }
            if user_id:
                doc["user_id"] = user_id
            inserted_result = await collection.insert_one(doc)
            inserted_mongo_id = str(inserted_result.inserted_id)

            # STEP 2: Batch-embed all AST chunks
            chunks = list(parse_file(raw_code, language))
            texts = [f"{c.name}\n{c.code_string}" for c in chunks]
            vectors = await _embeddings.embed_batch(texts)

            async with engine.pg_pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "DELETE FROM code_metadata WHERE filepath = $1 AND (user_id IS NOT DISTINCT FROM $2)",
                        filepath,
                        user_id,
                    )
                    for chunk, vector in zip(chunks, vectors):
                        await conn.execute(
                            """
                            INSERT INTO code_metadata
                                (filepath, language, node_type, name, start_line, end_line,
                                 file_hash, embedding, content_fts, mongo_ref_id, user_id)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::vector, 
                                    to_tsvector('english', $9 || ' ' || $10), $11, $12)
                            """,
                            filepath, language, chunk.node_type, chunk.name,
                            chunk.start_line, chunk.end_line,
                            file_hash, json.dumps(vector), chunk.name, chunk.code_string, inserted_mongo_id,
                            user_id,
                        )

            # STEP 3: Cache hash in Redis
            scope_key = f"private:{user_id}" if user_id else "shared"
            await engine.redis_client.setex(
                f"hash:{scope_key}:{filepath}", 3600, file_hash
            )
            log.info("[Worker] Finished indexing %s (%d chunks)", filepath, len(chunks))
            return {"status": "success", "chunks": len(chunks)}
            
        except Exception as e:
            log.exception("[Worker] Indexing failed for %s", filepath)
            if inserted_mongo_id:
                log.warning("[ROLLBACK] Removing orphaned Mongo doc %s", inserted_mongo_id)
                try:
                    await collection.delete_one({"_id": inserted_result.inserted_id})
                except Exception as mongo_exc:
                    log.error("[ROLLBACK] Mongo cleanup failed: %s", mongo_exc)
            raise
        finally:
            await engine.disconnect()

    return run_async(_index())
