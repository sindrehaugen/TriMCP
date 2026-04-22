# **Tri-MCP Memory Server: AI Agent Integration Plan**

## **1\. Architectural Rationale: The Superior Solution**

Most memory servers (like standard Mem0 or Supermemory) rely on a single or dual-database design (e.g., SQLite \+ Cloudflare, or just PostgreSQL). While easier to deploy, they suffer from architectural compromises at scale. The **Redis-PostgreSQL-MongoDB** triad eliminates these compromises by assigning specialized databases to their optimal data structures, mimicking human memory systems.

Adding an **AST-Aware Code Indexing Layer** supercharges this stack for developer agents, allowing the LLM to search across massive codebases semantically without losing structural integrity.

### **1.1 The Core Philosophy: Separation of Concerns**

This stack is built on a strict, pure separation of data responsibility:

* **Redis \= "Current Data" (Working Memory):**  
  * *Role:* Sub-millisecond retrieval of the current conversational context and recently accessed code snippets.  
  * *Advantage:* Prevents expensive vector searches for immediate follow-up questions. Handles Time-To-Live (TTL) automatically for ephemeral session data.  
* **PostgreSQL \+ pgvector \= "What Data is Stored" (The Index):**  
  * *Role:* Relational metadata (User \-\> Sessions \-\> Documents) and high-dimensional vector embeddings for cosine-similarity semantic search.  
  * *Advantage:* ACID compliance guarantees data integrity. pgvector allows highly efficient querying of *meaning*, acting as the precise map. For code, it stores function-level embeddings mapped exactly to file paths and line numbers.  
* **MongoDB \= "The Complete Data" (The Archive):**  
  * *Role:* Schema-less storage for massive, unstructured data (raw conversation transcripts, full repository files).  
  * *Advantage:* Prevents PostgreSQL from bloating. PostgreSQL rows stay incredibly lightweight (just ID, vector, and Mongo reference ID), while Mongo handles the heavy I/O of gigabytes of raw source code and context.

### **1.2 System Data Flow**

1. **Standard Write (Conversations/Docs):** LLM calls store\_memory ![][image1] MCP Server ![][image1]  
   * Caches raw text in **Redis** (Current Data).  
   * Dumps full heavy payload to **MongoDB**, returning a mongo\_id (Complete Data).  
   * Embeds text, saves vector \+ mongo\_id \+ metadata to **PostgreSQL** (What Data is Stored).  
2. **Code Indexing Write:** LLM calls index\_code\_file ![][image1] MCP Server ![][image1]  
   * Uses **Tree-sitter** to extract AST nodes (e.g., all functions and classes).  
   * Saves the *entire raw file* to **MongoDB** (Complete Data).  
   * Generates embeddings for *each individual function/class node* and saves them to **PostgreSQL** with metadata (filepath, node\_type, start\_line, end\_line, mongo\_id) (What Data is Stored).  
3. **Read (Retrieval):** LLM calls recall\_memory or search\_code ![][image1] MCP Server ![][image1]  
   * Checks **Redis** for recent context.  
   * On cache miss, performs pgvector semantic search in **PostgreSQL**.  
   * Takes the resulting pointers and fetches the required payload (either a full doc or a specific code block) from **MongoDB**.

### **1.3 Pure Python Orchestration (The Stacking Logic)**

To maintain the purity of the Tri-Stack without relying on external message brokers (like Kafka), the Python MCP Engine acts as the strict transaction manager using a Saga pattern.

The strict sequential logic is:

