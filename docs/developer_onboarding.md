# NCE Developer Onboarding Guide

Welcome to the Neuro Cognitive Engine (NCE) development team. This document provides a step-by-step tutorial to configure your local development environment, deploy backing databases, configure environment variables, run integration tests, and link NCE to your IDE as a Model Context Protocol (MCP) server.

---

## 📋 1. Prerequisites

Ensure your host machine has the following tools installed:

| Tool | Minimum Version | Required For |
| :--- | :--- | :--- |
| **Python** | 3.10 | Core engine runtime (`pyproject.toml` compatibility) |
| **Docker + Compose** | Docker 24+ / Compose v2 | Local Quad-Database stack deployment |
| **Git** | Recent version | Version control and source management |

---

## 🛠️ 2. Step-by-Step Local Workspace Setup

Follow these steps sequentially to configure NCE on your local environment:

### Step 2a: Clone the Repository & Initialize Environment
Clone the repository and enter the directory:
```bash
git clone https://github.com/your-org/NCE.git
cd NCE
```

### Step 2b: Boot the Backing Services (Docker Compose)
NCE uses a **Quad-Database Stack** to isolate storage models. Spin up the local development containers:
```bash
docker compose up -d postgres mongodb redis minio
```
Verify that all four containers are running and healthy:
```bash
docker compose ps
```
To verify that PostgreSQL is ready to accept connections, view the container logs:
```bash
docker compose logs postgres --tail 20
```
Look for the line: `database system is ready to accept connections`.

### Step 2c: Apply the Database Schema & Extensions
Initialize the PostgreSQL database (`memory_meta`) with the required schema, triggers, and extensions (`vector` and `pgcrypto`):
```bash
docker exec -i nce-postgres-1 psql -U mcp_user memory_meta < nce/schema.sql
```
Verify that the `vector` extension and RLS-compatible tables have been created successfully:
```bash
docker exec nce-postgres-1 psql -U mcp_user memory_meta -c "\dx"
```

### Step 2d: Configure the Local `.env` File
Copy the provided environment template to establish your local configuration:
```bash
cp .env.example .env
```
Open `.env` and fill in the required keys. Never commit your local `.env` file to version control. The critical development keys to populate are:

```bash
# --- Backing Services DSNs ---
MONGO_URI=mongodb://127.0.0.1:27017
PG_DSN=postgresql://mcp_user:mcp_password@127.0.0.1:5432/memory_meta
REDIS_URL=redis://127.0.0.1:6379/0
MINIO_ENDPOINT=127.0.0.1:9002
MINIO_ACCESS_KEY=mcp_admin
MINIO_SECRET_KEY=super_secure_minio_password

# --- Security Credentials (Required for startup) ---
# NCE_MASTER_KEY must be a 32+ character key. Use a strong random value:
NCE_MASTER_KEY=your-32-byte-long-master-key-here-for-aes-encryption

# API token to authorize incoming stdio tool requests
NCE_MCP_API_KEY=your-local-developer-mcp-api-key

# Binds the stdio interface to a single tenant namespace (mandatory in production)
NCE_MCP_NAMESPACE_ID=00000000-0000-4000-8000-000000000001
```

---

## 🐍 3. Python Virtual Environment Setup

Create an isolated virtual environment and install the pinned dependencies:

```bash
# Create the virtual environment
python -m venv .venv

# Activate the environment
# On Windows (Command Prompt):
.venv\Scripts\activate
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On macOS/Linux:
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### Optional Cognitive Extensions
If you are working on the AST Code Ingestion and spaCy NLP pipeline, download the English language model:
```bash
pip install spacy
python -m spacy download en_core_web_sm
```

---

## 💻 4. IDE Configuration (Cursor / Claude Desktop)

To allow your LLM client (Cursor or Claude Desktop) to invoke NCE tools via Model Context Protocol (MCP) over standard I/O, configure the IDE using `mcp_config.json.example` as a template.

### Step 4a: Create Local `mcp_config.json`
Copy the example file to a gitignored location:
```bash
cp mcp_config.json.example mcp_config.json
```
Populate the file with your local database connection URLs, your `NCE_MASTER_KEY`, `NCE_MCP_API_KEY`, and `NCE_MCP_NAMESPACE_ID`.

### Step 4b: Configuring Cursor
1. Open Cursor and navigate to **Settings → MCP**.
2. Click **+ Add New MCP Server**.
3. Fill out the dialog:
   *   **Name**: `nce-memory`
   *   **Type**: `command`
   *   **Command**: `python`
   *   **Arguments**: `["/absolute/path/to/NCE/server.py"]`
4. Add the environment variables from your `mcp_config.json`:
   *   `MONGO_URI`: `mongodb://127.0.0.1:27017`
   *   `PG_DSN`: `postgresql://mcp_user:mcp_password@127.0.0.1:5432/memory_meta`
   *   `REDIS_URL`: `redis://127.0.0.1:6379/0`
   *   `MINIO_ENDPOINT`: `127.0.0.1:9002`
   *   `MINIO_ACCESS_KEY`: `mcp_admin`
   *   `MINIO_SECRET_KEY`: `super_secure_minio_password`
   *   `NCE_MASTER_KEY`: `your-32-byte-master-key`
   *   `NCE_MCP_API_KEY`: `your-client-api-key`
   *   `NCE_MCP_NAMESPACE_ID`: `00000000-0000-4000-8000-000000000001`
