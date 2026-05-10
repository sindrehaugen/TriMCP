"""Tests for SafeAsyncClient SSRF blocking."""

from __future__ import annotations

import pytest

from trimcp._http_utils import SafeAsyncClient, UnsafeURLError


class TestSafeAsyncClient:
    @pytest.mark.asyncio
    async def test_blocks_private_ipv4(self, monkeypatch: pytest.MonkeyPatch):
        """Requests to RFC 1918 private IPs are rejected before connection."""

        def _mock_getaddrinfo(host, port, *args, **kwargs):
            return [(2, 1, 6, "", ("10.0.0.1", 0))]

        monkeypatch.setattr("socket.getaddrinfo", _mock_getaddrinfo)

        async with SafeAsyncClient() as client:
            with pytest.raises(UnsafeURLError, match="non-public IP"):
                await client.get("https://internal.example.com/secret")

    @pytest.mark.asyncio
    async def test_blocks_loopback(self, monkeypatch: pytest.MonkeyPatch):
        """Requests to loopback addresses are rejected."""

        def _mock_getaddrinfo(host, port, *args, **kwargs):
            return [(2, 1, 6, "", ("127.0.0.1", 0))]

        monkeypatch.setattr("socket.getaddrinfo", _mock_getaddrinfo)

        async with SafeAsyncClient() as client:
            with pytest.raises(UnsafeURLError, match="non-public IP"):
                await client.post("https://localhost:8000/api")

    @pytest.mark.asyncio
    async def test_allows_public_ip(self, monkeypatch: pytest.MonkeyPatch):
        """Requests to public IPs are allowed (connection may still fail)."""

        def _mock_getaddrinfo(host, port, *args, **kwargs):
            return [(2, 1, 6, "", ("1.2.3.4", 0))]

        monkeypatch.setattr("socket.getaddrinfo", _mock_getaddrinfo)

        async with SafeAsyncClient() as client:
            # Connection will fail because 1.2.3.4 is not a real server,
            # but the SSRF guard should NOT raise.
            with pytest.raises(Exception) as excinfo:
                await client.get("https://public.example.com/")
            assert not isinstance(excinfo.value, UnsafeURLError)

    @pytest.mark.asyncio
    async def test_allows_unresolvable_host(self):
        """Unresolvable hosts pass the guard and fail at connection time."""
        async with SafeAsyncClient() as client:
            with pytest.raises(Exception) as excinfo:
                await client.get("https://this-host-definitely-does-not-exist.invalid/")
            assert not isinstance(excinfo.value, UnsafeURLError)

    @pytest.mark.asyncio
    async def test_blocks_ipv6_loopback(self, monkeypatch: pytest.MonkeyPatch):
        """Requests to ::1 are rejected."""

        def _mock_getaddrinfo(host, port, *args, **kwargs):
            return [(10, 1, 6, "", ("::1", 0, 0, 0))]

        monkeypatch.setattr("socket.getaddrinfo", _mock_getaddrinfo)

        async with SafeAsyncClient() as client:
            with pytest.raises(UnsafeURLError, match="non-public IP"):
                await client.get("https://localhost:8000/")
