"""Tests for dead_letter_queue payload sanitisation."""

from __future__ import annotations

from trimcp.dead_letter_queue import _sanitize_dlq_kwargs


class TestSanitizeDlqKwargs:
    def test_passes_through_simple_values(self):
        assert _sanitize_dlq_kwargs("hello") == "hello"
        assert _sanitize_dlq_kwargs(42) == 42
        assert _sanitize_dlq_kwargs(None) is None

    def test_redacts_sensitive_keys(self):
        payload = {
            "provider": "sharepoint",
            "access_token": "super_secret_token",
            "refresh_token": "another_secret",
            "password": "hunter2",
            "api_key": "sk-12345",
        }
        out = _sanitize_dlq_kwargs(payload)
        assert out["provider"] == "sharepoint"
        assert out["access_token"] == "[REDACTED]"
        assert out["refresh_token"] == "[REDACTED]"
        assert out["password"] == "[REDACTED]"
        assert out["api_key"] == "[REDACTED]"

    def test_truncates_long_strings(self):
        long_str = "x" * 5000
        out = _sanitize_dlq_kwargs({"data": long_str})
        assert len(out["data"]) == 4110  # 4096 + len('...[truncated]')
        assert out["data"].endswith("...[truncated]")

    def test_limits_nested_dict_keys(self):
        big = {f"key_{i}": i for i in range(100)}
        out = _sanitize_dlq_kwargs(big)
        assert len(out) == 50

    def test_limits_list_length(self):
        big_list = [{"id": i} for i in range(100)]
        out = _sanitize_dlq_kwargs({"items": big_list})
        assert len(out["items"]) == 50

    def test_recursive_dict_redaction(self):
        nested = {
            "outer": {
                "access_token": "nested_secret",
                " innocent": "keep_me",
            }
        }
        out = _sanitize_dlq_kwargs(nested)
        assert out["outer"]["access_token"] == "[REDACTED]"
        assert out["outer"][" innocent"] == "keep_me"

    def test_string_in_list_truncated(self):
        long_str = "y" * 5000
        out = _sanitize_dlq_kwargs({"items": [long_str]})
        assert out["items"][0].endswith("...[truncated]")
