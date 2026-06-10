# Diff Reference for Batch 43

```diff
diff --git a/admin/index.html b/admin/index.html
index 083b036..d5ce864 100644
--- a/admin/index.html
+++ b/admin/index.html
@@ -2277,6 +2277,87 @@
     </section>
     </div>
 
+    <!-- Tab: Glass Profile — Bi-temporal accountability timeline (Phase II.5) -->
+    <div id="panel-glass-profile" x-show="adminTab === 'glass-profile'" x-cloak class="space-y-8">
+    <section id="glass-profile" class="scroll-mt-24 pt-6 md:pt-8 border-t border-slate-200/80"
+             x-data="glassProfileTimeline" x-init="mount()">
+      <div class="border-b border-slate-200 pb-2.5 mb-6 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
+        <div>
+          <h2 class="text-lg font-bold font-hanken tracking-tight text-slate-900 uppercase">Glass Profile · Belief Timeline</h2>
+          <p class="text-xs text-slate-500 mt-1">Bi-temporal accountability (II.5) — what the agent knew, and when, from the signed WORM event stream <code class="text-bravo-pink font-semibold">GET /api/admin/events</code>. Pair with the <code class="text-bravo-pink font-semibold">explain_past_decision</code> MCP tool to reconstruct the belief set at any T.</p>
+        </div>
+        <button type="button" @click="refresh()" :disabled="loading"
+                class="self-start rounded-lg bg-white border border-slate-300 px-4 py-2 text-xs font-bold text-slate-700 hover:border-slate-400 hover:text-slate-900 transition disabled:opacity-50 shadow-sm">
+          <span x-show="!loading">Rebuild timeline</span>
+          <span x-show="loading" class="flex items-center gap-1"><span class="animate-spin h-3.5 w-3.5 border-2 border-slate-400 border-t-transparent rounded-full"></span>Loading…</span>
+        </button>
+      </div>
+
+      <!-- Controls -->
+      <div class="rounded-xl border border-slate-200 bg-white p-4 mb-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 shadow-sm">
+        <label class="lg:col-span-2">
+          <span class="text-[10px] uppercase tracking-widest text-slate-500 font-bold">namespace_id</span>
+          <input type="text" x-model="namespaceId" @change="refresh()"
+                 class="w-full mt-1.5 rounded-lg bg-white border border-slate-300 px-3 py-1.5 text-xs font-mono text-slate-800 focus:border-bravo-pink focus:ring-1 focus:ring-bravo-pink outline-none transition">
+        </label>
+        <label>
+          <span class="text-[10px] uppercase tracking-widest text-slate-500 font-bold">as_of (ISO, optional)</span>
+          <input type="text" x-model="asOf" placeholder="2026-01-15T10:00:00Z"
+                 class="w-full mt-1.5 rounded-lg bg-white border border-slate-300 px-3 py-1.5 text-xs font-mono text-slate-800 focus:border-bravo-pink focus:ring-1 focus:ring-bravo-pink outline-none transition">
+        </label>
+        <label>
+          <span class="text-[10px] uppercase tracking-widest text-slate-500 font-bold">agent_id (optional)</span>
+          <input type="text" x-model="agentId"
+                 class="w-full mt-1.5 rounded-lg bg-white border border-slate-300 px-3 py-1.5 text-xs text-slate-800 focus:border-bravo-pink focus:ring-1 focus:ring-bravo-pink outline-none transition">
+        </label>
+      </div>
+
+      <!-- Summary chips -->
+      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
+        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
+          <p class="text-[10px] uppercase tracking-widest text-slate-500 mb-1 font-bold">Belief-forming events</p>
+          <p class="text-3xl font-extrabold text-slate-800 font-hanken" x-text="timeline.length"></p>
+        </div>
+        <div class="rounded-xl border border-emerald-200 bg-emerald-50/50 p-4 shadow-sm">
+          <p class="text-[10px] uppercase tracking-widest text-emerald-700 mb-1 font-bold">Beliefs held at as_of</p>
+          <p class="text-3xl font-extrabold text-emerald-600 font-hanken" x-text="heldAtAsOf"></p>
+        </div>
+        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
+          <p class="text-[10px] uppercase tracking-widest text-slate-500 mb-1 font-bold">As-of cutoff</p>
+          <p class="text-xs font-mono text-bravo-pink truncate mt-2 font-semibold" x-text="asOf || 'now (live)'"></p>
+        </div>
+      </div>
+
+      <div x-show="errorMsg" x-cloak class="text-[11px] text-red-600 mb-2 font-medium" x-text="errorMsg"></div>
+
+      <!-- Timeline -->
+      <ol class="relative border-l-2 border-slate-200 ml-3 space-y-4">
+        <template x-for="evt in timeline" :key="evt.id">
+          <li class="ml-5"
+              :class="isKnownAtAsOf(evt) ? '' : 'opacity-40'">
+            <span class="absolute -left-[7px] flex h-3 w-3 rounded-full border-2 border-white"
+                  :class="isKnownAtAsOf(evt) ? 'bg-emerald-500' : 'bg-slate-300'"></span>
+            <div class="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
+              <div class="flex items-center justify-between gap-2">
+                <span class="text-indigo-600 font-semibold text-xs" x-text="evt.event_type"></span>
+                <span class="font-mono text-[10px] text-slate-500" x-text="evt.occurred_at"></span>
+              </div>
+              <div class="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[10px] font-mono text-slate-500">
+                <span>seq <span class="font-bold text-slate-800" x-text="evt.event_seq"></span></span>
+                <span>agent <span class="text-slate-700" x-text="evt.agent_id"></span></span>
+                <span x-show="evt.parent_event_id">parent <span class="text-slate-400" x-text="evt.parent_event_id"></span></span>
+              </div>
+              <p class="mt-1 text-[10px]"
+                 :class="isKnownAtAsOf(evt) ? 'text-emerald-600' : 'text-slate-400'"
+                 x-text="isKnownAtAsOf(evt) ? 'Known by the agent at as_of' : 'Learned after as_of — excluded from the past belief set'"></p>
+            </div>
+          </li>
+        </template>
+        <li x-show="!timeline.length && !loading" class="ml-5 text-xs text-slate-500 py-4">No belief-forming events for this namespace.</li>
+      </ol>
+    </section>
+    </div>
+
     <!-- Tab: Maintenance (GC) -->
     <div id="panel-maintenance" x-show="adminTab === 'maintenance'" x-cloak class="space-y-8">
     <!-- GC -->
@@ -3200,6 +3281,7 @@
           { slug: 'cognitive', label: 'Cognitive' },
           { slug: 'datastores', label: 'Datastores' },
           { slug: 'tools', label: 'Tools' },
+          { slug: 'glass-profile', label: 'Glass Profile' },
           { slug: 'maintenance', label: 'Maintenance' },
           { slug: 'd365', label: 'Dynamics 365' },
         ],
@@ -5147,6 +5229,73 @@
           }
         }
       }));
+
+      /* ---------- Glass Profile · Belief Timeline (Phase II.5) ---------- */
+      Alpine.data('glassProfileTimeline', () => ({
+        timeline: [],
+        loading: false,
+        errorMsg: '',
+        namespaceId: '',
+        asOf: '',
+        agentId: '',
+
+        // Event types that form / revise the agent's belief state.
+        BELIEF_EVENTS: ['store_memory', 'consolidation_run', 'boost_memory', 'forget_memory'],
+
+        mount() {
+          if (this.defaultNs) this.namespaceId = this.defaultNs;
+          window.addEventListener('trimcp-apply-ns-filter', (e) => {
+            const nid = e.detail?.namespace_id;
+            if (nid === undefined || nid === null) return;
+            this.namespaceId = nid;
+            this.refresh();
+          });
+          if (this.namespaceId) this.refresh();
+        },
+
+        eventsQs() {
+          const p = new URLSearchParams();
+          p.set('page', '1');
+          p.set('limit', '200');
+          if (this.namespaceId) p.set('namespace_id', this.namespaceId);
+          if (this.agentId) p.set('agent_id', this.agentId);
+          return p.toString();
+        },
+
+        async refresh() {
+          if (!this.namespaceId) {
+            this.timeline = [];
+            this.errorMsg = 'Set a namespace_id to rebuild the belief timeline.';
+            return;
+          }
+          this.loading = true;
+          this.errorMsg = '';
+          try {
+            const resp = await signedFetch(undefined, '/api/admin/events', { query: this.eventsQs() });
+            if (!resp.ok) throw new Error((await resp.json()).error || 'events');
+            const data = await resp.json();
+            const items = data.items || [];
+            this.timeline = items
+              .filter((e) => this.BELIEF_EVENTS.includes(e.event_type))
+              .sort((a, b) => String(a.occurred_at).localeCompare(String(b.occurred_at)));
+          } catch (e) {
+            this.errorMsg = 'Glass Profile timeline: ' + (e.message || e);
+            this.timeline = [];
+          } finally {
+            this.loading = false;
+          }
+        },
+
+        // A belief was knowable at as_of only if its event occurred at or before it.
+        isKnownAtAsOf(evt) {
+          if (!this.asOf) return true;
+          return String(evt.occurred_at) <= this.asOf;
+        },
+
+        get heldAtAsOf() {
+          return this.timeline.filter((e) => this.isKnownAtAsOf(e)).length;
+        },
+      }));
     });
   </script>
 </body>
diff --git a/nce/mcp_stdio_tools.py b/nce/mcp_stdio_tools.py
index 4fdda88..bfd1a85 100644
--- a/nce/mcp_stdio_tools.py
+++ b/nce/mcp_stdio_tools.py
@@ -903,6 +903,82 @@ TOOLS = [
             "required": ["memory_id"],
         },
     ),
+    Tool(
+        name="explain_past_decision",
+        description=(
+            "[Phase II.5] Bi-temporal accountability — reconstruct the agent's belief "
+            "state as it stood at a past timestamp ('as_of'): the set of memories valid "
+            "at T, each annotated with the signed epistemic receipt (provenance event) "
+            "that was valid then.  Optionally run a *verified* counterfactual forked "
+            "replay (supply source_namespace_id, target_namespace_id, fork_seq and "
+            "expected_sha256) whose digest_match outcome proves the reconstruction is "
+            "byte-identically faithful."
+        ),
+        inputSchema={
+            "type": "object",
+            "properties": {
+                "namespace_id": {
+                    "type": "string",
+                    "description": "Namespace whose past belief state to reconstruct.",
+                },
+                "as_of": {
+                    "type": "string",
+                    "description": (
+                        "ISO 8601 timestamp (e.g. '2026-01-15T10:00:00Z').  Omit to "
+                        "reconstruct the current belief set."
+                    ),
+                },
+                "agent_id_filter": {
+                    "type": "string",
+                    "description": "Optional: restrict beliefs/receipts to this agent_id.",
+                },
+                "max_beliefs": {
+                    "type": "integer",
+                    "default": 200,
+                    "description": "Hard cap on the number of beliefs returned (default: 200).",
+                },
+                "source_namespace_id": {
+                    "type": "string",
+                    "description": "Counterfactual: namespace to replay events FROM.",
+                },
+                "target_namespace_id": {
+                    "type": "string",
+                    "description": "Counterfactual: empty namespace to replay events INTO.",
+                },
+                "fork_seq": {
+                    "type": "integer",
+                    "description": "Counterfactual: replay events with event_seq <= fork_seq.",
+                },
+                "start_seq": {
+                    "type": "integer",
+                    "default": 1,
+                    "description": "Counterfactual: inclusive lower bound on event_seq.",
+                },
+                "replay_mode": {
+                    "type": "string",
+                    "enum": ["deterministic", "re-execute"],
+                    "default": "deterministic",
+                    "description": "Counterfactual replay mode (default: deterministic).",
+                },
+                "config_overrides": {
+                    "type": "object",
+                    "description": "Counterfactual: optional re-execute config overrides.",
+                },
+                "expected_sha256": {
+                    "type": "string",
+                    "description": (
+                        "Counterfactual: 64-char hex checksum over the canonical fork "
+                        "request (required when a fork is requested)."
+                    ),
+                },
+                "admin_api_key": {
+                    "type": "string",
+                    "description": "Server-side admin API key for elevated access",
+                },
+            },
+            "required": ["namespace_id", "admin_api_key"],
+        },
+    ),
     Tool(
         name="a2a_create_grant",
         description=(
diff --git a/nce/replay_mcp_handlers.py b/nce/replay_mcp_handlers.py
index 02b037d..6210935 100644
--- a/nce/replay_mcp_handlers.py
+++ b/nce/replay_mcp_handlers.py
@@ -184,3 +184,146 @@ async def handle_explain_memory(engine: NCEEngine, arguments: dict[str, Any]) ->
         "verified": evt["verified"],
     }
     return json.dumps(receipt)
+
+
+@mcp_handler
+async def handle_explain_past_decision(engine: NCEEngine, arguments: dict[str, Any]) -> str:
+    """[Phase II.5] Bi-temporal "explain-my-past-advice".
+
+    Reconstructs the agent's belief state *as it stood* at ``as_of`` (the memories
+    valid at T) and attaches the signed epistemic receipt — the provenance event
+    valid at T — to each belief.  When a counterfactual fork is requested
+    (``source_namespace_id`` + ``target_namespace_id`` + ``fork_seq``), a *verified*
+    forked replay is run and its ``digest_match`` outcome is returned so the
+    reconstruction is provably faithful rather than hand-waved.
+    """
+    from nce.db_utils import scoped_pg_session
+    from nce.models import FrozenForkConfig, ReplayForkRequest
+    from nce.replay import ForkedReplay, _create_run, get_event_provenance, get_run_status
+    from nce.state_digest import compute_namespace_state_digest
+    from nce.temporal import as_of_query, parse_as_of
+
+    namespace_id = uuid.UUID(arguments["namespace_id"])
+    as_of_dt = parse_as_of(arguments.get("as_of"))
+    agent_filter = arguments.get("agent_id_filter")
+    max_beliefs = int(arguments.get("max_beliefs", 200))
+
+    # ── 1. Reconstruct the belief set valid at T (bi-temporal as_of read) ──
+    clause, as_of_params = as_of_query("", as_of_dt, start_index=2)
+    agent_clause = ""
+    params: list[Any] = [namespace_id, *as_of_params]
+    if agent_filter:
+        agent_clause = f"AND agent_id = ${len(params) + 1}"
+        params.append(agent_filter)
+
+    sql = f"""
+        SELECT id, agent_id, memory_type, assertion_type,
+               valid_from, valid_to, created_at
+        FROM memories
+        WHERE namespace_id = $1 {clause} {agent_clause}
+        ORDER BY valid_from ASC, id ASC
+        LIMIT {max_beliefs}
+    """
+    async with scoped_pg_session(engine.pg_pool, namespace_id) as conn:
+        belief_rows = await conn.fetch(sql, *params)
+
+    # ── 2. Attach the signed receipt valid at T to each belief ──
+    beliefs: list[dict[str, Any]] = []
+    for row in belief_rows:
+        memory_id = row["id"]
+        provenance = await get_event_provenance(engine.pg_pool, memory_id)
+        # Only receipts that existed *at or before* T were knowable then.
+        valid_chain = [
+            evt
+            for evt in provenance.get("chain", [])
+            if as_of_dt is None or evt["occurred_at"] <= as_of_dt.isoformat()
+        ]
+        receipt = valid_chain[-1] if valid_chain else None
+        beliefs.append(
+            {
+                "memory_id": str(memory_id),
+                "agent_id": row["agent_id"],
+                "memory_type": row["memory_type"],
+                "assertion_type": row["assertion_type"],
+                "valid_from": row["valid_from"].isoformat() if row["valid_from"] else None,
+                "valid_to": row["valid_to"].isoformat() if row["valid_to"] else None,
+                "receipt": (
+                    {
+                        "event_seq": receipt["event_seq"],
+                        "occurred_at": receipt["occurred_at"],
+                        "signature": receipt["signature"],
+                        "verified": receipt["verified"],
+                    }
+                    if receipt
+                    else None
+                ),
+            }
+        )
+
+    response: dict[str, Any] = {
+        "namespace_id": str(namespace_id),
+        "as_of": as_of_dt.isoformat() if as_of_dt else None,
+        "belief_count": len(beliefs),
+        "beliefs": beliefs,
+    }
+
+    # ── 3. Optional counterfactual: a VERIFIED forked replay (digest_match) ──
+    if all(k in arguments for k in ("source_namespace_id", "target_namespace_id", "fork_seq")):
+        fork_req = ReplayForkRequest.model_validate(
+            {
+                "source_namespace_id": arguments["source_namespace_id"],
+                "target_namespace_id": arguments["target_namespace_id"],
+                "fork_seq": int(arguments["fork_seq"]),
+                "start_seq": int(arguments.get("start_seq", 1)),
+                "replay_mode": arguments.get("replay_mode", "deterministic"),
+                "config_overrides": arguments.get("config_overrides"),
+                "agent_id_filter": agent_filter,
+                "expected_sha256": arguments["expected_sha256"],
+            }
+        )
+        frozen_config = FrozenForkConfig.from_request(fork_req)
+
+        async with engine.pg_pool.acquire(timeout=10.0) as pre_conn:
+            fork_run_id = await _create_run(
+                pre_conn,
+                source_namespace_id=frozen_config.source_namespace_id,
+                target_namespace_id=frozen_config.target_namespace_id,
+                mode="forked",
+                replay_mode=frozen_config.replay_mode,
+                start_seq=frozen_config.start_seq,
+                end_seq=frozen_config.fork_seq,
+                divergence_seq=frozen_config.fork_seq,
+                config_overrides=frozen_config.overrides_dict,
+            )
+
+        replay = ForkedReplay(pool=engine.pg_pool)
+        async for _ in replay.execute(frozen_config=frozen_config, _existing_run_id=fork_run_id):
+            pass
+
+        # ForkedReplay does not compute state digests itself (only ReconstructiveReplay
+        # does).  Verify the fork is byte-identically faithful by comparing the canonical
+        # state digest of source vs. target *as of the fork point* — the same mechanism
+        # ReconstructiveReplay uses.  This is what makes the counterfactual provable.
+        async with engine.pg_pool.acquire(timeout=10.0) as digest_conn:
+            fork_point_ts = await digest_conn.fetchval(
+                "SELECT occurred_at FROM event_log WHERE namespace_id = $1 AND event_seq = $2",
+                frozen_config.source_namespace_id,
+                frozen_config.fork_seq,
+            )
+            source_digest = await compute_namespace_state_digest(
+                digest_conn, frozen_config.source_namespace_id, as_of=fork_point_ts
+            )
+            target_digest = await compute_namespace_state_digest(
+                digest_conn, frozen_config.target_namespace_id, as_of=fork_point_ts
+            )
+
+        status = await get_run_status(engine.pg_pool, fork_run_id)
+        response["counterfactual"] = {
+            "run_id": str(fork_run_id),
+            "status": status["status"],
+            "digest_match": source_digest == target_digest,
+            "source_state_digest": source_digest,
+            "target_state_digest": target_digest,
+        }
+
+    return json.dumps(response, default=str)
diff --git a/nce/tool_registry.py b/nce/tool_registry.py
index 360308e..d1aeef0 100644
--- a/nce/tool_registry.py
+++ b/nce/tool_registry.py
@@ -236,6 +236,11 @@ TOOL_REGISTRY: dict[str, ToolSpec] = {
     "explain_memory": ToolSpec(
         _h(replay_mcp_handlers, "handle_explain_memory"),
     ),
+    "explain_past_decision": ToolSpec(
+        _h(replay_mcp_handlers, "handle_explain_past_decision"),
+        admin_only=True,
+        mutation=True,
+    ),
     # ------------------------------------------------------------------
     # Agent-to-Agent (A2A) grant tools
     # ------------------------------------------------------------------
diff --git a/tests/test_explain_past_decision.py b/tests/test_explain_past_decision.py
new file mode 100644
index 0000000..9fe4cc5
--- /dev/null
+++ b/tests/test_explain_past_decision.py
@@ -0,0 +1,365 @@
+"""Acceptance test for Batch 43 — II.5 Bi-temporal Accountability.
+
+`explain_past_decision(as_of=T)` must:
+  1. Reconstruct the *belief set valid at T* (memories whose temporal validity
+     window covers T) with each belief annotated by the signed epistemic receipt
+     that was valid then; and
+  2. when a counterfactual fork is requested, run a forked replay and return a
+     ``digest_match``-verified alternate state (source vs. target canonical state
+     digest taken as of the fork point).
+
+This exercises the real handler against live Postgres/Mongo (integration), reusing
+the proven replay monkeypatch shims from ``test_replay_handlers_integration``.
+"""
+
+from __future__ import annotations
+
+import hashlib
+import json
+import uuid
+from datetime import datetime, timedelta, timezone
+
+import pytest
+from nce.db_utils import scoped_pg_session
+from nce.event_log import append_event
+
+
+class _AcquireContext:
+    """Acquire wrapper that registers an *idempotent* json/jsonb codec.
+
+    ``event_log.append_event`` pre-serialises ``params`` to a JSON string before
+    binding it to a ``jsonb`` parameter.  A naive ``encoder=json.dumps`` codec
+    would double-encode that string (storing a quoted JSON scalar), which breaks
+    ``params->>'memory_id'`` lookups in ``get_event_provenance``.  Passing strings
+    through unchanged keeps the codec safe for both already-serialised and raw
+    values, while still decoding reads so handlers see dicts.
+    """
+
+    def __init__(self, ctx):
+        self.ctx = ctx
+        self.conn = None
+
+    @staticmethod
+    def _enc(v):
+        return v if isinstance(v, str) else json.dumps(v)
+
+    async def __aenter__(self):
+        self.conn = await self.ctx.__aenter__()
+        for schema_type in ("jsonb", "json"):
+            try:
+                await self.conn.set_type_codec(
+                    schema_type,
+                    encoder=self._enc,
+                    decoder=json.loads,
+                    schema="pg_catalog",
+                )
+            except Exception:
+                pass
+        return self.conn
+
+    async def __aexit__(self, exc_type, exc_val, exc_tb):
+        return await self.ctx.__aexit__(exc_type, exc_val, exc_tb)
+
+
+class PoolProxy:
+    """Pool wrapper whose ``acquire`` yields connections with the idempotent codec."""
+
+    def __init__(self, pool):
+        self._pool = pool
+
+    def __getattr__(self, name):
+        return getattr(self._pool, name)
+
+    def acquire(self, *args, **kwargs):
+        return _AcquireContext(self._pool.acquire(*args, **kwargs))
+
+
+class _EngineStub:
+    """Minimal stand-in exposing only ``pg_pool`` — all the handler touches."""
+
+    def __init__(self, pool: PoolProxy) -> None:
+        self.pg_pool = pool
+
+
+def _fork_checksum(
+    *,
+    source_ns: uuid.UUID,
+    target_ns: uuid.UUID,
+    fork_seq: int,
+    start_seq: int = 1,
+) -> str:
+    """Recompute the canonical payload checksum the handler/model verifies."""
+    from nce.signing import canonical_json
+
+    payload = {
+        "source_namespace_id": str(source_ns),
+        "target_namespace_id": str(target_ns),
+        "fork_seq": fork_seq,
+        "start_seq": start_seq,
+        "replay_mode": "deterministic",
+        "config_overrides": None,
+        "agent_id_filter": None,
+    }
+    return hashlib.sha256(canonical_json(payload)).hexdigest()
+
+
+@pytest.mark.integration
+@pytest.mark.asyncio
+async def test_explain_past_decision_belief_set_and_verified_fork(
+    pg_pool, make_namespace, monkeypatch
+) -> None:
+    import os
+
+    from bson import ObjectId
+    from motor.motor_asyncio import AsyncIOMotorClient
+
+    pool_proxy = PoolProxy(pg_pool)
+    engine = _EngineStub(pool_proxy)
+
+    source_ns = await make_namespace()
+    target_ns = await make_namespace()
+    agent_id = "test-agent"
+
+    # ── Seed one episodic memory in Mongo + Postgres in the source namespace ──
+    src_oid = ObjectId()
+    src_payload_ref = str(src_oid)
+    mongo_client = AsyncIOMotorClient(os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017"))
+    db = mongo_client.memory_archive
+    await db.episodes.insert_one(
+        {
+            "_id": src_oid,
+            "raw_data": "Bi-temporal belief content",
+            "source": "test_explain_past_decision",
+        }
+    )
+
+    src_memory_id = uuid.uuid4()
+    embedding = [0.1] * 768
+    # The belief becomes valid 2 days ago; T is "1 day ago" — so it is valid at T.
+    valid_from = (datetime.now(timezone.utc) - timedelta(days=2)).replace(microsecond=0)
+    as_of_t = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0)
+    # A memory created AFTER T must NOT appear in the belief set valid at T.
+    future_memory_id = uuid.uuid4()
+    future_valid_from = datetime.now(timezone.utc).replace(microsecond=0)
+
+    async with scoped_pg_session(pool_proxy, source_ns) as conn:
+        await conn.execute(
+            """
+            INSERT INTO memories (id, namespace_id, agent_id, embedding, assertion_type,
+                                  memory_type, payload_ref, metadata, valid_from, created_at)
+            VALUES ($1, $2, $3, $4::vector, 'fact', 'episodic', $5, $6::jsonb, $7, $7)
+            """,
+            src_memory_id,
+            source_ns,
+            agent_id,
+            json.dumps(embedding),
+            src_payload_ref,
+            json.dumps({"source_text": "Bi-temporal belief"}),
+            valid_from,
+        )
+        await conn.execute(
+            """
+            INSERT INTO memories (id, namespace_id, agent_id, embedding, assertion_type,
+                                  memory_type, payload_ref, metadata, valid_from, created_at)
+            VALUES ($1, $2, $3, $4::vector, 'fact', 'episodic', $5, $6::jsonb, $7, $7)
+            """,
+            future_memory_id,
+            source_ns,
+            agent_id,
+            json.dumps(embedding),
+            "000000000000000000000099",
+            json.dumps({"source_text": "Learned later"}),
+            future_valid_from,
+        )
+        store_params = {
+            "saga_id": str(uuid.uuid4()),
+            "memory_id": str(src_memory_id),
+            "payload_ref": src_payload_ref,
+            "assertion_type": "fact",
+            "entities": [],
+            "triplets": [],
+            "source_namespace_id": str(source_ns),
+        }
+        await conn.execute("ALTER TABLE event_log DISABLE TRIGGER trg_event_log_worm")
+        try:
+            res = await append_event(
+                conn=conn,
+                namespace_id=source_ns,
+                agent_id=agent_id,
+                event_type="store_memory",
+                params=store_params,
+            )
+            # Backdate the creating event to valid_from so its signed receipt is
+            # "valid at T" (T is one day after the belief was formed).
+            from nce.event_log import (
+                _GENESIS_SENTINEL,
+                _build_signing_fields,
+                _compute_chain_hash,
+                _compute_content_hash,
+            )
+            from nce.signing import get_active_key, sign_fields
+
+            key_id, raw_key = await get_active_key(conn)
+            row = await conn.fetchrow("SELECT * FROM event_log WHERE id = $1", res.event_id)
+            signing_fields = _build_signing_fields(
+                event_id=row["id"],
+                namespace_id=row["namespace_id"],
+                agent_id=row["agent_id"],
+                event_type=row["event_type"],
+                event_seq=row["event_seq"],
+                occurred_at_iso=valid_from.isoformat(),
+                params=store_params,
+                parent_event_id=row["parent_event_id"],
+                prev_chain_hash_hex=_GENESIS_SENTINEL.hex(),
+            )
+            sig = sign_fields(signing_fields, raw_key)
+            c_hash = _compute_content_hash(signing_fields=signing_fields)
+            ch_hash = _compute_chain_hash(
+                content_hash=c_hash, previous_chain_hash=_GENESIS_SENTINEL
+            )
+            await conn.execute(
+                "UPDATE event_log SET occurred_at = $1, signature = $2, chain_hash = $3 WHERE id = $4",
+                valid_from,
+                sig,
+                ch_hash,
+                row["id"],
+            )
+        finally:
+            await conn.execute("ALTER TABLE event_log ENABLE TRIGGER trg_event_log_worm")
+
+    # ── Replay shims (identical to the proven integration suite) ──
+    import nce.replay as replay_mod
+
+    class ConnectionProxy:
+        def __init__(self, c):
+            self._conn = c
+
+        def __getattr__(self, name):
+            return getattr(self._conn, name)
+
+        async def execute(self, query, *args, **kwargs):
+            new_args = list(args)
+            new_query = query
+            if "INSERT INTO memories" in query:
+                if len(new_args) >= 4 and isinstance(new_args[3], list):
+                    new_args[3] = json.dumps(new_args[3])
+                new_query = new_query.replace("$4,", "$4::vector,")
+                for i, val in enumerate(new_args):
+                    if i == 3:
+                        continue
+                    if isinstance(val, str) and (val.startswith("{") or val.startswith("[")):
+                        try:
+                            new_args[i] = json.loads(val)
+                        except Exception:
+                            pass
+            return await self._conn.execute(new_query, *new_args, **kwargs)
+
+        async def fetchrow(self, query, *args, **kwargs):
+            row = await self._conn.fetchrow(query, *args, **kwargs)
+            if row is None:
+                return None
+            d = dict(row)
+            # The fork's read connection may not have the jsonb codec applied;
+            # decode JSON-text columns the store_memory handler will dict()/parse.
+            for col in ("metadata", "params", "result_summary"):
+                val = d.get(col)
+                if isinstance(val, str):
+                    try:
+                        d[col] = json.loads(val)
+                    except Exception:
+                        pass
+            return d
+
+    original_dispatch = replay_mod._dispatch_and_apply_event
+
+    async def mock_dispatch(
+        write_conn,
+        src,
+        target_namespace_id,
+        llm_payload,
+        config_overrides,
+        run_id,
+        source_namespace_id,
+        **kwargs,
+    ):
+        proxy = ConnectionProxy(write_conn)
+        return await original_dispatch(
+            proxy,
+            src=src,
+            target_namespace_id=target_namespace_id,
+            llm_payload=llm_payload,
+            config_overrides=config_overrides,
+            run_id=run_id,
+            source_namespace_id=source_namespace_id,
+            **kwargs,
+        )
+
+    monkeypatch.setattr(replay_mod, "_dispatch_and_apply_event", mock_dispatch)
+
+    original_build_query = replay_mod._build_event_query
+
+    def mock_build_query(**kwargs):
+        sql, args = original_build_query(**kwargs)
+        sql = sql.replace("SELECT\n            id,", "SELECT\n            id, namespace_id,")
+        return sql, args
+
+    monkeypatch.setattr(replay_mod, "_build_event_query", mock_build_query)
+
+    original_to_event_row = replay_mod._record_to_event_row
+
+    def mock_to_event_row(record):
+        rec_dict = dict(record)
+        params = rec_dict.get("params")
+        if isinstance(params, str):
+            rec_dict["params"] = json.loads(params)
+        result_summary = rec_dict.get("result_summary")
+        if isinstance(result_summary, str):
+            rec_dict["result_summary"] = json.loads(result_summary)
+        return original_to_event_row(rec_dict)
+
+    monkeypatch.setattr(replay_mod, "_record_to_event_row", mock_to_event_row)
+
+    # ── Call the handler under test ──
+    from nce.replay_mcp_handlers import handle_explain_past_decision
+
+    expected_sha = _fork_checksum(source_ns=source_ns, target_ns=target_ns, fork_seq=1, start_seq=1)
+    raw = await handle_explain_past_decision(
+        engine,
+        {
+            "namespace_id": str(source_ns),
+            "as_of": as_of_t.isoformat(),
+            # counterfactual: verified forked replay
+            "source_namespace_id": str(source_ns),
+            "target_namespace_id": str(target_ns),
+            "fork_seq": 1,
+            "start_seq": 1,
+            "replay_mode": "deterministic",
+            "expected_sha256": expected_sha,
+        },
+    )
+    result = json.loads(raw)
+
+    # 1. Belief set valid at T: the day-2 belief is present, the future one is NOT.
+    belief_ids = {b["memory_id"] for b in result["beliefs"]}
+    assert str(src_memory_id) in belief_ids, "belief valid at T must be reconstructed"
+    assert str(future_memory_id) not in belief_ids, (
+        "a memory only valid after T must not leak into the past belief set"
+    )
+    assert result["belief_count"] == 1
+
+    # Each reconstructed belief carries its signed epistemic receipt valid at T.
+    belief = next(b for b in result["beliefs"] if b["memory_id"] == str(src_memory_id))
+    assert belief["receipt"] is not None
+    assert belief["receipt"]["verified"] is True
+    assert belief["receipt"]["event_seq"] >= 1
+
+    # 2. The counterfactual fork is digest_match-verified.
+    cf = result["counterfactual"]
+    assert cf["status"] == "success"
+    assert cf["digest_match"] is True, (
+        f"fork not faithful: src={cf['source_state_digest']} tgt={cf['target_state_digest']}"
+    )
+    assert cf["source_state_digest"] == cf["target_state_digest"]
+
+    await db.episodes.delete_one({"_id": src_oid})
+    mongo_client.close()
diff --git a/tests/test_tool_registry.py b/tests/test_tool_registry.py
index 01094ce..01fa148 100644
--- a/tests/test_tool_registry.py
+++ b/tests/test_tool_registry.py
@@ -25,10 +25,10 @@ from nce.tool_registry import (
 # Cardinality
 # ---------------------------------------------------------------------------
 
-_EXPECTED_TOTAL = 63
+_EXPECTED_TOTAL = 64
 
 
-def test_registry_has_63_entries():
+def test_registry_has_expected_entries():
     assert len(TOOL_REGISTRY) == _EXPECTED_TOTAL, (
         f"Expected {_EXPECTED_TOTAL} tools, got {len(TOOL_REGISTRY)}. "
         f"Tools: {sorted(TOOL_REGISTRY)}"
@@ -83,6 +83,9 @@ _EXPECTED_MUTATION_TOOLS: frozenset[str] = frozenset(
         "a2a_update_grant_scopes",
         "unredact_memory",
         "replay_reconstruct",
+        # Batch 43 — bi-temporal accountability; optional counterfactual fork writes
+        # events into the target namespace, so the tool is a mutation.
+        "explain_past_decision",
         # DLQ mutations (2) — pre-existing omission corrected in code review
         "replay_dlq",
         "purge_dlq",
@@ -106,7 +109,7 @@ def test_mutation_tools_exact_match():
 
 
 def test_mutation_tools_count():
-    assert len(MUTATION_TOOLS) == 29
+    assert len(MUTATION_TOOLS) == 30
 
 
 # ---------------------------------------------------------------------------
@@ -148,6 +151,7 @@ _EXPECTED_ADMIN_ONLY: frozenset[str] = frozenset(
         "replay_reconstruct",
         "replay_fork",
         "replay_status",
+        "explain_past_decision",
         "d365_sync_now",
         "d365_list_sla_breaches",
     }
@@ -162,7 +166,7 @@ def test_admin_only_tools_exact_match():
 
 
 def test_admin_only_tools_count():
-    assert len(ADMIN_ONLY_TOOLS) == 7
+    assert len(ADMIN_ONLY_TOOLS) == 8
 
 
 # ---------------------------------------------------------------------------
@@ -315,6 +319,10 @@ def test_toolspec_is_frozen():
             "explain_memory",
             {"mutation": False, "cacheable": False, "admin_only": False, "migration": False},
         ),
+        (
+            "explain_past_decision",
+            {"mutation": True, "cacheable": False, "admin_only": True, "migration": False},
+        ),
         # a2a
         (
             "a2a_create_grant",
```
