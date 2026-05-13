"""Tests for Datastore Connection Parameters Config REST Endpoints."""

from __future__ import annotations

import json
from unittest.mock import patch, mock_open, MagicMock
import pytest
from starlette.requests import Request
from starlette.datastructures import Headers

import os
os.environ.setdefault("TRIMCP_MASTER_KEY", "dev-test-key-32chars-long!!")


@pytest.mark.asyncio
async def test_datastores_status_endpoint():
    """Verify datastore status fetches correctly and masks secrets."""
    with patch("admin_server.cfg") as mock_cfg:
        mock_cfg.PG_DSN = "postgresql://user:password@localhost/trimcp"
        mock_cfg.DB_READ_URL = "postgresql://user:password@localhost/trimcp_replica"
        mock_cfg.DB_WRITE_URL = "postgresql://user:password@localhost/trimcp"
        mock_cfg.PG_MIN_POOL = 3
        mock_cfg.PG_MAX_POOL = 15
        mock_cfg.MONGO_URI = "mongodb://user:pwd@host:27017/trimcp"
        mock_cfg.REDIS_URL = "redis://:foobar@host:6379/0"
        mock_cfg.REDIS_TTL = 3600
        mock_cfg.REDIS_MAX_CONNECTIONS = 50
        mock_cfg.MINIO_ENDPOINT = "localhost:9000"
        mock_cfg.MINIO_ACCESS_KEY = "minio_user"
        mock_cfg.MINIO_SECRET_KEY = "minio_secret_password"
        mock_cfg.MINIO_SECURE = False

        from admin_server import api_admin_datastores_status

        request = Request({"type": "http", "method": "GET", "path": "/api/admin/datastores/status"})
        response = await api_admin_datastores_status(request)

        assert response.status_code == 200
        data = json.loads(response.body.decode())

        assert "postgres" in data
        assert "mongodb" in data
        assert "redis" in data
        assert "minio" in data

        # Check postgres fields are populated
        assert data["postgres"]["pg_dsn"] == "postgresql://user:••••••••@localhost/trimcp"
        assert data["postgres"]["pg_min_pool"] == 3

        # Check secrets are masked and reported properly (has_secret_key is True, actual secret is not leaked)
        assert data["minio"]["has_secret_key"] is True


@pytest.mark.asyncio
async def test_datastores_save_endpoint_with_secret_masked():
    """Verify saving connection parameters respects masked values and writes env file."""
    # Mocking standard open() call for .env updates
    env_content = "MINIO_ENDPOINT=localhost:9000\nMINIO_SECRET_KEY=real_password\nREDIS_TTL=3600\n"
    
    mock_engine = MagicMock()
    with (
        patch("admin_server.engine", mock_engine),
        patch("admin_server.cfg") as mock_cfg,
        patch("builtins.open", mock_open(read_data=env_content)) as mock_file_open,
    ):
        mock_cfg.PG_DSN = "postgresql://user:password@localhost/trimcp"
        mock_cfg.DB_READ_URL = "postgresql://user:password@localhost/trimcp_replica"
        mock_cfg.DB_WRITE_URL = "postgresql://user:password@localhost/trimcp"
        mock_cfg.PG_MIN_POOL = 3
        mock_cfg.PG_MAX_POOL = 15
        mock_cfg.MONGO_URI = "mongodb://user:pwd@host:27017/trimcp"
        mock_cfg.REDIS_URL = "redis://:foobar@host:6379/0"
        mock_cfg.REDIS_TTL = 3600
        mock_cfg.REDIS_MAX_CONNECTIONS = 50
        mock_cfg.MINIO_ENDPOINT = "localhost:9000"
        mock_cfg.MINIO_ACCESS_KEY = "minio_user"
        mock_cfg.MINIO_SECRET_KEY = "real_password"
        mock_cfg.MINIO_SECURE = False

        from admin_server import api_admin_datastores_save

        payload = {
            "minio": {
                "minio_endpoint": "s3.amazonaws.com",
                "minio_access_key": "aws_key",
                "minio_secret_key": "••••••••",  # Masked! Should not update the actual password.
                "minio_secure": True
            }
        }

        # Setup standard Starlette request mock
        async def receive():
            return {"type": "http.request", "body": json.dumps(payload).encode()}

        request = Request({"type": "http", "method": "POST", "path": "/api/admin/datastores/save"}, receive=receive)
        response = await api_admin_datastores_save(request)

        assert response.status_code == 200
        data = json.loads(response.body.decode())
        assert data["status"] == "success"

        # Check mock open calls to verify written data
        written_lines = []
        for call in mock_file_open().writelines.call_args_list:
            written_lines.extend(call[0][0])
        written = "".join(written_lines)

        # MINIO_ENDPOINT must have updated, but MINIO_SECRET_KEY must have stayed real_password!
        assert "MINIO_ENDPOINT=s3.amazonaws.com\n" in written
        assert "MINIO_SECRET_KEY=real_password\n" in written or not any("MINIO_SECRET_KEY=" in l for l in written_lines) # If left unchanged in-place
