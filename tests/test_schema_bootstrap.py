"""TASK-08: Verify schema.sql applies cleanly on a fresh database (idempotency)."""

from pathlib import Path

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_schema_applies_cleanly_on_fresh_database(pg_admin_conn):
    schema_sql = Path("trimcp/schema.sql").read_text(encoding="utf-8")

    await pg_admin_conn.execute(schema_sql)
    await pg_admin_conn.execute(schema_sql)  # second apply must not error

    exists = await pg_admin_conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name='embedding_migrations')"
    )
    assert exists is True

    has_namespace_id = await pg_admin_conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='embedding_migrations' "
        "AND column_name='namespace_id')"
    )
    assert has_namespace_id is True
