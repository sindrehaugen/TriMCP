"""Unit tests for nce.replay engine wiring (handler registry, mode guards)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import get_args
from unittest.mock import MagicMock

import pytest

from nce.event_types import EventType
from nce.replay import (
    ForkedReplay,
    ObservationalReplay,
    ReconstructiveReplay,
    ReplayModeError,
    _EventRow,
    _resolve_llm_payload,
)


def test_forked_replay_registers_all_event_types() -> None:
    pool = MagicMock()
    ForkedReplay(pool)  # raises ReplayHandlerMissingError if any EventType lacks a handler


def test_observational_and_reconstructive_handler_coverage() -> None:
    pool = MagicMock()
    ObservationalReplay(pool)
    ReconstructiveReplay(pool)


def test_handler_registry_matches_event_type_union() -> None:
    from nce.replay import _HANDLER_REGISTRY

    expected = frozenset(get_args(EventType))
    assert expected == frozenset(_HANDLER_REGISTRY)


@pytest.mark.asyncio
async def test_replay_mode_error_on_invalid_llm_mode() -> None:
    ns = uuid.UUID("00000000-0000-4000-8000-000000000001")
    src = _EventRow(
        event_id=uuid.uuid4(),
        event_seq=1,
        event_type="store_memory",
        occurred_at=datetime.now(timezone.utc),
        agent_id="agent-1",
        params={},
        result_summary=None,
        parent_event_id=None,
        llm_payload_uri="nce-llm-payloads/ns/event.json",
        llm_payload_hash=None,
    )

    with pytest.raises(ReplayModeError, match="Invalid replay_mode"):
        await _resolve_llm_payload(
            src,
            replay_mode="live",
            config_overrides=None,
            target_namespace_id=ns,
            source_namespace_id=ns,
        )
