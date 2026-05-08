import hashlib
import hmac
import os
from unittest.mock import patch

from fastapi.testclient import TestClient

os.environ.setdefault("DROPBOX_APP_SECRET", "test_dropbox_secret")
os.environ.setdefault("GRAPH_CLIENT_STATE", "test_graph_state")
os.environ.setdefault("DRIVE_CHANNEL_TOKEN", "test_drive_token")

from trimcp.webhook_receiver.main import (
    DRIVE_CHANNEL_TOKEN,
    DROPBOX_APP_SECRET,
    GRAPH_CLIENT_STATE,
    app,
)

client = TestClient(app)


def test_dropbox_challenge():
    response = client.get("/webhooks/dropbox?challenge=test_challenge_string")
    assert response.status_code == 200
    assert response.text == "test_challenge_string"


@patch("trimcp.webhook_receiver.main.enqueue_process_bridge_event", return_value="job-db-1")
def test_dropbox_webhook_valid_signature(mock_enqueue):
    body = b'{"list_folder": {"accounts": ["dbid:123"]}}'
    signature = hmac.new(DROPBOX_APP_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()

    response = client.post(
        "/webhooks/dropbox",
        content=body,
        headers={"X-Dropbox-Signature": signature},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "queued", "job_id": "job-db-1"}
    mock_enqueue.assert_called_once()
    args, kwargs = mock_enqueue.call_args
    assert args[0] == "dropbox"
    assert args[1]["list_folder"]["accounts"] == ["dbid:123"]


def test_dropbox_webhook_invalid_signature():
    body = b'{"list_folder": {"accounts": ["dbid:123"]}}'

    response = client.post(
        "/webhooks/dropbox",
        content=body,
        headers={"X-Dropbox-Signature": "invalid_signature"},
    )
    assert response.status_code == 403
    assert "Invalid signature" in response.json()["detail"]


def test_dropbox_webhook_missing_signature():
    body = b'{"list_folder": {"accounts": ["dbid:123"]}}'

    response = client.post(
        "/webhooks/dropbox",
        content=body,
    )
    assert response.status_code == 403
    assert "Missing X-Dropbox-Signature" in response.json()["detail"]


def test_graph_webhook_challenge():
    response = client.post("/webhooks/graph?validationToken=test_token")
    assert response.status_code == 200
    assert response.text == "test_token"


@patch("trimcp.webhook_receiver.main.enqueue_process_bridge_event", return_value="job-sp-1")
def test_graph_webhook_valid_client_state(mock_enqueue):
    payload = {
        "value": [
            {
                "clientState": GRAPH_CLIENT_STATE,
                "resource": "/users/user/drive/root",
                "changeType": "updated",
            }
        ]
    }
    response = client.post("/webhooks/graph", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "queued", "job_id": "job-sp-1"}
    mock_enqueue.assert_called_once()
    call_provider, call_payload = mock_enqueue.call_args[0]
    assert call_provider == "sharepoint"
    assert len(call_payload["notifications"]) == 1


def test_graph_webhook_invalid_client_state():
    payload = {
        "value": [
            {
                "clientState": "wrong_state",
                "resource": "Users/user/drive/root",
                "changeType": "updated",
            }
        ]
    }
    response = client.post("/webhooks/graph", json=payload)
    assert response.status_code == 403
    assert "Invalid clientState" in response.json()["detail"]


@patch("trimcp.webhook_receiver.main.enqueue_process_bridge_event", return_value="job-gd-1")
def test_drive_webhook_valid(mock_enqueue):
    response = client.post(
        "/webhooks/drive",
        headers={
            "X-Goog-Channel-Token": DRIVE_CHANNEL_TOKEN,
            "X-Goog-Resource-State": "update",
            "X-Goog-Channel-Id": "chan-abc",
            "X-Goog-Resource-Id": "res-xyz",
            "X-Goog-Message-Number": "1",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"status": "queued", "job_id": "job-gd-1"}
    mock_enqueue.assert_called_once()
    prov, payload = mock_enqueue.call_args[0]
    assert prov == "gdrive"
    assert payload["channel_id"] == "chan-abc"
    assert payload["resource_state"] == "update"


@patch("trimcp.webhook_receiver.main.enqueue_process_bridge_event")
def test_drive_webhook_sync_no_enqueue(mock_enqueue):
    response = client.post(
        "/webhooks/drive",
        headers={
            "X-Goog-Channel-Token": DRIVE_CHANNEL_TOKEN,
            "X-Goog-Resource-State": "sync",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "acknowledged"
    mock_enqueue.assert_not_called()


def test_drive_webhook_invalid_token():
    response = client.post(
        "/webhooks/drive",
        headers={
            "X-Goog-Channel-Token": "wrong_token",
            "X-Goog-Resource-State": "update",
        },
    )
    assert response.status_code == 403


def test_drive_webhook_missing_state():
    response = client.post(
        "/webhooks/drive",
        headers={
            "X-Goog-Channel-Token": DRIVE_CHANNEL_TOKEN,
        },
    )
    assert response.status_code == 400


# --- SSRF guard: Graph webhook resource URL validation ---


@patch("trimcp.webhook_receiver.main.enqueue_process_bridge_event", return_value="job-sp-2")
def test_graph_webhook_valid_sites_resource(mock_enqueue):
    """Valid Graph /sites/ resource path must be accepted."""
    payload = {
        "value": [
            {
                "clientState": GRAPH_CLIENT_STATE,
                "resource": "/sites/abc-123/drives/def-456/root",
                "changeType": "updated",
            }
        ]
    }
    response = client.post("/webhooks/graph", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "queued"


@patch("trimcp.webhook_receiver.main.enqueue_process_bridge_event", return_value="job-sp-3")
def test_graph_webhook_valid_drives_resource(mock_enqueue):
    """Valid Graph /drives/ resource path must be accepted."""
    payload = {
        "value": [
            {
                "clientState": GRAPH_CLIENT_STATE,
                "resource": "/drives/drive-id/root/delta",
                "changeType": "updated",
            }
        ]
    }
    response = client.post("/webhooks/graph", json=payload)
    assert response.status_code == 200


def test_graph_webhook_rejects_internal_resource():
    """SSRF guard must reject a resource path pointing to internal services."""
    payload = {
        "value": [
            {
                "clientState": GRAPH_CLIENT_STATE,
                "resource": "/internal/admin/panel",
                "changeType": "updated",
            }
        ]
    }
    response = client.post("/webhooks/graph", json=payload)
    assert response.status_code == 400
    assert "Invalid resource URL" in response.json()["detail"]


def test_graph_webhook_rejects_path_traversal_resource():
    """SSRF guard must reject path traversal in resource URLs."""
    payload = {
        "value": [
            {
                "clientState": GRAPH_CLIENT_STATE,
                "resource": "/../../internal/secret",
                "changeType": "updated",
            }
        ]
    }
    response = client.post("/webhooks/graph", json=payload)
    assert response.status_code == 400
    assert "Invalid resource URL" in response.json()["detail"]


def test_graph_webhook_rejects_http_resource():
    """SSRF guard must reject non-HTTPS fully-qualified resource URLs."""
    payload = {
        "value": [
            {
                "clientState": GRAPH_CLIENT_STATE,
                "resource": "http://evil.internal/hack",
                "changeType": "updated",
            }
        ]
    }
    response = client.post("/webhooks/graph", json=payload)
    assert response.status_code == 400
