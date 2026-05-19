"""Public package API contract for ``trimcp.__init__`` lazy exports."""

from __future__ import annotations

import builtins
import importlib
import sys

import pytest

_EXPECTED_ALL = frozenset(
    {
        "TriStackEngine",
        "MemoryPayload",
        "MediaPayload",
        "OrchestratorConfig",
        "run_gc_loop",
    }
)


def _purge_trimcp_modules() -> None:
    for key in list(sys.modules):
        if key == "trimcp" or key.startswith("trimcp."):
            del sys.modules[key]


def _fresh_trimcp():
    _purge_trimcp_modules()
    return importlib.import_module("trimcp")


def test_bare_import_does_not_load_orchestrator(monkeypatch) -> None:
    _purge_trimcp_modules()

    import trimcp  # noqa: F401

    assert "trimcp.orchestrator" not in sys.modules
    assert "trimcp.garbage_collector" not in sys.modules


def test_all_public_names_accessible() -> None:
    trimcp = _fresh_trimcp()

    for name in trimcp.__all__:
        obj = getattr(trimcp, name)
        assert obj is not None


def test_all_contains_expected_exports() -> None:
    trimcp = _fresh_trimcp()

    assert set(trimcp.__all__) == set(_EXPECTED_ALL)
    assert len(trimcp.__all__) == 5


def test_unknown_attribute_raises() -> None:
    trimcp = _fresh_trimcp()

    with pytest.raises(AttributeError):
        _ = trimcp.this_does_not_exist


def test_version_is_non_empty_string() -> None:
    trimcp = _fresh_trimcp()

    assert isinstance(trimcp.__version__, str)
    assert trimcp.__version__.strip() != ""


def test_lazy_cache_avoids_repeated_getattr() -> None:
    trimcp = _fresh_trimcp()

    assert "TriStackEngine" not in vars(trimcp)

    _ = trimcp.TriStackEngine

    assert "TriStackEngine" in vars(trimcp)


def test_broken_import_yields_attribute_error(monkeypatch) -> None:
    """Broken lazy imports surface as AttributeError with 'unavailable'."""

    real_import = builtins.__import__

    def blocking_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "trimcp.orchestrator":
            raise ImportError("simulated orchestrator import failure")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocking_import)

    real_import_module = importlib.import_module

    def blocking_import_module(name: str, package: str | None = None):
        # Lazy exports use importlib.import_module, which bypasses builtins.__import__.
        if name == "trimcp.orchestrator":
            blocking_import("trimcp.orchestrator")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", blocking_import_module)

    trimcp = _fresh_trimcp()

    with pytest.raises(AttributeError, match="unavailable"):
        _ = trimcp.TriStackEngine
