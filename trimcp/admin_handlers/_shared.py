"""Shared imports and constants for admin HTTP handlers."""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from starlette.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

from trimcp import admin_state
from trimcp.admin_http_support import (
    admin_client_error,
    admin_error_response,
    admin_validation_error,
    mask_uri_password,
    sanitize_admin_reason,
    serialize_pg_row,
    update_dotenv,
)
from trimcp.admin_routes import (
    ADMIN_MAX_LIST_LIMIT,
    ADMIN_MAX_ROWS_SKIP,
    ADMIN_NAMESPACES_DEFAULT_LIMIT,
    clamp_bounded_int,
    fetch_event_llm_payload_uri,
    fetch_fleet_overview_page,
    fetch_namespace_bridge_subscriptions,
    fetch_pg_rls_snapshot,
    fetch_recent_open_contradictions,
    fetch_salience_map_points,
    offset_from_page_limit,
    parse_optional_bigint_bounds,
    parse_optional_half_life_days,
    parse_optional_uuid,
    parse_page_limit_common,
    parse_salience_top_k,
    sanitize_event_type_filter,
    sanitize_optional_agent_filter,
    sanitize_resource_type_filter,
    sanitize_slug_prefix_filter,
    sanitize_task_name_filter,
    validate_dlq_status,
)
from trimcp.auth import set_namespace_context, validate_agent_id
from trimcp.background_task_manager import create_tracked_task
from trimcp.config import cfg
from trimcp.event_log import verify_merkle_chain
from trimcp.notifications import dispatcher
from trimcp.observability import MERKLE_CHAIN_VALID
from trimcp.signing import admin_signing_keys_status
from trimcp.temporal import parse_as_of

UTC = timezone.utc
logger = logging.getLogger("trimcp-admin")


