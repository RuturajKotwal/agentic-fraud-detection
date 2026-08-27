"""Unit tests for SQLAlchemy models structure and metadata."""

from src.db.models import Transaction, UserTransactionSummary


def test_transaction_model_structure():
    """Verify Transaction model table name, primary key, and column definitions."""
    assert Transaction.__tablename__ == "transactions"
    
    # Verify Composite Primary Key (transaction_id, transaction_date)
    pk_cols = [col.name for col in Transaction.__table__.primary_key.columns]
    assert "transaction_id" in pk_cols
    assert "transaction_date" in pk_cols
    assert len(pk_cols) == 2

    # Verify essential columns
    col_names = {col.name for col in Transaction.__table__.columns}
    expected_cols = {
        "transaction_id",
        "user_id",
        "transaction_date",
        "amount",
        "currency",
        "merchant_category",
        "merchant_country",
        "card_present",
        "device_id",
        "ip_country",
        "is_flagged",
        "flag_reason",
        "fraud_score",
        "created_at",
    }
    assert expected_cols.issubset(col_names)


def test_user_transaction_summary_model_structure():
    """Verify UserTransactionSummary model table name and primary key."""
    assert UserTransactionSummary.__tablename__ == "user_transaction_summary"

    pk_cols = [col.name for col in UserTransactionSummary.__table__.primary_key.columns]
    assert pk_cols == ["user_id"]

    col_names = {col.name for col in UserTransactionSummary.__table__.columns}
    expected_cols = {
        "user_id",
        "total_transactions",
        "avg_amount",
        "std_amount",
        "min_amount",
        "max_amount",
        "frequent_merchant_categories",
        "frequent_countries",
        "first_transaction_date",
        "last_transaction_date",
        "updated_at",
    }
    assert expected_cols.issubset(col_names)
