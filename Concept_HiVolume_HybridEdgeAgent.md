# **TriMCP Hybrid Edge Architecture: Federated Zero-Copy GraphRAG**

**Author:** Sindre Haugen

**Date:** May 08, 2026

**Purpose:** Define a safe, high-throughput local processing architecture (750M tokens/day) that integrates with the Enterprise TriMCP server without causing I/O contention, data duplication, or PII liability.

## **1\. The Concept: "Indexing and KG Sharing Without Storing"**

The Hybrid Edge Worker flips the traditional client-server AI model. Instead of the client sending raw data to the cloud for processing, the heavy AI compute (chunking, OCR, LLM extraction) runs on the user's local hardware or dedicated isolated compute node.

It connects to the Enterprise server purely to **read context** and **write insights**.

## **2\. Component Topology**

### **A. The Local Edge Node (Your Machine)**

* **Compute:** Runs local ASGI server and heavy background workers.  
* **Database:** Local PostgreSQL instance (temporary workspace).  
* **LLM API:** Uses personal/isolated API keys with extreme quotas.  
* **Data Lifecycle:** Ephemeral. Raw documents are ingested, processed, and purged locally after insights are extracted.

### **B. The Enterprise Link (Read-Only Federation)**

To make the local node "aware" of company data without downloading it, we utilize **PostgreSQL Foreign Data Wrappers (FDW)**.

* The Local DB mounts the Enterprise Read-Replica kg\_nodes and kg\_edges as virtual tables.  
* The local worker can perform Vector Similarity (\<=\>) searches directly against the Enterprise graph to see if entities already exist, ensuring the local LLM has perfect ontological context.

### **C. The Insight Write-Back (A2A Protocol)**

The local node is strictly prohibited from writing directly to the Enterprise database. All writes must pass through the Enterprise's security and RLS layers.

* The local node compiles its findings into a GraphMutationPayload.  
* It utilizes the existing trimcp/a2a.py (Agent-to-Agent) protocol to securely transmit *only* the new Semantic Edges (relationships) and localized summaries back to the Enterprise Core.  
* **Zero-Copy Rule:** Raw files (.pdf, .docx) are NEVER transmitted to the Enterprise MinIO/Mongo stores during this workflow.

## **3\. The Hybrid Execution Flow**

1. **Ingestion (Local):** Super-user drops massive datasets into the Local MCP server.  
2. **Extraction (Local):** Local workers burn through 100M+ tokens extracting entities.  
3. **Reconciliation (Federated):** Local node runs SELECT id FROM enterprise\_kg\_nodes ORDER BY embedding \<=\> local\_embedding LIMIT 1\.  
   * *Result:* Links the newly discovered insight to the existing Enterprise entity.  
4. **Consolidation (Local):** Local LLM writes a high-level summary of the findings.  
5. **Sync (A2A):** Local node hits the Enterprise POST /a2a/graph/merge endpoint with the new edges and the summary document.

## **4\. Business & Technical Benefits**

1. **Zero I/O Contention:** The 100 regular employees utilizing the Enterprise server experience zero lag because all 750M tokens of compute are isolated to the Edge Node.  
2. **Data Privacy & Compliance:** By not uploading raw datasets (which may contain sensitive vendor data or unvetted PII) to the central corporate brain, the attack surface and compliance liability are drastically reduced.  
3. **Ontological Consistency:** By reading the Enterprise Graph via FDW, the local agent uses the exact same terminology and UUIDs as the rest of the company, preventing graph fragmentation.