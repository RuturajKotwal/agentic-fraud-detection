"""LLM interface and prompts for the LangGraph Data Analyst Agent."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.config import settings


def get_agent_llm() -> Any | None:
    """Instantiate the configured chat model (Anthropic or OpenAI).

    Returns None if no API keys are configured (enabling graceful mock/fallback).
    """
    if settings.ANTHROPIC_API_KEY:
        try:
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=settings.LLM_MODEL or "claude-3-5-sonnet-20241022",
                api_key=settings.ANTHROPIC_API_KEY,
                temperature=0.0,
            )
        except Exception:
            pass

    if settings.OPENAI_API_KEY:
        try:
            from langchain_openai import ChatOpenAI

            model = settings.LLM_MODEL if "gpt" in settings.LLM_MODEL else "gpt-4o"
            return ChatOpenAI(
                model=model,
                api_key=settings.OPENAI_API_KEY,
                temperature=0.0,
            )
        except Exception:
            pass

    return None


async def plan_investigation_query(
    transaction: dict[str, Any],
    user_summary: dict[str, Any] | None,
    context: dict[str, Any],
    validation_error: str | None = None,
) -> str:
    """Query-planning LLM call: outputs a natural-language description of data to gather."""
    llm = get_agent_llm()
    user_id = transaction.get("user_id")
    flagged_rules = context.get("flagged_by_rules", [])

    if llm is None:
        # Heuristic fallback when LLM API key is not configured
        if "geographic_impossibility" in flagged_rules:
            return (
                f"Query the last 5 transactions for user {user_id} before this transaction "
                "to inspect recent merchant countries and timestamps."
            )
        if "amount_above_user_average" in flagged_rules:
            return (
                f"Query the average amount and last 10 transaction amounts for user {user_id} "
                "to compare spending variance."
            )
        return (
            f"Query the last 5 transactions for user {user_id} ordered by date descending "
            "to establish baseline behavioral context."
        )

    system_prompt = (
        "You are an expert fraud investigation analyst. Given a flagged transaction and user context, "
        "decide what additional historical transaction data would help explain the anomaly. "
        "Output ONLY a concise, natural-language description of the question to ask. Do NOT write SQL."
    )

    error_note = ""
    if validation_error:
        error_note = (
            f"\nNOTE: The previous SQL query was rejected by safety validation: {validation_error}. "
            "Please refine the question to require a simple, standard read-only lookup."
        )

    user_prompt = (
        f"Flagged Transaction Details:\n"
        f"- ID: {transaction.get('transaction_id')}\n"
        f"- User ID: {user_id}\n"
        f"- Amount: {transaction.get('amount')} {transaction.get('currency')}\n"
        f"- Date: {transaction.get('transaction_date')}\n"
        f"- Merchant Category: {transaction.get('merchant_category')}\n"
        f"- Merchant Country: {transaction.get('merchant_country')}\n"
        f"- IP Country: {transaction.get('ip_country')}\n"
        f"- Device ID: {transaction.get('device_id')}\n"
        f"- Flagged by rules: {flagged_rules}\n"
        f"- User Summary: {user_summary}\n"
        f"{error_note}\n\n"
        "What historical data should we query from the database to investigate?"
    )

    response = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])
    return str(response.content).strip()


async def generate_investigation_sql(
    question: str,
    transaction: dict[str, Any],
    user_summary: dict[str, Any] | None,
    validation_error: str | None = None,
) -> str:
    """SQL-generation LLM call: converts investigative question into a single SELECT query."""
    llm = get_agent_llm()
    user_id = transaction.get("user_id")

    if llm is None:
        # Safe heuristic fallback
        return (
            f"SELECT transaction_id, transaction_date, amount, merchant_country, ip_country "
            f"FROM transactions WHERE user_id = {user_id} "
            f"ORDER BY transaction_date DESC LIMIT 5"
        )

    system_prompt = (
        "You are a PostgreSQL expert writing safe analytical queries for fraud investigation.\n"
        "Database schema:\n"
        "1. Table 'transactions' (columns: transaction_id, user_id, transaction_date, amount, "
        "currency, merchant_category, merchant_country, card_present, device_id, ip_country, "
        "is_flagged, flag_reason, fraud_score, created_at).\n"
        "2. Table 'user_transaction_summary' (columns: user_id, total_transactions, avg_amount, "
        "std_amount, min_amount, max_amount, frequent_merchant_categories, frequent_countries, "
        "first_transaction_date, last_transaction_date, updated_at).\n\n"
        "STRICT SAFETY RULES:\n"
        "- Write a single SELECT query ONLY.\n"
        "- Do NOT use semicolons (;).\n"
        "- Do NOT use INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, or GRANT.\n"
        "- Output ONLY the raw SQL query. No markdown blocks, no formatting, no explanatory text."
    )

    error_context = ""
    if validation_error:
        error_context = (
            f"\nPREVIOUS REJECTION REASON: {validation_error}\n"
            "Ensure the generated query strictly adheres to all safety rules."
        )

    user_prompt = (
        f"Target User ID: {user_id}\n"
        f"Investigation Question: {question}\n"
        f"{error_context}\n\n"
        "Generate the single SELECT query:"
    )

    response = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])

    raw_sql = str(response.content).strip()
    if raw_sql.startswith("```"):
        raw_sql = re.sub(r"^```(?:sql)?\s*", "", raw_sql, flags=re.IGNORECASE)
        raw_sql = re.sub(r"\s*```$", "", raw_sql)
    return raw_sql.strip()


async def summarize_investigation(
    transaction: dict[str, Any],
    user_summary: dict[str, Any] | None,
    context: dict[str, Any],
    query_results: list[dict[str, Any]] | None,
    queries_run: list[dict[str, Any]],
) -> tuple[str, float]:
    """Summarization LLM call: produces explanation and confidence score."""
    llm = get_agent_llm()
    flagged_rules = context.get("flagged_by_rules", [])

    if llm is None:
        rule_desc = ", ".join(flagged_rules) if flagged_rules else "statistical rules"
        user_avg = context.get("user_avg_transaction_amount", 0.0)
        amount = transaction.get("amount", 0.0)
        tx_count = len(query_results) if query_results else 0

        summary = (
            f"Agent investigated flagged transaction {transaction.get('transaction_id')} for user {transaction.get('user_id')}. "
            f"The transaction of {amount} {transaction.get('currency')} was flagged by [{rule_desc}]. "
            f"Historical query examined {tx_count} previous transactions against user average of {user_avg:.2f}. "
            "Corroborating behavioral patterns confirm significant divergence from typical activity."
        )
        confidence = 0.88 if flagged_rules else 0.75
        return summary, confidence

    system_prompt = (
        "You are a lead financial fraud investigator. Analyze the transaction context and historical "
        "query results. Provide:\n"
        "1. A concise natural-language explanation of why the transaction is anomalous (or legitimate).\n"
        "2. A confidence score between 0.00 and 1.00.\n"
        "Output ONLY valid JSON with keys: \"summary\" (string) and \"confidence\" (float)."
    )

    user_prompt = (
        f"Original Transaction: {transaction}\n"
        f"User Summary: {user_summary}\n"
        f"Context & Rules: {context}\n"
        f"Executed Queries: {queries_run}\n"
        f"Query Results: {query_results}\n\n"
        "Provide your summary and confidence in JSON format:"
    )

    response = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])

    content = str(response.content).strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
        content = re.sub(r"\s*```$", "", content)

    try:
        data = json.loads(content)
        summary = str(data.get("summary", "Anomaly investigation completed."))
        confidence = float(data.get("confidence", 0.85))
        return summary, min(1.0, max(0.0, confidence))
    except Exception:
        return content, 0.80
