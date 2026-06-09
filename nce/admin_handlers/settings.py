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
            val = "••••set" if row["secret_enc"] else None
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
                    "SELECT key, value, secret_enc, is_secret, updated_by, updated_at FROM settings"
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
                rows = await conn.fetch("SELECT key, value, secret_enc, is_secret FROM settings")
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
                    "SELECT key, value, secret_enc, is_secret, updated_by, updated_at FROM settings WHERE key = $1",
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
