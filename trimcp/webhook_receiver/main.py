import hashlib
import hmac
import os
from typing import Any, Dict

from fastapi import FastAPI, Request, Response, HTTPException, Query, Header

app = FastAPI(title="TriMCP Webhook Receiver")

# In a real app, these would come from env config
DROPBOX_APP_SECRET = os.getenv("DROPBOX_APP_SECRET", "dummy_dropbox_secret")
GRAPH_CLIENT_STATE = os.getenv("GRAPH_CLIENT_STATE", "dummy_graph_state")
DRIVE_CHANNEL_TOKEN = os.getenv("DRIVE_CHANNEL_TOKEN", "dummy_drive_token")

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
    
    # Process webhook (mocked for tests)
    return {"status": "ok"}

@app.post("/webhooks/graph")
async def graph_webhook(
    request: Request,
    validationToken: str | None = Query(None)
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
            
    # Process webhook (mocked for tests)
    return {"status": "ok"}

@app.post("/webhooks/drive")
async def drive_webhook(
    request: Request,
    channel_token: str | None = Header(None, alias="X-Goog-Channel-Token"),
    resource_state: str | None = Header(None, alias="X-Goog-Resource-State")
):
    """Receive Google Drive webhook notifications."""
    if not channel_token or not hmac.compare_digest(channel_token, DRIVE_CHANNEL_TOKEN):
        raise HTTPException(status_code=403, detail="Invalid or missing X-Goog-Channel-Token")
        
    if not resource_state:
        raise HTTPException(status_code=400, detail="Missing X-Goog-Resource-State")
        
    # Process webhook (mocked for tests)
    return {"status": "ok"}
