#!/usr/bin/env python3
"""Apply trimcp/schema.sql to the database named by PG_DSN or DATABASE_URL."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg


def _dsn() -> str:
    raw = (os.getenv("PG_DSN") or os.getenv("DATABASE_URL") or "").strip()
    if not raw:
        print("PG_DSN or DATABASE_URL is required", file=sys.stderr)
        sys.exit(1)
    return raw


async def _main() -> None:
    schema_path = Path(__file__).resolve().parents[1] / "trimcp" / "schema.sql"
    sql = schema_path.read_text(encoding="utf-8")
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute(sql)
    finally:
        await conn.close()
    print(f"Applied schema from {schema_path}")


if __name__ == "__main__":
    asyncio.run(_main())
