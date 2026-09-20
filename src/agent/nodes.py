"""Graph nodes and routing logic for the LangGraph Data Analyst Agent."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select

from src.agent.db import execute_agent_query
from src.agent.llm import (
    generate_investigation_sql,
    plan_investigation_query,
    summarize_investigation,
)
from src.agent.sql_validator import validate_sql
from src.agent.state import AgentState
from src.db.models import Transaction, UserTransactionSummary
from src.db.session import async_session_factory


def _model_to_dict(obj: Any) -> dict[str, Any]:
    """Helper to convert SQLAlchemy model instance to dict with primitive types."""
    result: dict[str, Any] = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, (Decimal, UUID)):
            result[col.name] = str(val)
        elif isinstance(val, (datetime.datetime, datetime.date)):
            result[col.name] = val.isoformat()
        else:
            result[col.name] = val
    return result


async def context_gathering_node(state: AgentState) -> dict[str, Any]:
    """Fetch the flagged transaction and the corresponding user summary."""
    # If transaction is already populated in state (e.g. mock or pre-fetched in testing), use it directly
    if state.get("transaction"):
        tx_dict = state["transaction"]
        tx_uuid = tx_dict.get("transaction_id")
        summary_dict = state.get("user_summary")
        context = state.get("context")
        if not context:
            flag_reason = tx_dict.get("flag_reason", "")
            flagged_rules = [r.strip() for r in flag_reason.split(",") if r.strip()] if flag_reason else []
            user_avg = 0.0
            user_count = 0
            if summary_dict:
                user_avg = float(summary_dict.get("avg_amount", 0.0) or 0.0)
                user_count = summary_dict.get("total_transactions", 0)
            context = {
                "user_avg_transaction_amount": user_avg,
                "user_transaction_count_30d": user_count,
                "flagged_by_rules": flagged_rules,
            }
        return {
            "transaction_id": tx_uuid,
            "transaction": tx_dict,
            "user_summary": summary_dict,
            "context": context,
            "sql_attempts": 0,
            "queries_run": list(state.get("queries_run", [])),
        }

    raw_tx_id = state.get("transaction_id")
    if isinstance(raw_tx_id, str):
        tx_uuid = UUID(raw_tx_id)
    else:
        tx_uuid = raw_tx_id

    async with async_session_factory() as session:
        # 1. Fetch transaction
        stmt = select(Transaction).where(Transaction.transaction_id == tx_uuid)
        res = await session.execute(stmt)
        tx = res.scalar_one_or_none()
        if not tx:
            raise ValueError(f"Transaction {tx_uuid} not found")

        tx_dict = _model_to_dict(tx)

        # 2. Fetch user summary
        stmt_sum = select(UserTransactionSummary).where(
            UserTransactionSummary.user_id == tx.user_id
        )
        res_sum = await session.execute(stmt_sum)
        summary = res_sum.scalar_one_or_none()
        summary_dict = _model_to_dict(summary) if summary else None

    # Parse flagged rules
    flagged_rules = []
    if tx.flag_reason:
        flagged_rules = [r.strip() for r in tx.flag_reason.split(",") if r.strip()]

    user_avg = 0.0
    user_count_30d = 0
    if summary:
        user_avg = float(summary.avg_amount) if summary.avg_amount is not None else 0.0
        user_count_30d = summary.total_transactions

    context = {
        "user_avg_transaction_amount": user_avg,
        "user_transaction_count_30d": user_count_30d,
        "flagged_by_rules": flagged_rules,
    }

    return {
        "transaction_id": tx_uuid,
        "transaction": tx_dict,
        "user_summary": summary_dict,
        "context": context,
        "sql_attempts": 0,
        "queries_run": [],
    }


async def query_planning_node(state: AgentState) -> dict[str, Any]:
    """Formulate an analytical question to guide historical SQL generation."""
    tx = state["transaction"]
    summary = state.get("user_summary")
    context = state.get("context", {})
    validation_error = state.get("validation_error")

    question = await plan_investigation_query(
        transaction=tx,
        user_summary=summary,
        context=context,
        validation_error=validation_error,
    )

    return {"query_plan": question}


async def sql_generation_node(state: AgentState) -> dict[str, Any]:
    """Generate a single SELECT SQL statement from the query plan."""
    question = state["query_plan"]
    tx = state["transaction"]
    summary = state.get("user_summary")
    validation_error = state.get("validation_error")
    attempts = state.get("sql_attempts", 0) + 1

    sql = await generate_investigation_sql(
        question=question,
        transaction=tx,
        user_summary=summary,
        validation_error=validation_error,
    )

    return {
        "generated_sql": sql,
        "sql_attempts": attempts,
    }


async def sql_validation_node(state: AgentState) -> dict[str, Any]:
    """Validate generated SQL against strict security rules and record the attempt."""
    generated_sql = state.get("generated_sql", "")
    attempts = state.get("sql_attempts", 1)
    purpose = state.get("query_plan", "Investigate transaction history")
    queries_run = list(state.get("queries_run", []))

    is_valid, result_msg = validate_sql(generated_sql)

    if is_valid:
        # Record successful validation
        queries_run.append({
            "step": attempts,
            "purpose": purpose,
            "sql": result_msg,
            "row_count": 0,
            "execution_time_ms": 0,
            "status": "validated",
            "note": "Validation passed",
        })
        return {
            "validated_sql": result_msg,
            "validation_error": None,
            "queries_run": queries_run,
        }
    else:
        # Record rejected attempt with reason
        rejection_note = f"Rejected by validation: {result_msg}"
        queries_run.append({
            "step": attempts,
            "purpose": f"{purpose} ({rejection_note})",
            "sql": generated_sql,
            "row_count": 0,
            "execution_time_ms": 0,
            "status": "rejected",
            "note": rejection_note,
        })
        return {
            "validated_sql": None,
            "validation_error": result_msg,
            "queries_run": queries_run,
        }


def should_continue(state: AgentState) -> str:
    """Conditional router based on validation outcome and retry count (max 3)."""
    if state.get("validated_sql"):
        return "execution"

    attempts = state.get("sql_attempts", 0)
    if attempts < 3:
        return "query_planning"

    # Exceeded max attempts, give up gracefully
    return "summarization"


async def execution_node(state: AgentState) -> dict[str, Any]:
    """Execute validated SQL query via read-only agent_reader role."""
    validated_sql = state.get("validated_sql")
    queries_run = list(state.get("queries_run", []))

    if not validated_sql:
        return {"query_results": [], "execution_error": "No validated SQL to execute"}

    try:
        rows, count, duration_ms = await execute_agent_query(validated_sql)

        # Update the latest entry in queries_run with execution stats
        if queries_run:
            queries_run[-1]["row_count"] = count
            queries_run[-1]["execution_time_ms"] = duration_ms
            queries_run[-1]["status"] = "executed"

        return {
            "query_results": rows,
            "execution_error": None,
            "queries_run": queries_run,
        }
    except Exception as exc:
        err_msg = str(exc)
        if queries_run:
            queries_run[-1]["status"] = "execution_failed"
            queries_run[-1]["note"] = f"Execution failed: {err_msg}"

        return {
            "query_results": [],
            "execution_error": err_msg,
            "queries_run": queries_run,
        }


async def summarization_node(state: AgentState) -> dict[str, Any]:
    """Produce final natural-language explanation and confidence score."""
    tx = state["transaction"]
    summary = state.get("user_summary")
    context = state.get("context", {})
    query_results = state.get("query_results")
    queries_run = state.get("queries_run", [])

    summary_text, confidence = await summarize_investigation(
        transaction=tx,
        user_summary=summary,
        context=context,
        query_results=query_results,
        queries_run=queries_run,
    )

    return {
        "summary": summary_text,
        "confidence": confidence,
        "status": "completed",
    }
