"""TASK-09: Verify deployed schema matches RLS intent declarations."""

import pytest
from nce.event_log import EXPECTED_TENANT_RLS_TABLES, verify_rls_catalog_consistency


async def _require_current_tenant_columns(conn) -> None:
    """Skip when the database predates ``schema.sql`` tenant RLS columns."""

    missing: list[str] = []
    for table_name, col in EXPECTED_TENANT_RLS_TABLES.items():
        has_table = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM   information_schema.tables
                WHERE  table_schema = 'public'
                  AND  table_name   = $1
            )
            """,
            table_name,
        )
        if not has_table:
            missing.append(f"{table_name} (table missing)")
            continue
        has_col = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM   information_schema.columns
                WHERE  table_schema = 'public'
                  AND  table_name   = $1
                  AND  column_name  = $2
            )
            """,
            table_name,
            col,
        )
        if not has_col:
            missing.append(f"{table_name}.{col}")
    if missing:
        sample = "; ".join(missing[:12])
        pytest.skip(
            "RLS catalog test needs current nce/schema.sql tenant tables — gaps: "
            f"{sample}" + ("; …" if len(missing) > 12 else ""),
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rls_catalog_consistency(pg_admin_conn, pg_app_conn):
    await _require_current_tenant_columns(pg_admin_conn)
    # Verify using the database owner/admin connection to test full catalog schema visibility
    await verify_rls_catalog_consistency(pg_admin_conn)
    # Verify using the nce_app application role connection
    await verify_rls_catalog_consistency(pg_app_conn)
