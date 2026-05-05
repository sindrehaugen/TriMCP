"""Pytest bootstrap — lazy imports for environments importing trimcp late."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_tri_stack_signing_key_cache_after_test() -> None:
    yield
    try:
        import trimcp.signing as signing_mod
    except Exception:
        return
    signing_mod._key_cache = None
