import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from trimcp.notifications import NotificationDispatcher


@pytest_asyncio.fixture
async def dispatcher():
    d = NotificationDispatcher()
    d.slack_webhook = "http://slack.webhook.local"
    d.teams_webhook = "http://teams.webhook.local"
    d.smtp_host = "smtp.mock.local"
    yield d
    if d._worker_task is not None:
        await d.stop_worker()


@pytest.mark.asyncio
async def test_slack_dispatch(dispatcher):
    """Verify Slack webhook payloads are correctly formatted."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        await dispatcher._send_slack("Test Alert", "System is down")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://slack.webhook.local"
        assert kwargs["json"] == {"text": "*Test Alert*\nSystem is down"}


@pytest.mark.asyncio
async def test_teams_dispatch(dispatcher):
    """Verify Teams webhook payloads are correctly formatted."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        await dispatcher._send_teams("Test Alert", "System is down")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://teams.webhook.local"
        assert kwargs["json"] == {"title": "Test Alert", "text": "System is down"}


@pytest.mark.asyncio
async def test_email_dispatch(dispatcher):
    """Verify SMTP emails are constructed and sent correctly."""
    fake = MagicMock()
    fake.send = AsyncMock()
    with patch.dict(sys.modules, {"aiosmtplib": fake}):
        await dispatcher._send_email("Test Alert", "System is down")
    fake.send.assert_called_once()
    msg = fake.send.call_args[0][0]
    assert msg["Subject"] == "Test Alert"
    assert msg["To"] == "admin@example.com"
    assert msg["From"] == "trimcp-alerts@example.com"
    assert fake.send.call_args[1]["hostname"] == "smtp.mock.local"


@pytest.mark.asyncio
async def test_snmp_dispatch(dispatcher):
    """Verify SNMP dispatch executes without error."""
    # Currently a pass operation, but ensures it's callable
    await dispatcher._send_snmp("Test Alert", "System is down")


@pytest.mark.asyncio
async def test_worker_dispatches_to_all_channels(dispatcher):
    """Verify the worker pulls from the queue and calls all dispatch methods."""
    with (
        patch.object(dispatcher, "_send_slack", new_callable=AsyncMock) as mock_slack,
        patch.object(dispatcher, "_send_teams", new_callable=AsyncMock) as mock_teams,
        patch.object(dispatcher, "_send_email", new_callable=AsyncMock) as mock_email,
        patch.object(dispatcher, "_send_snmp", new_callable=AsyncMock) as mock_snmp,
    ):
        await dispatcher.start_worker()
        await dispatcher.dispatch_alert("Test Alert", "System is down")

        # Wait for the queue to process the alert
        await dispatcher._queue.join()
        await dispatcher.stop_worker()

        mock_slack.assert_called_once_with("Test Alert", "System is down")
        mock_teams.assert_called_once_with("Test Alert", "System is down")
        mock_email.assert_called_once_with("Test Alert", "System is down")
        mock_snmp.assert_called_once_with("Test Alert", "System is down")
