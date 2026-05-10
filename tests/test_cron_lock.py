"""Unit tests for the distributed cron lock helper in trimcp/cron.py."""

from __future__ import annotations

import os

os.environ.setdefault("TRIMCP_MASTER_KEY", "dev-test-key-32chars-long!!")

from unittest.mock import AsyncMock, patch

import pytest

from trimcp.cron_lock import acquire_cron_lock as _acquire_cron_lock


class TestAcquireCronLockNoRedis:
    @pytest.mark.asyncio
    async def test_returns_true_when_redis_url_empty(self):
        with patch("trimcp.cron_lock.cfg") as mock_cfg:
            mock_cfg.REDIS_URL = ""
            result = await _acquire_cron_lock("test_job", 300)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_on_redis_exception(self):
        with patch("trimcp.cron_lock.cfg") as mock_cfg:
            mock_cfg.REDIS_URL = "redis://localhost:6379"
            with patch("redis.asyncio.Redis.from_url", side_effect=ConnectionError("down")):
                result = await _acquire_cron_lock("test_job", 300)
        assert result is True  # fail-open


class TestAcquireCronLockAcquired:
    @pytest.mark.asyncio
    async def test_returns_true_when_set_nx_succeeds(self):
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()

        with patch("trimcp.cron_lock.cfg") as mock_cfg:
            mock_cfg.REDIS_URL = "redis://localhost:6379"
            with patch("redis.asyncio.Redis.from_url", return_value=mock_client):
                result = await _acquire_cron_lock("bridge_subscription_renewal", 2760)

        assert result is True
        mock_client.set.assert_awaited_once_with(
            "trimcp:cron:lock:bridge_subscription_renewal", "1", nx=True, ex=2760
        )
        mock_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_set_nx_returns_none(self):
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=None)
        mock_client.aclose = AsyncMock()

        with patch("trimcp.cron_lock.cfg") as mock_cfg:
            mock_cfg.REDIS_URL = "redis://localhost:6379"
            with patch("redis.asyncio.Redis.from_url", return_value=mock_client):
                result = await _acquire_cron_lock("sleep_consolidation", 7260)

        assert result is False

    @pytest.mark.asyncio
    async def test_lock_key_includes_job_id(self):
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()

        with patch("trimcp.cron_lock.cfg") as mock_cfg:
            mock_cfg.REDIS_URL = "redis://localhost:6379"
            with patch("redis.asyncio.Redis.from_url", return_value=mock_client):
                await _acquire_cron_lock("event_log_partition_maintenance", 3600)

        key_used = mock_client.set.call_args.args[0]
        assert key_used == "trimcp:cron:lock:event_log_partition_maintenance"
