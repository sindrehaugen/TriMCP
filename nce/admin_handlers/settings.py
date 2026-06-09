from __future__ import annotations

import json
import os
from typing import Any

from starlette.responses import JSONResponse

from nce import admin_state
from nce.admin_handlers._shared import UTC, logger
from nce.config import cfg
from nce.settings_registry import (
    REGISTRY,
    SettingMetadata,
    validate_bool,
    validate_str_list,
)


def get_validation_metadata(metadata: SettingMetadata) -> dict[str, Any]:
    """Inspect registry validator closures to extract min and allow_empty rules."""
    validator = metadata.validator
    val_dict: dict[str, Any] = {}
    if validator == validate_bool:
        return val_dict
    if validator == validate_str_list:
        return val_dict

    closure = getattr(validator, "__closure__", None)
    code = getattr(validator, "__code__", None)
    if closure and code:
        co_freevars = getattr(code, "co_freevars", ())
        for var_name, cell in zip(co_freevars, closure):
            try:
                val = cell.cell_contents
                if var_name == "minimum" and val is not None:
                    val_dict["min"] = val
                elif var_name == "allow_empty":
                    val_dict["allow_empty"] = val
            except (ValueError, AttributeError):
                pass
    return val_dict


def get_effective_value(
    key: str,
    metadata: SettingMetadata,
    db_overrides: dict[str, Any],
) -> tuple[Any, str, bool]:
    """Determine a setting's effective value, its source (store, env, or default), and override status."""
    if key == "NCE_MASTER_KEY":
        source = "env" if "NCE_MASTER_KEY" in os.environ else "default"
        val = getattr(cfg, "NCE_MASTER_KEY", None)
        if val:
            val = "••••set"
        return val, source, False

    if key in db_overrides:
        row = db_overrides[key]
        is_secret = row["is_secret"]
        if is_secret:
            has_sec = row.get("has_secret")
            if has_sec is None:
                has_sec = bool(row.get("secret_enc"))
            val = "••••set" if has_sec else None
            return val, "store", True
        else:
            val = row["value"]
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except Exception:
                    pass
            return val, "store", True

    if key in os.environ:
        val = getattr(cfg, key, None)
        if metadata.is_secret:
            val = "••••set" if val else None
        return val, "env", False

    val = getattr(cfg, key, None)
    if metadata.is_secret:
        val = "••••set" if val else None
    return val, "default", False


async def api_admin_settings_list(request: Any) -> JSONResponse:
    """GET /api/admin/settings

    List registered configuration settings grouped by section.
    Supports query filters:
      - section: filter by exact section name match
      - q: case-insensitive query matching key or description
    """
    if not admin_state.engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    section_filter = request.query_params.get("section")
    q_filter = request.query_params.get("q")

    # Fetch all DB overrides to avoid N+1 queries
    db_overrides: dict[str, Any] = {}
    if admin_state.engine.pg_pool:
        try:
            async with admin_state.engine.pg_pool.acquire(timeout=10.0) as conn:
                rows = await conn.fetch(
                    "SELECT key, value, (secret_enc IS NOT NULL) AS has_secret, is_secret, updated_by, updated_at FROM settings"
                )
                for row in rows:
                    db_overrides[row["key"]] = row
        except Exception as e:
            logger.error("Failed to fetch settings overrides from Postgres: %s", e)

    sections_list: list[str] = []
    section_to_keys: dict[str, list[dict[str, Any]]] = {}

    for key, metadata in REGISTRY.items():
        if section_filter and metadata.section != section_filter:
            continue
        if q_filter:
            q_lower = q_filter.lower()
            if q_lower not in key.lower() and q_lower not in metadata.description.lower():
                continue

        if metadata.section not in section_to_keys:
            sections_list.append(metadata.section)
            section_to_keys[metadata.section] = []

        effective_value, source, store_value_set = get_effective_value(key, metadata, db_overrides)
        validation_dict = get_validation_metadata(metadata)

        key_detail = {
            "key": key,
            "type": metadata.type,
            "reload_class": metadata.reload_class,
            "is_secret": metadata.is_secret,
            "prod_locked": metadata.prod_locked,
            "effective_value": effective_value,
            "source": source,
            "store_value_set": store_value_set,
            "validation": validation_dict,
            "description": metadata.description,
            "updated_by": None,
            "updated_at": None,
        }

        if store_value_set and key in db_overrides:
            row = db_overrides[key]
            key_detail["updated_by"] = row["updated_by"]
            if row["updated_at"]:
                key_detail["updated_at"] = row["updated_at"].astimezone(UTC).isoformat()

        section_to_keys[metadata.section].append(key_detail)

    response_sections = []
    for sec_name in sections_list:
        keys = section_to_keys[sec_name]
        if keys:
            response_sections.append({"section": sec_name, "keys": keys})

    return JSONResponse({"sections": response_sections})


