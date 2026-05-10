document\_type: architectural\_audit\_and\_remediation\_blueprint

project: TriMCP

target\_workload: 750M\_tokens\_per\_day\_write\_heavy\_plus\_100\_human\_read\_heavy

status: CRITICAL\_ACTION\_REQUIRED

date: 2026-05-08

ai\_parsing\_directives:

* "Read Section 2 for root cause analysis."  
* "Execute Section 3 sequentially."  
* "Adhere strictly to \[Implementation\_Guidelines\] to prevent distributed systems regressions."

# **TriMCP Architectural Audit & Global Remediation Plan**

## **1\. Executive Summary**

The TriMCP architecture handles a highly asymmetric operational profile: an aggressive ingestion/orchestration engine (\~750M tokens/day) alongside a read-heavy CRM/search interface for 70-100 staff. Under swarm concurrency, background mechanics fail, leading to cross-tenant data leaks, data destruction, and infrastructural deadlocks (The "Noisy Neighbor" problem). Feature development is frozen. This document serves as the machine-actionable remediation blueprint.

## **2\. Critical Vulnerabilities by Category**

### **A. Data Integrity & State Management**

* **Saga Pattern Fragility:** Python-driven compensating actions (\_apply\_rollback\_on\_failure in memory.py) fail on OOM-kills, leaving orphaned MongoDB documents and decoupled graphs.  
* **GC Race Condition:** garbage\_collector.py deletes MongoDB documents lacking PostgreSQL references after 5 minutes. High-volume extraction jobs (\>5m) have payloads deleted mid-flight.  
* **Graph Lobotomy:** GC actively deletes kg\_nodes with no edges. Isolated nodes are valid; GC destroys valid intelligence.  
* **Vaporware Time Travel:** Temporal queries (as\_of) rely on bitemporal modeling (valid\_to), but memory.py only performs INSERT/ON CONFLICT DO UPDATE, overwriting historical state.  
* **Re-embedding Race Conditions:** reembedding\_migration.py fetches rows without SELECT ... FOR UPDATE SKIP LOCKED. Concurrent workers process identical rows, thrashing API quotas.

### **B. Security & Compliance**

* **Cross-Tenant Session Leakage:** set\_namespace\_context (auth.py, memory.py) sets Postgres RLS but lacks a finally: block to reset to NULL. Pool borrowers inherit previous identities.  
* **Fake WORM Compliance:** event\_log lacks DB-level immutability. GC executes DELETE against it.  
* **mTLS Spoofing:** a2a.py trusts X-Client-Cert-Fingerprint headers if trusted\_proxy\_hops \> 0 without strict IP whitelisting.  
* **SSRF via Agent Tools:** Workers lack egress restrictions, allowing internal AWS/GCP metadata API queries (e.g., 169.254.169.254).  
* **DLQ PII Leakage:** Failed jobs dump unredacted kwargs (sensitive bytes) directly into dead\_letter\_queue.  
* **Stateless JWT Revocation:** jwt\_auth.py lacks a token denylist (JTI blocklist).

### **C. Concurrency & Performance**

* **Partition-Scan DoS:** trg\_event\_log\_parent\_fk\_insupd trigger checks parent\_event\_id without partition keys, forcing Full Table Scans across all monthly partitions.  
* **Rate Limiter / Quota Races:** Redis rate limiter (auth.py) and Quota checks use non-atomic "Read-Modify-Write" Python logic.  
* **N+1 Database Thrashing:** Consolidation/graph extraction iterates via Python for loops, exhausting connection pools.  
* **Event Loop Starvation:** Synchronous C/C++ libraries (pytesseract) lock the ASGI/worker Python GIL.  
* **OAuth "Thundering Herd":** 50 concurrent agents hitting expired tokens simultaneously trigger 50 refresh requests, causing vendor bans.

### **D. AppSec & App-Layer Physics**

* **PII ReDoS:** pii.py uses standard regex. Malicious documents trigger catastrophic backtracking, spiking CPU to 100%.  
* **Unbounded JSON-RPC:** memory\_mcp\_handlers.py lacks strict payload limits, introducing an OS OOM-kill vector for Uvicorn.  
* **Missing Pagination:** admin\_mcp\_handlers.py serializes millions of rows without keyset pagination, exhausting memory.

### **E. Hardware & Infrastructure**

* **VRAM Fragmentation:** openvino\_npu\_export.py and re\_embedder.py lack explicit NPU/GPU garbage collection, locking accelerators.  
* **Dimensionality Panic:** Mixing embeddings (e.g., 3072d vs 768d) in the same pgvector column breaks HNSW index building.  
* **Phantom MinIO Bloat:** Rollbacks ignore MinIO, causing infinite S3 bloat.  
* **Unencrypted Redis:** VPC internal Redis traffic is plaintext, exposing A2A nonces.

### **F. Operations & Architecture Scale**

* **Read/Write Contention:** 750M token writes starve DB disk IOPS, causing timeouts for human staff reads.  
* **Direct DB Connection Exhaustion:** Hundreds of scaled worker containers will instantly hit PostgreSQL max\_connections.  
* **RQ Polling Thrash:** High-volume RQ polling maxes out Redis single-threaded CPU.  
* **Vector Index Collapse:** pgvector HNSW indexes lack scheduled REINDEX maintenance, leading to fragmentation.

## **3\. Global Remediation Plan (Machine-Actionable Tasks)**

### **TASK 1: Workload Isolation & Infrastructure**

**\[Objective\]:** Eliminate the "Noisy Neighbor" problem and prevent PostgreSQL connection exhaustion.

**\[Target\_Files\]:** trimcp-infra/\*, .env.example, config.py

