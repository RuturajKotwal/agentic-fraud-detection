"""API Router for transaction queries and investigation commands."""

import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import InvestigationResponse, TransactionResponse
from src.db.models import Transaction
from src.db.session import get_db

router = APIRouter()


@router.get("/flagged", response_model=list[TransactionResponse])
async def get_flagged_transactions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    start_date: datetime.datetime | None = None,
    end_date: datetime.datetime | None = None,
    merchant_category: str | None = None,
    min_fraud_score: float | None = None,
    session: AsyncSession = Depends(get_db),
) -> list[Transaction]:
    """Retrieve paginated flagged transactions with optional filters."""
    # Always filter to flagged transactions
    stmt = select(Transaction).where(Transaction.is_flagged == True)

    # Optional Date range filter
    if start_date:
        stmt = stmt.where(Transaction.transaction_date >= start_date)
    if end_date:
        stmt = stmt.where(Transaction.transaction_date <= end_date)

    # Optional merchant category filter
    if merchant_category:
        stmt = stmt.where(Transaction.merchant_category == merchant_category)

    # Optional minimum fraud score filter
    if min_fraud_score is not None:
        stmt = stmt.where(Transaction.fraud_score >= min_fraud_score)

    # Order by date descending, then paginate
    stmt = stmt.order_by(Transaction.transaction_date.desc()).offset(skip).limit(limit)

    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> Transaction:
    """Retrieve full details for a single transaction by ID."""
    stmt = select(Transaction).where(Transaction.transaction_id == transaction_id)
    result = await session.execute(stmt)
    transaction = result.scalar_one_or_none()
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    return transaction


@router.post("/{transaction_id}/investigate", response_model=InvestigationResponse)
async def investigate_transaction(
    transaction_id: UUID,
) -> dict[str, str | UUID]:
    """Stub endpoint to queue a LangGraph investigation."""
    return {
        "transaction_id": transaction_id,
        "status": "queued",
        "message": "LangGraph agent investigation stub",
    }
