# Diff Reference for Batch 55

```diff
diff --git a/deploy/README.md b/deploy/README.md
index e8eacfd..98619a0 100644
--- a/deploy/README.md
+++ b/deploy/README.md
@@ -63,6 +63,33 @@ The multiuser compose file publishes MinIO on host **9000** (API) and **9001** (
 
 ---
 
+## Secrets management (production) — VI.1
+
+`scripts/bootstrap-compose-secrets.py` is the **development / single-host** path: it generates strong values into `deploy/compose.stack.env.generated`. **Do not commit that file, and do not use it as the production source of truth.**
+
+In production, source secrets from a real **secret manager** — HashiCorp Vault, AWS Secrets Manager, or Azure Key Vault — and have your orchestrator inject them into each container's environment. Plaintext secrets must never live in a committed compose/`.env` file.
+
+NCE exposes a thin **secrets-provider seam** (`nce/config.py`) so this is a drop-in:
+
+| Piece | Purpose |
+|-------|---------|
+| `SecretsProvider` | Abstract seam — `get_secret(name) -> str | None`. |
+| `EnvSecretsProvider` (default) | Reads from the process environment. The orchestrator feeds the env from your secret manager. |
+| `resolve_secret(name, default=...)` | Resolves through the active provider, then falls back to env. |
+| `set_secrets_provider(...)` | Installs a concrete manager-backed provider at startup. |
+| `NCE_SECRETS_PROVIDER` | Selects the backend (`env` by default). |
+
+**`NCE_MASTER_KEY` is environment / secret-manager only (R3).** `resolve_secret` refuses to route the master key through any non-environment provider, and `nce.config` reads it straight from the environment — it is never stored in or returned from a database / SettingsStore.
+
+**Production guardrails** (enforced by `cfg.validate()` and at import):
+
+- `NCE_LOAD_DOTENV` must be `false` — no `.env` is loaded at runtime.
+- `NCE_ALLOW_ADMIN_DOTENV_PERSIST` must be `false` — the admin UI cannot persist connector/datastore secrets to a local `.env`. `cfg.validate()` raises if it is true under `NCE_ENV=prod`.
+
+> Default-path stacks that still rely on `bootstrap-compose-secrets.py` are acceptable for dev and air-gapped single-host installs; for managed/cloud production, prefer the secret-manager injection above and leave `compose.stack.env.generated` unused.
+
+---
+
 ## D2 / D7 — Cognitive model
 
 - Image **`ghcr.io/sindrehaugen/nce-cognitive:v1`** on **11435**.
diff --git a/nce/config.py b/nce/config.py
index d1576f1..f6a3947 100644
--- a/nce/config.py
+++ b/nce/config.py
@@ -170,6 +170,99 @@ def _float_env(name: str, default: float, *, minimum: float | None = None) -> fl
     return value
 
 
+# ---------------------------------------------------------------------------
+# Secrets-provider seam (VI.1 / R3)
+# ---------------------------------------------------------------------------
+#
+# Production should source secrets from a real manager (HashiCorp Vault, AWS
+# Secrets Manager, Azure Key Vault) rather than committed compose/.env files.
+# ``scripts/bootstrap-compose-secrets.py`` remains the *dev* path.
+#
+# This is a thin abstraction only: a ``SecretsProvider`` protocol plus an
+# env-backed default provider. Real-manager providers are out of scope here
+# (no Vault/AWS/Azure SDK dependency is added) — the seam exists so a concrete
+# provider can be slotted in without touching every call site.
+#
+# Invariant (R3): ``NCE_MASTER_KEY`` is **secret-manager / environment only**.
+# It must never be read from a database or SettingsStore. ``resolve_secret``
+# therefore refuses to route the master key through any non-environment
+# provider, regardless of which provider is configured.
+
+
+class SecretsProvider:
+    """Abstract seam for resolving named secrets at runtime.
+
+    Implementations return the secret value for *name* or ``None`` when the
+    secret is not managed by this provider (the caller then falls back to its
+    configured default).
+    """
+
+    name: str = "abstract"
+
+    def get_secret(self, name: str) -> str | None:  # pragma: no cover - interface
+        raise NotImplementedError
+
+
+class EnvSecretsProvider(SecretsProvider):
+    """Default provider — reads secrets from the process environment.
+
+    This is the dev path and the safe production fallback: secrets are injected
+    into the environment by the orchestrator (which may itself be fed by a real
+    secret manager) rather than read from a committed file at runtime.
+    """
+
+    name = "env"
+
+    def get_secret(self, name: str) -> str | None:
+        raw = os.environ.get(name)
+        if raw is None:
+            return None
+        stripped = raw.strip()
+        return stripped or None
+
+
+# Names that must only ever come from the environment / secret manager and are
+# never permitted to flow through a database- or file-backed provider (R3).
+_ENV_ONLY_SECRETS: frozenset[str] = frozenset({"NCE_MASTER_KEY"})
+
+_DEFAULT_SECRETS_PROVIDER = EnvSecretsProvider()
+_SECRETS_PROVIDER: SecretsProvider = _DEFAULT_SECRETS_PROVIDER
+
+
+def get_secrets_provider() -> SecretsProvider:
+    """Return the active secrets provider (env-backed by default)."""
+    return _SECRETS_PROVIDER
+
+
+def set_secrets_provider(provider: SecretsProvider | None) -> None:
+    """Install a secrets provider (pass ``None`` to restore the env default).
+
+    The seam keeps provider wiring in one place; production deployments can
+    install a Vault / AWS / Azure provider at startup without changing call
+    sites. The env-only invariant in :func:`resolve_secret` still applies.
+    """
+    global _SECRETS_PROVIDER
+    _SECRETS_PROVIDER = provider or _DEFAULT_SECRETS_PROVIDER
+
+
+def resolve_secret(name: str, *, default: str | None = None) -> str | None:
+    """Resolve *name* via the active secrets provider, then fall back to env.
+
+    ``NCE_MASTER_KEY`` (and any other env-only secret) is always read straight
+    from the environment, bypassing the provider entirely so it can never be
+    sourced from a database / SettingsStore (R3).
+    """
+    if name in _ENV_ONLY_SECRETS:
+        raw = os.environ.get(name)
+        value = raw.strip() if raw is not None else None
+        return value or default
+
+    value = _SECRETS_PROVIDER.get_secret(name)
+    if value is None:
+        return default
+    return value
+
+
 class _EmbeddingConfig:
     """
     Embedding / pgvector dimension. Must stay aligned with ``memories.embedding`` and
@@ -391,6 +484,11 @@ class _Config:
     NCE_ADMIN_USERNAME: str = os.getenv("NCE_ADMIN_USERNAME", "")
     NCE_ADMIN_PASSWORD: str = os.getenv("NCE_ADMIN_PASSWORD", "")
     NCE_MASTER_KEY: str = os.getenv("NCE_MASTER_KEY", "")
+    # Selects the secrets-provider backend (VI.1). "env" (default) reads secrets
+    # from the process environment — the orchestrator may feed those from a real
+    # manager (Vault / AWS Secrets Manager / Azure Key Vault). See resolve_secret;
+    # NCE_MASTER_KEY is always environment-only regardless of this setting (R3).
+    NCE_SECRETS_PROVIDER: str = (os.getenv("NCE_SECRETS_PROVIDER") or "env").strip().lower()
     # When true, HTTP admin ``HMACAuthMiddleware`` uses ``NonceStore(cfg.REDIS_URL)``
     # for replay protection across multiple admin replicas (see nce.auth).
     NCE_DISTRIBUTED_REPLAY: bool = _bool_env("NCE_DISTRIBUTED_REPLAY", False)
@@ -801,6 +899,38 @@ class _Config:
         # P1: D365 module — require secrets when enabled in production
         cls.validate_d365_config()
 
+        # P1: Secrets-provider seam — reject the dev dotenv-persist path in prod
+        cls.validate_secrets_provider()
+
+    @classmethod
+    def validate_secrets_provider(cls) -> None:
+        """Enforce the production secrets-provider posture (VI.1 / R3).
+
+        In production:
+          * the dev ``NCE_ALLOW_ADMIN_DOTENV_PERSIST`` path (admin UI writing
+            connector/datastore secrets to a local ``.env``) is rejected —
+            production must source secrets from a real manager, never a
+            committed/written file; and
+          * ``NCE_MASTER_KEY`` must resolve from the environment / secret
+            manager only — never through a database- or file-backed provider.
+        """
+        if not cls.IS_PROD:
+            return
+        if cls.NCE_ALLOW_ADMIN_DOTENV_PERSIST:
+            raise RuntimeError(
+                "CRITICAL CONFIGURATION FAILURE: NCE_ALLOW_ADMIN_DOTENV_PERSIST must be "
+                "false in production. Production secrets must come from a secret manager "
+                "(Vault / AWS Secrets Manager / Azure Key Vault) injected into the "
+                "environment, not written to a local .env file."
+            )
+        # R3: the master key is env-only; it must never be sourced from a store.
+        if "NCE_MASTER_KEY" not in _ENV_ONLY_SECRETS:
+            raise RuntimeError(
+                "CRITICAL CONFIGURATION FAILURE: NCE_MASTER_KEY is no longer pinned to "
+                "environment-only resolution. It must never be sourced from a database "
+                "or SettingsStore (R3)."
+            )
+
     @classmethod
     def validate_d365_config(cls) -> None:
         """Fail fast when D365 is enabled in production without required secrets."""
diff --git a/scripts/bootstrap-compose-secrets.py b/scripts/bootstrap-compose-secrets.py
index 5ec0723..6eb0a42 100644
--- a/scripts/bootstrap-compose-secrets.py
+++ b/scripts/bootstrap-compose-secrets.py
@@ -6,6 +6,14 @@ Writes deploy/compose.stack.env.generated (loaded after deploy/compose.stack.env
 so production values override weak defaults without editing the tracked base file.
 
 Idempotent: only replaces keys that still look weak compared to compose.stack.env.
+
+Scope (VI.1): this is the **development / single-host** secrets path. Production
+deployments should source secrets from a real manager (HashiCorp Vault, AWS
+Secrets Manager, Azure Key Vault) injected into the container environment via
+the secrets-provider seam (NCE_SECRETS_PROVIDER / nce.config.resolve_secret),
+rather than generating them into a local env file. NCE_MASTER_KEY is always
+environment / secret-manager only and is never read from a database or
+SettingsStore (R3). See deploy/README.md "Secrets management (production)".
 """
 
 from __future__ import annotations
@@ -26,38 +34,48 @@ HEADER = """# AUTO-GENERATED — do not commit real secrets. Added by scripts/bo
 KEY_SPECS: list[tuple[str, Callable[[str], bool]]] = [
     (
         "NCE_MASTER_KEY",
-        lambda v: _weak(v, min_len=32)
-        or "dev" in v.lower()
-        or "change" in v.lower()
-        or "replace_me" in v.lower(),
+        lambda v: (
+            _weak(v, min_len=32)
+            or "dev" in v.lower()
+            or "change" in v.lower()
+            or "replace_me" in v.lower()
+        ),
     ),
     (
         "NCE_API_KEY",
-        lambda v: _weak(v, min_len=16)
-        or "change" in v.lower()
-        or v.lower().startswith("dev-")
-        or "replace_me" in v.lower(),
+        lambda v: (
+            _weak(v, min_len=16)
+            or "change" in v.lower()
+            or v.lower().startswith("dev-")
+            or "replace_me" in v.lower()
+        ),
     ),
     (
         "NCE_ADMIN_API_KEY",
-        lambda v: _weak(v, min_len=16)
-        or "change" in v.lower()
-        or v.lower().startswith("dev-")
-        or "replace_me" in v.lower(),
+        lambda v: (
+            _weak(v, min_len=16)
+            or "change" in v.lower()
+            or v.lower().startswith("dev-")
+            or "replace_me" in v.lower()
+        ),
     ),
     (
         "NCE_MCP_API_KEY",
-        lambda v: _weak(v, min_len=16)
-        or "change" in v.lower()
-        or v.lower().startswith("dev-")
-        or "replace_me" in v.lower(),
+        lambda v: (
+            _weak(v, min_len=16)
+            or "change" in v.lower()
+            or v.lower().startswith("dev-")
+            or "replace_me" in v.lower()
+        ),
     ),
     (
         "NCE_APP_PASSWORD",
-        lambda v: _weak(v, min_len=8)
-        or "change" in v.lower()
-        or "replace_me" in v.lower()
-        or v == "nce_app_secret",
+        lambda v: (
+            _weak(v, min_len=8)
+            or "change" in v.lower()
+            or "replace_me" in v.lower()
+            or v == "nce_app_secret"
+        ),
     ),
     (
         "NCE_JWT_SECRET",
@@ -65,10 +83,12 @@ KEY_SPECS: list[tuple[str, Callable[[str], bool]]] = [
     ),
     (
         "NCE_ADMIN_PASSWORD",
-        lambda v: _weak(v, min_len=8)
-        or v.lower() in ("changeme", "admin", "password")
-        or "replace_me" in v.lower()
-        or not v.startswith("$pbkdf2$"),
+        lambda v: (
+            _weak(v, min_len=8)
+            or v.lower() in ("changeme", "admin", "password")
+            or "replace_me" in v.lower()
+            or not v.startswith("$pbkdf2$")
+        ),
     ),
     (
         "DROPBOX_APP_SECRET",
@@ -109,6 +129,7 @@ def _parse_env_text(text: str) -> dict[str, str]:
 def _hash_pbkdf2(password: str) -> str:
     import hashlib
     import os
+
     iters = 600000
     salt = os.urandom(16)
     dk = hashlib.pbkdf2_hmac(
diff --git a/tests/test_secrets_provider_seam.py b/tests/test_secrets_provider_seam.py
new file mode 100644
index 0000000..f6bc45f
--- /dev/null
+++ b/tests/test_secrets_provider_seam.py
@@ -0,0 +1,205 @@
+"""Secrets-provider seam + production secret-handling guardrails (Batch 55 / VI.1 / R3).
+
+Asserts:
+  (a) the secrets seam resolves named secrets via the provider abstraction
+      (an installed provider is consulted; env is the fallback); and
+  (b) production config rejects the dev dotenv-persist path AND never sources
+      ``NCE_MASTER_KEY`` through a non-environment provider.
+
+The (a) tests run in-process against ``nce.config`` (importable under the dev
+test env). The (b) tests boot a fresh interpreter with ``NCE_ENV=prod`` —
+mirroring tests/test_config_prod_hardening.py — because the prod guardrails are
+import-time / ``validate()``-time and must not mutate the in-process singleton.
+"""
+
+from __future__ import annotations
+
+import os
+import subprocess
+import sys
+from pathlib import Path
+
+import nce.config as config
+from nce.config import (
+    EnvSecretsProvider,
+    SecretsProvider,
+    get_secrets_provider,
+    resolve_secret,
+    set_secrets_provider,
+)
+
+_REPO_ROOT = Path(__file__).resolve().parents[1]
+
+
+# ---------------------------------------------------------------------------
+# (a) The seam resolves via the provider abstraction
+# ---------------------------------------------------------------------------
+
+
+class _RecordingProvider(SecretsProvider):
+    """A non-env provider used to prove resolution flows through the seam."""
+
+    name = "recording"
+
+    def __init__(self, values: dict[str, str]) -> None:
+        self._values = values
+        self.seen: list[str] = []
+
+    def get_secret(self, name: str) -> str | None:
+        self.seen.append(name)
+        return self._values.get(name)
+
+
+def test_default_provider_is_env_backed() -> None:
+    assert isinstance(get_secrets_provider(), EnvSecretsProvider)
+    assert get_secrets_provider().name == "env"
+
+
+def test_seam_resolves_through_installed_provider(monkeypatch) -> None:
+    monkeypatch.delenv("NCE_DEMO_SECRET", raising=False)
+    provider = _RecordingProvider({"NCE_DEMO_SECRET": "from-manager"})
+    try:
+        set_secrets_provider(provider)
+        # Resolution must consult the installed provider, not the environment.
+        assert resolve_secret("NCE_DEMO_SECRET") == "from-manager"
+        assert "NCE_DEMO_SECRET" in provider.seen
+    finally:
+        set_secrets_provider(None)
+    # Restored to the env-backed default.
+    assert isinstance(get_secrets_provider(), EnvSecretsProvider)
+
+
+def test_seam_falls_back_to_default_when_provider_misses(monkeypatch) -> None:
+    monkeypatch.delenv("NCE_ABSENT_SECRET", raising=False)
+    provider = _RecordingProvider({})  # returns None for everything
+    try:
+        set_secrets_provider(provider)
+        assert resolve_secret("NCE_ABSENT_SECRET", default="fallback") == "fallback"
+    finally:
+        set_secrets_provider(None)
+
+
+def test_env_provider_reads_environment(monkeypatch) -> None:
+    monkeypatch.setenv("NCE_ENV_BACKED_SECRET", "  value-with-space  ")
+    assert resolve_secret("NCE_ENV_BACKED_SECRET") == "value-with-space"
+
+
+def test_master_key_never_sourced_from_a_store(monkeypatch) -> None:
+    """R3: even with a non-env provider installed, NCE_MASTER_KEY bypasses it."""
+    monkeypatch.setenv("NCE_MASTER_KEY", "env-master-key-32-characters-min!!")
+    provider = _RecordingProvider({"NCE_MASTER_KEY": "store-supplied-DANGER"})
+    try:
+        set_secrets_provider(provider)
+        resolved = resolve_secret("NCE_MASTER_KEY")
+        # Must be the environment value, and the provider must NOT have been
+        # consulted for the master key at all.
+        assert resolved == "env-master-key-32-characters-min!!"
+        assert "NCE_MASTER_KEY" not in provider.seen
+    finally:
+        set_secrets_provider(None)
+    assert "NCE_MASTER_KEY" in config._ENV_ONLY_SECRETS
+
+
+# ---------------------------------------------------------------------------
+# (b) Production config rejects dotenv-persist (fresh interpreter)
+# ---------------------------------------------------------------------------
+
+
+def _prod_env() -> dict[str, str]:
+    env = os.environ.copy()
+    env.update(
+        {
+            "NCE_ENV": "prod",
+            "NCE_LOAD_DOTENV": "false",
+            "NCE_MASTER_KEY": "prod-master-key-32-characters-min!!",
+            "NCE_API_KEY": "prod-api-key-for-ci-tests-only",
+            "NCE_MCP_API_KEY": "prod-mcp-key-for-config-tests-only!!",
+            "NCE_MCP_NAMESPACE_ID": "00000000-0000-4000-8000-000000000001",
+            "NCE_ADMIN_API_KEY": "prod-admin-key-for-config-tests",
+            "NCE_ADMIN_USERNAME": "admin",
+            "NCE_ADMIN_PASSWORD": "$pbkdf2$sha256$600000$testsalt$notarealhashbutformatok",
+            "PG_DSN": "postgresql://mcp_user:secret@db.internal.example:5432/memory_meta",
+            "MONGO_URI": "mongodb://mongo.internal.example:27017",
+            "REDIS_URL": "redis://redis.internal.example:6379/0",
+            "MINIO_ACCESS_KEY": "minio-access-key",
+            "MINIO_SECRET_KEY": "minio-secret-key-value",
+            "NCE_JWT_SECRET": "jwt-secret-for-prod-config-tests!!",
+            "NCE_A2A_JWT_AUDIENCE": "prod-jwt-audience-for-tests!!",
+        }
+    )
+    # Strip anything that would trip an unrelated guard.
+    for k in ("NCE_ADMIN_OVERRIDE", "NCE_BYPASS_WORM", "NCE_BYPASS_RLS"):
+        env.pop(k, None)
+    return env
+
+
+def _run(code: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
+    return subprocess.run(
+        [sys.executable, "-c", code],
+        cwd=_REPO_ROOT,
+        env=env,
+        capture_output=True,
+        text=True,
+        check=False,
+    )
+
+
+def test_prod_import_rejects_dotenv_persist() -> None:
+    """Importing config under prod with dotenv-persist enabled must fail fast."""
+    env = _prod_env()
+    env["NCE_ALLOW_ADMIN_DOTENV_PERSIST"] = "true"
+    result = _run("import nce.config  # noqa: F401", env)
+    assert result.returncode != 0
+    assert "NCE_ALLOW_ADMIN_DOTENV_PERSIST" in (result.stderr + result.stdout)
+
+
+def test_prod_validate_rejects_dotenv_persist() -> None:
+    """cfg.validate() must reject dotenv-persist in production.
+
+    The default in prod is already false, so we force it true via env. Because
+    the module-import guard also fires, validate() is the path under test here
+    only when the import guard is satisfied; we assert the dedicated method
+    rejects it directly to keep the contract explicit.
+    """
+    env = _prod_env()
+    env["NCE_ALLOW_ADMIN_DOTENV_PERSIST"] = "true"
+    code = "from nce.config import _Config; _Config.validate_secrets_provider()"
+    result = _run(code, env)
+    assert result.returncode != 0
+    assert "NCE_ALLOW_ADMIN_DOTENV_PERSIST" in (result.stderr + result.stdout)
+
+
+def test_prod_validate_passes_with_secret_manager_posture() -> None:
+    """A correct prod posture (no dotenv-persist, env-only master key) validates."""
+    env = _prod_env()
+    env["NCE_ALLOW_ADMIN_DOTENV_PERSIST"] = "false"
+    code = (
+        "from nce.config import _Config, _ENV_ONLY_SECRETS; "
+        "assert _Config.IS_PROD; "
+        "_Config.validate(); "
+        "assert 'NCE_MASTER_KEY' in _ENV_ONLY_SECRETS"
+    )
+    result = _run(code, env)
+    assert result.returncode == 0, result.stderr + result.stdout
+
+
+def test_prod_master_key_resolves_env_only_not_store() -> None:
+    """In a prod interpreter, NCE_MASTER_KEY resolves env-only even with a provider."""
+    env = _prod_env()
+    env["NCE_ALLOW_ADMIN_DOTENV_PERSIST"] = "false"
+    code = "\n".join(
+        [
+            "import nce.config as c",
+            "",
+            "class P(c.SecretsProvider):",
+            "    name = 'store'",
+            "    def get_secret(self, name):",
+            "        return 'store-DANGER'",
+            "",
+            "c.set_secrets_provider(P())",
+            "got = c.resolve_secret('NCE_MASTER_KEY')",
+            "assert got == 'prod-master-key-32-characters-min!!', got",
+        ]
+    )
+    result = _run(code, env)
+    assert result.returncode == 0, result.stderr + result.stdout
```
