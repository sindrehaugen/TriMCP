"""Pytest bootstrap — per-test signing cache isolation for parallel-safe execution."""

from __future__ import annotations

import os

# `trimcp.config` fails fast on import if unset; tests often import the package
# without a local .env — provide a deterministic dev-length key for collection only.
os.environ.setdefault("TRIMCP_MASTER_KEY", "x" * 32)

import pytest


@pytest.fixture(autouse=True)
def _reset_signing_key_cache_after_test() -> None:
    """Reset the signing key module-level cache after each test.

    Prevents test-order dependencies by clearing ``_key_cache`` so each
    test starts with a fresh signing state.  Uses ``yield`` to run after
    the test body (teardown semantics).  Safe under ``pytest-xdist``
    because each worker has its own module namespace.
    """
    yield
    try:
        import trimcp.signing as signing_mod

        # _key_cache is a _SigningKeyCache(TTLCache) — clear() removes all
        # entries and __delitem__ zeros their MutableKeyBuffer.
        signing_mod._key_cache.clear()
    except Exception:
        return
