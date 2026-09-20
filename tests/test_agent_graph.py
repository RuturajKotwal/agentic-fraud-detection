"""Tests for the LangGraph Data Analyst Agent (src/agent/).

Covers:
  - Graph compilation and node configuration
  - State management and schema conformance
  - sql_validation node with both valid and rejected SQL
  - Recording of every attempt in queries_run with notes on why
  - Retry routing loop back to query_planning upon validation rejection
  - Graceful exit after 3 failed attempts to summarization
  - Read-only execution via agent_reader
  - FastAPI endpoint POST /transactions/{id}/investigate integration
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.agent.graph import build_agent_graph
from src.agent.nodes import (
    should_continue,
    sql_validation_node,
)
from src.agent.state import AgentState
from src.api.main import app
from src.db.session import agent_engine, engine


@pytest.fixture(autouse=True)
async def reset_db_engines():
    """Ensure async connection pools do not cross event loops across tests."""
    await engine.dispose()
    await agent_engine.dispose()
    yield
    await engine.dispose()
    await agent_engine.dispose()


# ---------------------------------------------------------------------------
# 1. Graph Structure Tests
# ---------------------------------------------------------------------------


def test_agent_graph_structure():
    """Verify that the StateGraph compiles and contains all required nodes."""
    compiled_app = build_agent_graph()
    assert compiled_app is not None
    nodes = set(compiled_app.get_graph().nodes.keys())
    expected_nodes = {
        "__start__",
        "context_gathering",
        "query_planning",
        "sql_generation",
        "sql_validation",
        "execution",
        "summarization",
        "__end__",
    }
    assert expected_nodes.issubset(nodes)


# ---------------------------------------------------------------------------
# 2. SQL Validation Node & queries_run Logging Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sql_validation_node_accepts_valid_query():
    """Valid SELECT query is validated, injected with LIMIT if needed, and logged."""
    state: AgentState = {
        "query_plan": "Check recent user transactions",
        "generated_sql": "SELECT * FROM transactions WHERE user_id = 42",
        "sql_attempts": 1,
        "queries_run": [],
    }

    result = await sql_validation_node(state)
    assert result["validated_sql"] is not None
    assert "LIMIT 500" in result["validated_sql"]
    assert result["validation_error"] is None

    queries_run = result["queries_run"]
    assert len(queries_run) == 1
    assert queries_run[0]["step"] == 1
    assert queries_run[0]["status"] == "validated"
    assert queries_run[0]["sql"] == result["validated_sql"]
    assert "Validation passed" in queries_run[0]["note"]


@pytest.mark.asyncio
async def test_sql_validation_node_rejects_and_logs_destructive_query():
    """Blocked statements (e.g. DROP) are rejected and logged in queries_run with why."""
    state: AgentState = {
        "query_plan": "Check account balance",
        "generated_sql": "DROP TABLE transactions",
        "sql_attempts": 1,
        "queries_run": [],
    }

    result = await sql_validation_node(state)
    assert result["validated_sql"] is None
    assert result["validation_error"] is not None
    assert "DROP" in result["validation_error"] or "SELECT" in result["validation_error"]

    queries_run = result["queries_run"]
    assert len(queries_run) == 1
    assert queries_run[0]["step"] == 1
    assert queries_run[0]["status"] == "rejected"
    assert "rejected" in queries_run[0]["note"].lower()
    assert "rejected" in queries_run[0]["purpose"].lower()


@pytest.mark.asyncio
async def test_sql_validation_node_rejects_stacked_statements():
    """Stacked statements with semicolons are rejected and logged."""
    state: AgentState = {
        "query_plan": "Multi-query",
        "generated_sql": "SELECT * FROM transactions; SELECT * FROM users",
        "sql_attempts": 2,
        "queries_run": [{"step": 1, "status": "rejected"}],
    }

    result = await sql_validation_node(state)
    assert result["validated_sql"] is None
    assert "semicolon" in result["validation_error"].lower()

    queries_run = result["queries_run"]
    assert len(queries_run) == 2
    assert queries_run[1]["step"] == 2
    assert queries_run[1]["status"] == "rejected"
    assert "semicolon" in queries_run[1]["note"].lower()


# ---------------------------------------------------------------------------
# 3. Routing & Retry Logic Tests
# ---------------------------------------------------------------------------


def test_should_continue_routes_to_execution_on_valid_sql():
    """When validated_sql is present, route to execution."""
    state: AgentState = {
        "validated_sql": "SELECT * FROM transactions LIMIT 5",
        "sql_attempts": 1,
    }
    assert should_continue(state) == "execution"


def test_should_continue_retries_query_planning_under_limit():
    """When validation failed and attempts < 3, route back to query_planning."""
    state_attempt_1: AgentState = {
        "validated_sql": None,
        "sql_attempts": 1,
    }
    assert should_continue(state_attempt_1) == "query_planning"

    state_attempt_2: AgentState = {
        "validated_sql": None,
        "sql_attempts": 2,
    }
    assert should_continue(state_attempt_2) == "query_planning"


def test_should_continue_gives_up_after_three_attempts():
    """When validation failed and attempts == 3, give up and route to summarization."""
    state_attempt_3: AgentState = {
        "validated_sql": None,
        "sql_attempts": 3,
    }
    assert should_continue(state_attempt_3) == "summarization"


# ---------------------------------------------------------------------------
# 4. End-to-End Agent Workflow Tests with Retry Loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_retry_loop_recovers_on_second_attempt():
    """Agent encounters invalid SQL on attempt 1, re-plans, and succeeds on attempt 2."""
    tx_id = uuid4()
    mock_tx = {
        "transaction_id": str(tx_id),
        "user_id": 1001,
        "amount": 5000.0,
        "currency": "EUR",
        "transaction_date": "2025-01-15T12:00:00",
        "merchant_category": "electronics",
        "merchant_country": "US",
        "is_flagged": True,
        "flag_reason": "amount_above_user_average",
    }
    mock_summary = {"avg_amount": 120.0, "total_transactions": 15}

    sql_responses = [
        "UPDATE transactions SET amount = 0 WHERE user_id = 1001",
        "SELECT amount, transaction_date FROM transactions WHERE user_id = 1001 LIMIT 5",
    ]

    async def mock_sql_gen(question, transaction, user_summary, validation_error=None):
        nonlocal sql_responses
        if validation_error:
            return sql_responses[1]
        return sql_responses[0]

    async def mock_exec(sql):
        return [{"amount": 100.0}], 1, 12

    with patch("src.agent.nodes.generate_investigation_sql", side_effect=mock_sql_gen), \
         patch("src.agent.nodes.execute_agent_query", side_effect=mock_exec):

        test_graph = build_agent_graph()
        final_state = await test_graph.ainvoke({
            "transaction_id": tx_id,
            "transaction": mock_tx,
            "user_summary": mock_summary,
            "sql_attempts": 0,
            "queries_run": [],
        })

        assert final_state["status"] == "completed"
        queries = final_state["queries_run"]
        # Must record BOTH the rejected attempt and the successful attempt
        assert len(queries) == 2
        assert queries[0]["step"] == 1
        assert queries[0]["status"] == "rejected"
        assert "UPDATE" in queries[0]["note"]
        assert queries[1]["step"] == 2
        assert queries[1]["status"] == "executed"
        assert queries[1]["row_count"] == 1


@pytest.mark.asyncio
async def test_agent_max_attempts_gives_up_gracefully():
    """Agent exhausts all 3 attempts with invalid queries and finishes gracefully."""
    tx_id = uuid4()
    mock_tx = {
        "transaction_id": str(tx_id),
        "user_id": 999,
        "amount": 2500.0,
        "currency": "EUR",
        "is_flagged": True,
        "flag_reason": "rapid_succession",
    }

    async def mock_invalid_sql_gen(question, transaction, user_summary, validation_error=None):
        return "DELETE FROM transactions WHERE user_id = 999"

    with patch("src.agent.nodes.generate_investigation_sql", side_effect=mock_invalid_sql_gen):

        test_graph = build_agent_graph()
        final_state = await test_graph.ainvoke({
            "transaction_id": tx_id,
            "transaction": mock_tx,
            "user_summary": None,
            "sql_attempts": 0,
            "queries_run": [],
        })

        assert final_state["status"] == "completed"
        queries = final_state["queries_run"]
        # Exactly 3 rejected attempts recorded
        assert len(queries) == 3
        for i, q in enumerate(queries, 1):
            assert q["step"] == i
            assert q["status"] == "rejected"
            assert "DELETE" in q["note"]


# ---------------------------------------------------------------------------
# 5. FastAPI Endpoint POST /transactions/{id}/investigate Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_investigate_endpoint_404_for_unknown_id():
    """Endpoint returns 404 when transaction ID does not exist."""
    random_id = uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/transactions/{random_id}/investigate")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_investigate_endpoint_success():
    """Endpoint returns HTTP 200 and matches the expected investigation contract."""
    target_tx_id = None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        list_resp = await client.get("/transactions/flagged?limit=1")
        assert list_resp.status_code == 200
        txs = list_resp.json()
        if txs:
            target_tx_id = txs[0]["transaction_id"]

    if not target_tx_id:
        pytest.skip("No flagged transactions in database")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/transactions/{target_tx_id}/investigate")
        assert response.status_code == 200
        data = response.json()

        # Check required fields and shape
        assert data["transaction_id"] == target_tx_id
        assert data["status"] in ("completed", "failed")
        assert isinstance(data["summary"], str)
        assert len(data["summary"]) > 0
        assert isinstance(data["confidence"], float)
        assert 0.0 <= data["confidence"] <= 1.0
        assert isinstance(data["queries_run"], list)
        assert len(data["queries_run"]) >= 1

        # Verify queries_run entry structure
        first_query = data["queries_run"][0]
        assert "step" in first_query
        assert "purpose" in first_query
        assert "sql" in first_query
        assert "row_count" in first_query
        assert "execution_time_ms" in first_query

        # Check context
        assert "user_avg_transaction_amount" in data["context"]
        assert "user_transaction_count_30d" in data["context"]
        assert "flagged_by_rules" in data["context"]
        assert "generated_at" in data
