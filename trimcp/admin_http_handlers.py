"""Backward-compatible facade; implementation lives in ``trimcp.admin_handlers``."""

from trimcp.admin_handlers import *  # noqa: F403
from trimcp.admin_handlers._shared import (  # noqa: F401 — patch targets for tests
    cfg,
    fetch_fleet_overview_page,
    fetch_pg_rls_snapshot,
    logger,
    update_dotenv,
)
