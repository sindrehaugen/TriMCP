from __future__ import annotations

import logging

from trimcp import admin_state
from trimcp.admin_app import app
from trimcp.admin_http_support import admin_error_response
from trimcp.admin_http_support import update_dotenv  # noqa: F401 — re-export for tests

logging.basicConfig(level=logging.INFO)

# Backward compatibility for tests patching admin_server.engine
engine = admin_state.engine


def _admin_error_response(*args, **kwargs):
    return admin_error_response(*args, **kwargs)


if __name__ == "__main__":
    import uvicorn

    from trimcp.config import assert_admin_override_not_in_production

    assert_admin_override_not_in_production()
    uvicorn.run(app, host="0.0.0.0", port=8003)

# Re-export handlers for existing tests
from trimcp.admin_http_handlers import *  # noqa: F403, E402
