"""
tests/test_settings_registry.py
===============================
Unit tests for Settings Registry (Batch 33).
Verifies registry completeness, correct types, reload classes, validation,
and production-locking guardrails.
"""

from __future__ import annotations

import pytest
from nce.settings_registry import REGISTRY


def test_registry_completeness():
    """Verify that the registry contains settings across ~22 sections and is populated."""
    assert len(REGISTRY) > 0
    sections = {meta.section for meta in REGISTRY.values()}
    # Verify we have seeded settings across ~22 sections
    assert len(sections) >= 20


def test_registry_metadata_contracts():
    """Verify that every entry follows key contracts and reload class boundaries."""
    for key, meta in REGISTRY.items():
        assert meta.key == key
        assert meta.section
        assert meta.type in {"str", "int", "float", "bool", "secret", "list"}
        assert meta.reload_class in {"HOT", "WARM", "COLD"}
        assert meta.validator is not None
        assert callable(meta.validator)
        # Secrets must be marked is_secret
        if meta.type == "secret":
            assert meta.is_secret is True
        # If marked is_secret, type should be secret
        if meta.is_secret:
            assert meta.type == "secret" or meta.key == "NCE_MASTER_KEY"


def test_prod_locked_keys_flagged():
    """Verify that guardrail and security settings are flagged as prod_locked."""
    expected_prod_locked = {
        "NCE_BYPASS_WORM",
        "NCE_BYPASS_RLS",
        "NCE_ADMIN_OVERRIDE",
        "NCE_LOAD_DOTENV",
        "NCE_ALLOW_ADMIN_DOTENV_PERSIST",
        "NCE_MASTER_KEY",
        "WEBHOOK_DEDUP_FAIL_OPEN",
    }
    for key in expected_prod_locked:
        assert key in REGISTRY, f"Expected guardrail key {key} was not found in REGISTRY."
        assert REGISTRY[key].prod_locked is True, f"Key {key} must be flagged as prod_locked."


@pytest.mark.parametrize(
    "key,valid_val,invalid_val",
    [
        ("MONGO_URI", "mongodb://localhost", 123),
        ("PG_MIN_POOL", 5, "five"),
        ("PG_MIN_POOL", 2, True),  # True is an int in Python but should fail custom validator
        ("MINIO_SECURE", True, "yes"),
        ("CONSOLIDATION_HALF_LIFE_DAYS", 15.5, "fifteen"),
        ("NCE_TOOLS_DISABLED", ["tool1", "tool2"], "tool1"),
        ("NCE_TOOLS_DISABLED", ["tool1", "tool2"], [123, "tool2"]),
    ],
)
def test_validators(key, valid_val, invalid_val):
    """Test that setting validators accept valid values and reject invalid inputs."""
    meta = REGISTRY[key]
    assert meta.validator(valid_val) is True, (
        f"Validator for {key} rejected valid value: {valid_val}"
    )
    assert meta.validator(invalid_val) is False, (
        f"Validator for {key} accepted invalid value: {invalid_val}"
    )
