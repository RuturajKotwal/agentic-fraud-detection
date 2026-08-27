"""SQLAlchemy declarative models for transactions and summaries."""

import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Transaction(Base):
    """Partitioned transactions model.
    
    Partitioned by RANGE on transaction_date.
    Composite PK: (transaction_id, transaction_date).
    """

    __tablename__ = "transactions"

    transaction_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    transaction_date: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    merchant_category: Mapped[str] = mapped_column(String(50), nullable=False)
    merchant_country: Mapped[str] = mapped_column(String(2), nullable=False)
    card_present: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    flag_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    fraud_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    __table_args__ = (
        PrimaryKeyConstraint("transaction_id", "transaction_date"),
    )


class UserTransactionSummary(Base):
    """Precomputed per-user transaction aggregates."""

    __tablename__ = "user_transaction_summary"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    total_transactions: Mapped[int] = mapped_column(nullable=False, default=0)
    avg_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    std_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), nullable=True, default=Decimal("0.00")
    )
    min_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), nullable=True, default=Decimal("0.00")
    )
    max_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), nullable=True, default=Decimal("0.00")
    )
    frequent_merchant_categories: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, nullable=False
    )
    frequent_countries: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, nullable=False
    )
    first_transaction_date: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    last_transaction_date: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
