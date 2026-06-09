from __future__ import annotations

import time
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nce.admin_app import app
from nce.config import cfg
from starlette.testclient import TestClient

from tests.fixtures.http_hmac_helpers import admin_hmac_headers


@pytest.fixture(autouse=True)
def bypass_lifespan():
    """Bypass Starlette app lifespan to avoid real DB connections at startup."""

    @asynccontextmanager
    async def dummy_lifespan(app):
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = dummy_lifespan
    yield
    app.router.lifespan_context = original_lifespan


@pytest.fixture
def mock_conn():
    c = AsyncMock()
    return c


@pytest.fixture
def mock_engine(mock_conn):
    engine = MagicMock()
    # Mock pool acquire context manager
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    engine.pg_pool.acquire.return_value = ctx
    engine.redis_client = None
    return engine


def test_settings_endpoints_require_hmac():
    """Verify settings endpoints reject unsigned requests with 401."""
    with TestClient(app, raise_server_exceptions=False) as client:
        # GET /api/admin/settings
        resp = client.get("/api/admin/settings")
        assert resp.status_code == 401

        # GET /api/admin/settings/effective
        resp = client.get("/api/admin/settings/effective")
        assert resp.status_code == 401

        # GET /api/admin/settings/MONGO_URI
        resp = client.get("/api/admin/settings/MONGO_URI")
        assert resp.status_code == 401


def test_get_settings_list(mock_engine, mock_conn):
    """Verify settings listing groups by section, filters, and masks secrets."""
    # Mock DB select to return one override
    mock_conn.fetch.return_value = [
        {
            "key": "MINIO_SECURE",
            "value": "true",
            "secret_enc": None,
            "is_secret": False,
            "updated_by": "admin_user",
            "updated_at": None,
        }
    ]

    with patch("nce.admin_state.engine", mock_engine):
        key = cfg.NCE_API_KEY or "test_key"
        with patch.object(cfg, "NCE_API_KEY", key):
            ts = int(time.time())
            headers = admin_hmac_headers(
                hex_key_material=key,
                method="GET",
                path="/api/admin/settings",
                timestamp=ts,
            )
            with TestClient(app, raise_server_exceptions=True) as client:
                resp = client.get("/api/admin/settings", headers=headers)

            assert resp.status_code == 200
            data = resp.json()
            assert "sections" in data
            sections = data["sections"]
            assert len(sections) > 0

            # Find Datastores & connections section
            ds_sec = next((s for s in sections if s["section"] == "Datastores & connections"), None)
            assert ds_sec is not None

            # MONGO_URI is a secret, must be masked
            mongo_key = next((k for k in ds_sec["keys"] if k["key"] == "MONGO_URI"), None)
            assert mongo_key is not None
            assert mongo_key["is_secret"] is True
            # MONGO_URI is set by default in cfg, so it should be masked
            assert mongo_key["effective_value"] == "••••set"
            assert mongo_key["source"] in ("env", "default")

            # MINIO_SECURE is overridden in DB
            minio_sec_key = next((k for k in ds_sec["keys"] if k["key"] == "MINIO_SECURE"), None)
            assert minio_sec_key is not None
            assert minio_sec_key["source"] == "store"
            assert minio_sec_key["store_value_set"] is True
            assert minio_sec_key["updated_by"] == "admin_user"


def test_get_settings_list_filtering(mock_engine, mock_conn):
    """Verify settings listing supports section and search query filtering."""
    mock_conn.fetch.return_value = []

    with patch("nce.admin_state.engine", mock_engine):
        key = cfg.NCE_API_KEY or "test_key"
        with patch.object(cfg, "NCE_API_KEY", key):
            # Test filter by section
            ts = int(time.time())
            headers = admin_hmac_headers(
                hex_key_material=key,
                method="GET",
                path="/api/admin/settings",
                timestamp=ts,
            )
            with TestClient(app) as client:
                resp = client.get(
                    "/api/admin/settings?section=Datastores%20%26%20connections",
                    headers=headers,
                )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["sections"]) == 1
            assert data["sections"][0]["section"] == "Datastores & connections"

            # Test filter by q matching NCE_API_KEY
            headers = admin_hmac_headers(
                hex_key_material=key,
                method="GET",
                path="/api/admin/settings",
                timestamp=ts,
            )
            with TestClient(app) as client:
                resp = client.get(
                    "/api/admin/settings?q=NCE_API_KEY",
                    headers=headers,
                )
            assert resp.status_code == 200
            data = resp.json()
            # Should match only the section containing NCE_API_KEY
            found_key = False
            for sec in data["sections"]:
                for k in sec["keys"]:
                    if k["key"] == "NCE_API_KEY":
                        found_key = True
            assert found_key is True


def test_get_effective_settings(mock_engine, mock_conn):
    """Verify flat effective settings endpoint."""
    mock_conn.fetch.return_value = []

    with patch("nce.admin_state.engine", mock_engine):
        key = cfg.NCE_API_KEY or "test_key"
        with patch.object(cfg, "NCE_API_KEY", key):
            ts = int(time.time())
            headers = admin_hmac_headers(
                hex_key_material=key,
                method="GET",
                path="/api/admin/settings/effective",
                timestamp=ts,
            )
            with TestClient(app) as client:
                resp = client.get("/api/admin/settings/effective", headers=headers)

            assert resp.status_code == 200
            data = resp.json()
            # Check MONGO_URI is flatly present and masked
            assert "MONGO_URI" in data
            assert data["MONGO_URI"] == "••••set"
            assert "MINIO_ENDPOINT" in data
            assert data["MINIO_ENDPOINT"] == cfg.MINIO_ENDPOINT


def test_get_single_setting(mock_engine, mock_conn):
    """Verify single setting detail endpoint."""
    mock_conn.fetchrow.return_value = None

    with patch("nce.admin_state.engine", mock_engine):
        key = cfg.NCE_API_KEY or "test_key"
        with patch.object(cfg, "NCE_API_KEY", key):
            ts = int(time.time())
            headers = admin_hmac_headers(
                hex_key_material=key,
                method="GET",
                path="/api/admin/settings/MONGO_URI",
                timestamp=ts,
            )
            with TestClient(app) as client:
                resp = client.get("/api/admin/settings/MONGO_URI", headers=headers)

            assert resp.status_code == 200
            data = resp.json()
            assert data["key"] == "MONGO_URI"
            assert data["type"] == "secret"
            assert data["is_secret"] is True
            assert data["effective_value"] == "••••set"
            assert "validation" in data


def test_get_single_setting_not_found(mock_engine, mock_conn):
    """Verify single setting returns 404 for invalid key."""
    with patch("nce.admin_state.engine", mock_engine):
        key = cfg.NCE_API_KEY or "test_key"
        with patch.object(cfg, "NCE_API_KEY", key):
            ts = int(time.time())
            headers = admin_hmac_headers(
                hex_key_material=key,
                method="GET",
                path="/api/admin/settings/NON_EXISTENT_KEY",
                timestamp=ts,
            )
            with TestClient(app) as client:
                resp = client.get("/api/admin/settings/NON_EXISTENT_KEY", headers=headers)
            assert resp.status_code == 404
