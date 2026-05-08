# **MongoDB Configuration**

MONGO\_URI=mongodb://localhost:27017

# **PostgreSQL Configuration (Update with actual secure passwords in production)**

PG\_DSN=postgresql://mcp\_user:mcp\_password@localhost:5432/memory\_meta

# **Redis Configuration**

REDIS\_URL=redis://localhost:6379/0

# **Admin API Key (Required for Production)**

TRIMCP\_ADMIN\_API\_KEY=set-a-strong-random-secret-here

The admin API key is used by the server-side ``_check_admin()`` gate to
authenticate administrative MCP tool calls (``manage_namespace``,
``trigger_consolidation``, ``manage_quotas``, etc.).  The client sends
this value as the ``admin_api_key`` argument in the MCP tool call, and
the server validates it using ``secrets.compare_digest()``.

**Security notes:**
- Must be set in production — the server will refuse to start admin tools
  without it (``ValueError``).
- Use a strong random value (e.g. ``openssl rand -hex 32``).
- Include in the ``env`` block of ``mcp_config.json`` for IDE-based clients.
- **Development only**: Set ``TRIMCP\_ADMIN\_OVERRIDE=true`` to bypass the
  check without an API key (never use in production).

# **Temporal Query Lookback**

TRIMCP\_MAX\_TEMPORAL\_LOOKBACK\_DAYS=90

Maximum lookback window (in days) for historical ``as_of`` temporal queries.
Queries attempting to read state older than this window are rejected with a
``ValueError`` (mapped to 422 Unprocessable Entity in REST, JSON-RPC error in
MCP).  Prevents unbounded historical searches that trigger full-table scans on
``event_log``.

Set to **0** to disable boundary enforcement (not recommended — use only for
admin maintenance tasks where querying the full archive is genuinely needed).