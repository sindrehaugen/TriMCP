# TriMCP Recursive Indexing Flow

This document focuses on **async code indexing** via MCP + RQ. For the full **v1.0** runtime (temporal queries, A2A, scheduled re-embedding, GC), see [architecture-v1.md](./architecture-v1.md).

TriMCP can ingest its own codebase or any other directory in two ways:
1. **Ad-hoc via MCP**: An LLM client calls the `index_code_file` tool. This operation is asynchronous, utilizing an RQ-enqueued worker path.
2. **Bulk Recursive Indexing**: The `index_all.py` script bypasses the MCP protocol entirely to interface directly with the internal `TriStackEngine` for maximum throughput.

The diagram below illustrates the ad-hoc flow via MCP. It demonstrates the asynchronous processing model where the MCP server immediately returns a `job_id`, while a background worker processes the file and employs the Saga pattern to ensure database consistency across the Tri-Stack.

```mermaid
sequenceDiagram
    participant LLM as LLM Client (Claude/Cursor)
    participant MCP as TriMCP Server (server.py)
    participant RedisQ as Redis (RQ Queue)
    participant Worker as Background Worker (start_worker.py)
    participant AST as ast_parser.py
    participant Mongo as MongoDB (Episodic)
    participant PG as PostgreSQL (Semantic)
    participant Redis as Redis (Working Cache)

    Note over LLM, Redis: Recursive AST Indexing Flow (Async)
    LLM->>MCP: Call tool: index_code_file(source)
    MCP->>RedisQ: Enqueue indexing job
    RedisQ-->>MCP: Return job_id
    MCP-->>LLM: Return status: enqueued & job_id
    
    Note over Worker, Redis: Async Processing
    Worker->>RedisQ: Fetch job
    Worker->>AST: Parse source code into AST chunks
    AST-->>Worker: Return code chunks & structure
    
    rect rgb(200, 220, 240)
        Note right of Worker: Saga Transaction Begins
        Worker->>Mongo: Store full file payload (Episodic)
        Mongo-->>Worker: Return mongo_ref_id
        
        Worker->>PG: Store vector embeddings & KG triplets (Semantic)
        alt PG Insertion Fails
            PG-->>Worker: Error
            Worker->>Mongo: ROLLBACK (Delete payload)
            Worker-->>RedisQ: Mark job failed
        else PG Insertion Succeeds
            PG-->>Worker: Success
            Worker->>Redis: Update recent context (Working)
            Worker-->>RedisQ: Mark job complete
        end
    end
    
    Note over LLM, MCP: Status Polling
    LLM->>MCP: Call tool: check_indexing_status(job_id)
    MCP->>RedisQ: Query job status
    RedisQ-->>MCP: Return status (finished/failed)
    MCP-->>LLM: Return indexing results
```
