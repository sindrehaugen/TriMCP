import hashlib
import hmac
import json
import pytest
from fastapi.testclient import TestClient

from trimcp.webhook_receiver.main import app, DROPBOX_APP_SECRET, GRAPH_CLIENT_STATE, DRIVE_CHANNEL_TOKEN

client = TestClient(app)

def test_dropbox_challenge():
    response = client.get("/webhooks/dropbox?challenge=test_challenge_string")
    assert response.status_code == 200
    assert response.text == "test_challenge_string"

def test_dropbox_webhook_valid_signature():
    body = b'{"list_folder": {"accounts": ["dbid:123"]}}'
    signature = hmac.new(
        DROPBOX_APP_SECRET.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    
    response = client.post(
        "/webhooks/dropbox",
        content=body,
        headers={"X-Dropbox-Signature": signature}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_dropbox_webhook_invalid_signature():
    body = b'{"list_folder": {"accounts": ["dbid:123"]}}'
    
    response = client.post(
        "/webhooks/dropbox",
        content=body,
        headers={"X-Dropbox-Signature": "invalid_signature"}
    )
    assert response.status_code == 403
    assert "Invalid signature" in response.json()["detail"]

def test_dropbox_webhook_missing_signature():
    body = b'{"list_folder": {"accounts": ["dbid:123"]}}'
    
    response = client.post(
        "/webhooks/dropbox",
        content=body
    )
    assert response.status_code == 403
    assert "Missing X-Dropbox-Signature" in response.json()["detail"]

def test_graph_webhook_challenge():
    response = client.post("/webhooks/graph?validationToken=test_token")
    assert response.status_code == 200
    assert response.text == "test_token"

def test_graph_webhook_valid_client_state():
    payload = {
        "value": [
            {
                "clientState": GRAPH_CLIENT_STATE,
                "resource": "Users/user/drive/root",
                "changeType": "updated"
            }
        ]
    }
    response = client.post("/webhooks/graph", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_graph_webhook_invalid_client_state():
    payload = {
        "value": [
            {
                "clientState": "wrong_state",
                "resource": "Users/user/drive/root",
                "changeType": "updated"
            }
        ]
    }
    response = client.post("/webhooks/graph", json=payload)
    assert response.status_code == 403
    assert "Invalid clientState" in response.json()["detail"]

def test_drive_webhook_valid():
    response = client.post(
        "/webhooks/drive",
        headers={
            "X-Goog-Channel-Token": DRIVE_CHANNEL_TOKEN,
            "X-Goog-Resource-State": "update"
        }
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_drive_webhook_invalid_token():
    response = client.post(
        "/webhooks/drive",
        headers={
            "X-Goog-Channel-Token": "wrong_token",
            "X-Goog-Resource-State": "update"
        }
    )
    assert response.status_code == 403

def test_drive_webhook_missing_state():
    response = client.post(
        "/webhooks/drive",
        headers={
            "X-Goog-Channel-Token": DRIVE_CHANNEL_TOKEN
        }
    )
    assert response.status_code == 400