* **\[Design\_Pattern: CQRS & Connection Pooling\]**  
* **\[Implementation\_Guidelines\]:**  
  1. **PgBouncer:** Introduce PgBouncer configured strictly in pool\_mode \= transaction. Update worker DATABASE\_URL to point to PgBouncer.  
  2. **Read Replicas:** Configure PostgreSQL native physical replication. Update config.py to maintain a DB\_READ\_URL and DB\_WRITE\_URL.  
  3. **Routing:** Force Uvicorn/ASGI GET routes (staff searches) to use the Read Replica. Force background workers (Agent batches) to use the Primary Write node.  
  4. **Telemetry Sink:** Reroute event\_log appending to a high-throughput message broker (Kafka/Redis Streams) or append-only DB (TimescaleDB) to preserve primary IOPS.

### **TASK 2: The Transactional Outbox**

**\[Objective\]:** Guarantee distributed consistency between Postgres, MongoDB, and MinIO without Python-level Sagas.

**\[Target\_Files\]:** schema.sql, memory.py, orchestrator.py, \[new\_file: outbox\_relay.py\]

* **\[Design\_Pattern: Transactional Outbox & Eventual Consistency\]**  
* **\[Implementation\_Guidelines\]:**  
  1. **Schema:** Add CREATE TABLE outbox\_events (id UUID PRIMARY KEY, aggregate\_type VARCHAR, payload JSONB, status VARCHAR DEFAULT 'pending', created\_at TIMESTAMPTZ).  
  2. **Atomic Write:** In memory.py, remove MongoDB insert\_one and MinIO put\_object from the primary execution path. Instead, write the raw bytes/document references as a JSONB payload to outbox\_events *inside* the same asyncpg transaction block that writes the semantic vectors.  
  3. **Relay Worker:** Create outbox\_relay.py that polls or uses Postgres LISTEN/NOTIFY on outbox\_events. It safely pushes payloads to Mongo/MinIO.  
  4. **Idempotency:** Ensure the Relay Worker uses ON CONFLICT or logical checks so retries do not duplicate Mongo/S3 objects. Drop the manual Saga rollback code.

### **TASK 3: Atomic State Controls**

**\[Objective\]:** Prevent connection leakage, race conditions in rate limits, and quota bypasses.

**\[Target\_Files\]:** auth.py, schema.sql, quotas.py, reembedding\_worker.py

* **\[Design\_Pattern: Resource Acquisition Is Initialization (RAII), Lua Atomicity, Row-Level Locks\]**  
* **\[Implementation\_Guidelines\]:**  
  1. **RLS Patch:** Wrap all yield conn statements in auth.py and memory.py with try: ... finally: await conn.execute("SELECT set\_config('trimcp.namespace\_id', '', false)").  
  2. **Lua Rate Limiter:** Replace Python-side zcard/zadd in auth.py with redis\_client.eval(). The Lua script must verify capacity, insert the timestamp, and reset the TTL in one atomic Redis instruction.  
  3. **DB Quota Enforcement:** Add ALTER TABLE resource\_quotas ADD CONSTRAINT chk\_quota CHECK (used\_amount \<= limit\_amount);.  
  4. **Concurrency Locks:** Update queue consumers (reembedding\_worker.py) to use SELECT ... FOR UPDATE SKIP LOCKED when fetching batches to prevent duplicate API executions.

### **TASK 4: WORM & Cryptographic Hardening**

**\[Objective\]:** Secure the audit trail and prevent I/O deadlock during signature chaining.

**\[Target\_Files\]:** schema.sql, signing.py

* **\[Design\_Pattern: DB-Level Immutability, Advisory Locks\]**  
* **\[Implementation\_Guidelines\]:**  
  1. **I/O Fix:** Delete trg\_event\_log\_parent\_fk\_insupd. If parent validation is required, enforce it at the application layer or include the partition key in the FK.  
  2. **Immutability:** Add a Postgres trigger function: CREATE OR REPLACE FUNCTION prevent\_mutation() RETURNS TRIGGER AS $$BEGIN RETURN NULL; END;$$. Attach as BEFORE UPDATE OR DELETE ON event\_log FOR EACH ROW EXECUTE FUNCTION prevent\_mutation();.  
  3. **Chain Integrity:** In signing.py, execute SELECT pg\_try\_advisory\_xact\_lock(hashtext(namespace\_id::text)) before fetching the latest\_event\_id to strictly serialize WORM appends across concurrent agent workers.

### **TASK 5: Internal Defense & GC Stabilization**

**\[Objective\]:** Prevent SSRF, OOM-kills, Thundering Herds, and data destruction.

**\[Target\_Files\]:** garbage\_collector.py, \_http\_utils.py, dispatch.py, bridge\_renewal.py, pii.py

* **\[Design\_Pattern: Network Egress Filtering, Distributed Mutex, Thread-pool Offloading\]**  
* **\[Implementation\_Guidelines\]:**  
  1. **GC Safe-Mode:** Change GC\_ORPHAN\_AGE\_SECONDS to 86400 (24h). Remove all SQL executing DELETE FROM kg\_nodes WHERE label NOT IN....  
  2. **Thread Offloading:** In dispatch.py and pii.py, wrap pytesseract and heavy regex compilation in asyncio.get\_running\_loop().run\_in\_executor(None, func).  
  3. **SSRF Guard:** Subclass httpx.AsyncClient or urllib3 transport in \_http\_utils.py to intercept and block DNS resolutions to 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, and 169.254.169.254.  
  4. **OAuth Mutex:** In bridge\_renewal.py, implement the Redlock algorithm (or a simple Redis SET key value NX EX 10\) around the vendor token refresh logic to serialize requests and prevent vendor API bans.  
  5. **ReDoS Defense:** Replace the re module with re2 or Google's re2 Python wrapper for all PII scrubbing, forcing O(N) execution time regardless of input malice.