5. Click **Save**. The status should turn green once connected.

### Step 4c: Configuring Claude Desktop
Edit the configurations file:
*   **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
*   **macOS / Linux**: `~/Library/Application Support/Claude/claude_desktop_config.json`

Insert the following JSON payload (adjust Python path and repository paths to absolute paths):
```json
{
  "mcpServers": {
    "nce-memory": {
      "command": "python",
      "args": ["/absolute/path/to/NCE/server.py"],
      "env": {
        "MONGO_URI": "mongodb://127.0.0.1:27017",
        "PG_DSN": "postgresql://mcp_user:mcp_password@127.0.0.1:5432/memory_meta",
        "REDIS_URL": "redis://127.0.0.1:6379/0",
        "MINIO_ENDPOINT": "127.0.0.1:9002",
        "MINIO_ACCESS_KEY": "mcp_admin",
        "MINIO_SECRET_KEY": "super_secure_minio_password",
        "NCE_MASTER_KEY": "your-32-byte-master-key",
        "NCE_MCP_API_KEY": "your-client-api-key",
        "NCE_MCP_NAMESPACE_ID": "00000000-0000-4000-8000-000000000001"
      }
    }
  }
}
```
Restart Claude Desktop to load the server.

---

## 🏃 5. Launching Services Locally

For full feature execution, start the following long-running processes in separate shell windows:

### 1. Stdio MCP Server
Binds to your standard input/output streams for MCP JSON-RPC routing:
```bash
python server.py
```

### 2. Async RQ Task Worker
Processes background code AST parses and embedding migrations enqueued to Redis:
```bash
python start_worker.py
```

### 3. Cron Scheduler
Executes document bridge sweeps, token expiry validations, and cognitive consolidation jobs:
```bash
python -m nce.cron
```

### 4. Admin REST Server
Provides the Starlette admin interface and tool control toggle APIs (port `8003`):
```bash
python admin_server.py
```

Verify that the admin server is up and database connections are healthy:
```bash
curl http://localhost:8003/api/health
```

---

## 🧪 6. Running Tests

NCE uses pytest for test-driven development. 

### Run Unit Tests
Unit tests use mocked pools (`FakeAsyncpgPool`) and do not require live Docker services. Use the default fast run with CPU-autodetected parallelism:
```bash
pytest -n auto
```
For standard single-threaded execution:
```bash
pytest
```

### Run Integration Tests
Integration tests execute against live PostgreSQL, MongoDB, Redis, and MinIO endpoints to validate triggers, transaction checkouts, and RLS behaviors:
```bash
# Ensure Docker Compose containers are up, then run:
pytest -m integration
```

### Useful Testing Flags
*   To stop on first failure: `pytest -x`
*   To run a single file: `pytest tests/test_signing_cache.py -v`
*   To search for a specific test: `pytest -k "time_travel"`

---

## ⚖️ 7. Core Contribution Standards
*   **Type Safety**: All codebase files inside `nce/` must compile cleanly under `mypy --strict`.
*   **Linting**: Use `ruff` for code styling and standard compliance (`ruff check .`).
*   **SQL Contexts**: Never bypass RLS. All queries targeting user data must run within the `scoped_pg_session(pool, namespace_id)` block. Bypassing this will cause test failures.
*   **WORM Enforcement**: Never attempt to write update or delete statement paths against `event_log`. This is a write-once, read-many table monitored by integrity triggers.
