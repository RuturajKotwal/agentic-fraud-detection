"""Pydantic schemas for the FastAPI transactions router."""

import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TransactionResponse(BaseModel):
    """Pydantic model representing a Transaction from the database."""

    transaction_id: UUID
    user_id: int
    transaction_date: datetime.datetime
    amount: Annotated[Decimal, Field(max_digits=14, decimal_places=2)]
    currency: str
    merchant_category: str
    merchant_country: str
    card_present: bool
    device_id: str | None
    ip_country: str | None
    is_flagged: bool
    flag_reason: str | None
    fraud_score: Annotated[Decimal | None, Field(max_digits=5, decimal_places=4)]
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class QueryRun(BaseModel):
    """Represents a single SQL query executed by the LangGraph agent."""
    step: int
    purpose: str
    sql: str
    row_count: int
    execution_time_ms: int


class InvestigationContext(BaseModel):
    """Contextual data drawn from the rules engine or user history."""
    user_avg_transaction_amount: float
    user_transaction_count_30d: int
    flagged_by_rules: list[str]


class InvestigationResponse(BaseModel):
    """Comprehensive response from the LangGraph investigation agent."""

    transaction_id: UUID
    status: str
    summary: str
    confidence: float
    queries_run: list[QueryRun]
    context: InvestigationContext
    generated_at: datetime.datetime