async def api_admin_settings_effective(request: Any) -> JSONResponse:
    """GET /api/admin/settings/effective

    Returns a flat key-value object of all settings with effective values (secrets masked).
    """
    if not admin_state.engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    db_overrides: dict[str, Any] = {}
    if admin_state.engine.pg_pool:
        try:
            async with admin_state.engine.pg_pool.acquire(timeout=10.0) as conn:
                rows = await conn.fetch("SELECT key, value, (secret_enc IS NOT NULL) AS has_secret, is_secret FROM settings")
                for row in rows:
                    db_overrides[row["key"]] = row
        except Exception as e:
            logger.error("Failed to fetch settings overrides for effective: %s", e)

    effective_dict = {}
    for key, metadata in REGISTRY.items():
        effective_value, _, _ = get_effective_value(key, metadata, db_overrides)
        effective_dict[key] = effective_value

    return JSONResponse(effective_dict)


async def api_admin_settings_get(request: Any) -> JSONResponse:
    """GET /api/admin/settings/{key}

    Returns detailed schema, metadata, and status for a single configuration setting.
    """
    if not admin_state.engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    key = request.path_params.get("key")
    if not key or key not in REGISTRY:
        return JSONResponse({"error": f"Setting key '{key}' not found"}, status_code=404)

    metadata = REGISTRY[key]

    db_row = None
    if admin_state.engine.pg_pool:
        try:
            async with admin_state.engine.pg_pool.acquire(timeout=10.0) as conn:
                db_row = await conn.fetchrow(
                    "SELECT key, value, (secret_enc IS NOT NULL) AS has_secret, is_secret, updated_by, updated_at FROM settings WHERE key = $1",
                    key,
                )
        except Exception as e:
            logger.error("Failed to fetch settings key '%s' from Postgres: %s", key, e)

    db_overrides = {key: db_row} if db_row else {}
    effective_value, source, store_value_set = get_effective_value(key, metadata, db_overrides)

    key_detail = {
        "key": key,
        "type": metadata.type,
        "reload_class": metadata.reload_class,
        "is_secret": metadata.is_secret,
        "prod_locked": metadata.prod_locked,
        "effective_value": effective_value,
        "source": source,
        "store_value_set": store_value_set,
        "validation": get_validation_metadata(metadata),
        "description": metadata.description,
        "updated_by": None,
        "updated_at": None,
    }

    if store_value_set and db_row:
        key_detail["updated_by"] = db_row["updated_by"]
        if db_row["updated_at"]:
            key_detail["updated_at"] = db_row["updated_at"].astimezone(UTC).isoformat()

    return JSONResponse(key_detail)


