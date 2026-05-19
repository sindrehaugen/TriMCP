"""Production configuration hardening (P1-B)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _prod_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "TRIMCP_ENV": "prod",
            "TRIMCP_LOAD_DOTENV": "true",
            "TRIMCP_MASTER_KEY": "prod-master-key-32-characters-min!!",
            "TRIMCP_API_KEY": "prod-api-key-for-ci-tests-only",
            "TRIMCP_MCP_API_KEY": "prod-mcp-key-for-config-tests-only!!",
            "TRIMCP_MCP_NAMESPACE_ID": "00000000-0000-4000-8000-000000000001",
            "TRIMCP_ADMIN_API_KEY": "prod-admin-key-for-config-tests",
            "TRIMCP_ADMIN_USERNAME": "admin",
            "TRIMCP_ADMIN_PASSWORD": (
                "$pbkdf2$sha256$600000$testsalt$notarealhashbutformatok"
            ),
            "PG_DSN": "postgresql://mcp_user:secret@db.internal.example:5432/memory_meta",
            "MONGO_URI": "mongodb://mongo.internal.example:27017",
            "REDIS_URL": "redis://redis.internal.example:6379/0",
            "MINIO_ACCESS_KEY": "minio-access-key",
            "MINIO_SECRET_KEY": "minio-secret-key-value",
            "TRIMCP_JWT_SECRET": "jwt-secret-for-prod-config-tests!!",
        }
    )
    return env


def test_load_dotenv_forbidden_when_env_is_prod() -> None:
    """Import trimcp.config in a fresh process — must not mutate in-process singleton."""

    code = "import trimcp.config  # noqa: F401"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_REPO_ROOT,
        env=_prod_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "TRIMCP_LOAD_DOTENV" in (result.stderr + result.stdout)


def test_load_dotenv_allowed_when_not_prod() -> None:
    env = os.environ.copy()
    env["TRIMCP_ENV"] = "dev"
    env["TRIMCP_LOAD_DOTENV"] = "true"
    env.setdefault("TRIMCP_MASTER_KEY", "x" * 32)

    code = "import trimcp.config as c; assert c.cfg.IS_PROD is False"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_migration_mcp_disabled_by_default_in_prod() -> None:
    env = _prod_env()
    env["TRIMCP_LOAD_DOTENV"] = "false"
    env.pop("TRIMCP_DISABLE_MIGRATION_MCP", None)
    code = (
        "import trimcp.config as c; "
        "assert c.cfg.IS_PROD; "
        "assert c.cfg.TRIMCP_DISABLE_MIGRATION_MCP is True"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_validate_rejects_webhook_dedup_fail_open_in_prod() -> None:
    env = _prod_env()
    env["TRIMCP_LOAD_DOTENV"] = "false"
    env["WEBHOOK_DEDUP_FAIL_OPEN"] = "true"
    env["TRIMCP_MCP_API_KEY"] = "prod-mcp-key-for-config-tests-only!!"
    env["TRIMCP_MCP_NAMESPACE_ID"] = "00000000-0000-4000-8000-000000000001"
    env["TRIMCP_ADMIN_API_KEY"] = "prod-admin-key-for-config-tests"
    env["TRIMCP_ADMIN_USERNAME"] = "admin"
    env["TRIMCP_ADMIN_PASSWORD"] = (
        "$pbkdf2$sha256$600000$testsalt$notarealhashbutformatok"
    )

    code = "from trimcp.config import _Config; _Config.validate()"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "WEBHOOK_DEDUP_FAIL_OPEN" in (result.stderr + result.stdout)


def test_validate_rejects_migration_mcp_enabled_in_prod_without_opt_in() -> None:
    env = _prod_env()
    env["TRIMCP_LOAD_DOTENV"] = "false"
    env["TRIMCP_DISABLE_MIGRATION_MCP"] = "false"
    env["TRIMCP_MCP_API_KEY"] = "prod-mcp-key-for-config-tests-only!!"
    env["TRIMCP_MCP_NAMESPACE_ID"] = "00000000-0000-4000-8000-000000000001"
    env["TRIMCP_ADMIN_API_KEY"] = "prod-admin-key-for-config-tests"
    env["TRIMCP_ADMIN_USERNAME"] = "admin"
    env["TRIMCP_ADMIN_PASSWORD"] = (
        "$pbkdf2$sha256$600000$testsalt$notarealhashbutformatok"
    )

    code = "from trimcp.config import _Config; _Config.validate()"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Migration MCP tools" in (result.stderr + result.stdout)


def test_validate_requires_mcp_namespace_in_prod_when_mcp_key_set() -> None:
    env = _prod_env()
    env["TRIMCP_LOAD_DOTENV"] = "false"
    env.pop("TRIMCP_MCP_NAMESPACE_ID", None)

    code = "from trimcp.config import _Config; _Config.validate()"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "TRIMCP_MCP_NAMESPACE_ID" in (result.stderr + result.stdout)
