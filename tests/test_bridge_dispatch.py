"""Bridge dispatch and RQ worker entrypoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from nce.bridges import dispatch_bridge_event
from nce.tasks import process_bridge_event


def test_dispatch_bridge_event_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unknown bridge provider"):
        dispatch_bridge_event("onedrive", {})


@patch("nce.bridges.dispatch_bridge_event", return_value={"status": "ok"})
@patch("nce.tasks._clear_attempt")
@patch("nce.tasks._get_redis")
@patch("nce.tasks._get_job_id", return_value="job-1")
def test_process_bridge_event_success(
    _job: object,
    _redis: object,
    _clear: object,
    mock_dispatch: object,
) -> None:
    out = process_bridge_event("sharepoint", {"notifications": []})
    assert out == {"status": "ok"}
    mock_dispatch.assert_called_once_with("sharepoint", {"notifications": []})


@patch(
    "nce.bridges.dispatch_bridge_event",
    side_effect=ValueError("bad payload"),
)
@patch("nce.tasks._get_redis")
@patch("nce.tasks._get_job_id", return_value="job-2")
def test_process_bridge_event_value_error_returns_error_dict(
    _job: object,
    _redis: object,
    _dispatch: object,
) -> None:
    out = process_bridge_event("gdrive", {})
    assert out["status"] == "error"
    assert "bad payload" in out["error"]