async def api_admin_settings_patch(request: Any) -> JSONResponse:
    """PATCH /api/admin/settings

    Batch apply settings updates with per-key status.
    Enforces optimistic-concurrency guard expected_updated_at (409),
    production-lock guard prod_locked (403),
    and server-side metadata validation (422).
    Appends a signed config_changed WORM event (secrets redacted to set/unset).
    """
    if not admin_state.engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    # Accept both {"settings": { ... }} and direct flat dictionary updates
    if isinstance(body, dict) and "settings" in body:
        updates = body["settings"]
        reason = body.get("reason", "")
    elif isinstance(body, dict):
        updates = {k: v for k, v in body.items() if k != "reason"}
        reason = body.get("reason", "")
    else:
        return JSONResponse({"error": "Invalid settings update payload format"}, status_code=422)

    if not isinstance(updates, dict):
        return JSONResponse({"error": "Settings must be a dictionary"}, status_code=422)

    # Extract actor (agent_id)
    agent_id = "admin"
    ns_ctx = getattr(request.state, "namespace_ctx", None)
    if ns_ctx and ns_ctx.agent_id:
        agent_id = ns_ctx.agent_id
    else:
        agent_id = request.headers.get("x-nce-agent-id") or "admin"

    # Pre-fetch all current DB overrides for the keys in the batch in a single query
    db_overrides: dict[str, Any] = {}
    if admin_state.engine.pg_pool:
        try:
            async with admin_state.engine.pg_pool.acquire(timeout=10.0) as conn:
                rows = await conn.fetch(
                    "SELECT key, value, (secret_enc IS NOT NULL) AS has_secret, is_secret, updated_by, updated_at FROM settings WHERE key = ANY($1)",
                    list(updates.keys()),
                )
                for row in rows:
                    db_overrides[row["key"]] = row
        except Exception as e:
            logger.error("Failed to pre-fetch settings overrides: %s", e)

    results: dict[str, dict[str, Any]] = {}
    has_rejections = False
    valid_updates: dict[str, dict[str, Any]] = {}

    import uuid
    from datetime import datetime, timezone

    # First pass: Validate all keys in the batch
    for key, update_info in updates.items():
        if key not in REGISTRY:
            results[key] = {
                "status": "rejected",
                "error": f"Setting key '{key}' not found in registry",
                "status_code": 422,
            }
            has_rejections = True
            continue

        metadata = REGISTRY[key]

        # Extract value and expected_updated_at
        if isinstance(update_info, dict) and (
            "value" in update_info or "expected_updated_at" in update_info
        ):
            value = update_info.get("value")
            expected_updated_at = update_info.get("expected_updated_at")
        else:
            value = update_info
            expected_updated_at = None

        # 1. Guardrail check: prod_locked -> 403
        if metadata.prod_locked:
            results[key] = {
                "status": "rejected",
                "error": f"Setting '{key}' is production locked and cannot be updated dynamically",
                "status_code": 403,
            }
            has_rejections = True
            continue

        # 2. Optimistic-concurrency guard: stale expected_updated_at -> 409
        db_row = db_overrides.get(key)
        db_updated_at = db_row["updated_at"] if db_row else None

        # If expected_updated_at is provided (either as string or None), check it
        if isinstance(update_info, dict) and "expected_updated_at" in update_info:
            is_stale = False
            if expected_updated_at is not None:
                try:
                    expected_dt = datetime.fromisoformat(
                        expected_updated_at.replace("Z", "+00:00")
                    ).astimezone(timezone.utc)
                    if db_updated_at is None:
                        is_stale = True
                    else:
                        db_dt = db_updated_at.astimezone(timezone.utc)
                        if expected_dt != db_dt:
                            is_stale = True
                except Exception as e:
                    results[key] = {
                        "status": "rejected",
                        "error": f"Invalid expected_updated_at format: {e}",
                        "status_code": 422,
                    }
                    has_rejections = True
                    continue
            else:
                if db_updated_at is not None:
                    is_stale = True

            if is_stale:
                results[key] = {
                    "status": "rejected",
                    "error": f"Optimistic lock conflict: Setting '{key}' has been updated since last read",
                    "status_code": 409,
                }
                has_rejections = True
                continue

        # 3. Secret no-op check: if is_secret is True and value is "••••set", skip validation/update
        if metadata.is_secret and value == "••••set":
            valid_updates[key] = {
                "value": value,
                "noop": True,
                "metadata": metadata,
            }
            continue

        # 4. Validation check -> 422
        if not metadata.validator(value):
            results[key] = {
                "status": "rejected",
                "error": f"Validation failed for setting '{key}'",
                "status_code": 422,
            }
            has_rejections = True
            continue

        valid_updates[key] = {
            "value": value,
            "noop": False,
            "metadata": metadata,
        }

    # If any key failed validation/concurrency/lock, reject the entire batch
    if has_rejections:
        for key in updates.keys():
            if key not in results:
                results[key] = {
                    "status": "rejected",
                    "error": "Batch aborted due to rejections on other keys",
                    "status_code": 422,
                }
        return JSONResponse({"settings": results}, status_code=207)

    # Second pass: Apply changes transactionally
    from nce import settings_store
    from nce.event_log import append_event

    updated_keys: list[str] = []
    event_changes: dict[str, dict[str, Any]] = {}

    def redact_value(val: Any, is_secret: bool) -> Any:
        if not is_secret:
            return val
        if val is not None and val != "":
            return "••••set"
        return "••••unset"

    try:
        async with admin_state.engine.pg_pool.acquire(timeout=10.0) as conn:
            async with conn.transaction():
                for key, info in valid_updates.items():
                    if info.get("noop"):
                        metadata = info["metadata"]
                        if metadata.reload_class == "HOT":
                            status = "applied"
                        elif metadata.reload_class == "WARM":
                            status = "pending_reload"
                        else:
                            status = "pending_restart"
                        results[key] = {"status": status}
                        continue

                    metadata = info["metadata"]
                    value = info["value"]

                    db_row = db_overrides.get(key)
                    if db_row:
                        old_raw = db_row["value"]
                        if db_row["is_secret"]:
                            old_val = "••••set" if db_row["has_secret"] else None
                        else:
                            if isinstance(old_raw, str):
                                try:
                                    old_val = json.loads(old_raw)
                                except Exception:
                                    old_val = old_raw
                            else:
                                old_val = old_raw
                    else:
                        old_val = getattr(cfg, key, None)

                    await settings_store.set(
                        key,
                        value,
                        is_secret=metadata.is_secret,
                        section=metadata.section,
                        updated_by=agent_id,
                        conn=conn,
                    )
                    updated_keys.append(key)

                    old_redacted = redact_value(old_val, metadata.is_secret)
                    new_redacted = redact_value(value, metadata.is_secret)

                    event_changes[key] = {
                        "old_value": old_redacted,
                        "new_value": new_redacted,
                    }

                    if metadata.reload_class == "HOT":
                        status = "applied"
                    elif metadata.reload_class == "WARM":
                        status = "pending_reload"
                    else:
                        status = "pending_restart"
                    results[key] = {"status": status}

                if updated_keys:
                    ns_id = None
                    if ns_ctx and ns_ctx.namespace_id:
                        ns_id = ns_ctx.namespace_id

                    if not ns_id:
                        ns_id_raw = await conn.fetchval(
                            "SELECT id FROM namespaces WHERE slug = '_global_legacy'"
                        )
                        if not ns_id_raw:
                            ns_id_raw = await conn.fetchval(
                                "SELECT id FROM namespaces ORDER BY created_at ASC LIMIT 1"
                            )
                        if ns_id_raw:
                            ns_id = (
                                uuid.UUID(str(ns_id_raw))
                                if not isinstance(ns_id_raw, uuid.UUID)
                                else ns_id_raw
                            )

                    if not ns_id:
                        raise RuntimeError("No namespace found to log config_changed event")

                    await append_event(
                        conn=conn,
                        namespace_id=ns_id,
                        agent_id=agent_id,
                        event_type="config_changed",
                        params={
                            "actor": agent_id,
                            "reason": reason,
                            "changes": event_changes,
                        },
                    )

    except Exception as exc:
        logger.exception("Failed to apply settings update transactionally: %s", exc)
        return JSONResponse({"error": f"Database transaction failed: {exc}"}, status_code=500)

    # Post-commit: Invalidate and populate Redis + local cache
    active_redis = admin_state.engine.redis_client
    if active_redis and updated_keys:
        try:
            for key in updated_keys:
                await active_redis.hdel("nce:settings:overrides", key)
                await active_redis.publish("nce:settings:invalidate", key)
        except Exception as e:
            logger.warning("Failed to invalidate Redis cache post-commit: %s", e)

    for key in updated_keys:
        settings_store._local_cache.pop(key, None)

    return JSONResponse({"settings": results}, status_code=207)
