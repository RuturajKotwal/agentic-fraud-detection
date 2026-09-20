"""LangGraph definition for the Fraud Investigation Data Analyst Agent."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langgraph.graph import END, START, StateGraph

from src.agent.nodes import (
    context_gathering_node,
    execution_node,
    query_planning_node,
    should_continue,
    sql_generation_node,
    sql_validation_node,
    summarization_node,
)
from src.agent.state import AgentState


def build_agent_graph() -> Any:
    """Construct and compile the state graph for transaction investigation."""
    workflow = StateGraph(AgentState)

    # Add Nodes
    workflow.add_node("context_gathering", context_gathering_node)
    workflow.add_node("query_planning", query_planning_node)
    workflow.add_node("sql_generation", sql_generation_node)
    workflow.add_node("sql_validation", sql_validation_node)
    workflow.add_node("execution", execution_node)
    workflow.add_node("summarization", summarization_node)

    # Add Edges
    workflow.add_edge(START, "context_gathering")
    workflow.add_edge("context_gathering", "query_planning")
    workflow.add_edge("query_planning", "sql_generation")
    workflow.add_edge("sql_generation", "sql_validation")

    # Conditional routing after validation (execution, retry query_planning, or give up to summarization)
    workflow.add_conditional_edges(
        "sql_validation",
        should_continue,
        {
            "execution": "execution",
            "query_planning": "query_planning",
            "summarization": "summarization",
        },
    )

    workflow.add_edge("execution", "summarization")
    workflow.add_edge("summarization", END)

    return workflow.compile()


# Pre-compiled agent graph application
agent_app = build_agent_graph()


async def run_investigation(transaction_id: str | UUID) -> dict[str, Any]:
    """Execute the compiled LangGraph agent workflow for a given transaction ID."""
    initial_state: AgentState = {
        "transaction_id": transaction_id,
        "sql_attempts": 0,
        "queries_run": [],
    }
    result = await agent_app.ainvoke(initial_state)
    return result
