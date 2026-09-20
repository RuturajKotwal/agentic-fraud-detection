"""Database access layer for the agent using the read-only agent_reader role."""

from __future__ import annotations

import datetime
from decimal import Decimal
import time
from typing import Any
from uuid import UUID

from sqlalchemy import text
from src.db.session import agent_session_factory


def _serialize_value(val: Any) -> Any:
    """Convert database types into JSON-serializable types."""
    if isinstance(val, (Decimal, UUID)):
        return str(val)
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.isoformat()
    return val


async def execute_agent_query(sql: str) -> tuple[list[dict[str, Any]], int, int]:
    """Execute a validated query using the read-only agent_reader role.

    Args:
        sql: Safe SELECT query that has passed validate_sql().

    Returns:
        Tuple of (rows as list of dicts, row_count, execution_time_ms).

    Raises:
        Exception: If execution fails (e.g., statement_timeout or DB error).
    """
    start_time = time.perf_counter()
    async with agent_session_factory() as session:
        result = await session.execute(text(sql))
        mappings = result.mappings().all()
        rows = [
            {k: _serialize_value(v) for k, v in row.items()}
            for row in mappings
        ]
        row_count = len(rows)

    execution_time_ms = max(1, int((time.perf_counter() - start_time) * 1000))
    return rows, row_count, execution_time_ms
