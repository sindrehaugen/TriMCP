# TriMCP Quick Start Guide

Welcome to **TriMCP v1.0**. This guide covers running the engine **from source** (Docker + Python), selecting a deployment posture, and connecting the MCP server to Cursor or Claude Desktop. Package installers, when available, layer on top of the same `server.py` and Compose stack.

## 1. Prerequisite: stack and repo

- Install **Docker Desktop** (or compatible engine) and **Python 3.9+**.
- Clone the repository and install dependencies (`pip install -r requirements.txt` or your env manager).

## 2. Deployment posture (conceptual)

### Local (default dev)

- Run **PostgreSQL**, **MongoDB**, **Redis**, and **MinIO** via the repo’s `docker-compose` (see [deploy/README.md](../deploy/README.md)).
- Copy `.env.example` → `.env` and set connection strings.

### Multi-user

- Same services, hosted for a team: enforce **namespace isolation**, **HMAC/JWT auth**, and **quotas** in production (see `admin_server.py`, tests under `tests/test_a2a.py` and `tests/test_quotas.py`).

### Cloud

- Use managed equivalents for each store; point `.env` at cloud URIs. No code changes required for the v1.0 paths.

## 3. Connect to your LLM client

TriMCP operates as a Model Context Protocol (MCP) server over standard input/output (`stdio`). Once installed, configure your client to point to the `server.py` entrypoint.

### Cursor

1. Open Cursor Settings -> **MCP** -> **Add Server**.
2. Set the type to `command`.
3. Configure the server:
   - **Name**: `tri-stack-memory`
   - **Command**: `python`
   - **Args**: `/absolute/path/to/TriMCP/server.py` (Use double backslashes `\\` or forward slashes `/` on Windows).

### Claude Desktop

Edit your `claude_desktop_config.json` file:
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

Add the following configuration:

```json
{
  "mcpServers": {
    "tri-stack-memory": {
      "command": "python",
      "args": ["/absolute/path/to/TriMCP/server.py"]
    }
  }
}
```

*Note: In shared deployments, manage **secrets** via your platform; do not hardcode database passwords in MCP JSON when avoid.*

## 4. Verify installation

Once connected, restart your LLM client and ask:
> "What MCP tools do you have available for TriMCP?"

You should see tools such as `semantic_search` (with optional `as_of`), `graph_search`, `store_memory`, `index_code_file`, bridge tools, salience, contradictions, replay, and migration tools — see `server.py` for the authoritative list.

---

## Architecture reference

**v1.0 runtime** (temporal engine, A2A protocol, cognitive / background workers, Mermaid diagrams): [architecture-v1.md](./architecture-v1.md).

Phase **0.1** / **0.2** (multi-tenant model, signing): [architecture-phase-0-1-0-2.md](./architecture-phase-0-1-0-2.md).

**Docker Compose** defaults: [deploy/README.md](../deploy/README.md).
