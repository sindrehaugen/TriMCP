from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from redis import Redis
from starlette.responses import JSONResponse

from nce.config import cfg
from nce.extractors.dispatch import get_priority_queue
from nce.net_safety import BridgeURLValidationError, validate_webhook_payload_url
from nce.tasks import process_bridge_event

log = logging.getLogger("nce.webhook_receiver")

app = FastAPI(title="NCE Webhook Receiver")

# Production guardrails (override via nce.config.cfg / env).
_MAX_BODY_BYTES = cfg.WEBHOOK_MAX_BODY_BYTES
_RATE_LIMIT = cfg.WEBHOOK_RATE_LIMIT
_RATE_PERIOD_S = cfg.WEBHOOK_RATE_PERIOD_SECONDS

# In-memory sliding window per client IP (per webhook-receiver instance).
_ip_windows: dict[str, list[float]] = {}

_DEDUP_TTL_S = cfg.WEBHOOK_DEDUP_TTL_SECONDS
_DEDUP_FAIL_OPEN = cfg.WEBHOOK_DEDUP_FAIL_OPEN

# Atomic sliding-window rate limit (sync Redis; mirrors nce.auth._RATE_LIMIT_LUA).
_RATE_LIMIT_LUA = """
local key = KEYS[1]
local window_start = ARGV[1]
local now = ARGV[2]
local limit = tonumber(ARGV[3])
local period = tonumber(ARGV[4])

redis.call('ZREMRANGEBYSCORE', key, 0, window_start)
local count = redis.call('ZCARD', key)
if count >= limit then
    return 0
end
redis.call('ZADD', key, now, now)
redis.call('EXPIRE', key, period)
return 1
"""


@app.get("/health")
async def health():
    """Baseline healthcheck for container orchestration."""
    return {"status": "ok"}


def _require_cfg_secret(attr: str) -> str:
    value = (os.environ.get(attr) or getattr(cfg, attr, "") or "").strip()
    if not value:
        raise RuntimeError(
            f"{attr} must be set in the environment (no default allowed for webhook secrets)"
        )
    return value


DROPBOX_APP_SECRET = _require_cfg_secret("DROPBOX_APP_SECRET")
GRAPH_CLIENT_STATE = _require_cfg_secret("GRAPH_CLIENT_STATE")
DRIVE_CHANNEL_TOKEN = _require_cfg_secret("DRIVE_CHANNEL_TOKEN")


@lru_cache(maxsize=1)
def _redis_client() -> Redis:
    """Shared sync Redis client for RQ enqueue (one pool per process)."""
    return Redis.from_url(cfg.REDIS_URL)


def _client_ip(request: Request) -> str:
    """Client IP for rate limiting; honor X-Forwarded-For only behind a trusted proxy."""
    if cfg.NCE_WEBHOOK_TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _allow_webhook_request_memory(client_ip: str, path: str) -> bool:
    """In-memory sliding window keyed by IP + path (single-instance fallback)."""
    now = time.time()
    key = f"{client_ip}:{path}"
    window = _ip_windows.setdefault(key, [])
    window[:] = [t for t in window if t > now - _RATE_PERIOD_S]
    if len(window) >= _RATE_LIMIT:
        return False
    window.append(now)
    return True


def _allow_webhook_request_redis(client_ip: str, path: str) -> bool | None:
    """Redis sliding window; returns None when Redis is unavailable."""
    try:
        now = time.time()
        redis_key = f"nce:ratelimit:webhook:{client_ip}:{path}"
        result = _redis_client().eval(
            _RATE_LIMIT_LUA,
            1,
            redis_key,
            str(now - _RATE_PERIOD_S),
            str(now),
            str(_RATE_LIMIT),
            str(_RATE_PERIOD_S),
        )
        return bool(result)
    except Exception as exc:
        log.warning("Webhook Redis rate limiter unavailable: %s", exc)
        return None


