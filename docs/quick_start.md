# TriMCP Quick Start Guide

Welcome to TriMCP v2.2. This guide covers the installation of the TriMCP client, selecting your deployment mode, and connecting the engine to your preferred LLM interface (Cursor or Claude Desktop).

## 1. Download and Install

TriMCP provides a unified native installer (`trimcp-launch`) for all supported platforms.

- **Windows**: Download the `.exe` or `.msi` (Enterprise) installer.
- **macOS**: Download the `.dmg` (Universal Binary for Apple Silicon and Intel).
- **Linux**: Download the standalone binary.

Run the installer. The setup wizard will prompt you to select your **Deployment Mode**.

## 2. Select Deployment Mode

During installation, you must choose how TriMCP connects to its underlying Quad-DB storage stack:

### Local Mode
Best for solo developers and highly sensitive, offline-only data.
- **How it works**: The installer automatically configures Docker Desktop on your machine to run PostgreSQL/pgvector, MongoDB, Redis, and MinIO locally.
- **Requirements**: Docker Desktop must be installed and running.

### Multi-User Mode
Best for single-office teams sharing a centralized knowledge base.
- **How it works**: Connects to an on-premise server running the TriMCP database stack.
- **Requirements**: You will be prompted for your Active Directory UPN (User Principal Name) for identity resolution and the internal IP/hostname of your office server. Requires office LAN or VPN access.

### Cloud Mode
Best for distributed enterprises and remote workforces.
- **How it works**: Connects to managed cloud services (AWS, Azure, or GCP) provisioned by your IT department.
- **Requirements**: Requires your corporate IAM identity/SSO login and the cloud endpoint URL provided by your administrator.

## 3. Connect to Your LLM Client

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

*Note: In Multi-User and Cloud modes, authentication and connection strings are managed automatically by the `trimcp-launch` shim and your local environment variables. You do not need to hardcode database credentials into the MCP configuration.*

## 4. Verify Installation

Once connected, restart your LLM client and ask:
> "What MCP tools do you have available for TriMCP?"

You should see tools like `semantic_search`, `store_memory`, `index_code_file`, and `graph_search` ready for use.
