"""  
Phase 3.5: Tri-Stack Information Stacking Logic (The Orchestrator)  
Implements the Python Saga Pattern for distributed transactions across Redis, Postgres, and Mongo.  
"""  
import asyncio  
import json  
import os  
from datetime import datetime  
from pydantic import BaseModel, Field  
from motor.motor\_asyncio import AsyncIOMotorClient  
import asyncpg  
import redis.asyncio as redis  
from dotenv import load\_dotenv

\# Load environment variables from .env file  
load\_dotenv()

\# \--- 1\. Pydantic Data Models (Phase 2.1) \---

class MemoryPayload(BaseModel):  
    user\_id: str  
    session\_id: str  
    content\_type: str \= Field(description="'chat' or 'code'")  
    summary: str  
    heavy\_payload: str | dict \# The massive raw data  
     
class OrchestratorConfig:  
    MONGO\_URI \= os.getenv("MONGO\_URI", "mongodb://localhost:27017")  
    PG\_DSN \= os.getenv("PG\_DSN", "postgresql://mcp\_user:mcp\_password@localhost:5432/memory\_meta")  
    REDIS\_URL \= os.getenv("REDIS\_URL", "redis://localhost:6379/0")

\# \--- 2\. The Engine \---

class TriStackEngine:  
    def \_\_init\_\_(self):  
        self.mongo\_client \= None  
        self.pg\_pool \= None  
        self.redis\_client \= None

    async def connect(self):  
        """Initialize connections to all three databases."""  
        self.mongo\_client \= AsyncIOMotorClient(OrchestratorConfig.MONGO\_URI)  
        self.pg\_pool \= await asyncpg.create\_pool(OrchestratorConfig.PG\_DSN)  
        self.redis\_client \= redis.from\_url(OrchestratorConfig.REDIS\_URL)  
         
        \# Ensure PG Table exists (Phase 2.2 Setup snippet)  
        async with self.pg\_pool.acquire() as conn:  
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")  
            await conn.execute("""  
                CREATE TABLE IF NOT EXISTS memory\_metadata (  
                    id uuid PRIMARY KEY DEFAULT gen\_random\_uuid(),  
                    user\_id VARCHAR(255),  
                    session\_id VARCHAR(255),  
                    embedding vector(768),  
                    mongo\_ref\_id VARCHAR(255),  
                    created\_at TIMESTAMP DEFAULT CURRENT\_TIMESTAMP  
                );  
            """)

    async def disconnect(self):  
        self.mongo\_client.close()  
        await self.pg\_pool.close()  
        await self.redis\_client.aclose()

    async def \_generate\_embedding(self, text: str) \-\> list\[float\]:  
        """Stub for Phase 3.3. Replace with Jina/HuggingFace model."""  
        \# Mocking a 768-dimensional vector  
        return \[0.1\] \* 768

    async def store\_memory(self, payload: MemoryPayload) \-\> str:  
        """  
        The Core Stacking Logic (Saga Pattern).  
        Enforces: Mongo \-\> PG \-\> Redis. If PG fails, Mongo is rolled back.  
        """  
        db \= self.mongo\_client.memory\_archive  
        collection \= db.episodes  
        inserted\_mongo\_id \= None

        try:  
            \# STEP 1: Episodic Commit (MongoDB)  
            \# Write the heavy payload first to get the source-of-truth ID.  
            mongo\_doc \= {  
                "user\_id": payload.user\_id,  
                "session\_id": payload.session\_id,  
                "type": payload.content\_type,  
                "raw\_data": payload.heavy\_payload,  
                "ingested\_at": datetime.utcnow()  
            }  
            result \= await collection.insert\_one(mongo\_doc)  
            inserted\_mongo\_id \= str(result.inserted\_id)  
            print(f"\[Mongo\] Inserted heavy payload. ID: {inserted\_mongo\_id}")

            \# STEP 2: Semantic Commit (PostgreSQL)  
            \# Generate vector and store lightweight index pointing to Mongo.  
            vector \= await self.\_generate\_embedding(payload.summary)  
             
            async with self.pg\_pool.acquire() as conn:  
                await conn.execute(  
                    """  
                    INSERT INTO memory\_metadata (user\_id, session\_id, embedding, mongo\_ref\_id)  
                    VALUES ($1, $2, $3, $4)  
                    """,  
                    payload.user\_id,  
                    payload.session\_id,  
                    json.dumps(vector), \# pgvector accepts JSON array string  
                    inserted\_mongo\_id  
                )  
            print(f"\[PG\] Inserted vector index mapped to Mongo ID: {inserted\_mongo\_id}")

            \# STEP 3: Working Memory Commit (Redis)  
            \# Make the summary immediately available for sub-millisecond recall.  
            \# TTL set to 3600 seconds (1 hour).  
            redis\_key \= f"cache:{payload.user\_id}:{payload.session\_id}"  
            await self.redis\_client.setex(redis\_key, 3600, payload.summary)  
            print(f"\[Redis\] Cached summary for immediate recall.")

            return inserted\_mongo\_id

        except Exception as e:  
            \# THE ROLLBACK MECHANISM  
            print(f"\[ERROR\] Transaction failed during PG/Redis commit: {str(e)}")  
            if inserted\_mongo\_id:  
                print(f"\[ROLLBACK\] Removing orphaned document {inserted\_mongo\_id} from MongoDB...")  
                await collection.delete\_one({"\_id": result.inserted\_id})  
                print("\[ROLLBACK\] Clean up complete. Tri-Stack remains pure.")  
            raise e

\# \--- 3\. Execution Test \---

async def test\_orchestrator():  
    engine \= TriStackEngine()  
    await engine.connect()  
     
    mock\_payload \= MemoryPayload(  
        user\_id="dev\_user\_1",  
        session\_id="session\_alpha",  
        content\_type="chat",  
        summary="User is setting up a Tri-Stack DB architecture with Docker.",  
        heavy\_payload="... imagine 50 pages of raw chat transcript and docker configs here ..."  
    )  
     
    print("--- Starting Tri-Stack Ingestion \---")  
    try:  
        mongo\_id \= await engine.store\_memory(mock\_payload)  
        print(f"--- Success\! Memory committed perfectly. Reference: {mongo\_id} \---")  
    except Exception as e:  
        print(f"--- Failed: {str(e)} \---")  
    finally:  
        await engine.disconnect()

if \_\_name\_\_ \== "\_\_main\_\_":  
    asyncio.run(test\_orchestrator())  