1. **Validation & Parsing:** Accept payload, validate via [Pydantic](https://docs.pydantic.dev/), and run Tree-sitter (if code).  
2. **Episodic Commit (Mongo):** Write the massive raw payload to MongoDB. *Retrieve the inserted \_id.* (This must happen first because PG needs the pointer).  
3. **Semantic Commit (PG):** Generate vectors. Write vectors \+ metadata \+ mongo\_id to PostgreSQL.  
   * *Rollback Trigger:* If the PG write fails, an automated try/except rollback MUST execute mongo.delete\_one({"\_id": inserted\_id}) to prevent orphaned data.  
4. **Working Memory Commit (Redis):** If steps 2 & 3 succeed, write to Redis to signal immediate availability.

## **2\. AI Agent Execution Sequence (The Integration Plan)**

*Instructions for AI Agent:* Execute the following phases sequentially. Do not proceed to the next phase until the validation criteria of the current phase are met.

### **Phase 1: Infrastructure & Orchestration**

**Goal:** Establish the local development environment using Docker to ensure exact version parity for the three databases.

* **Task 1.1:** Create a docker-compose.yml file.  
  * Include redis:alpine (Port 6379).  
  * Include postgres:15 with the pgvector/pgvector:pg15 image (Port 5432).  
  * Include mongo:latest (Port 27017).  
* **Validation:** All three containers start cleanly without volume permission errors.

### **Phase 2: Schema & Data Modeling**

**Goal:** Define the Python data structures and exact database schemas, now including code-specific metadata.

* **Task 2.1:** Define Pydantic models for the data flow (MemoryPayload, CodeChunk, VectorRecord, MongoDocument).  
* **Task 2.2:** Write PostgreSQL initialization scripts.  
  * CREATE EXTENSION IF NOT EXISTS vector;  
  * Create table memory\_metadata: id (UUID), user\_id, session\_id, embedding (VECTOR(768)), mongo\_ref\_id.  
  * Create table code\_metadata: id (UUID), filepath, language, node\_type (e.g., 'function', 'class'), start\_line, end\_line, embedding (VECTOR(768)), mongo\_ref\_id.  
* **Task 2.3:** Write MongoDB collection indexes (Index on user\_id and filepath).  
* **Validation:** Python models successfully validate mock data; PG schema instantiates successfully.

### **Phase 3: The Engine (Connections, Embeddings & AST Parsing)**

**Goal:** Build the core Python backend logic handling the tri-routing and code parsing.

* **Task 3.1:** Set up async DB drivers: [redis-py](https://redis.readthedocs.io/), [asyncpg](https://magicstack.github.io/asyncpg/current/), and [motor](https://motor.readthedocs.io/).  
* **Task 3.2 (AST Setup):** Install [tree-sitter](https://github.com/tree-sitter/py-tree-sitter) and language bindings (e.g., tree-sitter-python, tree-sitter-javascript). Write a utility script to parse a file and yield tuples of (node\_type, code\_string, start\_line, end\_line).  
* **Task 3.3 (Code Embeddings):** Integrate a code-optimized embedding model. Use [jinaai/jina-embeddings-v2-base-code](https://huggingface.co/jinaai/jina-embeddings-v2-base-code) (generates 768-dimensional vectors, optimized for source code) via the transformers library.  
* **Task 3.4:** Implement Engine.store(), Engine.index\_code(), and Engine.search\_code(query) methods.  
* **Task 3.5 (Stacking Orchestrator):** Implement the atomic routing script (orchestrator.py).  
  * **Logic Rule 1:** Write heavy\_payload to Mongo ![][image1] await inserted\_id.  
  * **Logic Rule 2:** Try writing vector \+ inserted\_id to PG. Except Exception ![][image1] trigger Mongo delete\_one(inserted\_id) ![][image1] raise Error.  
  * **Logic Rule 3:** On success of Rule 1 & 2, push summary to Redis queue.  
* **Validation:** A test script successfully parses a local Python file, breaks it into functions via AST, vectorizes them, stores the full file in Mongo and the chunks in PG, and retrieves a specific function via natural language query. *Crucially, test the rollback mechanism by forcing a PG failure and ensuring Mongo stays clean.*

### **Phase 4: MCP Server Layer**

**Goal:** Wrap the Engine in the official Model Context Protocol to make it LLM-agnostic.

* **Task 4.1:** Install the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).  
* **Task 4.2:** Initialize the MCP stdio\_server.  
* **Task 4.3:** Register MCP Tools:  
  * @app.tool: store\_memory(user\_id, content, metadata)  
  * @app.tool: semantic\_search(user\_id, query\_string)  
  * @app.tool: index\_code\_file(filepath, raw\_code, language) (Triggers AST pipeline)  
  * @app.tool: search\_codebase(query, language\_filter) (Queries code\_metadata table)  
  * @app.tool: get\_recent\_context(user\_id) (Hits Redis only).  
* **Validation:** Run the MCP server in CLI mode. Ensure the JSON-RPC over stdio correctly lists the tools and accepts incoming arguments matching the JSON Schema.

### **Phase 5: Client Integration & Safety Nets**

**Goal:** Connect to an LLM client and handle failure states without external message brokers.

* **Task 5.1:** Provide the mcp\_config.json configuration for Claude Desktop or Cursor to connect to the local python script.  
* **Task 5.2 (Tri-Stack Garbage Collector):** Because we rely entirely on Python for orchestration, create a lightweight async background task (gc.py). Once an hour, it queries MongoDB for \_ids older than 5 minutes that do *not* exist in the PostgreSQL mongo\_ref\_id column. If found, it deletes them. This guarantees absolute data purity even if the Python process is hard-killed mid-transaction.  
* **Task 5.3 (Code Syncing):** Implement a background hashing check. If a file is re-indexed, calculate an MD5 hash of the file. If it hasn't changed, skip ingestion. If it has, delete old vectors from Postgres and re-run the AST pipeline.  
* **Validation:** The LLM client successfully invokes the code tools, searches for a function semantically, and correctly receives the exact lines of code sourced from the tri-db stack.

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABMAAAAYCAYAAAAYl8YPAAAAqklEQVR4XmNgGAWjYBACZWVlWXl5+W4FBQUOdDmygJycXDkIo4uTBYCuEwO6br+ioqIZuhxZAGQQ0MAjMjIyKigSoqKiPEAJSTJwMNC7j4AGcsINAwZmBUiQVAw07BkQ/wfqj0dyG+lAXFycG2jIQqBhfehyJAGgq1yBhqxG8R6ZgAXkIiD2QJcgGQBdIw101WYpKSkRdDmSgbGxMSvQQCEgkxFdbhQMMAAAwdwthtTzqmQAAAAASUVORK5CYII=>