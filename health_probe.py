"""
TriMCP Internal Health Probe
Verifies connectivity to all required backends (Redis, PG, Mongo)
and checks embedding model readiness.
"""

import asyncio
import logging
import sys

import asyncpg
from motor.motor_asyncio import AsyncIOMotorClient
from redis import from_url as redis_from_url

from trimcp.config import cfg

logging.basicConfig(level=logging.ERROR)


async def probe():
    # 0. P0 Security Check: Master Key
    if not cfg.TRIMCP_MASTER_KEY or len(cfg.TRIMCP_MASTER_KEY) < 32:
        print("CRITICAL: TRIMCP_MASTER_KEY is missing or too short")
        return False

    # 1. Config Validation
    try:
        cfg.validate()
    except Exception as e:
        print(f"Config Error: {e}")
        return False

    # 2. Redis Probe
    try:
        r = redis_from_url(cfg.REDIS_URL, socket_connect_timeout=2)
        r.ping()
    except Exception as e:
        print(f"Redis Connection Failed: {e}")
        return False

    # 3. Postgres Probe
    try:
        conn = await asyncpg.connect(cfg.PG_DSN, timeout=2)
        await conn.execute("SELECT 1")
        await conn.close()
    except Exception as e:
        print(f"Postgres Connection Failed: {e}")
        return False

    # 4. MongoDB Probe
    try:
        client = AsyncIOMotorClient(cfg.MONGO_URI, serverSelectionTimeoutMS=2000)
        await client.admin.command('ping')
    except Exception as e:
        print(f"MongoDB Connection Failed: {e}")
        return False

    # 5. Embedding Engine Check (Soft Check)
    # We check if the model is reachable or loaded if we are the worker/server
    # For now, reaching the cognitive sidecar is a good proxy.
    import httpx

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{cfg.TRIMCP_COGNITIVE_BASE_URL}/health")
            if resp.status_code != 200:
                print(f"Cognitive Engine Unhealthy: {resp.status_code}")
                return False
    except Exception as e:
        # Don't fail the whole probe if LLM is optional/down during boot,
        # but log it for the container health status.
        print(f"Cognitive Engine Probe Warning: {e}")

    return True


if __name__ == "__main__":
    success = asyncio.run(probe())
    sys.exit(0 if success else 1)