def _allow_webhook_request(client_ip: str, path: str) -> bool:
    """Sliding-window rate limit keyed by IP + path (Redis with RAM fallback)."""
    redis_allowed = _allow_webhook_request_redis(client_ip, path)
    if redis_allowed is not None:
        return redis_allowed
    if cfg.IS_PROD:
        log.warning(
            "Webhook rate limit: Redis unavailable in production; rejecting ip=%s path=%s",
            client_ip,
            path,
        )
        return False
    return _allow_webhook_request_memory(client_ip, path)


def _dedup_key(provider: str, payload: dict[str, Any]) -> str | None:
    """Stable deduplication key per provider payload (None = always process)."""
    if provider == "dropbox":
        accounts = (payload.get("list_folder") or {}).get("accounts") or []
        if not accounts:
            return None
        digest = hashlib.sha256(
            json.dumps(sorted(accounts), sort_keys=True).encode("utf-8")
        ).hexdigest()[:32]
        return f"nce:webhook:dedup:dropbox:{digest}"
    if provider == "sharepoint":
        notifications = payload.get("notifications") or []
        parts: list[str] = []
        for note in notifications:
            if not isinstance(note, dict):
                continue
            note_id = note.get("id") or note.get("subscriptionId") or ""
            resource = note.get("resource") or ""
            change = note.get("changeType") or ""
            parts.append(f"{note_id}|{resource}|{change}")
        if not parts:
            return None
        digest = hashlib.sha256("|".join(sorted(parts)).encode("utf-8")).hexdigest()[:32]
        return f"nce:webhook:dedup:sharepoint:{digest}"
    if provider == "gdrive":
        channel_id = str(payload.get("channel_id") or "")
        if not channel_id:
            return None
        resource_id = str(payload.get("resource_id") or "")
        message_number = str(payload.get("message_number") or "")
        resource_state = str(payload.get("resource_state") or "")
        raw = f"{channel_id}|{resource_id}|{message_number}|{resource_state}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
        return f"nce:webhook:dedup:gdrive:{digest}"
    return None


def _claim_dedup(key: str) -> bool:
    """Return True when this delivery should be enqueued (first-seen within TTL)."""
    try:
        return bool(_redis_client().set(key, "1", nx=True, ex=_DEDUP_TTL_S))
    except Exception as exc:
        log.warning("Webhook dedup Redis unavailable: %s", exc)
        if _DEDUP_FAIL_OPEN:
            return True
        return False


async def _read_body_bounded(request: Request) -> bytes:
    """Read request body and reject oversize payloads before parsing."""
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > _MAX_BODY_BYTES:
                raise HTTPException(status_code=413, detail="Request body too large")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from None

    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Request body too large")
    return body


async def _read_json_bounded(request: Request) -> Any:
    body = await _read_body_bounded(request)
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from None


@app.middleware("http")
async def webhook_rate_limit_middleware(request: Request, call_next):
    """Apply per-IP rate limits on webhook routes only."""
    path = request.url.path
    if path.startswith("/webhooks/"):
        client_ip = _client_ip(request)
        if not _allow_webhook_request(client_ip, path):
            log.warning("Webhook rate limit exceeded ip=%s path=%s", client_ip, path)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
            )
    return await call_next(request)


def enqueue_process_bridge_event(provider: str, payload: dict[str, Any]) -> str:
    """Push ``process_bridge_event`` to the ``batch_processing`` queue lane.

    Webhook-triggered events are background work — they use the
    batch lane so real-time API extractions aren't starved (§5.4).
    Isolated for tests via monkeypatch.
    """
    dedup = _dedup_key(provider, payload)
    if dedup and not _claim_dedup(dedup):
        log.info("Webhook dedup skip provider=%s key=%s", provider, dedup)
        return "dedup-skipped"

    q = get_priority_queue(0, _redis_client())
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

    body = await _read_body_bounded(request)
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

    payload = await _read_json_bounded(request)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Validate clientState and resource URLs for security (SSRF guard)
    for notification in payload.get("value", []):
        client_state = notification.get("clientState")
        if not client_state or not hmac.compare_digest(client_state, GRAPH_CLIENT_STATE):
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
        raise HTTPException(status_code=403, detail="Invalid or missing X-Goog-Channel-Token")

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
