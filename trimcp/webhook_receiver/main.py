from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, Response, HTTPException, Query, Header
from redis import Redis
from rq import Queue

from trimcp.config import cfg
from trimcp.tasks import process_bridge_event

app = FastAPI(title="TriMCP Webhook Receiver")

# In a real app, these would come from env config
DROPBOX_APP_SECRET = os.getenv("DROPBOX_APP_SECRET", "dummy_dropbox_secret")
GRAPH_CLIENT_STATE = os.getenv("GRAPH_CLIENT_STATE", "dummy_graph_state")
DRIVE_CHANNEL_TOKEN = os.getenv("DRIVE_CHANNEL_TOKEN", "dummy_drive_token")


def enqueue_process_bridge_event(provider: str, payload: Dict[str, Any]) -> str:
    """Push `process_bridge_event` to RQ. Isolated for tests via monkeypatch."""
    q = Queue("default", connection=Redis.from_url(cfg.REDIS_URL))
    job = q.enqueue(
        process_bridge_event,
        kwargs={"provider": provider, "payload": payload},
        job_timeout="30m",
    )
    return job.id


@app.get("/webhooks/dropbox")
async def dropbox_challenge(challenge: str = Query(..., alias="challenge")):
    """Respond to Dropbox webhook verification challenge."""
    return Response(content=challenge, media_type="text/plain")


@app.post("/webhooks/dropbox")
async def dropbox_webhook(request: Request):
    """Receive Dropbox webhook notifications."""
    signature = request.headers.get("X-Dropbox-Signature")
    if not signature:
        raise HTTPException(status_code=403, detail="Missing X-Dropbox-Signature header")

    body = await request.body()
    expected_signature = hmac.new(
        DROPBOX_APP_SECRET.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    list_folder = parsed.get("list_folder") if isinstance(parsed, dict) else None
    payload: Dict[str, Any] = {"list_folder": list_folder or {}}
    job_id = enqueue_process_bridge_event("dropbox", payload)
    return {"status": "queued", "job_id": job_id}


@app.post("/webhooks/graph")
async def graph_webhook(
    request: Request,
    validationToken: Optional[str] = Query(None),
):
    """Receive MS Graph webhook notifications and handle validation."""
    # Handle the validation token challenge from MS Graph
    if validationToken:
        return Response(content=validationToken, media_type="text/plain")

    payload = await request.json()

    # Validate clientState for security
    for notification in payload.get("value", []):
        client_state = notification.get("clientState")
        if not client_state or not hmac.compare_digest(client_state, GRAPH_CLIENT_STATE):
            raise HTTPException(status_code=403, detail="Invalid clientState")

    enqueue_payload: Dict[str, Any] = {"notifications": list(payload.get("value", []))}
    job_id = enqueue_process_bridge_event("sharepoint", enqueue_payload)
    return {"status": "queued", "job_id": job_id}


@app.post("/webhooks/drive")
async def drive_webhook(
    request: Request,
    channel_token: Optional[str] = Header(None, alias="X-Goog-Channel-Token"),
    resource_state: Optional[str] = Header(None, alias="X-Goog-Resource-State"),
    channel_id: Optional[str] = Header(None, alias="X-Goog-Channel-Id"),
    resource_id: Optional[str] = Header(None, alias="X-Goog-Resource-Id"),
    message_number: Optional[str] = Header(None, alias="X-Goog-Message-Number"),
):
    """Receive Google Drive webhook notifications."""
    if not channel_token or not hmac.compare_digest(channel_token, DRIVE_CHANNEL_TOKEN):
        raise HTTPException(status_code=403, detail="Invalid or missing X-Goog-Channel-Token")

    if not resource_state:
        raise HTTPException(status_code=400, detail="Missing X-Goog-Resource-State")

    if resource_state == "sync":
        return {"status": "acknowledged", "reason": "sync_handshake"}

    enqueue_payload: Dict[str, Any] = {
        "channel_id": channel_id or "",
        "resource_id": resource_id or "",
        "resource_state": resource_state,
        "message_number": message_number,
    }
    job_id = enqueue_process_bridge_event("gdrive", enqueue_payload)
    return {"status": "queued", "job_id": job_id}
