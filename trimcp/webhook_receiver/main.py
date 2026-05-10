from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from redis import Redis

from trimcp.config import cfg
from trimcp.extractors.dispatch import get_priority_queue
from trimcp.net_safety import BridgeURLValidationError, validate_webhook_payload_url
from trimcp.tasks import process_bridge_event

app = FastAPI(title="TriMCP Webhook Receiver")


@app.get("/health")
async def health():
    """Baseline healthcheck for container orchestration."""
    return {"status": "ok"}


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"{name} must be set in the environment (no default allowed for webhook secrets)"
        )
    return value


DROPBOX_APP_SECRET = _require_env("DROPBOX_APP_SECRET")
GRAPH_CLIENT_STATE = _require_env("GRAPH_CLIENT_STATE")
DRIVE_CHANNEL_TOKEN = _require_env("DRIVE_CHANNEL_TOKEN")


def enqueue_process_bridge_event(provider: str, payload: dict[str, Any]) -> str:
    """Push ``process_bridge_event`` to the ``batch_processing`` queue lane.

    Webhook-triggered events are background work — they use the
    batch lane so real-time API extractions aren't starved (§5.4).
    Isolated for tests via monkeypatch.
    """
    q = get_priority_queue(0, Redis.from_url(cfg.REDIS_URL))
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
        raise HTTPException(
            status_code=403, detail="Missing X-Dropbox-Signature header"
        )

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
    payload: dict[str, Any] = {"list_folder": list_folder or {}}
    job_id = enqueue_process_bridge_event("dropbox", payload)
    return {"status": "queued", "job_id": job_id}


@app.post("/webhooks/graph")
async def graph_webhook(
    request: Request,
    validationToken: str | None = Query(None),
):
    """Receive MS Graph webhook notifications and handle validation."""
    # Handle the validation token challenge from MS Graph
    if validationToken:
        return Response(content=validationToken, media_type="text/plain")

    payload = await request.json()

    # Validate clientState and resource URLs for security (SSRF guard)
    for notification in payload.get("value", []):
        client_state = notification.get("clientState")
        if not client_state or not hmac.compare_digest(
            client_state, GRAPH_CLIENT_STATE
        ):
            raise HTTPException(status_code=403, detail="Invalid clientState")

        resource = notification.get("resource", "")
        if resource:
            try:
                validate_webhook_payload_url(resource, field_name="resource")
            except BridgeURLValidationError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid resource URL in webhook payload: {e}",
                )

    enqueue_payload: dict[str, Any] = {"notifications": list(payload.get("value", []))}
    job_id = enqueue_process_bridge_event("sharepoint", enqueue_payload)
    return {"status": "queued", "job_id": job_id}


@app.post("/webhooks/drive")
async def drive_webhook(
    request: Request,
    channel_token: str | None = Header(None, alias="X-Goog-Channel-Token"),
    resource_state: str | None = Header(None, alias="X-Goog-Resource-State"),
    channel_id: str | None = Header(None, alias="X-Goog-Channel-Id"),
    resource_id: str | None = Header(None, alias="X-Goog-Resource-Id"),
    message_number: str | None = Header(None, alias="X-Goog-Message-Number"),
):
    """Receive Google Drive webhook notifications."""
    if not channel_token or not hmac.compare_digest(channel_token, DRIVE_CHANNEL_TOKEN):
        raise HTTPException(
            status_code=403, detail="Invalid or missing X-Goog-Channel-Token"
        )

    if not resource_state:
        raise HTTPException(status_code=400, detail="Missing X-Goog-Resource-State")

    if resource_state == "sync":
        return {"status": "acknowledged", "reason": "sync_handshake"}

    enqueue_payload: dict[str, Any] = {
        "channel_id": channel_id or "",
        "resource_id": resource_id or "",
        "resource_state": resource_state,
        "message_number": message_number,
    }
    job_id = enqueue_process_bridge_event("gdrive", enqueue_payload)
    return {"status": "queued", "job_id": job_id}
