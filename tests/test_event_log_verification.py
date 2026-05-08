import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trimcp.event_log import DataIntegrityError, verify_event_signature
from trimcp.replay import ObservationalReplay


@pytest.mark.asyncio
async def test_verify_event_signature_tampered_record_raises_error():
    conn = AsyncMock()

    # Mock a tampered event record
    record = {
        "id": uuid.uuid4(),
        "namespace_id": uuid.uuid4(),
        "agent_id": "test_agent",
        "event_type": "store_memory",
        "event_seq": 1,
        "occurred_at": datetime.now(UTC),
        "params": '{"tampered": "yes"}',
        "parent_event_id": None,
        "signature": b"fake_signature",
        "signature_key_id": "sk-12345",
    }

    # Patch get_key_by_id and verify_fields
    with patch("trimcp.signing.get_key_by_id", new_callable=AsyncMock) as mock_get_key:
        mock_get_key.return_value = b"raw_secret_key"
        with patch("trimcp.signing.verify_fields", return_value=False) as mock_verify:
            with pytest.raises(DataIntegrityError, match="Event signature mismatch for event_id="):
                await verify_event_signature(conn, record)
            mock_verify.assert_called_once()


@pytest.mark.asyncio
async def test_observational_replay_yields_error_on_tampering():
    pool = MagicMock()
    conn = AsyncMock()

    # Setup mock cursor to yield 1 tampered record
    record = {
        "id": uuid.uuid4(),
        "namespace_id": uuid.uuid4(),
        "agent_id": "test_agent",
        "event_type": "store_memory",
        "event_seq": 1,
        "occurred_at": datetime.now(UTC),
        "params": '{"tampered": "yes"}',
        "parent_event_id": None,
        "signature": b"fake_signature",
        "signature_key_id": "sk-12345",
        "llm_payload_uri": None,
        "llm_payload_hash": None,
        "result_summary": None,
    }

    async def async_generator():
        yield record

    conn.cursor = MagicMock()
    conn.cursor.return_value = async_generator()

    @asynccontextmanager
    async def mock_transaction(*args, **kwargs):
        yield

    conn.transaction = mock_transaction

    @asynccontextmanager
    async def mock_acquire(*args, **kwargs):
        yield conn

    pool.acquire = mock_acquire

    replay = ObservationalReplay(pool)

    with patch("trimcp.replay.verify_event_signature", new_callable=AsyncMock) as mock_verify:
        mock_verify.side_effect = DataIntegrityError("Tampering detected.")

        # We need to mock _create_run and _build_event_query to not fail
        with patch("trimcp.replay._create_run", new_callable=AsyncMock, return_value=uuid.uuid4()):
            with patch("trimcp.replay._build_event_query", return_value=("SQL", [])):
                with patch("trimcp.replay._finish_run", new_callable=AsyncMock):
                    with pytest.raises(DataIntegrityError):
                        async for item in replay.execute(source_namespace_id=uuid.uuid4()):
                            if item["type"] == "error":
                                assert item["message"] == "Tampering detected."
