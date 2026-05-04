# **TriMCP — Enterprise Deployment Plan & Requirements**

**Project:** TriMCP — sindrehaugen/TriMCP

**Version:** 2.2 (Final Comprehensive Plan \+ Extended Format Specs)

**Date:** May 2026

**Status:** Ready for engineering kickoff

## **Table of Contents**

* [1\. Executive Summary](#bookmark=id.3ju4hjpyrum3)  
* [2\. Architecture Overview](#bookmark=id.lcdh7r451k7w)  
  * [2.1 Mode Comparison](#bookmark=id.z68je46896re)  
  * [2.2 Local Mode](#bookmark=id.ymujh9k5815v)  
  * [2.3 Multi-User Mode](#bookmark=id.783x57bf0hxp)  
  * [2.4 Cloud Mode](#bookmark=id.3qf4taf8pr2q)  
  * [2.5 Why stdio Beats SSE for All Three Modes](#bookmark=id.9600tcd7oevm)  
  * [2.6 SSE Deprecation Decision](#bookmark=id.x2qop0fa4sz9)  
* [3\. Identity & Authentication](#bookmark=id.gl8xyk7ugdq7)  
  * [3.1 Identity Sources](#bookmark=id.3nav5bc59ei7)  
  * [3.2 Required server.py Patches for Namespacing](#bookmark=id.p7x5gskwxgha)  
* [4\. Server-Side Infrastructure (Multi-User Mode)](#bookmark=id.n7clvwk327yv)  
  * [4.1 Hardware Minimum Specification](#bookmark=id.jtp88f9bo3fx)  
  * [4.2 Docker Compose — Full Stack](#bookmark=id.ougen3ftqvv5)  
  * [4.3 Network Security](#bookmark=id.3eyvdon8ud)  
* [5\. Cloud Deployment (Azure / AWS / GCP)](#bookmark=id.9gyp9nhl8wcl)  
  * [5.1 Service Mapping](#bookmark=id.d6njhwxb6gij)  
  * [5.2 Infrastructure-as-Code](#bookmark=id.3hdr5uu4rwor)  
  * [5.3 Cost Estimates](#bookmark=id.gsctiwqn5b7k)  
  * [5.4 Hybrid Mode](#bookmark=id.kdi06hchvbx3)  
* [6\. Client Installer Requirements](#bookmark=id.9xexijiukhk4)  
  * [6.1 What the Installer Bundles](#bookmark=id.nt4u8kqh8gqz)  
  * [6.2 Wizard Flow](#bookmark=id.33gw041zzdaq)  
  * [6.3 What the Installer Writes](#bookmark=id.8at8qs9qjv01)  
  * [6.4 Mode-Aware Shim (trimcp-launch)](#bookmark=id.ew4vgp8b0bbp)  
* [7\. Installer Build Toolchain](#bookmark=id.otpfrd9vvezu)  
  * [7.1 Windows EXE — Inno Setup](#bookmark=id.ivyj164xxxhp)  
  * [7.2 Windows MSI — WiX Toolset v4](#bookmark=id.sdcweqiko0ah)  
  * [7.3 macOS DMG — Signed and Notarized](#bookmark=id.vg6cbjvhec0j)  
  * [7.4 Build Pipeline (GitHub Actions)](#bookmark=id.pqj74v2s7f16)  
* [8\. Hardware Acceleration — CPU / GPU / NPU](#bookmark=id.ixrnnjlj4twc)  
  * [8.1 Supported Backends](#bookmark=id.nvkbowdrt9bl)  
  * [8.2 Backend Abstraction in embeddings.py](#bookmark=id.ydt1q7e8to8y)  
  * [8.3 Intel NPU Specifics](#bookmark=id.onh58v3jeurq)  
  * [8.4 Installer Hardware Detection](#bookmark=id.ltu4lqtjj6rw)  
  * [8.5 Bundle Size Implications](#bookmark=id.auo1fvbwozd6)  
* [9\. Language Support Expansion (Tree-sitter)](#bookmark=id.spd99nthnya1)  
  * [9.1 The Change](#bookmark=id.cdc2zjlk1abk)  
  * [9.2 Code Change in ast\_parser.py](#bookmark=id.snb8b88exj5h)  
  * [9.3 Custom Grammars for Proprietary DSLs](#bookmark=id.74nan9s5jg9i)  
* [10\. Document Bridge System (Push Architecture)](#bookmark=id.3mnbatstzg5y)  
  * [10.1 Push-Based Architecture](#bookmark=id.ja7u7c2g642o)  
  * [10.2 High-Level Flow](#bookmark=id.2aqt2e5mlcbn)  
  * [10.3 Provider-Specific Implementations](#bookmark=id.izinlt3h7fn8)  
  * [10.4 Webhook Receiver Service](#bookmark=id.q1jd2lexeku7)  
  * [10.5 File Processing Pipeline](#bookmark=id.fq2awlnw2udh)  
  * [10.6 New MCP Tools Exposed](#bookmark=id.e3xv19au0v4s)  
  * [10.7 Subscription Renewal Cron](#bookmark=id.gps3smr7bq47)  
  * [10.8 Fallback to Pull (Local Mode \+ Degraded)](#bookmark=id.gbk82jixdip2)  
* [11\. Non-Technical User Experience](#bookmark=id.rpmjqjna07jc)  
  * [11.1 Friction Points and Resolutions](#bookmark=id.y0r2abyybnhk)  
  * [11.2 User Documentation Deliverables](#bookmark=id.gw8blswfetyy)  
* [12\. Phased Implementation Plan](#bookmark=id.1ayba1r2qygf)  
* [13\. Open Questions & Decisions](#bookmark=id.m30rjdhwrdlc)  
* [14\. Effort Estimate](#bookmark=id.lj3fmpftal9z)  
* [15\. Success Criteria](#bookmark=id.7cvgn64x7yas)  
* [16\. Appendices](#bookmark=id.ee1a19tng4i5)  
  * [A. Complete MCP Tool Reference](#bookmark=id.bqjdp5gmv99m)  
  * [B. Certificate Requirements](#bookmark=id.oj3t1zb1bzpy)  
  * [C. Hardware Backend Decision Matrix](#bookmark=id.rz784c1a33j0)  
  * [D. Cloud Region Recommendations](#bookmark=id.t46xzn8nktdk)  
  * [E. Bridge Provider Comparison](#bookmark=id.nr85j3cyyuz4)  
  * [F. Migration Paths](#bookmark=id.21ym4o3svg1s)  
  * [G. Reference Stack Versions](#bookmark=id.iymh77brf77o)  
  * [H. Bridge Subscription Lifecycle — Detailed Specification](#bookmark=id.1ucwn3b6lcm1)  
  * [I. Cloud IaC Module Specifications](#bookmark=id.893cb2q5k6oc)  
  * [J. Document Format Extraction — Detailed Specification](#bookmark=id.j81btqbrcds6)  
    * [J.1 Goals and Scope](#bookmark=id.g4iedog8dq0g)  
    * [J.2 Common Extraction Result Schema](#bookmark=id.1gx30eae249o)  
    * [J.3 .docx (Word, Modern)](#bookmark=id.n8a8sreggav8)  
    * [J.4 .doc (Word, Legacy)](#bookmark=id.ffup8pgtzd7v)  
    * [J.5 .xlsx (Excel, Modern)](#bookmark=id.2yv6wxpysb2p)  
    * [J.6 .xls (Excel, Legacy)](#bookmark=id.mcg6h13zpaxw)  
    * [J.7 .pptx (PowerPoint, Modern)](#bookmark=id.9q4nd7y6q6bu)  
    * [J.8 .ppt (PowerPoint, Legacy)](#bookmark=id.oz3bcyozye94)  
    * [J.9 .msg and .eml (Outlook / Standard Email)](#bookmark=id.gsec2gcbitjy)  
    * [J.10 .one (OneNote)](#bookmark=id.8ssseop2y1ob)  
    * [J.11 .pdf (with OCR Fallback)](#bookmark=id.7igvcboram86)  
    * [J.12 Plain-Text Family (.txt, .md, .csv, .tsv, .html, .rtf, .json, .xml)](#bookmark=id.x7vl16y3cjcr)  
    * [J.13 OpenDocument (.odt, .ods, .odp)](#bookmark=id.dz2khwtepjym)  
    * [J.14 Diagrams and Whiteboards (.vsdx, .drawio, .mermaid)](#bookmark=id.ou8daev0uxaj)  
    * [J.15 Adobe Creative Suite (.psd, .ai, .indd / .idml)](#bookmark=id.1b7tkzdk0kr6)  
    * [J.16 Engineering & CAD (.dxf, .dwg, .rvt, .skp)](#bookmark=id.adafdleqkc45)  
    * [J.17 Project Management & Publisher (.mpp, .pub)](#bookmark=id.2xhjo8cge1eh)  
    * [J.18 Encrypted / Password-Protected Files](#bookmark=id.e85yqjprk2oq)  
    * [J.19 OCR Fallback for Image-Only Documents](#bookmark=id.gxymhcu5jhfd)  
    * [J.20 Unknown Formats and Failure Handling](#bookmark=id.xvqcrrr3wk0q)  
    * [J.21 Library Dependency Summary](#bookmark=id.321c7m1wp1vz)  
    * [J.22 LibreOffice Headless Service](#bookmark=id.pmyn8u1tr6td)  
    * [J.23 Performance Benchmarks](#bookmark=id.uadh97ofpz9v)

## **1\. Executive Summary**

This document defines the architecture, requirements, and phased implementation plan for deploying TriMCP as a complete enterprise-grade AI memory layer. The deployment supports three distinct modes selected by the user at install time:

| Mode | For whom | Where the databases run | Network requirement |
| :---- | :---- | :---- | :---- |
| **Local** | Individual users, developers | The user's own machine (Docker Desktop) | None — fully offline capable |
| **Multi-User** | Office teams sharing knowledge | A central on-premise server | Office LAN or VPN |
| **Cloud** | Distributed teams, hybrid workforce | Managed cloud services (Azure / AWS / GCP) | Internet \+ VPN to private VNet/VPC |

All three modes use the **stdio** MCP transport on the client — chosen for its reliability and simplicity over the SSE/HTTP transport. The MCP server.py runs locally on every client machine, and only the data layer differs between modes.

### **Key capabilities delivered**

| Capability | Description |
| :---- | :---- |
| **Three-mode installer** | Single EXE/MSI/DMG installer with mode selection wizard |
| **Microsoft SSO identity** | Azure AD UPN resolved at install time, namespaces memory per user |
| **Hardware acceleration** | Auto-detects CPU, NVIDIA CUDA, AMD ROCm, Intel NPU (via OpenVINO), Apple Silicon — uses best available |
| **305+ programming languages** | Tree-sitter language pack replaces hardcoded grammars |
| **Universal format support** | Word, Excel, PowerPoint, Outlook, OneNote, PDF. **New:** Engineering (DXF/DWG/Revit/SketchUp), Design (Adobe PSD/AI/INDD), and Diagrams (Visio, Draw.io, Mermaid, Miro, Lucidchart) — all extracted, structured, and indexed |
| **Document bridges with push** | SharePoint, Google Drive, Dropbox indexed automatically via webhooks — no manual syncing |
| **Cloud-native deployment** | Terraform/Bicep modules for Azure, AWS, GCP using managed PostgreSQL, Redis, MongoDB, S3-compatible blob storage |
| **Non-technical UX** | Native installers, zero CLI, automatic AI client config patching |

### **Headline numbers**

* **\~53.5 engineering days** for full implementation  
* **\~500 MB** installer size for Multi-User / Cloud modes (Windows EXE, CPU-only torch); **\~1.1 GB** for Local mode (adds LibreOffice \+ Tesseract for office-format support)  
* **\~150 MB** first-launch model download (or zero if pre-seeded by IT)  
* **Three deployment modes** × **three platforms** (Windows/macOS/Linux) × **five hardware backends** \= comprehensive coverage

## **2\. Architecture Overview**

The architecture cleanly separates the MCP process from the data layer. The same server.py runs on every client machine. What changes between modes is where the four databases — PostgreSQL/pgvector, MongoDB, Redis, MinIO/S3 — physically live.

### **2.1 Mode comparison**

| Aspect | Local | Multi-User | Cloud |
| :---- | :---- | :---- | :---- |
| Databases run on | Client machine (Docker Desktop) | On-premise server | Managed cloud services |
| RQ worker runs on | Client (managed by shim) | On-premise server | Container instance (ACI / ECS / Cloud Run) |
| Identity | Local username | Azure AD UPN | Azure AD UPN / IAM identity |
| Data sharing | Private (single user) | Shared (office) | Shared (any authenticated org member) |
| Document bridge push | Not supported (no public endpoint) | Supported via reverse proxy | Native (webhook receiver in cloud) |
| Network | None required | Office LAN or VPN | Internet \+ private VNet/VPC |
| IT involvement | Zero | One-time server setup | Cloud subscription \+ Terraform |
| Disk on client | \~3 GB | \~500 MB | \~500 MB |
| Scalability | 1 user | \~50 users | 1000s of users |
| Best for | Solo developers, sensitive data | Single-office teams | Multi-site companies, remote teams |

### **2.2 Local Mode**

┌──────────────────────────────────────────────────────┐  
│  CLIENT MACHINE                                      │  
│                                                      │  
│   Claude Desktop / Cursor                            │  
│        ↕ stdio                                       │  
│   trimcp-launch.exe                                  │  
│        │                                             │  
│        ├─→ start\_worker.py (RQ subprocess)           │  
│        └─→ server.py (bundled Python 3.11)           │  
│                  ↕ localhost                         │  
│   ┌─────────────────────────────────────────────┐    │  
│   │ Docker Desktop                              │    │  
│   │   Postgres/pgvector · MongoDB               │    │  
│   │   Redis · MinIO                             │    │  
│   └─────────────────────────────────────────────┘    │  
└──────────────────────────────────────────────────────┘

All four databases run inside Docker containers on the user's machine. The shim starts the Docker stack at login (Task Scheduler / LaunchAgent). Document bridges are limited to **scheduled pull** in Local mode — push requires a public webhook endpoint.

### **2.3 Multi-User Mode**

CLIENT MACHINES (one per employee)         OFFICE SERVER  
                                              
 Claude Desktop / Cursor                   ┌─────────────────────┐  
      ↕ stdio                              │ Docker Compose:     │  
 trimcp-launch.exe                         │   Postgres/pgvector │  
      ↕                                    │   MongoDB           │  
 server.py ←───── TCP ─────────────────────┤   Redis             │  
                                           │   MinIO             │  
                                           │   start\_worker.py   │  
                                           │   webhook-receiver  │  
                                           └─────────────────────┘  
                                                    ↑  
                              ┌─────────────────────┴──────────────┐  
                              │ Reverse proxy (Caddy / nginx)      │  
                              │ Public HTTPS for webhooks          │  
                              │ /webhooks/sharepoint               │  
                              │ /webhooks/gdrive                   │  
                              │ /webhooks/dropbox                  │  
                              └────────────────────────────────────┘  
                                            ↑  
                              SharePoint / Google Drive / Dropbox push

The on-premise server runs the four databases plus the RQ worker plus a webhook receiver service. The webhook receiver sits behind a reverse proxy with a public HTTPS endpoint (typically a subdomain like trimcp.company.com) so that SharePoint/Drive/Dropbox can deliver push notifications.

### **2.4 Cloud Mode**

CLIENT MACHINES                            CLOUD (Azure / AWS / GCP)  
                                              
 Claude Desktop / Cursor                   ┌─────────────────────────┐  
      ↕ stdio                              │ Managed PostgreSQL      │  
 trimcp-launch.exe                         │  \+ pgvector             │  
      ↕                                    │ Cosmos DB / DocumentDB  │  
 server.py ←──── TLS ──────────────────────┤ Managed Redis           │  
                  via VPN                  │ Blob Storage / S3       │  
                                           │ Container worker        │  
                                           │ API Gateway → webhooks  │  
                                           └─────────────────────────┘

Identical client-side stack, but the data layer is fully managed. Webhook receivers run as containers (Azure Container Apps, AWS Fargate, Cloud Run) behind a managed API gateway. No on-premise infrastructure needed.

### **2.5 Why stdio beats SSE for all three modes**

SSE requires a persistent HTTP server that must stay alive, handle reconnects, manage CORS, and survive process crashes gracefully. Every client holds an open TCP connection to it. Under load this creates reliability pressure.

With stdio, the MCP transport is the OS pipe between the AI client and server.py. If server.py crashes the AI client simply restarts it on the next call. There is nothing to keep alive on the client. The only always-on processes are the database containers/services and the RQ worker — all designed for long-running server operation.

### **2.6 SSE Deprecation Decision**

**Decision: the existing sse\_server.py is removed from the enterprise distribution.**

The current TriMCP repository ships an sse\_server.py that implements the older SseServerTransport from the MCP Python SDK. This transport is not appropriate for the enterprise scenarios this plan addresses:

| Concern | Detail |
| :---- | :---- |
| **Reliability under load** | A long-lived HTTP/SSE connection per client requires careful handling of network blips, proxy timeouts, and reconnect logic. Real-world office networks (VPNs, captive portals, sleeping laptops) make this fragile. |
| **Operational burden** | Someone has to keep the SSE server alive, monitor it, restart it on crash, manage TLS certificates for it. stdio has none of these concerns — the AI client owns the lifecycle. |
| **Authentication gap** | The current sse\_server.py ships with no auth layer. Adding one (oauth2-proxy or in-process MSAL) is real work that delivers no advantage over the stdio \+ DB-credential model already specified. |
| **Maintenance scope creep** | Two transport paths means two codepaths to test, two failure modes for users, two sets of documentation. For an enterprise rollout, one well-tested path is better than two half-tested ones. |
| **Spec drift** | The MCP specification has evolved past pure SSE. The modern HTTP-based transport is **Streamable HTTP**, which has a different API surface than SseServerTransport. The existing sse\_server.py is therefore already legacy code. |

**What this means concretely:**

1. sse\_server.py and run\_sse.bat are **deleted** from the enterprise distribution.  
2. sse-server-related dependencies (starlette, uvicorn) remain in requirements.txt because the **webhook receiver** (§10.4) uses Starlette/FastAPI — but this is a different service with a different purpose, not an MCP transport.  
3. The mcp\_config.json example in the README is updated to show only the stdio configuration.  
4. Tests in tests/test\_smoke\_sse.py are removed; test\_smoke\_stdio.py is kept and expanded.

**Future-proofing — when HTTP transport might come back:**

If a future use case requires HTTP-based MCP (e.g. a web-based Claude client, a hosted multi-tenant TriMCP-as-a-service, or a kiosk deployment where stdio isn't viable), the right approach is to implement **Streamable HTTP transport** per the current MCP spec — not to revive the deprecated SSE code. Streamable HTTP supports the same enterprise needs (auth via standard HTTP headers, load balancing, observability) in a way that aligns with the broader MCP ecosystem. This is explicitly out of scope for v1 but documented here so the decision can be revisited cleanly.

**Migration note for existing TriMCP users:**

Anyone currently using sse\_server.py for development convenience can continue to do so by checking out the pre-v2.0 tag of the repo. The enterprise distribution from v2.0 onward only ships stdio.

## **3\. Identity & Authentication**

server.py already accepts user\_id as a parameter on every tool call. The installer resolves the employee's identity once and stores it in the per-user .env file. The wrapper script injects TRIMCP\_USER\_ID into the environment before launching server.py, which passes it through to every tool call automatically.

### **3.1 Identity sources**

| Platform | Identity source | Resolution method |
| :---- | :---- | :---- |
| Windows (domain) | Azure AD UPN | whoami /upn at install time → stored in .env |
| Windows (local) | USERPRINCIPALNAME env var | Fallback: COMPUTERNAME\\USERNAME |
| macOS (Entra-joined) | Azure AD UPN via dscl | dscl . \-read /Users/$USER EMailAddress |
| macOS (standalone) | Apple ID / local login | id \-un → username@computername.local |
| Cloud mode | Azure AD UPN via OAuth | OAuth device code flow on first run, cached token |

### **3.2 Required server.py patches for namespacing**

The current TriMCP code already supports user\_id on three of the eight tools. A small patch is required to add namespace scoping to the remaining two:

| Tool | user\_id accepted today | Patch needed |
| :---- | :---- | :---- |
| store\_memory | ✅ Yes | None |
| semantic\_search | ✅ Yes | None |
| get\_recent\_context | ✅ Yes | None |
| store\_media | ✅ Yes | None |
| index\_code\_file | ❌ No | Add optional user\_id param; if set, scope by namespace |
| search\_codebase | ❌ No | Add optional user\_id filter to PG query |
| graph\_search | ❌ No | Add optional user\_id filter to KG entity table |
| check\_indexing\_status | ❌ Not needed | (job\_id is already unique) |

**Decision**: codebase and graph search should default to **shared across the user's organization** (the main value of a shared deployment is collective knowledge), with an optional private=true parameter to scope to the calling user only. Personal memories via store\_memory remain namespaced by user.

## **4\. Server-Side Infrastructure (Multi-User Mode)**

This section applies to Multi-User mode only. In Local mode all infrastructure runs on the client. In Cloud mode see §5.

### **4.1 Hardware minimum specification**

| Resource | Minimum | Recommended |
| :---- | :---- | :---- |
| CPU | 4 cores | 8 cores (for embedding workloads) |
| RAM | 16 GB | 32 GB |
| Storage | 500 GB SSD | 1 TB NVMe |
| Network | 100 Mbit LAN | 1 Gbit LAN, public IP for webhook receiver |
| OS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS or Windows Server 2022 |
| GPU (optional) | None | NVIDIA T4 / A10 for embedding speedup, or AMD MI50 |

### **4.2 Docker Compose — full stack**

services:  
  postgres:  
    image: pgvector/pgvector:pg16  
    restart: always  
    environment:  
      POSTGRES\_USER: mcp\_user  
      POSTGRES\_PASSWORD: ${PG\_PASSWORD}  
      POSTGRES\_DB: memory\_meta  
    ports: \["5432:5432"\]  
    volumes: \["pgdata:/var/lib/postgresql/data"\]

  mongodb:  
    image: mongo:7  
    restart: always  
    environment:  
      MONGO\_INITDB\_ROOT\_USERNAME: mcp\_user  
      MONGO\_INITDB\_ROOT\_PASSWORD: ${MONGO\_PASSWORD}  
    ports: \["27017:27017"\]  
    volumes: \["mongodata:/data/db"\]

  redis:  
    image: redis:7-alpine  
    restart: always  
    command: redis-server \--requirepass ${REDIS\_PASSWORD}  
    ports: \["6379:6379"\]

  minio:  
    image: minio/minio  
    restart: always  
    command: server /data \--console-address ':9001'  
    environment:  
      MINIO\_ROOT\_USER: mcp\_user  
      MINIO\_ROOT\_PASSWORD: ${MINIO\_PASSWORD}  
    ports: \["9000:9000", "9001:9001"\]  
    volumes: \["miniodata:/data"\]

  worker:  
    image: trimcp-worker:latest  
    restart: always  
    depends\_on: \[postgres, mongodb, redis, minio\]  
    env\_file: .env

  webhook-receiver:  
    image: trimcp-webhooks:latest  
    restart: always  
    depends\_on: \[redis\]  
    env\_file: .env  
    ports: \["8080:8080"\]

  caddy:  
    image: caddy:2  
    restart: always  
    ports: \["443:443", "80:80"\]  
    volumes:  
      \- "./Caddyfile:/etc/caddy/Caddyfile"  
      \- "caddy\_data:/data"  
    depends\_on: \[webhook-receiver\]

volumes:  
  pgdata:  
  mongodata:  
  miniodata:  
  caddy\_data:

### **4.3 Network security**

| Measure | Implementation |
| :---- | :---- |
| Firewall (DB ports) | Allow 5432, 27017, 6379, 9000 from office subnet CIDR only |
| Firewall (webhook port) | Allow 443 from public internet (required for cloud webhooks to reach) |
| Postgres auth | scram-sha-256 in pg\_hba.conf — one DB user per employee or shared service account |
| Redis ACLs | requirepass \+ ACL LIST to restrict dangerous commands |
| MongoDB auth | x.509 certificate auth for production; username/password acceptable for LAN-only |
| MinIO | Bucket policy restricts object access by prefix matching user\_id |
| Webhook auth | HMAC signature verification per provider (Graph validation token, Drive X-Goog-Channel-Token, Dropbox X-Dropbox-Signature) |
| TLS | Caddy auto-provisions Let's Encrypt certificates for the webhook subdomain |

## **5\. Cloud Deployment (Azure / AWS / GCP)**

Cloud mode replaces on-premise Docker containers with managed cloud services. The client-side install is identical — only the .env file differs.

### **5.1 Service mapping**

| TriMCP component | Azure | AWS | GCP |
| :---- | :---- | :---- | :---- |
| Postgres \+ pgvector | Azure Database for PostgreSQL Flexible Server | Amazon RDS for PostgreSQL | Cloud SQL for PostgreSQL |
| MongoDB | Azure Cosmos DB for MongoDB | Amazon DocumentDB or MongoDB Atlas | MongoDB Atlas on GCP |
| Redis | Azure Cache for Redis | Amazon ElastiCache for Redis | Memorystore for Redis |
| MinIO/S3 | Azure Blob Storage (S3-compatible mode) | Amazon S3 | Cloud Storage (S3 interop) |
| RQ worker | Azure Container Apps | AWS Fargate | Cloud Run Jobs |
| Webhook receiver | Azure Container Apps \+ Front Door | AWS Lambda \+ API Gateway | Cloud Run \+ Cloud Endpoints |
| Identity | Microsoft Entra ID | AWS IAM Identity Center | Cloud IAM \+ Workload Identity |
| Network | Private VNet \+ Private Endpoints | VPC \+ PrivateLink | VPC \+ Private Service Connect |
| VPN access | Azure VPN Gateway / ExpressRoute | AWS VPN / Direct Connect | Cloud VPN / Interconnect |

### **5.2 Infrastructure-as-code**

Each cloud provider gets its own deployment module:

trimcp-infra/  
├── azure/  
│   ├── main.bicep              \# Bicep templates for Azure  
│   ├── modules/  
│   │   ├── postgres.bicep  
│   │   ├── cosmos.bicep  
│   │   ├── redis.bicep  
│   │   ├── storage.bicep  
│   │   └── containerapp.bicep  
│   └── parameters.example.json  
├── aws/  
│   ├── main.tf                 \# Terraform for AWS  
│   ├── modules/  
│   │   ├── rds-postgres/  
│   │   ├── documentdb/  
│   │   ├── elasticache/  
│   │   ├── s3/  
│   │   └── fargate-worker/  
│   └── terraform.tfvars.example  
└── gcp/  
    ├── main.tf                 \# Terraform for GCP  
    ├── modules/  
    │   ├── cloudsql/  
    │   ├── memorystore/  
    │   ├── gcs/  
    │   └── cloudrun/  
    └── terraform.tfvars.example

A single terraform apply (or az deployment group create) provisions the entire stack including private networking and webhook receiver. Output values populate the client .env template.

### **5.3 Cost estimates (rough, monthly USD)**

| Component | Azure | AWS | GCP |
| :---- | :---- | :---- | :---- |
| Postgres (4 vCPU, 16 GB, 256 GB storage) | \~$280 | \~$300 | \~$290 |
| MongoDB (M30 / equivalent) | \~$540 | \~$520 | \~$540 |
| Redis (5 GB cache) | \~$150 | \~$160 | \~$170 |
| Blob/Object storage (500 GB) | \~$10 | \~$12 | \~$10 |
| Container worker (always-on, 2 vCPU) | \~$70 | \~$80 | \~$75 |
| Webhook receiver (autoscale, low traffic) | \~$15 | \~$10 | \~$12 |
| Egress / networking | \~$50 | \~$60 | \~$55 |
| **Total** | **\~$1,115/mo** | **\~$1,142/mo** | **\~$1,152/mo** |

For a 50-person team this works out to \~$22/user/month — comparable to a SaaS knowledge tool but with full data sovereignty.

### **5.4 Hybrid mode**

A team can mix modes — e.g. office HQ runs Multi-User on-premise while remote workers use Cloud. Both back-ends can share the same data store if Cloud mode is configured to point at the on-premise databases via VPN, or vice versa. This is configurable but requires careful network design.

## **6\. Client Installer Requirements**

The installer is the most important piece of work for non-technical user adoption. It must require zero terminal interaction, zero Python knowledge, and produce a working MCP connection in under five minutes from download to first use.

### **6.1 What the installer bundles**

| Component | Notes |
| :---- | :---- |
| Python 3.11 embedded | Windows: python-3.11-embed-amd64.zip (\~10 MB). macOS: standalone framework build. No system Python dependency. |
| All pip packages | Pre-installed into bundled site-packages at build time. No pip run on user machine. |
| torch (CPU \+ accelerator wheels) | Multiple wheels bundled: CPU baseline, CUDA, ROCm, Intel XPU. Hardware detection picks the right one at install. |
| sentence-transformers \+ optimum-intel | Jina model downloaded on first launch (or pre-seeded — see §6.2). Optimum-Intel for OpenVINO NPU path. |
| spaCy en\_core\_web\_sm | Pre-downloaded and bundled. |
| tree-sitter-language-pack | All 305+ language grammars in one package (see §9). |
| server.py \+ trimcp/ package | Full TriMCP source. |
| docker-compose.local.yml | Local mode only — Docker Compose definition. |
| .env templates | Three templates: local, multi-user, cloud. Wizard writes the correct one. |
| trimcp-launch shim (Go) | Mode-aware launcher (see §6.4). |
| MS Graph SDK \+ Google API client \+ Dropbox SDK | For document bridge OAuth flows initiated from the wizard. |

### **6.2 Wizard flow**

┌─ Screen 1 ─────────────────────────────────────┐  
│ Welcome to TriMCP                              │  
│ "Connect your AI assistant to a memory system" │  
│                              \[Next\] \[Cancel\]   │  
└────────────────────────────────────────────────┘

┌─ Screen 2: Mode Selection ─────────────────────┐  
│  ◯ Local                                       │  
│    Just for me. Data stays on this computer.   │  
│    Requires Docker Desktop.                    │  
│                                                │  
│  ◯ Office Shared                               │  
│    Connect to my company's TriMCP server.      │  
│    Memories shared with my team.               │  
│                                                │  
│  ◯ Cloud                                       │  
│    Connect to a cloud TriMCP deployment.       │  
│    Sign in with your work account.             │  
│                              \[Back\] \[Next\]     │  
└────────────────────────────────────────────────┘

──── LOCAL PATH ────────────────────────────────  
┌─ Screen 3a: Docker Desktop Check ──────────────┐  
│ ✓ Docker Desktop is installed and running      │  
│   (or)                                         │  
│ ⚠ Docker Desktop not found                     │  
│   \[Download Docker Desktop\] (opens browser)    │  
│                              \[Back\] \[Next\]     │  
└────────────────────────────────────────────────┘

──── MULTI-USER PATH ───────────────────────────  
┌─ Screen 3b: Server Address ────────────────────┐  
│ Office server:                                 │  
│ \[trimcp.company.com               \]            │  
│                              \[Back\] \[Next\]     │  
└────────────────────────────────────────────────┘

──── CLOUD PATH ────────────────────────────────  
┌─ Screen 3c: Sign In ───────────────────────────┐  
│ Click "Sign In" to authenticate with your      │  
│ Microsoft work or school account.              │  
│                  \[Sign In with Microsoft\]      │  
│                              \[Back\] \[Next\]     │  
└────────────────────────────────────────────────┘

┌─ Screen 4: Hardware Acceleration ──────────────┐  
│ Detected hardware:                             │  
│   ✓ Intel Core Ultra 7 165H with NPU           │  
│   Recommended: Intel NPU (5x faster)           │  
│                                                │  
│  ◉ Use recommended (Intel NPU)                 │  
│  ◯ CPU only (slowest, most compatible)         │  
│  ◯ Advanced... (manual selection)              │  
│                              \[Back\] \[Next\]     │  
└────────────────────────────────────────────────┘

┌─ Screen 5: Document Bridges (optional) ────────┐  
│ Connect to your document libraries?            │  
│  ☐ Microsoft SharePoint / OneDrive             │  
│  ☐ Google Workspace / Drive                    │  
│  ☐ Dropbox                                     │  
│                                                │  
│ (You can configure these later)                │  
│                              \[Back\] \[Install\]  │  
└────────────────────────────────────────────────┘

┌─ Screen 6: Progress ───────────────────────────┐  
│ Setting up your AI memory…                     │  
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━ 78%                │  
│ Configuring hardware acceleration              │  
└────────────────────────────────────────────────┘

┌─ Screen 7: Finish ─────────────────────────────┐  
│ ✓ TriMCP is ready                              │  
│   Open Claude Desktop or Cursor to start.      │  
│                                                │  
│ ☑ Launch Claude Desktop now                    │  
│                                   \[Finish\]     │  
└────────────────────────────────────────────────┘

### **6.3 What the installer writes**

| File / location | Mode | Purpose |
| :---- | :---- | :---- |
| C:\\Program Files\\TriMCP\\python\\ | All | Embedded Python interpreter and packages |
| C:\\Program Files\\TriMCP\\app\\ | All | server.py, trimcp/, spaCy model, Docker Compose files |
| C:\\Program Files\\TriMCP\\torch-wheels\\ | All | Multiple torch variants for hot-swap |
| %APPDATA%\\TriMCP\\.env | All | DB URIs, TRIMCP\_USER\_ID, hardware backend choice |
| %APPDATA%\\TriMCP\\mode.txt | All | local / multiuser / cloud |
| %APPDATA%\\TriMCP\\bridges.json | All | OAuth tokens for SharePoint/Drive/Dropbox bridges |
| %APPDATA%\\TriMCP\\data\\ | Local | Docker volume mount for DB data |
| %APPDATA%\\TriMCP\\logs\\ | All | Shim and server logs for IT diagnostics |
| Task Scheduler entry | Local | Starts Docker stack at login |
| LaunchAgent plist | Local (macOS) | Same on macOS |
| %APPDATA%\\Claude\\claude\_desktop\_config.json | All | Patched MCP config |
| \~/.cursor/mcp.json (if Cursor detected) | All | Patched MCP config |
| /Applications/TriMCP/ | All (macOS) | App bundle |

### **6.4 Mode-aware shim (trimcp-launch)**

The shim is a small Go binary (\~3 MB) that abstracts mode-specific startup. The MCP client config is identical for all modes — the shim handles everything.

**Shim startup sequence:**

1\. Read mode.txt  
2\. Switch on mode:  
     
   case "local":  
     \- Check Docker Desktop is running  
     \- docker compose \-f docker-compose.local.yml up \-d \--wait  
     \- Start start\_worker.py as subprocess  
     \- Launch server.py with TRIMCP\_USER\_ID from .env  
     
   case "multiuser":  
     \- TCP connectivity check to Postgres host  
     \- If fail: dialog "Cannot reach office server. VPN connected?"  
     \- Refresh Azure AD UPN if cache expired  
     \- Launch server.py with TRIMCP\_USER\_ID  
     
   case "cloud":  
     \- Refresh OAuth token if expired (via MSAL)  
     \- TLS connectivity check to managed Postgres endpoint  
     \- Launch server.py with TRIMCP\_USER\_ID  
     
3\. On server.py exit: graceful cleanup (stop worker subprocess in local mode)

**Error handling:** every failure produces a plain-language native dialog. No tracebacks. No terminal windows. Technical details logged to %APPDATA%\\TriMCP\\logs\\ for IT diagnostics.

## **7\. Installer Build Toolchain**

### **7.1 Windows EXE — Inno Setup**

Self-extracting installer for ad-hoc download distribution.

| Property | Value |
| :---- | :---- |
| Tool | Inno Setup 6.x |
| Output | TriMCP-Setup-2.0.0.exe (\~600 MB with multiple torch wheels) |
| Signing | Authenticode with EV certificate (DigiCert / Sectigo) |
| Silent install | TriMCP-Setup.exe /SILENT /MODE=cloud /TENANT=company.onmicrosoft.com |
| Wizard customization | Company branding via \[Setup\] and \[Code\] sections |
| Uninstaller | Auto-generated, registered in Add/Remove Programs |

### **7.2 Windows MSI — WiX Toolset v4**

Enterprise GPO/Intune deployment.

| Property | Value |
| :---- | :---- |
| Tool | WiX Toolset v4 |
| Output | TriMCP-2.0.0-x64.msi |
| Public properties | MODE, SERVERADDR, TENANT, BRIDGES, BACKEND |
| Silent install | msiexec /i TriMCP.msi /quiet MODE=multiuser SERVERADDR=trimcp.company.com BRIDGES=sharepoint,gdrive |
| Transform files | .mst per department for different configs |
| Upgrade | Full MSI upgrade path via UpgradeCode |
| GPO deployment | Computer Configuration → Software Installation → Assigned |

### **7.3 macOS DMG — signed and notarized**

| Property | Value |
| :---- | :---- |
| Tool | create-dmg \+ Apple codesign \+ notarytool |
| Output | TriMCP-2.0.0-universal.dmg (Intel \+ Apple Silicon) |
| Signing | Apple Developer ID Application certificate ($99–299/year) |
| Notarization | xcrun notarytool submit ... \--wait (\~3–5 min) |
| Stapling | xcrun stapler staple for offline Gatekeeper |
| Installer type | Drag-to-Applications, post-install script on first launch |
| Silent install | hdiutil attach && cp \-R /Volumes/TriMCP/TriMCP.app /Applications/ for Jamf/Mosyle |

### **7.4 Build pipeline (GitHub Actions)**

on:  
  push:  
    tags: \['v\*'\]

jobs:  
  build-windows:  
    runs-on: windows-latest  
    steps:  
      \- checkout  
      \- bundle-python-embedded  \# python-3.11-embed-amd64  
      \- install-pip-packages    \# incl. tree-sitter-language-pack  
      \- download-spacy-model  
      \- bundle-torch-wheels     \# CPU \+ CUDA \+ ROCm \+ XPU variants  
      \- download-jina-model     \# for offline pre-seed  
      \- build-go-shim           \# GOOS=windows GOARCH=amd64  
      \- run-inno-setup          \# produces .exe  
      \- run-wix                 \# produces .msi  
      \- sign-with-evcert        \# signtool /fd SHA256  
      \- upload-artifacts

  build-macos:  
    runs-on: macos-latest  
    steps:  
      \- checkout  
      \- bundle-python-framework  \# python-build-standalone  
      \- install-pip-packages  
      \- download-spacy-model  
      \- bundle-torch-wheels      \# CPU \+ MPS variants  
      \- build-go-shim-universal  \# lipo amd64+arm64  
      \- codesign  
      \- create-dmg  
      \- notarize  
      \- staple  
      \- upload-artifacts

  release:  
    needs: \[build-windows, build-macos\]  
    steps:  
      \- create-github-release  
      \- upload .exe, .msi, .dmg

## **8\. Hardware Acceleration — CPU / GPU / NPU**

The original TriMCP only used CPU torch. The updated architecture detects available hardware at install time and runtime, then routes embedding inference through the optimal backend.

### **8.1 Supported backends**

| Backend | Hardware | Speedup vs CPU | How it works |
| :---- | :---- | :---- | :---- |
| **CPU** | Any x86\_64 / ARM64 | 1× (baseline) | Standard torch CPU wheel |
| **NVIDIA CUDA** | RTX 20-series and newer | 10–30× | torch CUDA wheel, native sentence-transformers |
| **AMD ROCm** | Radeon RX 7000/9000, Ryzen AI 300/MAX APUs | 8–20× | torch ROCm wheel (PyTorch 2.9 variant), works on Windows \+ Linux as of Sept 2025 |
| **Intel XPU** | Intel Arc GPU, Intel Data Center GPU Max | 10–20× | torch XPU wheel via Intel Extension for PyTorch |
| **Intel NPU** | Core Ultra Series 1 and 2, Lunar Lake | 3–5× (low power) | OpenVINO \+ Optimum-Intel, model exported to OpenVINO IR |
| **Apple Silicon** | M1/M2/M3/M4 | 5–15× | torch MPS backend |

### **8.2 Backend abstraction in embeddings.py**

A new abstraction layer replaces direct sentence-transformers calls:

\# trimcp/embeddings.py

class EmbeddingBackend(ABC):  
    @abstractmethod  
    async def embed(self, texts: list\[str\]) \-\> list\[list\[float\]\]: ...

class CPUBackend(EmbeddingBackend):  
    """Default fallback. Works everywhere."""

class CUDABackend(EmbeddingBackend):  
    """NVIDIA GPUs via torch CUDA."""

class ROCmBackend(EmbeddingBackend):  
    """AMD GPUs via torch ROCm wheel."""

class XPUBackend(EmbeddingBackend):  
    """Intel Arc / Data Center GPU via torch.xpu."""

class OpenVINONPUBackend(EmbeddingBackend):  
    """Intel NPU via OpenVINO IR. Requires static-shape model export."""

class MPSBackend(EmbeddingBackend):  
    """Apple Silicon via torch MPS."""

def detect\_backend() \-\> EmbeddingBackend:  
    user\_pref \= os.getenv("TRIMCP\_BACKEND")  
    if user\_pref:  
        return BACKENDS\[user\_pref\]()  
      
    \# Auto-detect best available  
    if torch.cuda.is\_available() and not \_is\_rocm():  
        return CUDABackend()  
    if \_is\_rocm() and torch.cuda.is\_available():  
        return ROCmBackend()  
    if hasattr(torch, "xpu") and torch.xpu.is\_available():  
        return XPUBackend()  
    if \_intel\_npu\_available():  
        return OpenVINONPUBackend()  
    if torch.backends.mps.is\_available():  
        return MPSBackend()  
    return CPUBackend()

### **8.3 Intel NPU specifics**

The Intel NPU has one important constraint: it only supports **static models** — every node must have a defined shape. This is why the standard sentence-transformers path doesn't work directly. The export step handled at install time:

\# Done once at install time, cached afterward  
from optimum.intel import OVModelForFeatureExtraction  
from optimum.exporters.openvino import export\_from\_model

model \= OVModelForFeatureExtraction.from\_pretrained(  
    "jinaai/jina-embeddings-v2-base-code",  
    export=True,  
    compile=False,  
)  
\# Reshape to fixed sequence length (e.g. 512 tokens)  
model.reshape(batch\_size=1, sequence\_length=512)  
model.compile()  
model.save\_pretrained("./jina-openvino-npu")

The NPU path then loads this pre-exported model. Texts longer than 512 tokens are chunked. The trade-off — fixed shape — is acceptable because embedding contexts are bounded anyway.

### **8.4 Installer hardware detection**

The installer wizard runs detection at Screen 4 (see §6.2):

// trimcp-launch detect-hardware

func detectHardware() HardwareInfo {  
    info := HardwareInfo{CPU: detectCPU()}  
      
    // NVIDIA via nvidia-smi  
    if hasNvidiaGPU() { info.CUDA \= true }  
      
    // AMD via rocminfo / lspci  
    if hasAMDGPUWithROCm() { info.ROCm \= true }  
      
    // Intel NPU via lspci or Windows Device Manager  
    if hasIntelNPU() { info.IntelNPU \= true }  
      
    // Intel Arc GPU  
    if hasIntelArcGPU() { info.IntelXPU \= true }  
      
    // Apple Silicon  
    if isAppleSilicon() { info.MPS \= true }  
      
    return info  
}

The wizard pre-selects the fastest detected backend but offers manual override in an "Advanced" sub-screen. The choice is written to .env as TRIMCP\_BACKEND=openvino\_npu etc.

### **8.5 Bundle size implications**

Bundling all torch variants would be \~5 GB. The pragmatic approach:

* **Windows EXE**: bundles CPU \+ downloads accelerator wheel post-install based on detection (\~600 MB → first-launch download)  
* **Windows MSI**: full bundle for offline GPO scenarios (\~2 GB)  
* **macOS DMG**: bundles CPU \+ MPS only (Apple hardware) (\~500 MB)  
* **Linux AppImage** (future): full bundle (\~2 GB)

## **9\. Language Support Expansion (Tree-sitter)**

### **9.1 The change**

Replace the five hardcoded grammars in requirements.txt:

\- tree-sitter\>=0.20.4  
\- tree-sitter-python\>=0.20.4  
\- tree-sitter-javascript\>=0.20.1  
\- tree-sitter-typescript\>=0.20.0  
\- tree-sitter-go\>=0.20.0  
\- tree-sitter-rust\>=0.20.0  
\+ tree-sitter\>=0.23.0  
\+ tree-sitter-language-pack\>=1.6.3

The tree-sitter-language-pack package provides 305+ pre-compiled tree-sitter parsers in a single dependency, with automatic on-demand grammar loading.

### **9.2 Code change in ast\_parser.py**

\# OLD: hardcoded language imports  
import tree\_sitter\_python  
import tree\_sitter\_javascript  
\# ...

\# NEW: dynamic grammar loading  
from tree\_sitter\_language\_pack import get\_language, get\_parser

def parse\_file(filepath: str, raw\_code: str, language: str | None \= None):  
    if language is None:  
        language \= detect\_language\_from\_extension(filepath)  
      
    parser \= get\_parser(language)  \# auto-loads grammar on first use  
    tree \= parser.parse(bytes(raw\_code, "utf-8"))  
    return extract\_chunks(tree, language)

def detect\_language\_from\_extension(filepath: str) \-\> str:  
    ext \= Path(filepath).suffix.lower()  
    return EXTENSION\_MAP.get(ext, "python")  \# default fallback

EXTENSION\_MAP \= {  
    ".py": "python",     ".pyi": "python",  
    ".js": "javascript", ".mjs": "javascript",  
    ".ts": "typescript", ".tsx": "tsx",  
    ".jsx": "javascript",  
    ".go": "go",  
    ".rs": "rust",  
    ".java": "java",     ".kt": "kotlin",  
    ".swift": "swift",  
    ".cpp": "cpp",       ".cc": "cpp",       ".h": "c",       ".c": "c",  
    ".cs": "csharp",  
    ".rb": "ruby",       ".php": "php",  
    ".scala": "scala",   ".clj": "clojure",  ".ex": "elixir",  
    ".lua": "lua",       ".pl": "perl",      ".r": "r",  
    ".sql": "sql",       ".sh": "bash",      ".ps1": "powershell",  
    ".html": "html",     ".css": "css",      ".scss": "scss",  
    ".yaml": "yaml",     ".yml": "yaml",     ".toml": "toml",  
    ".json": "json",     ".xml": "xml",  
    ".md": "markdown",   ".tex": "latex",  
    ".vue": "vue",       ".svelte": "svelte",  
    ".tf": "hcl",        ".dockerfile": "dockerfile",  
    ".proto": "proto",   ".graphql": "graphql",  
    ".elm": "elm",       ".dart": "dart",    ".zig": "zig",  
    ".nim": "nim",       ".cr": "crystal",   ".jl": "julia",  
    \# ... 305+ total in the language pack  
}

### **9.3 Custom grammars for proprietary DSLs**

For company-specific DSLs (config languages, internal scripting), tree-sitter's grammar DSL allows authoring custom grammars. These can be added to TriMCP without touching the core code:

\# trimcp/custom\_grammars/

from tree\_sitter import Language, Parser

\# Compile custom grammar at install time  
COMPANY\_DSL \= Language("./build/company\_dsl.so", "company\_dsl")  
EXTENSION\_MAP\[".cdsl"\] \= "company\_dsl"

A small add\_custom\_grammar helper script in the installer makes this self-service for IT teams with internal DSLs.

## **10\. Document Bridge System (Push Architecture)**

The document bridges enable TriMCP to automatically index files from corporate document libraries — keeping the AI's knowledge synchronised with the company's actual documents without manual action.

### **10.1 Push-based architecture**

We're going with **push** (not pull) as the primary mechanism. Push means:

* Document changes trigger near-instant indexing (seconds, not hours)  
* No polling waste — only changed files are processed  
* Webhook-driven event flow integrates cleanly with the existing RQ worker

This requires a publicly-reachable HTTPS endpoint to receive webhook callbacks from the cloud providers. The endpoint runs on the on-premise server (Multi-User mode) or as a managed container service (Cloud mode). **Local mode falls back to scheduled pull** because client machines can't reasonably expose public HTTPS endpoints.

### **10.2 High-level flow**

┌──────────────────┐  
│ SharePoint /     │  
│ Google Drive /   │  1\. User edits a file  
│ Dropbox          │  
└────────┬─────────┘  
         │ 2\. Provider sends webhook  
         ↓  
┌──────────────────────────────────────┐  
│ Webhook Receiver (FastAPI)           │  
│  \- Validates signature/token          │  
│  \- Returns 200 OK within 3 seconds    │  
│  \- Enqueues job to Redis (RQ)         │  
└────────┬─────────────────────────────┘  
         │ 3\. Job queued  
         ↓  
┌──────────────────────────────────────┐  
│ RQ Worker                            │  
│  \- Fetches changes via delta API      │  
│  \- Downloads modified files           │  
│  \- Extracts text (docx/pdf/xlsx)      │  
│  \- Calls store\_memory \+ chunks       │  
│  \- Updates last\_sync cursor           │  
└──────────────────────────────────────┘

### **10.3 Provider-Specific Implementations**

#### **SharePoint / OneDrive (Microsoft Graph)**

| Aspect | Details |
| :---- | :---- |
| Auth | Azure AD app registration with Sites.Read.All \+ Files.Read.All |
| Subscription endpoint | POST /v1.0/subscriptions with changeType: updated, resource: /sites/{id}/drive/root |
| Subscription lifetime | Max 3 days for SharePoint — must be renewed via cron |
| Validation | Graph sends a validation token on subscription creation; receiver echoes it within 10 seconds |
| Notification payload | {value: \[{subscriptionId, changeType, resource, clientState}\]} — note: payload does NOT include the file content; receiver must use delta API |
| Delta API | GET /v1.0/sites/{id}/drive/root/delta?token={cursor} returns changed items since last cursor |
| Throughput | \~10,000 events/second per subscription, so one subscription per drive is plenty |

\# trimcp/bridges/sharepoint.py

class SharePointBridge:  
    async def subscribe(self, drive\_id: str):  
        return await self.graph.post("/subscriptions", json={  
            "changeType": "updated",  
            "notificationUrl": f"{PUBLIC\_URL}/webhooks/sharepoint",  
            "resource": f"/sites/root/drives/{drive\_id}/root",  
            "expirationDateTime": (now() \+ timedelta(days=3)).isoformat(),  
            "clientState": secrets.token\_urlsafe(32),  
        })  
      
    async def handle\_webhook(self, payload: dict):  
        for notif in payload\["value"\]:  
            if notif\["clientState"\] \!= self.expected\_state:  
                raise ValueError("Invalid clientState")  
            queue.enqueue(process\_sharepoint\_delta,   
                         drive\_id=notif\["resource"\].split("/")\[-2\])  
      
    async def process\_delta(self, drive\_id: str):  
        cursor \= await redis.get(f"sp\_cursor:{drive\_id}") or ""  
        url \= f"/sites/root/drives/{drive\_id}/root/delta?token={cursor}"  
        while url:  
            response \= await self.graph.get(url)  
            for item in response\["value"\]:  
                if item.get("file"):  
                    await self.index\_file(item)  
                elif item.get("deleted"):  
                    await self.remove\_file(item\["id"\])  
            url \= response.get("@odata.nextLink")  
            await redis.set(f"sp\_cursor:{drive\_id}",   
                          response.get("@odata.deltaLink", ""))

#### **Google Workspace / Drive**

| Aspect | Details |
| :---- | :---- |
| Auth | Service account with domain-wide delegation, or OAuth user consent |
| Subscription | POST /drive/v3/files/{folderId}/watch for folder-level watch, or POST /drive/v3/changes/watch for org-wide |
| Subscription lifetime | Up to 7 days, renew via cron |
| Validation | Google sends X-Goog-Resource-State: sync on initial subscribe; subsequent are update/add/remove/trash |
| Push token | X-Goog-Channel-Token header — set by us on subscribe, validated on every callback |
| Changes API | GET /drive/v3/changes?pageToken={token} with delta-style pagination |
| Quota | 10 queries/second per user, 1000 QPS per project — generous |

#### **Dropbox**

| Aspect | Details |
| :---- | :---- |
| Auth | OAuth 2.0 with files.metadata.read \+ files.content.read scopes |
| Subscription | Set webhook URL once in app config (Dropbox dashboard) |
| Subscription lifetime | Permanent (no renewal) — simplest of the three |
| Validation | GET request with ?challenge=xyz on subscribe; receiver echoes the challenge value |
| Signature | X-Dropbox-Signature HMAC-SHA256 header — must verify before processing |
| Cursor API | /2/files/list\_folder/continue with cursor-based pagination |
| Throughput | Webhook delivers user account ID only; receiver fetches deltas |

#### **Miro / Lucidchart (Cloud Diagrams)**

| Aspect | Details |
| :---- | :---- |
| Auth | OAuth 2.0 with Board Read scopes |
| Subscription | App-level Webhooks (board\_subscription / document\_updated) |
| Notification payload | Board ID / Document ID. Worker fetches delta via REST API. |
| Extraction strategy | Spatial reading order lost; text extracted iteratively from sticky\_note, shape, and text object types. |

### **10.4 Webhook receiver service**

A FastAPI service that handles all three providers with minimal logic — its job is purely to validate, enqueue, and return 200 OK fast.

\# trimcp/webhook\_receiver/main.py

from fastapi import FastAPI, Request, HTTPException  
import hmac, hashlib

app \= FastAPI()

@app.post("/webhooks/sharepoint")  
async def sharepoint\_webhook(request: Request):  
    \# Validation handshake  
    if token := request.query\_params.get("validationToken"):  
        return Response(content=token, media\_type="text/plain")  
      
    payload \= await request.json()  
    for notif in payload\["value"\]:  
        if notif\["clientState"\] \!= EXPECTED\_STATES\["sharepoint"\]:  
            raise HTTPException(401)  
        queue.enqueue("trimcp.bridges.sharepoint.process\_delta",  
                     resource=notif\["resource"\])  
    return {"status": "queued"}

@app.post("/webhooks/gdrive")  
async def gdrive\_webhook(request: Request):  
    if request.headers.get("X-Goog-Channel-Token") \!= GDRIVE\_TOKEN:  
        raise HTTPException(401)  
      
    state \= request.headers.get("X-Goog-Resource-State")  
    if state \== "sync":  
        return  \# initial subscribe, no action  
      
    queue.enqueue("trimcp.bridges.gdrive.process\_changes",  
                 resource\_id=request.headers\["X-Goog-Resource-Id"\])  
    return {"status": "queued"}

@app.post("/webhooks/dropbox")  
async def dropbox\_webhook(request: Request):  
    body \= await request.body()  
    signature \= request.headers.get("X-Dropbox-Signature", "")  
    expected \= hmac.new(DROPBOX\_SECRET.encode(), body, hashlib.sha256).hexdigest()  
    if not hmac.compare\_digest(signature, expected):  
        raise HTTPException(401)  
      
    payload \= await request.json()  
    for account in payload.get("list\_folder", {}).get("accounts", \[\]):  
        queue.enqueue("trimcp.bridges.dropbox.process\_changes", account\_id=account)  
    return {"status": "queued"}

@app.get("/webhooks/dropbox")  
async def dropbox\_verify(challenge: str):  
    return Response(content=challenge, media\_type="text/plain")

### **10.5 File Processing Pipeline**

Once a webhook job is in the queue, the worker processes it. The processor dispatches to format-specific extractors based on file extension and MIME type. **TriMCP today has no Office-format support whatsoever** — adding it is a core part of this plan and is specified in detail in [Appendix J](#bookmark=id.j81btqbrcds6).

**Format support matrix (summary):**

| Format | Library | Capability | Detail in Appendix J |
| :---- | :---- | :---- | :---- |
| .docx (Word, modern) | python-docx \+ custom XML | Full: text, headings, tables, lists, comments, headers/footers, tracked changes | §J.3 |
| .doc (Word, legacy) | LibreOffice headless conversion | Convert to .docx first, then extract | §J.4 |
| .xlsx (Excel, modern) | openpyxl (read-only mode, data\_only=True) | All sheets, computed cell values, named ranges, basic formula reference resolution | §J.5 |
| .xls (Excel, legacy) | LibreOffice headless conversion | Convert to .xlsx first | §J.6 |
| .pptx (PowerPoint, modern) | python-pptx | Slide text, titles, speaker notes, table content, slide order preserved | §J.7 |
| .ppt (PowerPoint, legacy) | LibreOffice headless conversion | Convert to .pptx first | §J.8 |
| .msg (Outlook message) | extract-msg | Headers, body (HTML or plain), recipients, attachments (recursively extracted) | §J.9 |
| .eml (RFC 822 email) | Python stdlib email | Headers, body, attachments | §J.9 |
| .one (OneNote) | Microsoft Graph API direct (not file parsing) | Pages fetched as HTML via Graph; raw .one files skipped | §J.10 |
| .pdf | pypdf \+ pdfminer.six fallback \+ Tesseract OCR for scanned PDFs | Text extraction with layout, OCR fallback when text layer is empty | §J.11 |
| .txt, .md, .csv, .tsv | Built-in | Direct decode with encoding detection | §J.12 |
| .html, .htm | selectolax | Text extraction, navigation/script stripped | §J.12 |
| .rtf | striprtf | Plain text from rich text format | §J.12 |
| .odt, .ods, .odp | LibreOffice or odfpy | Treated like Office equivalents | §J.13 |
| .vsdx, .drawio, .mermaid | vsdx, xml.etree, direct parsing | Text from shapes, structural connections preserved | §J.14 |
| .psd, .ai, .indd / .idml | psd-tools, pypdf, lxml | Text layers, artboard titles, structured text frames | §J.15 |
| .dxf, .dwg | ezdxf, ODA/Teigha headless | Annotations, text entities, block attributes | §J.16 |
| .rvt, .skp (Revit/SketchUp) | Meta-only / Cloud API | Model metadata, component text (geometry skipped) | §J.16 |
| .mpp, .pub | mpxj (sidecar), LibreOffice | Task names/notes, text frames | §J.17 |
| Miro, Lucidchart | Bridge API integration | Board notes, shape text, sticky notes (via Webhooks) | §10.3 / §J.14 |
| Encrypted / password-protected | Detected, skipped with audit log entry | Not extracted; user notified | §J.18 |
| Image-only documents | Tesseract OCR triggered automatically | Falls back when text extraction yields \< 50 chars | §J.19 |
| Unknown / unsupported | Logged, skipped | Bridge continues with next file | §J.20 |

**Core processor logic:**

\# trimcp/bridges/processor.py

from trimcp.extractors import EXTRACTORS, extract\_with\_fallback

async def process\_file(provider: str, file\_id: str, user\_id: str):  
    metadata \= await PROVIDERS\[provider\].get\_metadata(file\_id)

    \# Skip if content unchanged  
    if await redis.get(f"hash:{provider}:{file\_id}") \== metadata.hash:  
        return

    \# Skip files exceeding size limit (default 100 MB, configurable)  
    if metadata.size \> settings.MAX\_FILE\_SIZE:  
        await audit\_log(file\_id, "skipped\_size", size=metadata.size)  
        return

    blob \= await PROVIDERS\[provider\].download(file\_id)

    \# Extract via format-specific pipeline; auto-fallback to OCR if needed.  
    \# Returns ExtractionResult with text, structured metadata, and warnings.  
    result \= await extract\_with\_fallback(  
        blob=blob,  
        filename=metadata.name,  
        mime\_type=metadata.mime\_type,  
    )

    if result.skipped:  
        await audit\_log(file\_id, "skipped", reason=result.skip\_reason)  
        return

    \# Chunk preserving extracted document structure (headings, slides, sheets)  
    chunks \= chunk\_structured(result, max\_tokens=512, overlap=64)

    for i, chunk in enumerate(chunks):  
        await engine.store\_memory(MemoryPayload(  
            user\_id=user\_id,  
            session\_id=f"{provider}:{metadata.parent\_path}",  
            content\_type="document",  
            summary=chunk.summary,  
            heavy\_payload=chunk.text,  
            metadata={  
                "source": provider,  
                "file\_id": file\_id,  
                "file\_name": metadata.name,  
                "mime\_type": metadata.mime\_type,  
                "modified": metadata.modified.isoformat(),  
                "url": metadata.web\_url,  
                "structure\_path": chunk.structure\_path,  \# e.g. "Sheet1\!A1:F50" or "Slide 7" or "Section 2.3"  
                "extraction\_method": result.method,  
                "extraction\_warnings": result.warnings,  
            }  
        ))

    await redis.set(f"hash:{provider}:{file\_id}", metadata.hash)

The full per-format implementation, library choices, edge cases, and OCR fallback are specified in Appendix J.

### **10.6 New MCP tools exposed**

| Tool | Purpose |
| :---- | :---- |
| connect\_bridge | Initiate OAuth flow for a provider; returns auth URL |
| complete\_bridge\_auth | Exchange OAuth code for tokens, create subscription |
| list\_bridges | Show currently connected bridges and their sync status |
| disconnect\_bridge | Remove subscription, optionally delete indexed content |
| force\_resync\_bridge | Force a full delta walk (recovery from missed events) |
| bridge\_status | Last sync time, files indexed, errors |

### **10.7 Subscription renewal cron**

A scheduled job runs hourly to renew expiring subscriptions:

@scheduler.scheduled\_job("interval", hours=1)  
async def renew\_subscriptions():  
    for provider in \["sharepoint", "gdrive"\]:  \# dropbox is permanent  
        subs \= await db.list\_subscriptions(provider)  
        for sub in subs:  
            if sub.expires \< now() \+ timedelta(days=1):  
                try:  
                    await PROVIDERS\[provider\].renew(sub)  
                except Exception as e:  
                    log.error(f"Failed to renew {provider} sub {sub.id}: {e}")  
                    \# Trigger force-resync on next webhook to recover any missed events  
                    await db.mark\_for\_resync(sub)

### **10.8 Fallback to pull (Local mode \+ Degraded)**

In Local mode, or if the webhook receiver is temporarily unreachable, the system falls back to scheduled pull:

@scheduler.scheduled\_job("interval", minutes=15)  
async def poll\_bridges\_fallback():  
    if mode \!= "local" and webhook\_receiver\_healthy():  
        return  \# push is working, no need to poll  
      
    for bridge in connected\_bridges:  
        await bridge.process\_delta()  \# uses cursor, only fetches changes

## **11\. Non-Technical User Experience**

### **11.1 Friction points and resolutions**

| Pain point | Severity | Solution |
| :---- | :---- | :---- |
| Requires Python 3.10+ installed | CRITICAL | Bundled Python in installer |
| Manual pip install (\~2.5 GB torch) | CRITICAL | Pre-installed at build time, CPU-only wheel default |
| Manual .env editing | HIGH | Wizard writes correct one based on mode |
| Manual claude\_desktop\_config.json patching | HIGH | Installer post-step |
| LOCAL: Docker Desktop not installed | HIGH | Wizard detects, offers download link |
| LOCAL: Docker Desktop license for \>250 employees | HIGH | Disclosed on mode screen, alternative: Podman Desktop |
| LOCAL: Docker uses 2 GB RAM on user laptop | MEDIUM | Documented in minimum spec; not noticeable on 16+ GB |
| start\_worker.py troubleshooting | MEDIUM | Worker is managed by shim (Local) or runs server-side (Multi-User/Cloud) |
| Embedding model download on first run | MEDIUM | Pre-seed via shared drive (recommended) or progress dialog |
| Python tracebacks shown to user | MEDIUM | Shim catches all errors, shows native dialogs |
| No status indicator | LOW | Optional tray icon showing mode and connection state |
| spaCy model download | LOW | Bundled in installer |
| Tree-sitter grammar compilation | LOW | language-pack ships pre-compiled |
| Hardware accelerator setup | LOW | Auto-detected, manual override available |
| OAuth flows for bridges | MEDIUM | Wizard launches browser, captures token, stores in bridges.json |

### **11.2 User documentation deliverables**

| Document | Audience | Length |
| :---- | :---- | :---- |
| Quick Start (PDF) | End user | 1 page, screenshots only |
| IT Admin Guide | IT | 15–20 pages, includes Terraform examples |
| Bridge Setup Guide | End user | 3 pages per bridge with screenshots |
| Troubleshooting FAQ | End user \+ IT | 10 most common errors, plain language |
| Privacy Notice | End user | Required for GDPR/data residency clarity |
| API Reference | Developer | All MCP tools, parameters, examples |

## **12\. Phased Implementation Plan**

### **Phase 0 — Foundation (Week 1\)**

* Provision multi-user server (or pick cloud target)  
* Deploy databases-only docker-compose.yml  
* Apply firewall rules and credential management  
* Patch server.py: add user\_id to index\_code\_file, search\_codebase, graph\_search  
* Replace tree-sitter grammars with tree-sitter-language-pack  
* **Remove SSE transport**: delete sse\_server.py, run\_sse.bat, tests/test\_smoke\_sse.py; update README to show only stdio config  
* Run TriMCP test suite against new infrastructure

### **Phase 1 — Hardware Backend Abstraction (Week 2\)**

* Refactor embeddings.py into backend-agnostic interface  
* Implement CPU, CUDA, ROCm, XPU, MPS backends  
* Implement OpenVINO NPU backend with static-shape Jina export  
* Build hardware detection in Go (used by both installer and shim)  
* Test on representative hardware (NVIDIA, AMD, Intel NPU laptop, M3 Mac)

### **Phase 2 — Document Bridge System (Weeks 3–4)**

* Build trimcp/bridges/ module with provider abstractions  
* Implement SharePoint bridge (Graph API \+ delta \+ subscriptions)  
* Implement Google Drive bridge (Drive API \+ changes \+ watch)  
* Implement Dropbox bridge (API v2 \+ cursor \+ webhooks)  
* Build webhook receiver FastAPI service  
* Build subscription renewal cron  
* Add MCP tools: connect\_bridge, bridge\_status, etc.

### **Phase 2b — Document Format Extraction (Weeks 4–5, parallelisable with Phase 2\)**

* Build trimcp/extractors/ module with the format dispatch layer  
* Implement Word extractors (.docx via python-docx \+ XML, .doc via LibreOffice)  
* Implement Excel extractors (.xlsx via openpyxl, .xls via LibreOffice)  
* Implement PowerPoint extractors (.pptx via python-pptx, .ppt via LibreOffice)  
* Implement PDF extractor with three-layer fallback (pypdf → pdfminer → OCR)  
* Implement email extractors (.msg, .eml) with recursive attachment handling  
* Implement plain-text family (.txt, .md, .csv, .html, .rtf, .json, .xml)  
* Implement OneNote integration via Graph API (not file parsing)  
* Implement Engineering & Design extractors (CAD annotations, Adobe text layers, Desktop Publishing)  
* Implement Diagram/Whiteboard extractors (Draw.io XML, Mermaid, Miro/Lucid API hooks)  
* Build encrypted-file detection (no password handling — skip with audit)  
* Build OCR fallback service (Tesseract \+ optional EasyOCR for GPU)  
* Package LibreOffice headless service for the worker container  
* Build extraction test corpus (50+ real-world documents per format)  
* Benchmark and document throughput per format

### **Phase 3 — Cloud Infrastructure (Weeks 5–6)**

* Author Bicep modules for Azure (Postgres \+ Cosmos \+ Redis \+ Blob \+ Container Apps)  
* Author Terraform modules for AWS (RDS \+ DocumentDB \+ ElastiCache \+ S3 \+ Fargate)  
* Author Terraform modules for GCP (Cloud SQL \+ Memorystore \+ GCS \+ Cloud Run)  
* Build cloud OAuth flow for client identity  
* Test deployment on each cloud provider end-to-end  
* Document IaC parameters and deployment runbooks

### **Phase 4 — Mode-Aware Shim (Week 7\)**

* Build trimcp-launch Go shim with Local / Multi-User / Cloud paths  
* Hardware detection and backend selection  
* Connectivity health checks for each mode  
* Native error dialogs (Windows MessageBox, macOS NSAlert)  
* Logging to %APPDATA%\\TriMCP\\logs\\  
* Cross-platform OAuth helper for Cloud mode and bridges

### **Phase 5 — Installer Build Pipeline (Weeks 8–10)**

* GitHub Actions workflow with matrix build  
* Bundle Python embedded \+ packages \+ spaCy \+ Jina (pre-seeded)  
* Bundle multiple torch wheels for accelerator hot-swap  
* Inno Setup .iss with mode \+ hardware \+ bridges wizard screens  
* WiX .wxs for MSI with public properties  
* Apple create-dmg \+ codesign \+ notarize \+ staple  
* EV code signing certificate procurement  
* Apple Developer Program enrollment  
* Test on clean VMs: Win 10/11, macOS Sonoma/Sequoia

### **Phase 6 — Pilot & Iteration (Weeks 11–12)**

* Internal alpha: 3 developers, all three modes  
* External beta: 5 non-technical users, observed installation sessions  
* Iterate on installer UX (typically 2–3 rounds)  
* Refine documentation based on observed confusion points  
* Stress test bridges with realistic SharePoint/Drive/Dropbox traffic

### **Phase 7 — Production Rollout (Week 13+)**

* IT deploys MSI via GPO/Intune for Windows  
* macOS DMG distributed via SharePoint / internal portal  
* Cloud customers deploy via Terraform  
* Establish update procedure (new tag → CI build → re-deploy)  
* Monitor server resource usage, scale as needed

## **13\. Open Questions & Decisions**

| Question | Recommendation |
| :---- | :---- |
| Should Local mode be available to all employees? | Yes by default; IT can hide via MSI ALLOWLOCALMODE=0 if they want Multi-User-only |
| Default mode in wizard? | Multi-User if IT bakes a server address at build time; Local for generic distribution |
| Docker Desktop license for \>250 employees? | Disclose in wizard. If cost prohibitive, support Podman Desktop as alternative (\~3 days extra work) |
| Per-user or shared codebase/graph search? | Shared by default with private=true opt-in; matches the spirit of shared deployment |
| HuggingFace cache pre-seeding? | Strongly recommended via shared drive for offices with strict proxy/firewall |
| Multiple AI clients (Claude Desktop \+ Cursor)? | Yes — installer detects all and patches all |
| GDPR data residency? | On-premise keeps data local; Cloud mode requires choosing region carefully (EU customers → EU regions) |
| Update policy? | IT-gated for Multi-User; auto-update for Local with user opt-in |
| Bridge sync: PUSH vs PULL? | **Push primary** with pull fallback. Local mode \= pull only (no public endpoint) |
| Cloud webhook receiver authentication? | Provider-specific HMAC \+ clientState/token validation per webhook |
| Cross-tenant identity for Cloud mode? | Each cloud deployment is single-tenant; multi-tenant is future scope |
| Migration between modes? | Re-run installer to switch; data does not migrate automatically (manual export tool, deferred to v2) |
| Custom DSL grammars? | Supported via add\_custom\_grammar helper, not in initial scope |
| Webhook delivery failures? | Pull-based recovery: subscription renewal cron also force-resyncs any subs that missed events |
| What happens if a user installs Local then their org switches to Multi-User? | Re-running installer in Multi-User mode reconfigures .env and mode.txt. Local data is left behind (orphaned). v2 feature: migration tool. |

## **14\. Effort Estimate**

| Work item | Days | Notes |
| :---- | :---- | :---- |
| server.py patches (user\_id for codebase/graph) | 0.5 | Small SQL filter additions |
| SSE transport removal \+ README update | 0.25 | Delete sse\_server.py, related tests, update docs |
| Tree-sitter language pack swap | 0.5 | Drop-in replacement |
| Hardware backend abstraction (CPU/CUDA/ROCm/MPS) | 2 | Refactor embeddings.py |
| Intel NPU OpenVINO backend | 2 | Static export \+ integration |
| Hardware detection (Go) | 1 | Cross-platform NPU/GPU detection |
| Local-mode docker-compose.local.yml | 0.5 | Stack bound to localhost |
| trimcp-launch shim (3 modes) | 3 | Mode dispatch \+ error handling |
| Document extractors — Word (docx \+ doc fallback) | 1.5 | python-docx \+ LibreOffice for legacy |
| Document extractors — Excel (xlsx \+ xls fallback, large-sheet strategy) | 1.5 | openpyxl \+ large-table summarisation |
| Document extractors — PowerPoint (pptx \+ ppt fallback) | 1 | python-pptx \+ spatial reading order |
| Document extractors — PDF (3-layer with OCR fallback) | 2 | pypdf \+ pdfminer \+ Tesseract |
| Document extractors — Email (msg \+ eml \+ recursive attachments) | 1 | extract-msg \+ stdlib email |
| Document extractors — Plain text family \+ HTML \+ OpenDocument | 1 | Multiple small libraries |
| Document extractors — Diagrams (Draw.io, Mermaid, Visio) | 1 | XML decoding and graph traversal |
| Document extractors — Design (Adobe PSD/AI/INDD) | 1.5 | psd-tools \+ PDF fallback \+ IDML XML parsing |
| Document extractors — Engineering (DXF/DWG/RVT/SKP) | 2 | ezdxf \+ headless sidecar abstractions. Focus on text annotations. |
| Document extractors — Desktop Publishing & Project (PUB/MPP) | 1 | LibreOffice fallback \+ mpxj or python-mpp |
| Bridge Integrations — Miro & Lucidchart | 2 | API auth, webhook registration, and canvas traversal |
| OneNote via Graph API integration | 0.5 | API path, not file parsing |
| Encrypted-file detection across all formats | 0.5 | Magic-byte and structure checks |
| OCR fallback service (Tesseract worker \+ EasyOCR GPU path) | 1.5 | Including queue separation and language packs |
| LibreOffice headless service packaging | 1 | Sidecar container \+ REST wrapper \+ pooling |
| Document extraction test corpus \+ benchmarks | 1 | 50+ real-world docs per format |
| SharePoint bridge | 2 | Graph API \+ delta \+ subscriptions |
| Google Drive bridge | 1.5 | Drive API \+ changes \+ watch |
| Dropbox bridge | 1.5 | API v2 \+ cursor \+ webhooks |
| Webhook receiver service | 1 | FastAPI \+ signature validation |
| Subscription renewal cron | 0.5 | APScheduler job |
| Bridge MCP tools | 1 | OAuth, status, force-resync |
| Bicep module for Azure | 2 | Postgres \+ Cosmos \+ Redis \+ Blob \+ Containers |
| Terraform module for AWS | 2 | RDS \+ DocumentDB \+ ElastiCache \+ S3 \+ Fargate |
| Terraform module for GCP | 2 | Cloud SQL \+ Memorystore \+ GCS \+ Cloud Run |
| Cloud OAuth flow for client | 1 | MSAL device code |
| CI build pipeline | 2 | GitHub Actions matrix, signing |
| Windows EXE (Inno Setup) with full wizard | 2 | All screens, branching logic |
| Windows MSI (WiX) | 2 | Public properties, transforms |
| macOS DMG \+ notarization | 2 | Universal binary, signing, stapling |
| Pre-seeding cache \+ spaCy bundle | 1 | Build-time download |
| Non-technical user pilot \+ iteration | 3 | Multi-mode UX is fiddly |
| Documentation (Quick Start, IT Admin, Bridges) | 2 | Three deliverables |
| **TOTAL** | **\~53.5 days** | Two developers in parallel \= \~6 calendar weeks. Document extraction adds \~19.5 days vs the v2.1 estimate, reflecting the comprehensive parsing of enterprise, CAD, and design formats. |

## **15\. Success Criteria**

The deployment is successful when all of the following are true:

1. A non-technical employee installs TriMCP in under 5 minutes from a downloaded EXE/DMG, picks a mode, and reaches the finish screen without terminal interaction.  
2. **Local mode**: Docker stack starts at login, no user action needed.  
3. **Local mode**: A user without Docker Desktop is clearly directed to install it before the wizard proceeds.  
4. **Multi-User mode**: stdio MCP connection works reliably for a full workday without manual restart.  
5. **Multi-User mode**: One user's memories are not visible to another (namespace isolation verified).  
6. **Cloud mode**: A team can be deployed via terraform apply in under 30 minutes per cloud provider.  
7. **Hardware detection**: Each test machine (NVIDIA, AMD, Intel NPU, Apple Silicon, plain CPU) auto-selects the correct backend.  
8. **Tree-sitter**: Files in 50+ different languages are indexed correctly (sample test corpus).  
9. **Document bridges**: A file edited in SharePoint/Drive/Dropbox is reflected in semantic\_search results within 60 seconds.  
10. **Bridge resilience**: Subscriptions renew automatically; missed webhooks are recovered via delta resync within 1 hour.  
11. **Mode switching**: Re-running the installer to switch modes completes cleanly; AI client config remains valid.  
12. **IT deployment**: Multi-User MSI deployment via GPO works without per-machine user action.  
13. **Cloud cost**: Per-user monthly cost stays under $25 at 50-user scale.  
14. The Multi-User server (or cloud stack) survives a weekend with no manual intervention.

## **16\. Appendices**

### **Appendix A — Complete MCP Tool Reference**

| Tool | Purpose | Mode availability |
| :---- | :---- | :---- |
| store\_memory | Save a conversation, document, or summary | All modes |
| store\_media | Save an audio/video/image file with text summary | All modes |
| semantic\_search | Find memories related to a query | All modes |
| graph\_search | Traverse the knowledge graph for related concepts | All modes |
| index\_code\_file | Index a source code file (async) | All modes |
| check\_indexing\_status | Check progress of an async indexing job | All modes |
| search\_codebase | Find functions/classes by description | All modes |
| get\_recent\_context | Instant Redis recall of recent session | All modes |
| connect\_bridge | Initiate OAuth for SharePoint/Drive/Dropbox | All modes |
| complete\_bridge\_auth | Complete OAuth and create subscription | Multi-User, Cloud (push); Local (pull only) |
| list\_bridges | Show connected bridges and sync status | All modes |
| disconnect\_bridge | Remove a bridge connection | All modes |
| force\_resync\_bridge | Force full delta walk for recovery | All modes |
| bridge\_status | Detailed status of a specific bridge | All modes |

### **Appendix B — Certificate Requirements**

| Certificate | Source | Cost | Required for |
| :---- | :---- | :---- | :---- |
| Windows EV Code Signing | DigiCert / Sectigo / GlobalSign | $300–500/year | EXE and MSI signing — avoids SmartScreen warnings |
| Apple Developer ID | developer.apple.com | $99/year individual, $299/year org | macOS Gatekeeper notarization |
| TLS for webhook receiver | Let's Encrypt (free, via Caddy) | $0 | HTTPS endpoint for cloud webhooks |
| Postgres TLS (cloud mode) | Provider-managed | Included | Encrypted DB connections |

### **Appendix C — Hardware Backend Decision Matrix**

| User has... | Chose at install | Backend used | Notes |
| :---- | :---- | :---- | :---- |
| Plain Windows laptop | Auto | CPU | Slowest but always works |
| Gaming PC with RTX 4070 | Auto | CUDA | Fastest path |
| Gaming PC with Radeon RX 7800 XT | Auto | ROCm | Windows ROCm 6.4.4+ required |
| Intel Core Ultra 7 165H laptop | Auto | OpenVINO NPU | Low-power, 5x CPU |
| Intel Core Ultra \+ RTX 4090 dGPU | Auto | CUDA (priority) | NPU available as override |
| MacBook Pro M3 | Auto | MPS | Apple Silicon native |
| Server with Tesla T4 | Cloud worker | CUDA | Server-side embedding |
| Server with no GPU | Cloud worker | CPU | Acceptable for batch indexing |

### **Appendix D — Cloud Region Recommendations**

| Customer location | Azure region | AWS region | GCP region | Reason |
| :---- | :---- | :---- | :---- | :---- |
| US East Coast | East US 2 | us-east-1 | us-east1 | Lowest latency, mature |
| US West Coast | West US 3 | us-west-2 | us-west1 | West Coast latency |
| EU (GDPR) | West Europe / North Europe | eu-west-1 (Ireland) | europe-west1 (Belgium) | EU data residency |
| UK | UK South | eu-west-2 (London) | europe-west2 (London) | UK GDPR equivalent |
| Nordics | Sweden Central | eu-north-1 (Stockholm) | europe-north1 (Finland) | Lower latency for Norway/Sweden |
| APAC | Southeast Asia / Japan East | ap-southeast-1 / ap-northeast-1 | asia-southeast1 / asia-northeast1 | Regional latency |

### **Appendix E — Bridge Provider Comparison**

| Aspect | SharePoint | Google Drive | Dropbox |
| :---- | :---- | :---- | :---- |
| Auth complexity | High (Azure AD app reg) | Medium (service account or OAuth) | Low (single OAuth) |
| Webhook setup | Per-resource subscription | Per-folder or org-wide watch | Single app-level webhook |
| Subscription renewal | Every 3 days | Every 7 days | Permanent |
| Validation handshake | validationToken query param | X-Goog-Resource-State: sync header | ?challenge= query param |
| Signature verification | clientState opaque value | X-Goog-Channel-Token | X-Dropbox-Signature HMAC-SHA256 |
| Delta API | /delta?token= | /changes?pageToken= | /list\_folder/continue |
| Rate limits | 130 req/min/app | 1000 QPS/project | 600 req/min/user |
| File metadata in webhook? | No (must fetch) | No (must fetch) | No (must fetch) |
| Best for | M365 shops | Google Workspace shops | Mixed / SMB |

### **Appendix F — Migration Paths**

| From → To | Difficulty | Notes |
| :---- | :---- | :---- |
| Local → Multi-User | Easy | Re-run installer, local data abandoned (or manually exported) |
| Local → Cloud | Easy | Re-run installer, sign in with work account |
| Multi-User → Cloud | Medium | Bulk export from on-premise DBs, import to cloud (one-time tool needed) |
| Cloud → Multi-User | Medium | Reverse of above |
| Cloud (Azure) → Cloud (AWS) | Hard | Cross-cloud data migration, requires custom export/import |

### **Appendix G — Reference Stack Versions**

| Component | Pinned Version | Rationale |
| :---- | :---- | :---- |
| Python | 3.11.x | LTS, stable, all deps support |
| torch | 2.9.0 | Variant wheel support (CUDA/ROCm/XPU) |
| sentence-transformers | ≥2.7 | Modern API |
| optimum-intel | ≥1.25 | Intel NPU \+ Whisper fixes |
| openvino | 2025.3.x | NPU torch.compile preview |
| spaCy | ≥3.7 | en\_core\_web\_sm compatibility |
| tree-sitter | ≥0.23 | language-pack compatibility |
| tree-sitter-language-pack | ≥1.6.3 | 305+ grammars |
| Postgres | 16 | pgvector built-in for pgvector/pgvector:pg16 |
| MongoDB | 7 | Latest stable |
| Redis | 7-alpine | Latest stable |
| MinIO | latest | S3-compatible |

### **Appendix H — Bridge Subscription Lifecycle — Detailed Specification**

This appendix specifies the complete lifecycle of document-bridge subscriptions for SharePoint, Google Drive, and Dropbox. It is the engineering reference for the developer building trimcp/bridges/.

#### **H.1 Lifecycle Overview**

A subscription progresses through six distinct states from creation to termination:

                ┌─────────────┐  
                │  REQUESTED  │  User clicks "Connect" in wizard  
                └──────┬──────┘  
                       │ OAuth completes successfully  
                       ↓  
                ┌─────────────┐  
                │  VALIDATING │  Provider sends validation handshake  
                └──────┬──────┘  
                       │ Receiver echoes token within deadline  
                       ↓  
                ┌─────────────┐  
                │   ACTIVE    │  Webhooks delivering events  
                └──┬───────┬──┘  
                   │       │  
        renewal ───┘       └─── failure / expiry  
        succeeds                       │  
                                       ↓  
                                ┌─────────────┐  
                                │  DEGRADED   │  Pull fallback active  
                                └──────┬──────┘  
                                       │ user disconnects, or repeated failure  
                                       ↓  
                                ┌─────────────┐  
                                │  TERMINATED │  Cleanup: tokens revoked, indexed content optionally removed  
                                └─────────────┘

State transitions are atomic and persisted to the bridge\_subscriptions table after each change. Every transition emits an audit log entry.

#### **H.2 Subscription Database Schema**

A new PostgreSQL table tracks bridge state. This sits in the same memory\_meta database as the existing TriMCP schema.

CREATE TABLE bridge\_subscriptions (  
    id              UUID PRIMARY KEY DEFAULT gen\_random\_uuid(),  
    provider        TEXT NOT NULL CHECK (provider IN ('sharepoint','gdrive','dropbox')),  
    user\_id         TEXT NOT NULL,           \-- TRIMCP\_USER\_ID who owns the bridge  
    resource\_id     TEXT NOT NULL,           \-- drive ID / folder ID / account ID  
    resource\_path   TEXT,                    \-- human-readable path for UI  
    state           TEXT NOT NULL DEFAULT 'requested'  
                    CHECK (state IN ('requested','validating','active','degraded','terminated')),  
    external\_sub\_id TEXT,                    \-- ID returned by provider (Graph subscription ID, etc.)  
    client\_state    TEXT,                    \-- opaque secret echoed back by provider for validation  
    cursor          TEXT,                    \-- delta token / page token / cursor for resync  
    expires\_at      TIMESTAMPTZ,             \-- next renewal deadline  
    last\_event\_at   TIMESTAMPTZ,             \-- last successful webhook delivery  
    last\_sync\_at    TIMESTAMPTZ,             \-- last successful delta processing  
    failure\_count   INT NOT NULL DEFAULT 0,  
    last\_error      TEXT,  
    created\_at      TIMESTAMPTZ NOT NULL DEFAULT now(),  
    updated\_at      TIMESTAMPTZ NOT NULL DEFAULT now()  
);

CREATE INDEX idx\_bridge\_subs\_provider\_state ON bridge\_subscriptions(provider, state);  
CREATE INDEX idx\_bridge\_subs\_expires ON bridge\_subscriptions(expires\_at)  
    WHERE state IN ('active','degraded');  
CREATE INDEX idx\_bridge\_subs\_user ON bridge\_subscriptions(user\_id);

CREATE TABLE bridge\_audit\_log (  
    id              BIGSERIAL PRIMARY KEY,  
    subscription\_id UUID NOT NULL REFERENCES bridge\_subscriptions(id) ON DELETE CASCADE,  
    event           TEXT NOT NULL,           \-- e.g. 'created', 'renewed', 'webhook\_received', 'failed'  
    detail          JSONB,  
    created\_at      TIMESTAMPTZ NOT NULL DEFAULT now()  
);

CREATE INDEX idx\_bridge\_audit\_sub ON bridge\_audit\_log(subscription\_id, created\_at DESC);

Token storage is **not** in this schema. OAuth tokens go in a dedicated encrypted table (bridge\_tokens) using PostgreSQL's pgcrypto extension, with the encryption key sourced from the deployment's secret manager (Azure Key Vault / AWS Secrets Manager / GCP Secret Manager). Tokens never appear in logs or audit entries.

#### **H.3 SharePoint Subscription Lifecycle**

**3.1 Creation flow**

User picks "Microsoft SharePoint" in installer wizard  
        ↓  
trimcp-launch opens browser → MSAL device code flow  
        ↓  
User signs in, consents to Sites.Read.All \+ Files.Read.All  
        ↓  
Token stored in bridge\_tokens (encrypted)  
        ↓  
User selects which sites/drives to subscribe to  
        ↓  
For each drive:  
    POST \[https://graph.microsoft.com/v1.0/subscriptions\](https://graph.microsoft.com/v1.0/subscriptions)  
    {  
      "changeType": "updated",  
      "notificationUrl": "\[https://trimcp.company.com/webhooks/sharepoint\](https://trimcp.company.com/webhooks/sharepoint)",  
      "resource": "/sites/{site-id}/drives/{drive-id}/root",  
      "expirationDateTime": "\<= now \+ 4230 minutes\>",   ← max \~3 days  
      "clientState": "\<32-byte random\>",  
      "lifecycleNotificationUrl": "\[https://trimcp.company.com/webhooks/sharepoint/lifecycle\](https://trimcp.company.com/webhooks/sharepoint/lifecycle)"  
    }  
        ↓  
Graph returns 201 Created with subscription\_id  
        ↓  
Insert row in bridge\_subscriptions with state='validating'

**3.2 Validation handshake**

Within \~10 seconds of creation, Graph sends a POST to the notificationUrl with ?validationToken=xyz. The receiver must respond 200 OK with xyz as a text/plain body. If validation fails or times out, Graph silently abandons the subscription — no notifications will arrive. The receiver therefore must:

1. Detect the validation request by presence of validationToken query param  
2. Echo it back in the response body verbatim  
3. **Not** parse the body or do any auth checks (validation requests are unsigned)  
4. Update subscription state to active after the first real event arrives (not after validation, since silent failure is possible)

**3.3 Notification delivery**

Each notification POST contains a JSON body:

{  
  "value": \[{  
    "subscriptionId": "\<uuid\>",  
    "clientState": "\<echoed back\>",  
    "changeType": "updated",  
    "resource": "sites/{site-id}/drives/{drive-id}/root",  
    "resourceData": { "id": "...", "@odata.type": "..." },  
    "tenantId": "\<tenant\>"  
  }\]  
}

Crucially, **the notification does not contain the changed file**. It only signals that *something* changed within the watched resource. The webhook handler must:

1. Verify clientState matches the stored secret (constant-time comparison)  
2. Look up the subscription by subscriptionId  
3. Enqueue a delta-processing job to the RQ worker  
4. Return 202 Accepted within 3 seconds (Graph timeout)

The RQ worker then calls the delta API:

GET \[https://graph.microsoft.com/v1.0/sites/\](https://graph.microsoft.com/v1.0/sites/){site-id}/drives/{drive-id}/root/delta?token={cursor}

This returns all changes since cursor. On the first call cursor is empty (full crawl). On subsequent calls cursor is whatever was returned as @odata.deltaLink last time. The cursor is updated atomically with each batch.

**3.4 Lifecycle notifications**

Graph also sends notifications about the subscription itself (separate from content changes) to lifecycleNotificationUrl. These signal subscription removal, missed events, or token expiry. Three types matter:

| Lifecycle event | Action |
| :---- | :---- |
| subscriptionRemoved | Subscription was deleted by Graph (rare, e.g. tenant change). Re-create on user demand. |
| missed | Graph dropped events due to overload. Force a full delta resync from current cursor. |
| reauthorizationRequired | Token approaching expiry. Refresh the OAuth token and call PATCH /subscriptions/{id} with new expiration. |

**3.5 Renewal**

Subscriptions cannot exceed \~3 days for drive resources (Graph hard limit, currently 4230 minutes). The renewal cron (§H.6) extends them before expiry:

PATCH \[https://graph.microsoft.com/v1.0/subscriptions/\](https://graph.microsoft.com/v1.0/subscriptions/){id}  
{  
  "expirationDateTime": "\<now \+ 4230 minutes\>"  
}

On 200 OK, update expires\_at in the DB. On 404 Not Found (subscription was deleted server-side), transition to degraded and trigger force-resync flow.

#### **H.4 Google Drive Subscription Lifecycle**

**4.1 Creation flow**

User picks "Google Workspace" in wizard  
        ↓  
OAuth flow with scopes:  
    \[https://www.googleapis.com/auth/drive.readonly\](https://www.googleapis.com/auth/drive.readonly)  
    \[https://www.googleapis.com/auth/drive.metadata.readonly\](https://www.googleapis.com/auth/drive.metadata.readonly)  
        ↓  
For org-wide watch:  
    POST \[https://www.googleapis.com/drive/v3/changes/watch\](https://www.googleapis.com/drive/v3/changes/watch)  
    {  
      "id": "\<our-uuid\>",                ← we generate  
      "type": "web\_hook",  
      "address": "\[https://trimcp.company.com/webhooks/gdrive\](https://trimcp.company.com/webhooks/gdrive)",  
      "token": "\<32-byte random\>",       ← stored as client\_state  
      "expiration": \<now \+ 7 days, in ms\>  
    }

For folder-specific watch (alternative):  
    POST \[https://www.googleapis.com/drive/v3/files/\](https://www.googleapis.com/drive/v3/files/){folderId}/watch  
    {same body}

Drive returns 200 OK with a resourceId and resourceUri. Both are stored.

**4.2 Validation handshake**

Drive's "validation" is implicit — the first webhook arrives with header X-Goog-Resource-State: sync immediately after creation. The receiver acknowledges with 200 OK and updates state to active. No body echo required.

**4.3 Notification delivery**

Subsequent webhooks contain headers but **no body**:

| Header | Meaning |
| :---- | :---- |
| X-Goog-Channel-Id | Our subscription ID |
| X-Goog-Channel-Token | Our client\_state — must validate |
| X-Goog-Resource-State | update / add / remove / trash / untrash |
| X-Goog-Resource-Id | Drive's internal resource ID |
| X-Goog-Message-Number | Monotonically increasing per subscription |

The webhook handler:

1. Looks up subscription by X-Goog-Channel-Id  
2. Constant-time-compares X-Goog-Channel-Token against client\_state  
3. Checks X-Goog-Message-Number is greater than the last one stored (gap detection — see §H.7)  
4. Enqueues delta processing job  
5. Returns 200 OK

The RQ worker then calls:

GET \[https://www.googleapis.com/drive/v3/changes?pageToken=\](https://www.googleapis.com/drive/v3/changes?pageToken=){cursor}  
    \&fields=nextPageToken,newStartPageToken,changes(fileId,removed,file(id,name,mimeType,modifiedTime,parents,md5Checksum,webViewLink))

Pagination follows nextPageToken. When exhausted, newStartPageToken becomes the new cursor.

**4.4 Renewal**

Drive subscriptions expire at most 7 days after creation. The renewal cron pre-expires the old subscription and creates a new one (Drive does not support PATCH-style renewal for watches):

1\. Create new subscription with same address, new token, fresh 7-day expiry  
2\. Update DB row to point at new external\_sub\_id and new client\_state  
3\. Stop the old subscription:  
   POST \[https://www.googleapis.com/drive/v3/channels/stop\](https://www.googleapis.com/drive/v3/channels/stop)  
   { "id": "\<old-uuid\>", "resourceId": "\<old-resourceId\>" }

The window between steps 1 and 3 may produce duplicate events — handled by idempotency (§H.8).

#### **H.5 Dropbox Subscription Lifecycle**

Dropbox is the simplest of the three.

**5.1 Creation flow**

Webhooks are configured **once per app** in the Dropbox App Console, not per-user. So the notificationUrl is set at deployment time, not per subscription.

When a user connects Dropbox:

OAuth flow with scopes: files.metadata.read, files.content.read  
        ↓  
Token stored in bridge\_tokens  
        ↓  
Initial /list\_folder call to establish cursor:  
    POST \[https://api.dropboxapi.com/2/files/list\_folder\](https://api.dropboxapi.com/2/files/list\_folder)  
    { "path": "", "recursive": true, "include\_deleted": true }  
        ↓  
Process initial listing, store cursor returned in response  
        ↓  
Subscription is implicit — we just track this user's account\_id and cursor

There is no per-user "subscription" object on Dropbox's side. The webhook simply tells us *which user* changed something; the cursor in our DB tells us *what* to fetch.

**5.2 Validation handshake**

Dropbox sends GET ?challenge=xyz once when the webhook URL is first registered (or re-registered) in the App Console. The receiver echoes xyz as the response body. This happens at deployment time, not per user.

**5.3 Notification delivery**

Webhook body:

{  
  "list\_folder": {  
    "accounts": \["dbid:abc...", "dbid:xyz..."\]  
  },  
  "delta": {  
    "users": \[12345, 67890\]  
  }  
}

Headers include X-Dropbox-Signature: \<hex hmac-sha256\>. The handler:

1. Computes HMAC-SHA256 of the raw body using the app secret  
2. hmac.compare\_digest against the header value  
3. For each account\_id in list\_folder.accounts, looks up the matching subscription  
4. Enqueues delta processing for each  
5. Returns 200 OK

The RQ worker then calls:

POST \[https://api.dropboxapi.com/2/files/list\_folder/continue\](https://api.dropboxapi.com/2/files/list\_folder/continue)  
{ "cursor": "\<stored\>" }

Returns entries (added/modified/removed) plus has\_more and a new cursor. Loop until has\_more=false.

**5.4 Renewal**

Dropbox cursors **never expire** as long as they are used at least once every 90 days. The renewal cron does a no-op list\_folder/continue call every 60 days to keep cursors warm. If a cursor returns reset (meaning Dropbox cannot honour it any more), force-resync from a fresh list\_folder call.

#### **H.6 Renewal Cron — Detailed Behaviour**

A single cron job, scheduled hourly, handles renewal for all three providers. It uses one query:

SELECT \* FROM bridge\_subscriptions  
WHERE state IN ('active','degraded')  
  AND expires\_at IS NOT NULL  
  AND expires\_at \< now() \+ INTERVAL '24 hours'  
ORDER BY expires\_at ASC  
LIMIT 100;

For each row, it dispatches to the provider-specific renewer. The 24-hour buffer ensures we have multiple retry windows before actual expiry.

**Retry policy:**

| Failure type | Retries | Backoff | Action on final failure |
| :---- | :---- | :---- | :---- |
| Network error / 5xx | 5 | Exponential 1s → 60s | Mark degraded, alert ops |
| 401 Unauthorized | 1 (after token refresh) | None | Mark degraded, prompt user to reconnect |
| 404 Subscription not found | 0 | None | Force re-create (Graph silently dropped it) |
| 429 Rate limited | Unlimited | Honour Retry-After | Continue retrying |

After 3 consecutive failure cycles the subscription is moved to degraded and the pull fallback (§10.8) takes over until the next successful renewal or user intervention.

#### **H.7 Failure Modes and Recovery**

| Failure | Symptom | Recovery |
| :---- | :---- | :---- |
| **Webhook receiver down** | No events arriving despite changes | Cron monitor alerts; pull fallback runs every 15 min in degraded state; on receiver recovery, force-resync from cursor |
| **Webhook delivered but worker queue backed up** | RQ queue depth growing; last\_event\_at recent but last\_sync\_at stale | Add worker capacity; events are durable in Redis until processed |
| **Cursor invalidated** (Drive invalidatedToken, Dropbox reset, Graph tokenExpired) | Provider-specific error code on delta call | Discard cursor, perform full resync from root, replace cursor with fresh value |
| **Missed events** (Graph lifecycleEvent: missed, Drive gap in X-Goog-Message-Number) | Lifecycle notification or sequence number gap | Force-resync from current cursor — delta API guarantees no missed changes since last cursor |
| **Token expired / revoked** | 401 on any API call | Attempt refresh; if refresh token also expired, mark degraded and emit user-facing notification "Reconnect Dropbox" |
| **Provider rate-limited the app** | 429 on delta calls | Exponential backoff with Retry-After header; do not delete subscription |
| **Deletion in provider** (file deleted) | Delta returns removed: true or trashed: true | Find existing memories with matching metadata.file\_id, mark deleted in MongoDB (soft delete with deleted\_at); remove from PG vector index |
| **Restoration** (file un-trashed) | Delta returns untrashed | Re-index file from current state; old soft-deleted memories remain for audit |
| **File renamed** | Delta returns updated name and parents | Update metadata of existing memories without re-indexing content (content hash unchanged) |
| **Webhook receiver compromised** | Suspect events arriving | Rotate clientState for all subscriptions; force-resync on next healthy cycle |

#### **H.8 Idempotency and Deduplication**

Three deduplication layers prevent re-indexing the same file repeatedly:

**Layer 1 — Content hash check.** Before processing any file, hash its content (MD5 from provider metadata where available, otherwise SHA-256 of downloaded body). Compare against redis: hash:{provider}:{file\_id}. Skip if unchanged.

**Layer 2 — Webhook deduplication.** Each webhook delivery includes a unique ID (Graph: subscriptionId+changeType+resource, Drive: X-Goog-Message-Number, Dropbox: account\_id+timestamp). The webhook handler stores recent IDs in Redis with 5-minute TTL and rejects duplicates. This handles provider retry storms.

**Layer 3 — Delta cursor advancement.** Cursors are only advanced after the entire batch is successfully processed. If processing fails halfway through a batch, the next run replays from the same cursor — re-processing files but the content hash check (layer 1\) skips already-indexed ones.

Combining all three: a file modified once results in exactly one index operation, even if its webhook is delivered three times across two retries.

#### **H.9 Rate Limit Handling**

Each provider exposes different rate limits:

| Provider | Per-app limit | Per-user limit | Headers |
| :---- | :---- | :---- | :---- |
| SharePoint / Graph | 130 req/min/app | varies by tenant | Retry-After, RateLimit-Limit, RateLimit-Remaining, RateLimit-Reset |
| Google Drive | 1000 QPS/project | 10 QPS/user | X-RateLimit-Remaining, exponential backoff per status 403 userRateLimitExceeded |
| Dropbox | 600 req/min/user | 600 req/min/user | Retry-After on 429 |

The bridge uses a token-bucket rate limiter per provider, sized below the limit:

rate\_limiters \= {  
    "sharepoint": TokenBucket(rate=2, burst=20),    \# 120/min sustained  
    "gdrive":     TokenBucket(rate=8, burst=50),    \# \~480/min sustained  
    "dropbox":    TokenBucket(rate=8, burst=30),    \# \~480/min sustained  
}

Rate limit hits are logged but not alerted on; backoff is automatic. Persistent rate limiting (more than 1 hour of continuous backoff) does trigger an alert — it suggests config error or unusual load.

#### **H.10 Monitoring and Alerting**

Metrics published per subscription, scraped by Prometheus or equivalent:

| Metric | Type | Labels | Alert threshold |
| :---- | :---- | :---- | :---- |
| trimcp\_bridge\_subscriptions\_active | gauge | provider | — |
| trimcp\_bridge\_subscriptions\_degraded | gauge | provider | \> 5% of active |
| trimcp\_bridge\_webhooks\_received\_total | counter | provider, result | — |
| trimcp\_bridge\_webhook\_lag\_seconds | histogram | provider | p99 \> 30s |
| trimcp\_bridge\_files\_indexed\_total | counter | provider | — |
| trimcp\_bridge\_renewal\_failures\_total | counter | provider | \> 0 in 1h window |
| trimcp\_bridge\_rate\_limit\_hits\_total | counter | provider | \> 100/h |

Three pre-configured alerts ship in Grafana / Azure Monitor / CloudWatch dashboards:

1. **Bridge degraded** — any subscription in degraded for \> 6 hours  
2. **No events received** — last\_event\_at for an active subscription \> 24 hours stale (but only if expected — quiet weekends are not anomalies for some bridges)  
3. **Renewal failure** — any renewal\_failures increment

#### **H.11 Cleanup and Disconnection**

When a user calls disconnect\_bridge:

1\. Update subscription state to 'terminated' (atomic)  
2\. Call provider's unsubscribe API:  
   \- SharePoint: DELETE /v1.0/subscriptions/{external\_sub\_id}  
   \- Drive:     POST /drive/v3/channels/stop  
   \- Dropbox:   no-op (no per-user subscription)  
3\. Revoke the OAuth refresh token via provider's revocation endpoint  
4\. Delete the bridge\_tokens row  
5\. If user passed \`delete\_indexed\_content=true\`:  
       Soft-delete all memories with metadata.source \= provider AND user\_id \= caller  
6\. Audit log entry

Subscription rows are retained in terminated state for 90 days for audit, then hard-deleted by a separate cleanup cron. This allows reconstructing what was connected and when, even after disconnection.

### **Appendix I — Cloud IaC Module Specifications**

This appendix specifies the structure, inputs, and outputs of the infrastructure-as-code modules for Cloud mode deployment. It is the engineering reference for the developer building trimcp-infra/.

#### **I.1 Repository Structure**

trimcp-infra/  
├── README.md  
├── azure/  
│   ├── main.bicep                    \# Top-level orchestration  
│   ├── parameters.example.json       \# Customer-supplied values  
│   ├── modules/  
│   │   ├── network.bicep             \# VNet, subnets, NSGs, Private DNS zones  
│   │   ├── postgres.bicep            \# Flexible Server \+ pgvector  
│   │   ├── cosmos.bicep              \# Cosmos DB for MongoDB API  
│   │   ├── redis.bicep               \# Azure Cache for Redis Premium  
│   │   ├── storage.bicep             \# Storage Account \+ Blob container  
│   │   ├── keyvault.bicep            \# Secrets, encryption keys  
│   │   ├── containerapp.bicep        \# Worker \+ webhook receiver  
│   │   ├── frontdoor.bicep           \# Public webhook endpoint with WAF  
│   │   └── monitoring.bicep          \# Log Analytics, Application Insights  
│   └── scripts/  
│       ├── deploy.sh  
│       └── destroy.sh  
├── aws/  
│   ├── main.tf                       \# Top-level orchestration  
│   ├── variables.tf  
│   ├── outputs.tf  
│   ├── terraform.tfvars.example  
│   ├── modules/  
│   │   ├── network/                  \# VPC, subnets, security groups  
│   │   ├── rds-postgres/             \# RDS for PostgreSQL with pgvector  
│   │   ├── documentdb/               \# DocumentDB cluster (MongoDB-compatible)  
│   │   ├── elasticache/              \# ElastiCache Redis with auth  
│   │   ├── s3/                       \# S3 bucket with versioning and encryption  
│   │   ├── secrets/                  \# Secrets Manager  
│   │   ├── fargate-worker/           \# ECS Fargate service  
│   │   ├── api-gateway/              \# API Gateway \+ Lambda for webhooks  
│   │   └── monitoring/               \# CloudWatch dashboards and alarms  
│   └── scripts/  
│       ├── deploy.sh  
│       └── destroy.sh  
├── gcp/  
│   ├── main.tf                       \# Top-level orchestration  
│   ├── variables.tf  
│   ├── outputs.tf  
│   ├── terraform.tfvars.example  
│   ├── modules/  
│   │   ├── network/                  \# VPC, subnets, firewall rules  
│   │   ├── cloudsql/                 \# Cloud SQL for PostgreSQL  
│   │   ├── memorystore/              \# Memorystore Redis  
│   │   ├── gcs/                      \# Cloud Storage bucket  
│   │   ├── secret-manager/           \# Secret Manager  
│   │   ├── cloudrun-worker/          \# Cloud Run service for worker  
│   │   ├── cloudrun-webhooks/        \# Cloud Run service for webhook receiver  
│   │   ├── load-balancer/            \# External HTTPS load balancer  
│   │   └── monitoring/               \# Cloud Monitoring dashboards  
│   └── scripts/  
│       ├── deploy.sh  
│       └── destroy.sh  
└── shared/  
    ├── client-env-template.j2        \# Jinja template for .env distribution  
    └── post-deploy-checklist.md      \# Manual steps after IaC apply

The shared/ directory contains cross-cloud artifacts. The client-env-template.j2 is rendered after deployment with the cloud-specific output values, producing a .env that the installer consumes.

#### **I.2 Common Variables Across Clouds**

These variables map to inputs on every cloud's deployment to keep the customer experience consistent. The Bicep parameters.json and Terraform tfvars.example both expose the same names.

| Variable | Type | Description | Example |
| :---- | :---- | :---- | :---- |
| deployment\_name | string | Globally unique short identifier | acme-prod |
| region | string | Cloud region (cloud-specific format) | Azure: westeurope / AWS: eu-west-1 / GCP: europe-west1 |
| environment | string | dev / staging / prod — drives sizing | prod |
| tenant\_id | string | Microsoft Entra tenant ID for SSO | acme.onmicrosoft.com |
| allowed\_admin\_ips | list(string) | CIDRs allowed to admin DBs (e.g. office IPs, VPN gateway) | \["203.0.113.0/24"\] |
| vpn\_subnet\_cidr | string | Subnet that VPN clients sit in | 10.100.0.0/24 |
| webhook\_dns\_name | string | Public hostname for webhook receiver | trimcp.acme.com |
| bridges\_enabled | list(string) | Which bridges to provision auth for | \["sharepoint","gdrive"\] |
| db\_size\_postgres | string | Sizing tier per environment | dev: small / prod: medium |
| db\_size\_mongo | string | Sizing tier | dev: small / prod: medium |
| db\_size\_redis | string | Sizing tier | dev: 1GB / prod: 5GB |
| enable\_geo\_redundant\_backup | bool | Cross-region backups on/off | true (prod) |
| tags | map(string) | Resource tags for cost allocation | {owner: "platform", costcenter: "1234"} |

Sizing tiers expand into provider-specific SKUs internally — customers don't need to know AWS instance types vs Azure SKU names.

#### **I.3 Azure Bicep Modules**

**Top-level orchestration (main.bicep):**

targetScope \= 'subscription'

param deploymentName string  
param region string \= 'westeurope'  
param environment string \= 'prod'  
param tenantId string  
param allowedAdminIps array  
param webhookDnsName string  
param tags object \= {}

var rgName \= 'rg-trimcp-${deploymentName}'

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' \= {  
  name: rgName  
  location: region  
  tags: tags  
}

module network 'modules/network.bicep' \= {  
  scope: rg  
  name: 'network'  
  params: {  
    deploymentName: deploymentName  
    region: region  
    tags: tags  
  }  
}

module keyvault 'modules/keyvault.bicep' \= {  
  scope: rg  
  name: 'keyvault'  
  params: {  
    deploymentName: deploymentName  
    region: region  
    tenantId: tenantId  
    allowedAdminIps: allowedAdminIps  
    tags: tags  
  }  
}

module postgres 'modules/postgres.bicep' \= {  
  scope: rg  
  name: 'postgres'  
  params: {  
    deploymentName: deploymentName  
    region: region  
    subnetId: network.outputs.dbSubnetId  
    privateDnsZoneId: network.outputs.postgresDnsZoneId  
    keyVaultId: keyvault.outputs.id  
    environment: environment  
    tags: tags  
  }  
}

// ... cosmos, redis, storage, containerapp, frontdoor, monitoring follow same pattern

output postgresHost string \= postgres.outputs.fqdn  
output cosmosConnectionString string \= cosmos.outputs.connectionStringSecretUri  
output redisConnectionString string \= redis.outputs.connectionStringSecretUri  
output blobEndpoint string \= storage.outputs.endpoint  
output webhookEndpoint string \= frontdoor.outputs.endpoint

**Postgres module (modules/postgres.bicep):**

| Resource | Notes |
| :---- | :---- |
| Microsoft.DBforPostgreSQL/flexibleServers | PG 16, 4 vCPU GeneralPurpose for prod, B1ms for dev |
| firewallRules | Block all by default; access via private endpoint only |
| configurations | azure.extensions \= vector,pg\_trgm,pgcrypto |
| databases | memory\_meta |
| administrators | Entra ID admin group |
| Private endpoint | Into dbSubnet |
| Private DNS zone link | privatelink.postgres.database.azure.com |

**Container App module (modules/containerapp.bicep):**

| Resource | Notes |
| :---- | :---- |
| Microsoft.App/managedEnvironments | Shared environment for worker \+ webhooks |
| Microsoft.App/containerApps (worker) | Pulls trimcp-worker:latest from ACR; scale 1–10 on Redis queue depth |
| Microsoft.App/containerApps (webhook-receiver) | Public ingress; scale 1–20 on HTTP concurrency |
| Managed identity | Used to fetch secrets from Key Vault |

**Front Door module (modules/frontdoor.bicep):**

Routes https://{webhookDnsName}/webhooks/\* to the webhook-receiver Container App. Includes:

* WAF policy with managed rules (OWASP top 10\)  
* Custom rule: rate limit 100 req/min per IP  
* Custom domain with managed TLS certificate  
* Origin health probe on /health

**Outputs:** Connection strings stored as Key Vault references (not returned in plaintext). The post-deploy script (scripts/deploy.sh) extracts them via Key Vault CLI for the client .env template rendering.

#### **I.4 AWS Terraform Modules**

**Top-level (main.tf):**

terraform {  
  required\_version \= "\>= 1.6"  
  required\_providers {  
    aws \= { source \= "hashicorp/aws", version \= "\~\> 5.0" }  
  }  
  backend "s3" {  
    \# Configured per customer in backend.tfvars  
  }  
}

provider "aws" {  
  region \= var.region  
  default\_tags { tags \= var.tags }  
}

module "network" {  
  source         \= "./modules/network"  
  deployment\_name \= var.deployment\_name  
  vpc\_cidr       \= "10.10.0.0/16"  
}

module "secrets" {  
  source         \= "./modules/secrets"  
  deployment\_name \= var.deployment\_name  
}

module "rds" {  
  source              \= "./modules/rds-postgres"  
  deployment\_name      \= var.deployment\_name  
  vpc\_id              \= module.network.vpc\_id  
  db\_subnet\_ids       \= module.network.db\_subnet\_ids  
  allowed\_security\_groups \= \[module.network.app\_sg\_id\]  
  size                \= var.db\_size\_postgres  
  engine\_version      \= "16.4"  
  enable\_pgvector     \= true  
  backup\_retention    \= var.environment \== "prod" ? 35 : 7  
  multi\_az            \= var.environment \== "prod"  
  storage\_kms\_key\_id  \= module.secrets.kms\_key\_id  
}

module "documentdb" { /\* ... \*/ }  
module "elasticache" { /\* ... \*/ }  
module "s3" { /\* ... \*/ }  
module "fargate\_worker" { /\* ... \*/ }  
module "api\_gateway" { /\* webhook receiver \*/ }  
module "monitoring" { /\* ... \*/ }

\# All sensitive values land in AWS Secrets Manager, never as plain outputs

**RDS Postgres module (modules/rds-postgres/):**

| Resource | Notes |
| :---- | :---- |
| aws\_db\_instance | Engine postgres 16.x, encryption at rest with customer KMS key |
| aws\_db\_parameter\_group | Custom params: shared\_preload\_libraries \= pg\_stat\_statements,pgvector |
| aws\_db\_subnet\_group | Multi-AZ subnets in private subnets only |
| aws\_security\_group | Ingress 5432 from app SG only — no public access |
| null\_resource (post-create) | Runs CREATE EXTENSION IF NOT EXISTS vector; via local-exec with bastion or via Lambda |
| aws\_secretsmanager\_secret | Master password, rotated every 30 days via Secrets Manager rotation |

**Fargate worker module (modules/fargate-worker/):**

| Resource | Notes |
| :---- | :---- |
| aws\_ecs\_cluster | Capacity provider Fargate \+ Fargate Spot for cost |
| aws\_ecs\_task\_definition | Pulls from ECR; CPU 1024 / Mem 4096 baseline |
| aws\_ecs\_service | Desired count 1; auto-scale on CloudWatch alarm "Redis queue depth \> 100" |
| aws\_iam\_role (task) | Read-only IAM access to Secrets Manager \+ S3 bucket prefix |

**API Gateway \+ Lambda for webhooks:**

API Gateway HTTP API (cheaper than REST API) routes /webhooks/{provider} to a Lambda function that runs the same FastAPI handler in Mangum. Cold-start is acceptable for webhooks (200ms first call, none afterward). Reserved concurrency caps at 100 to prevent runaway charges.

#### **I.5 GCP Terraform Modules**

**Cloud SQL Postgres module:**

| Resource | Notes |
| :---- | :---- |
| google\_sql\_database\_instance | PG 16, private IP only via VPC peering |
| google\_sql\_database | memory\_meta |
| google\_sql\_user | Entra-federated user via Workload Identity Federation |
| Database flag | cloudsql.enable\_pgvector \= on |
| Backups | Point-in-time recovery enabled, 7-day retention |

**Cloud Run modules** (worker and webhooks):

Cloud Run is ideal for the webhook receiver because it scales to zero between webhook bursts. The worker uses Cloud Run Jobs (long-running) rather than services. Both authenticate to other GCP services via service account with minimal IAM roles.

**Network module:**

Creates a VPC with regional subnets, Private Service Connect endpoints for Cloud SQL and Memorystore, and a Cloud NAT gateway for egress (so the worker can reach external APIs like SharePoint without giving it a public IP).

**Load balancer module:**

Global external HTTPS LB with Google-managed certificate for webhook\_dns\_name. Cloud Armor policy provides WAF. Traffic routes to a serverless NEG pointing at the webhooks Cloud Run service.

#### **I.6 Network Architecture**

All three clouds follow the same logical topology:

                    Internet  
                       │  
                       ↓  
        ┌──────────────────────────────────┐  
        │  Public ingress (TLS termination)│  
        │  \- Front Door / API GW / LB      │  
        │  \- WAF \+ rate limit              │  
        └──────────────┬───────────────────┘  
                       ↓  
        ╔══════════════════════════════════╗  
        ║   Private VNet / VPC             ║  
        ║                                  ║  
        ║   ┌──────────────────────┐       ║  
        ║   │  App subnet          │       ║  
        ║   │  \- Worker            │       ║  
        ║   │  \- Webhook receiver  │       ║  
        ║   └─────────┬────────────┘       ║  
        ║             │                    ║  
        ║   ┌─────────↓────────────┐       ║  
        ║   │  DB subnet           │       ║  
        ║   │  \- PostgreSQL        │       ║  
        ║   │  \- MongoDB           │       ║  
        ║   │  \- Redis             │       ║  
        ║   └──────────────────────┘       ║  
        ║                                  ║  
        ║   ┌──────────────────────┐       ║  
        ║   │  VPN subnet          │ ← Office VPN clients   ║  
        ║   └──────────────────────┘       ║  
        ║                                  ║  
        ║   Egress NAT → external APIs     ║  
        ╚══════════════════════════════════╝  
                       │  
                       ↓  
            S3 / Blob / GCS (separate, accessed via private endpoint)

**Key principles:**

1. Databases never have public IPs. Period.  
2. Webhook receiver is the only inbound public endpoint.  
3. Office clients access via VPN or ExpressRoute/Direct Connect/Cloud Interconnect into the VPN subnet.  
4. Egress for the worker (calling Microsoft Graph, Drive API, Dropbox API) goes through NAT — outbound traffic only, no inbound exposure.

#### **I.7 Secrets Management**

| Secret | Storage | Access pattern |
| :---- | :---- | :---- |
| Postgres master password | Cloud secret manager (Key Vault / Secrets Manager / Secret Manager) | Worker pulls at startup via managed identity |
| MongoDB password | Cloud secret manager | Worker pulls at startup |
| Redis auth token | Cloud secret manager | Worker pulls at startup |
| OAuth client secrets (Graph/Drive/Dropbox) | Cloud secret manager | Worker pulls when initiating OAuth flow |
| Per-user OAuth refresh tokens | bridge\_tokens PG table, encrypted with pgcrypto | Encryption key in cloud secret manager, fetched once at process start |
| Webhook validation clientState | bridge\_subscriptions.client\_state column | Per-subscription, generated on creation |
| TRIMCP\_USER\_ID | Client-side .env only | Never sent to cloud secret manager — derived from Azure AD UPN |

**Rotation policy:**

* DB master passwords: automatic rotation every 30 days via cloud-native rotation  
* OAuth client secrets: manual rotation, documented in operational runbook (typically annual)  
* pgcrypto encryption key: rotated on a 12-month cadence, with a re-encrypt migration script

#### **I.8 Deployment Runbook**

**First-time deployment:**

\# 1\. Customer provides parameters  
cp parameters.example.json parameters.json  
$EDITOR parameters.json   \# fill in tenant, IPs, dns name, etc.

\# 2\. Authenticate to cloud  
az login                                    \# Azure  
aws sso login \--profile trimcp-prod         \# AWS  
gcloud auth application-default login       \# GCP

\# 3\. Initialize state (first run only)  
cd azure && az deployment sub create ...    \# Azure  
cd aws   && terraform init                  \# AWS  
cd gcp   && terraform init                  \# GCP

\# 4\. Plan and review  
terraform plan \-var-file=terraform.tfvars   \# AWS / GCP  
az deployment sub what-if ...               \# Azure

\# 5\. Apply  
terraform apply \-var-file=terraform.tfvars  
\# Typical duration: 25-40 minutes (Postgres provisioning is the long pole)

\# 6\. Render client .env from outputs  
./scripts/render-env.sh \> client.env

\# 7\. Run post-deploy validation  
./scripts/validate-deployment.sh  
\# Checks: DB connectivity, pgvector extension, webhook URL responds 200, ...

\# 8\. Distribute client.env via the build pipeline  
\# (Becomes the bundled .env in the next installer build)

**Update / drift detection:**

A CI workflow runs terraform plan (or az deployment sub what-if) weekly against main. Any drift produces a Slack notification to the platform team.

**Disaster recovery:**

Each module enables point-in-time recovery for stateful resources:

| Resource | RPO | RTO |
| :---- | :---- | :---- |
| Postgres | 5 min | 30 min (PITR restore) |
| MongoDB / Cosmos / DocumentDB | 5 min | 60 min |
| Redis | 0 min (cache, recoverable from PG) | 5 min (re-provision) |
| Object storage | 0 min (versioning \+ cross-region replication for prod) | 0 min |

The runbook for each scenario is in shared/runbooks/.

#### **I.9 Day-2 Operations**

| Operation | Frequency | Tool |
| :---- | :---- | :---- |
| Cost review | Monthly | Cloud-native cost analysis (Azure Cost Management / AWS Cost Explorer / GCP Billing) |
| Patching | Automatic for managed services; manual for container images quarterly | CI rebuild \+ redeploy worker image |
| Capacity scaling | On-demand | terraform apply with new sizing tier |
| Audit log review | Quarterly | Cloud-native audit logs (Activity Log / CloudTrail / Cloud Audit Logs) |
| Penetration test | Annual | Third-party engagement |
| Backup restore drill | Quarterly | Restore to a separate dr environment, validate integrity |
| Certificate renewal | Automatic for managed certs (90-day renewal); manual review annually | — |

### **Appendix J — Document Format Extraction — Detailed Specification**

This appendix specifies how each document format is parsed into the text and structure that gets indexed by store\_memory. It is the engineering reference for the developer building trimcp/extractors/.

#### **J.1 Goals and Scope**

The extractors are responsible for converting raw file bytes into:

1. **Searchable text** — preserving meaningful order (top-to-bottom, slide-by-slide, sheet-by-sheet) so semantic chunking produces coherent results.  
2. **Structural anchors** — slide numbers, sheet names, heading paths, page numbers — stored as structure\_path metadata so search results can cite "Sheet1\!B12" or "Slide 7".  
3. **Provenance metadata** — author, last-modified, comments, tracked changes, where applicable.

What's explicitly **out of scope**:

* Formatting fidelity (fonts, colors, margins) — irrelevant for semantic search.  
* Round-tripping (extract → modify → re-save). TriMCP is read-only for indexed documents.  
* Macro/VBA code execution. Extractors must never execute embedded code.  
* Math equation rendering. LaTeX-style equations are extracted as their source text where possible (Word's OMath), otherwise skipped with a warning.

The system is designed so that **partial extraction always beats failed extraction**: if an extractor can read 80% of a document but chokes on one embedded chart, it returns the 80% with a warning rather than failing the whole file.

#### **J.2 Common Extraction Result Schema**

All extractors return the same dataclass:

@dataclass  
class ExtractionResult:  
    method: str                     \# 'python-docx', 'libreoffice', 'tesseract-ocr', etc.  
    text: str                       \# full extracted text  
    sections: list\[Section\]         \# structured breakdown for chunking  
    metadata: dict\[str, Any\]        \# author, dates, language, etc.  
    warnings: list\[str\]             \# non-fatal issues (skipped image, unreadable table)  
    skipped: bool \= False           \# True if file rejected entirely  
    skip\_reason: str | None \= None  \# e.g. "encrypted", "corrupt", "unsupported\_format"

@dataclass  
class Section:  
    text: str                       \# the actual content  
    structure\_path: str             \# human-readable anchor: "Slide 7" / "Sheet1\!A1:F50" / "Heading 2 \> Subheading"  
    section\_type: str               \# 'heading','body','table','slide','sheet','note','comment','footer','metadata'  
    order: int                      \# original document order

Chunking respects section boundaries — a chunk never spans across two slides or two spreadsheet sheets, even if it would fit by token count.

#### **J.3 .docx (Word, Modern)**

**Library choice:** python-docx for the high-level API, supplemented by **direct XML parsing via lxml** for features not exposed by python-docx (comments, tracked changes, footnotes, embedded objects).

**Why both:** python-docx is the de-facto standard but doesn't expose comments or tracked changes well. Since .docx is a ZIP of XML files, we can mount it and read word/comments.xml, word/footnotes.xml, etc. directly when needed.

**What we extract:**

| Element | Method | Output |
| :---- | :---- | :---- |
| Paragraphs and runs | doc.paragraphs | Body text, ordered |
| Heading levels (H1–H9) | Style names (Heading 1, etc.) | Maps to structure\_path heading hierarchy |
| Tables | doc.tables → row-by-row | Markdown-style table for chunking |
| Bullet / numbered lists | Paragraph numbering properties | Plain text with bullet markers |
| Hyperlinks | XML walk for w:hyperlink | URL captured as \[link text\](url) |
| Headers and footers | section.header.paragraphs | Tagged section\_type='header'/'footer' |
| Footnotes / endnotes | word/footnotes.xml, word/endnotes.xml | Inserted as numbered references |
| Comments | word/comments.xml | Tagged section\_type='comment', includes author \+ range |
| Tracked changes (insertions / deletions) | w:ins / w:del elements | Default behaviour: render the **accepted** state. Configurable: also extract change history. |
| Speaker notes / hidden text | w:vanish runs | Skipped by default (typically formatting artifact) |
| Embedded images | word/media/\* | Extracted to MinIO/blob via store\_media, reference inserted in text. OCR triggered if image looks text-heavy (J.19). |
| Embedded Excel sheets | OLE objects in word/embeddings/ | Recursively extracted via xlsx pipeline (J.5) |
| OMath equations | m:oMath elements | Extract the math text content; mark with \[equation: ...\] |
| Document properties | docProps/core.xml, app.xml | author, created, modified, last\_modified\_by, word\_count |

**Code sketch:**

from docx import Document  
from docx.oxml.ns import qn  
import zipfile, lxml.etree as ET

async def extract\_docx(blob: bytes) \-\> ExtractionResult:  
    sections \= \[\]  
    warnings \= \[\]

    if is\_password\_protected(blob):  
        return ExtractionResult(method='python-docx', skipped=True,  
                                skip\_reason='encrypted', text='', sections=\[\], metadata={}, warnings=\[\])

    try:  
        doc \= Document(io.BytesIO(blob))  
    except Exception as e:  
        \# Fall back to LibreOffice conversion if python-docx fails  
        return await \_libreoffice\_fallback(blob, '.docx', warnings=\[f'python-docx failed: {e}'\])

    heading\_stack \= \[\]  
    order \= 0

    for para in doc.paragraphs:  
        if not para.text.strip():  
            continue

        style \= para.style.name  
        if style.startswith('Heading'):  
            level \= int(style.replace('Heading ', '')) if style \!= 'Heading' else 1  
            heading\_stack \= heading\_stack\[:level-1\] \+ \[para.text\]  
            sections.append(Section(text=para.text,  
                                    structure\_path=' \> '.join(heading\_stack),  
                                    section\_type='heading', order=order))  
        else:  
            sections.append(Section(text=para.text,  
                                    structure\_path=' \> '.join(heading\_stack) or 'Body',  
                                    section\_type='body', order=order))  
        order \+= 1

    \# Tables  
    for tbl in doc.tables:  
        rows \= \['| ' \+ ' | '.join(cell.text for cell in row.cells) \+ ' |'  
                for row in tbl.rows\]  
        sections.append(Section(text='\\n'.join(rows),  
                                structure\_path=' \> '.join(heading\_stack) \+ ' \> Table',  
                                section\_type='table', order=order))  
        order \+= 1

    \# Comments — direct XML walk  
    with zipfile.ZipFile(io.BytesIO(blob)) as z:  
        if 'word/comments.xml' in z.namelist():  
            comments\_xml \= ET.parse(z.open('word/comments.xml'))  
            for comment in comments\_xml.iter(qn('w:comment')):  
                author \= comment.get(qn('w:author'))  
                text \= ''.join(t.text or '' for t in comment.iter(qn('w:t')))  
                sections.append(Section(text=f"\[{author}\]: {text}",  
                                        structure\_path='Comment', section\_type='comment', order=order))  
                order \+= 1

    \# Headers / footers  
    for section in doc.sections:  
        for hdr\_para in section.header.paragraphs:  
            if hdr\_para.text.strip():  
                sections.append(Section(text=hdr\_para.text,  
                                        structure\_path='Header', section\_type='header', order=order))  
                order \+= 1  
        \# ... footer similarly

    \# OCR fallback if text is suspiciously empty  
    full\_text \= '\\n\\n'.join(s.text for s in sections)  
    if len(full\_text.strip()) \< 50:  
        ocr\_result \= await ocr\_fallback(blob, '.docx')  
        if ocr\_result.text:  
            sections.append(Section(text=ocr\_result.text,  
                                    structure\_path='OCR', section\_type='body', order=order))  
            warnings.append('Text extraction yielded \< 50 chars; OCR fallback used')

    metadata \= \_extract\_core\_props(doc)  
    return ExtractionResult(method='python-docx', text=full\_text,  
                            sections=sections, metadata=metadata, warnings=warnings)

**Edge cases:**

* **Macro-enabled docs (.docm)**: Treated identically to .docx. Macros never executed; macro source code in word/vbaProject.bin is binary and is not extracted (we don't index code-as-data here — the index\_code\_file tool is for source files).  
* **Linked images**: Word can reference external images via URL. The reference is preserved as text; no fetch.  
* **Form fields**: Content controls (w:sdt) are treated as their resolved text value.  
* **Math-heavy documents** (e.g. mathematics theses): OMath blocks become text but lose visual rendering. Acceptable — semantic search on equations was never realistic.  
* **Mail merge templates**: MERGEFIELD instructions are rendered as their literal placeholder text («FirstName»).

**Limits:** Tested cleanly against documents up to 200 MB. Above that, streaming via xml.sax instead of loading the full XML into memory.

#### **J.4 .doc (Word, Legacy)**

The legacy .doc binary format pre-dates Office 2007\. Native Python parsers exist (olefile, compoundfiles) but coverage is incomplete. The pragmatic, reliable approach:

**Strategy: convert to .docx first via LibreOffice headless, then run the J.3 pipeline.**

async def extract\_doc(blob: bytes) \-\> ExtractionResult:  
    converted \= await libreoffice\_convert(blob, source\_ext='.doc', target\_ext='.docx')  
    if not converted:  
        return ExtractionResult(method='libreoffice', skipped=True,  
                                skip\_reason='conversion\_failed', ...)  
    result \= await extract\_docx(converted)  
    result.method \= 'libreoffice→python-docx'  
    result.warnings.insert(0, 'Converted from legacy .doc via LibreOffice')  
    return result

LibreOffice runs as a long-lived headless service in the worker container (see §J.22). Conversion takes 1–5 seconds typically, \~30 seconds for very large or complex documents. The conversion is lossy for some elements (legacy WordArt, certain proprietary objects) but preserves all text content reliably.

**Why not antiword, wvText, or pure Python?** Tried and rejected: antiword is unmaintained (last release 2008), wvText is Linux-only and brittle, olefile-based extractors miss tables and lists. LibreOffice covers more edge cases than any of these.

#### **J.5 .xlsx (Excel, Modern)**

**Library choice:** openpyxl in **read-only mode** with data\_only=True.

The data\_only=True flag is critical: it returns the cached **computed values** of formulas (e.g. 42 for \=SUM(A1:A10)) rather than the formula text itself. For semantic search this is exactly what we want — agents asking "what was Q3 revenue" should match cells containing the numerical answer, not formula syntax.

import openpyxl

async def extract\_xlsx(blob: bytes) \-\> ExtractionResult:  
    if is\_password\_protected(blob):  
        return ExtractionResult(method='openpyxl', skipped=True, skip\_reason='encrypted', ...)

    wb \= openpyxl.load\_workbook(io.BytesIO(blob), read\_only=True, data\_only=True)  
    sections \= \[\]  
    warnings \= \[\]  
    order \= 0

    for sheet\_name in wb.sheetnames:  
        ws \= wb\[sheet\_name\]  
        if ws.sheet\_state \== 'hidden':  
            warnings.append(f'Skipped hidden sheet: {sheet\_name}')  
            continue

        \# Detect dense vs sparse layout  
        rows \= list(ws.iter\_rows(values\_only=True))  
        if not rows:  
            continue

        \# Trim trailing fully-empty rows/columns  
        rows \= \_trim\_empty(rows)

        \# Render as Markdown table  
        markdown \= \_rows\_to\_markdown(rows)

        sections.append(Section(  
            text=markdown,  
            structure\_path=f"Sheet: {sheet\_name}",  
            section\_type='sheet', order=order  
        ))  
        order \+= 1

        \# Named ranges and cell comments worth capturing  
        for name in wb.defined\_names:  
            \# ...  
            pass

    metadata \= {  
        'creator': wb.properties.creator,  
        'created': wb.properties.created.isoformat() if wb.properties.created else None,  
        'modified': wb.properties.modified.isoformat() if wb.properties.modified else None,  
        'sheet\_count': len(wb.sheetnames),  
    }

    return ExtractionResult(method='openpyxl', text='\\n\\n'.join(s.text for s in sections),  
                            sections=sections, metadata=metadata, warnings=warnings)

**What we extract:**

| Element | Output |
| :---- | :---- |
| All visible sheets | One Section per sheet, structure\_path \= "Sheet: {name}" |
| Hidden sheets | Skipped with warning (often contain stale data, lookups) |
| Cell values | Computed values (not formulas), as Markdown table |
| Cell comments | Appended as \[cell A5 comment by Alice: ...\] |
| Named ranges | Stored in metadata; resolved range value included in section |
| Defined tables (ListObjects) | Title row used as header in Markdown rendering |
| Charts | Skipped — chart titles captured if present, data already in source cells |
| PivotTables | Cached pivot data captured if present; pivot definition skipped |

**Special handling for large sheets:**

A sheet with 100,000+ rows produces a 50+ MB markdown blob that's neither useful nor chunkable cleanly. The strategy:

1. If a sheet has ≤ 1,000 rows: full extraction.  
2. If 1,000–10,000 rows: extract header row \+ sample (first 100 \+ last 100 \+ 100 random middle rows), with a warning.  
3. If \> 10,000 rows: extract header \+ summary statistics (column types, distinct count, min/max for numeric, top frequencies for categorical), warning notes "data sheet — full content not indexed for semantic search; query columns by name".

This means a million-row CSV-like sheet doesn't blow up the embedding pipeline but is still discoverable by structural metadata.

**Edge cases:**

* **Multi-table sheets**: A single sheet often contains several logical tables separated by blank rows. We detect blank-row separators and emit a sub-section per detected table when row count \> 50\.  
* **Currency / date formatting**: Values are read as Python types (datetime, Decimal); rendered to text via locale-aware formatter (default ISO 8601 for dates, dot-decimal for numbers — locale override available).  
* **.xlsm (macro-enabled)**: Same as .xlsx. VBA project skipped.  
* **Streaming for very large files**: openpyxl's read\_only=True already streams; we don't need our own SAX layer.

#### **J.6 .xls (Excel, Legacy)**

Same strategy as .doc: **convert to .xlsx via LibreOffice, then run J.5**.

xlrd (versions ≤ 1.2) supports legacy .xls directly but has been unmaintained for years and dropped support in 2.0+. Conversion via LibreOffice is more reliable.

#### **J.7 .pptx (PowerPoint, Modern)**

**Library:** python-pptx.

PowerPoint extraction has a particular gotcha: **most of a slide's meaning is in shapes (text boxes, tables, SmartArt) and speaker notes**, not in a single body field like Word. The extractor walks each slide's shape tree.

from pptx import Presentation  
from pptx.util import Emu

async def extract\_pptx(blob: bytes) \-\> ExtractionResult:  
    prs \= Presentation(io.BytesIO(blob))  
    sections \= \[\]  
    order \= 0

    for slide\_num, slide in enumerate(prs.slides, start=1):  
        slide\_text\_parts \= \[\]

        \# Title (if a title placeholder exists)  
        if slide.shapes.title and slide.shapes.title.has\_text\_frame:  
            slide\_text\_parts.append(f"\# {slide.shapes.title.text\_frame.text}")

        \# Walk all shapes top-to-bottom, left-to-right based on shape position  
        sorted\_shapes \= sorted(  
            (s for s in slide.shapes if s \!= slide.shapes.title),  
            key=lambda s: (s.top or 0, s.left or 0\)  
        )

        for shape in sorted\_shapes:  
            if shape.has\_text\_frame:  
                txt \= shape.text\_frame.text.strip()  
                if txt:  
                    slide\_text\_parts.append(txt)

            elif shape.has\_table:  
                rows \= \[  
                    '| ' \+ ' | '.join(cell.text for cell in row.cells) \+ ' |'  
                    for row in shape.table.rows  
                \]  
                slide\_text\_parts.append('\\n'.join(rows))

            elif shape.shape\_type \== MSO\_SHAPE\_TYPE.PICTURE:  
                \# OCR if it looks text-heavy (heuristic: large picture, \> 200x200 px)  
                if shape.width \> Emu(2\_000\_000):  
                    ocr\_text \= await ocr\_image(shape.image.blob)  
                    if ocr\_text:  
                        slide\_text\_parts.append(f"\[image text: {ocr\_text}\]")

            elif shape.shape\_type \== MSO\_SHAPE\_TYPE.GROUP:  
                \# Recursively walk grouped shapes  
                slide\_text\_parts.extend(\_extract\_group(shape))

        slide\_body \= '\\n\\n'.join(slide\_text\_parts)  
        sections.append(Section(  
            text=slide\_body,  
            structure\_path=f"Slide {slide\_num}",  
            section\_type='slide', order=order  
        ))  
        order \+= 1

        \# Speaker notes — often the highest-value content on a slide  
        if slide.has\_notes\_slide and slide.notes\_slide.notes\_text\_frame.text.strip():  
            sections.append(Section(  
                text=slide.notes\_slide.notes\_text\_frame.text,  
                structure\_path=f"Slide {slide\_num} — Speaker Notes",  
                section\_type='note', order=order  
            ))  
            order \+= 1

    return ExtractionResult(method='python-pptx', text='\\n\\n'.join(s.text for s in sections),  
                            sections=sections, metadata=\_pptx\_meta(prs), warnings=\[\])

**What we extract:**

| Element | Output |
| :---- | :---- |
| Slide titles | First line of each slide's section, prefixed \# |
| Text boxes | Extracted in spatial reading order |
| Tables on slides | Markdown table |
| SmartArt | Text content extracted; structure flattened |
| Speaker notes | Separate section per slide, marked section\_type='note' |
| Pictures with text content | OCR via Tesseract |
| Slide layout / master text placeholders | Skipped (often boilerplate) |
| Animations | Ignored entirely |
| Embedded video / audio | Filename captured; content not extracted |

**Edge cases:**

* **Hidden slides**: Skipped with warning.  
* **Slide ordering**: Always honour prs.slides order (matches presenter view).  
* **Master / Layout templates**: Not extracted as content; their \<sp\> text is usually placeholder text like "Click to add title".  
* **Embedded Excel charts**: Underlying data extracted via the embedded .xlsx part if present.

#### **J.8 .ppt (PowerPoint, Legacy)**

Same strategy: **LibreOffice convert to .pptx, then run J.7**.

#### **J.9 .msg and .eml (Outlook / Standard Email)**

Email is a frequent file type in SharePoint and OneDrive (people drop .msg files into folders for shared reference). Two formats:

* **.msg** — Outlook's proprietary OLE-based format. Library: extract-msg.  
* **.eml** — RFC 822 standard. Library: Python stdlib email.

from extract\_msg import Message  
from email import policy  
from email.parser import BytesParser

async def extract\_msg(blob: bytes) \-\> ExtractionResult:  
    msg \= Message(io.BytesIO(blob))  
    sections \= \[\]

    \# Headers section  
    headers \= (  
        f"From: {msg.sender}\\n"  
        f"To: {msg.to}\\n"  
        f"Cc: {msg.cc or ''}\\n"  
        f"Subject: {msg.subject}\\n"  
        f"Date: {msg.date}\\n"  
    )  
    sections.append(Section(text=headers, structure\_path='Headers',  
                            section\_type='metadata', order=0))

    \# Body — prefer plain text, fall back to HTML stripped  
    body\_text \= msg.body or \_html\_to\_text(msg.htmlBody)  
    sections.append(Section(text=body\_text, structure\_path='Body',  
                            section\_type='body', order=1))

    \# Attachments — recursively extract each  
    order \= 2  
    for att in msg.attachments:  
        att\_result \= await extract\_with\_fallback(  
            blob=att.data, filename=att.longFilename, mime\_type=None  
        )  
        sections.append(Section(  
            text=f"\[Attachment: {att.longFilename}\]\\n\\n{att\_result.text}",  
            structure\_path=f"Attachment: {att.longFilename}",  
            section\_type='body', order=order  
        ))  
        order \+= 1

    return ExtractionResult(method='extract-msg', text='\\n\\n'.join(s.text for s in sections),  
                            sections=sections, metadata=\_msg\_meta(msg), warnings=\[\])

**Recursive attachment handling**: an email containing an .xlsx attachment becomes one indexed memory containing email body \+ parsed spreadsheet text. Search results citing the email surface both the discussion and the data.

**Privacy consideration:** Emails often contain content the user receiving the email is not the author of. Indexed messages are still namespaced to the user who shared/owns the file in the bridge — they don't accidentally cross-pollinate.

#### **J.10 .one (OneNote)**

OneNote files (.one, .onetoc2) use a proprietary, undocumented binary format. There are no good Python parsers — every attempt has stalled at partial coverage.

**Strategy: read OneNote via Microsoft Graph API directly, not by parsing files.**

When the SharePoint bridge encounters a OneNote notebook reference, it switches code paths:

GET /v1.0/me/onenote/notebooks/{id}/sections  
GET /v1.0/me/onenote/sections/{id}/pages  
GET /v1.0/me/onenote/pages/{id}/content   ← returns rendered HTML

The HTML is then run through the standard HTML extractor (J.12). This loses page structure (sections, page hierarchy) which we synthesise from the API metadata.

.one files found in non-Microsoft sources (e.g. dropped into Dropbox) are skipped with a warning.

#### **J.11 .pdf (with OCR Fallback)**

PDF is the most variable format — it can be a clean text-layer document, a scanned image, or anywhere in between. Strategy is layered:

async def extract\_pdf(blob: bytes) \-\> ExtractionResult:  
    if is\_pdf\_encrypted(blob):  
        return ExtractionResult(method='pypdf', skipped=True, skip\_reason='encrypted', ...)

    \# Layer 1: pypdf for fast text extraction  
    text, sections, warnings \= \_pypdf\_extract(blob)

    \# Layer 2: pdfminer.six fallback for complex layouts where pypdf fails  
    if len(text.strip()) \< 200 or \_looks\_garbled(text):  
        text2, sections2, warnings2 \= \_pdfminer\_extract(blob)  
        if len(text2) \> len(text) \* 1.5:  
            text, sections, warnings \= text2, sections2, warnings2 \+ \['used pdfminer fallback'\]

    \# Layer 3: OCR fallback if no usable text layer  
    if len(text.strip()) \< 200:  
        text, sections, warnings \= await \_ocr\_pdf(blob, warnings)

    return ExtractionResult(method=\_method\_name, text=text,  
                            sections=sections, metadata=\_pdf\_meta(blob), warnings=warnings)

| Layer | Library | Speed | Coverage |
| :---- | :---- | :---- | :---- |
| Fast path | pypdf | \~50 ms/page | Clean PDFs with text layer |
| Layout-aware | pdfminer.six | \~200 ms/page | Multi-column, complex layout |
| OCR | pdf2image \+ tesseract | \~2 s/page | Scanned / image-only |

**Per-page sections:** PDFs always produce one Section per page with structure\_path \= "Page N". Headings detected via font-size heuristics (largest fonts on page \= headings) supplement the structure path when reliable.

**Tables in PDFs:** Notoriously hard. Use pdfplumber for table detection on a per-page basis when font-based heuristics suggest tabular data; otherwise leave as flowed text and accept that table semantics are lost. (Future improvement: tabula-py for more accurate extraction, but it requires Java runtime — adds installer weight.)

#### **J.12 Plain-Text Family**

| Format | Method | Notes |
| :---- | :---- | :---- |
| .txt | Decode with chardet for encoding detection | Treat as single section |
| .md | Decode \+ parse with markdown-it-py | Use heading levels for structure\_path |
| .csv / .tsv | pandas.read\_csv (or stdlib csv for very large) | Render as Markdown table; large-table strategy from J.5 applies |
| .html / .htm | selectolax | Strip \<script\>, \<style\>, \<nav\>, \<header\>, \<footer\> boilerplate; extract \<main\> or \<article\> if present |
| .rtf | striprtf | Plain text only; loses formatting |
| .json | json.loads \+ pretty-print | Indexed as the formatted JSON string |
| .xml | lxml parse \+ serialise | Indented XML for readability |
| .yaml / .yml | pyyaml parse \+ re-dump | Same approach |
| .ipynb (Jupyter) | nbformat parse | Markdown cells extracted; code cells routed to index\_code\_file instead |

#### **J.13 OpenDocument (.odt, .ods, .odp)**

Use odfpy for direct extraction — it's pure Python, MIT-licensed, and handles all three formats. As a fallback, LibreOffice convert-to-Office and re-extract.

#### **J.14 Diagrams and Whiteboards (.vsdx, .drawio, .mermaid)**

**Strategy: Extract text nodes and synthesize connections.**

* **.drawio**: Uncompress (usually deflate \+ base64) the XML. Parse \<mxCell\> elements. Extract the value attribute (text).  
* **.mermaid**: Treat as plain text. The semantic structure (e.g., A \--\> B) is already highly readable by LLMs. Chunk by graph definitions.  
* **.vsdx**: Use vsdx. Extract text from shapes and synthesize spatial or connected relationships ("Shape A connects to Shape B") into metadata.

#### **J.15 Adobe Creative Suite (.psd, .ai, .indd / .idml)**

**Strategy: Extract text layers; ignore raster/vector data.**

* **.psd**: Use psd-tools. Walk the layer tree, find TypeLayer instances, and extract the raw text. Log warnings for rasterized text (fallback to OCR if requested).  
* **.ai**: Modern Illustrator files are PDF-compatible under the hood. Run them through the pypdf layer (J.11).  
* **.indd (InDesign)**: Highly proprietary binary. **Pragmatic approach:** TriMCP demands .idml (InDesign Markup Language, an XML ZIP) instead. If .indd is encountered, skip with warning recommending .idml. Parse .idml \<Story\> elements for text threads.

#### **J.16 Engineering & CAD (.dxf, .dwg, .rvt, .skp)**

**Strategy: Text annotations and metadata only. TriMCP is a semantic search engine, not a 3D viewer.**

* **.dxf**: Use ezdxf. Iterate through TEXT, MTEXT, and ATTDEF (block attributes) entities.  
* **.dwg**: Proprietary binary. If a headless ODA (Open Design Alliance) / Teigha converter is available in the worker container, convert to DXF and run the ezdxf pipeline. Otherwise, skip with audit log.  
* **.rvt (Revit) & .skp (SketchUp)**: No native Python parsers. Extract file metadata only. (Future scope: BIM360 API bridge).

#### **J.17 Project Management & Publisher (.mpp, .pub)**

* **.pub**: Routed through the LibreOffice headless conversion service (J.22) to extract text frames.  
* **.mpp**: Use a containerized mpxj sidecar (Java) or mppbase to extract Task Names, Descriptions, and Assignees. Rendered as a Markdown table.

#### **J.18 Encrypted / Password-Protected Files**

Detection happens before any parsing attempt:

| Format | Detection method |
| :---- | :---- |
| .docx, .xlsx, .pptx | ZIP file header check; encrypted Office files have a CDF/OLE structure instead of ZIP |
| .pdf | /Encrypt dictionary in trailer |
| .doc, .xls, .ppt (legacy OLE) | WordDocument / Workbook stream encryption flag |
| .zip archives | Standard ZIP encryption flag in central directory |

When detected:

1. The file is **not** processed.  
2. An audit\_log entry records skipped: encrypted with file\_id and provider.  
3. A user-facing notification (configurable per-deployment) tells the user "Encrypted document not indexed: \[filename\]".  
4. **TriMCP never asks for a password.** This is a deliberate decision — passwords don't belong in indexing config, and prompting users would create a phishing-vector training experience.

If an organization wants encrypted docs indexed, the recommendation is to remove encryption at the document-management-layer (e.g. SharePoint sensitivity labels with controlled access) rather than build password-handling into TriMCP.

#### **J.19 OCR Fallback for Image-Only Documents**

OCR is triggered automatically when text extraction yields suspiciously little content:

* .docx / .pptx with extracted text \< 50 characters per page-equivalent  
* .pdf with empty or near-empty text layer  
* Image attachments (.png, .jpg, .tiff) \> 200×200 px  
* Image-only sections within otherwise text-bearing documents (e.g. a scanned signature page in a Word doc)

**Engine:** Tesseract 5.x via pytesseract, running in the worker container. Languages pre-loaded based on configurable list (default: English \+ the deployment's primary language).

**Performance budget:** OCR is expensive (1–3 seconds per page typically). To avoid degrading bridge throughput:

* OCR jobs run on a **separate, lower-priority RQ queue** (ocr\_queue).  
* Worker concurrency for OCR is capped at 2 (configurable).  
* Files exceeding 100 pages of OCR work are deferred and processed during off-hours.  
* Results are cached by content hash so re-indexed identical images don't re-OCR.

**Quality threshold:** Tesseract's confidence score per word is checked. If average confidence \< 60%, the OCR result is included but with a warning ocr\_low\_confidence: average 45%. Below 30%, OCR is discarded entirely.

**GPU acceleration:** When the worker host has an available GPU (NVIDIA CUDA), Tesseract can be replaced with EasyOCR (PyTorch-based, GPU-accelerated). The hardware backend abstraction from §8 already detects GPU availability — same logic gates OCR engine choice. \~10x speedup on the GPU path.

#### **J.20 Unknown Formats and Failure Handling**

When a file's extension or MIME type isn't in the extractor registry:

1. **Magic-byte sniff:** Try python-magic to detect actual content type — files often have wrong extensions.  
2. **Plain-text attempt:** If chardet reports \>95% confidence in a text encoding and the content is mostly printable, treat as .txt.  
3. **Skip with audit:** Otherwise log skipped: unsupported\_format with detected MIME type. Tracked metrics surface frequency, prompting future extractor additions.

When an extractor **crashes** on a malformed file:

1. The exception is caught, never propagating to crash the worker.  
2. The file is marked skipped: extraction\_failed with the exception summary.  
3. An audit log entry includes file metadata and traceback for IT investigation.  
4. The next file in the queue proceeds normally.

**This is the "partial extraction beats failed extraction" principle in practice** — one corrupt file in a 10,000-document SharePoint folder must not block the other 9,999.

#### **J.21 Library Dependency Summary**

Additions to requirements.txt:

\# Document extraction  
python-docx\>=1.1.0  
openpyxl\>=3.1.2  
python-pptx\>=1.0.0  
extract-msg\>=0.50.0  
pypdf\>=4.0.0  
pdfminer.six\>=20231228  
pdfplumber\>=0.11.0  
pdf2image\>=1.17.0  
pytesseract\>=0.3.10  
chardet\>=5.2.0  
markdown-it-py\>=3.0.0  
selectolax\>=0.3.20  
striprtf\>=0.0.27  
odfpy\>=1.4.1  
vsdx\>=0.5.2  
psd-tools\>=1.9.31  
ezdxf\>=1.1.0  
defusedxml\>=0.7.1  
python-magic\>=0.4.27  
nbformat\>=5.10.0  
lxml\>=5.0.0   \# already required transitively, pinned explicitly

\# Optional GPU OCR  
easyocr\>=1.7.1   \# only installed when GPU detected at install time

**System dependencies (installer must include or detect):**

* LibreOffice (headless) — bundled in worker container; client installer detects existing installation in Local mode and offers to install if missing  
* Tesseract OCR engine — bundled in worker; client installer ships Tesseract for Windows/macOS in Local mode  
* Tesseract language data files — English baseline \+ configurable additional languages  
* Poppler utilities (pdftoppm) — required by pdf2image; bundled with installer

**Installer size impact:**

| Component | Size added |
| :---- | :---- |
| Python extraction libs | \~80 MB |
| LibreOffice (Local mode) | \~350 MB |
| Tesseract engine \+ English data | \~120 MB |
| Poppler | \~20 MB |
| Additional language data (per language) | \~20–50 MB each |
| **Total Local-mode addition** | **\~570 MB baseline** |

Multi-User and Cloud modes don't include LibreOffice/Tesseract on the client — these run server-side only — keeping the client installer lean.

#### **J.22 LibreOffice Headless Service**

In Multi-User and Cloud modes, LibreOffice runs as a sidecar service in the worker container, exposed via a small REST wrapper. This avoids spawning a fresh soffice process per file (cold-start cost is \~3 seconds — too high for high-volume conversions).

\# Added to docker-compose.yml  
  libreoffice:  
    image: linuxserver/libreoffice:latest  
    restart: always  
    command: \["python", "/app/lo\_service.py"\]   \# custom REST wrapper  
    networks: \[internal\]  
    \# Not exposed externally; only worker connects

The wrapper exposes POST /convert taking the source bytes and target format, returning the converted bytes. It pools LibreOffice processes (typically 4 workers per container) to handle parallel conversions.

In Local mode, the client launches LibreOffice on demand via subprocess against the system installation. Conversion latency is higher (\~3 second cold start per call) but acceptable for the lower file volume of single-user scenarios.

#### **J.23 Performance Benchmarks**

Indicative throughput on a 4-vCPU worker (no GPU):

| Format | Typical size | Extraction time | Throughput |
| :---- | :---- | :---- | :---- |
| .docx (10-page report) | \~200 KB | \~150 ms | \~6/sec |
| .docx (200-page book) | \~5 MB | \~3 sec | \~0.3/sec |
| .xlsx (small, 10 sheets, \~1k rows each) | \~500 KB | \~400 ms | \~2.5/sec |
| .xlsx (large, 100k rows) | \~30 MB | \~8 sec | \~0.13/sec |
| .pptx (30-slide deck) | \~10 MB | \~2 sec | \~0.5/sec |
| .pdf text-layer (50 pages) | \~2 MB | \~1.5 sec | \~0.7/sec |
| .pdf scanned/OCR (50 pages) | \~10 MB | \~90 sec | \~0.01/sec |
| .msg with 3 attachments | \~1 MB | \~600 ms | \~1.5/sec |

OCR dominates total indexing time wherever it's invoked. Push-based architecture means this is rarely a problem — files trickle in over time rather than arriving as a batch — but during initial bridge sync of a folder with thousands of scanned PDFs, the OCR queue can run for hours. The bridge\_status MCP tool surfaces this with pending\_ocr\_jobs: N so users understand why their full search isn't immediate.

**End of document.**

For questions, corrections, or additions, please open an issue at https://github.com/sindrehaugen/TriMCP/issues.