"""State definition for the LangGraph Data Analyst Agent."""

from __future__ import annotations

from typing import Any, TypedDict
from uuid import UUID


class AgentState(TypedDict, total=False):
    """State carried through the fraud investigation LangGraph workflow."""

    transaction_id: str | UUID
    transaction: dict[str, Any] | None
    user_summary: dict[str, Any] | None
    context: dict[str, Any]
    query_plan: str | None
    generated_sql: str | None
    validated_sql: str | None
    validation_error: str | None
    sql_attempts: int
    queries_run: list[dict[str, Any]]
    query_results: list[dict[str, Any]] | None
    execution_error: str | None
    summary: str | None
    confidence: float
    status: str
