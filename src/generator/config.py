"""Configuration schemas and settings for synthetic data generation."""

import datetime
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class GeneratorConfig:
    """Settings controlling synthetic dataset creation and fraud pattern injection."""

    total_records: int = 100_000
    fraud_rate: float = 0.02  # 2% injection rate (default in range 1-3%)
    num_users: int = 5_000
    start_date: datetime.datetime = field(
        default_factory=lambda: datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=datetime.UTC)
    )
    end_date: datetime.datetime = field(
        default_factory=lambda: datetime.datetime(2025, 12, 31, 23, 59, 59, tzinfo=datetime.UTC)
    )
    batch_size: int = 25_000
    seed: int | None = 42

    # Distribution parameters
    primary_currencies: list[str] = field(default_factory=lambda: ["USD", "EUR", "GBP"])
    currency_weights: list[float] = field(default_factory=lambda: [0.80, 0.15, 0.05])

    primary_countries: list[str] = field(
        default_factory=lambda: ["US", "GB", "DE", "FR", "CA", "JP", "AU"]
    )
    country_weights: list[float] = field(
        default_factory=lambda: [0.65, 0.10, 0.08, 0.07, 0.04, 0.03, 0.03]
    )

    merchant_categories: list[str] = field(
        default_factory=lambda: [
            "grocery",
            "dining",
            "retail",
            "electronics",
            "travel",
            "entertainment",
            "utilities",
            "health",
            "luxury",
        ]
    )
    category_weights: list[float] = field(
        default_factory=lambda: [0.25, 0.20, 0.18, 0.10, 0.08, 0.07, 0.05, 0.04, 0.03]
    )

    # Structuring threshold amounts (just under common AML/reporting thresholds like $10k, $5k, $3k)
    structuring_amounts: list[Decimal] = field(
        default_factory=lambda: [
            Decimal("9900.00"),
            Decimal("9950.00"),
            Decimal("9850.00"),
            Decimal("4900.00"),
            Decimal("4950.00"),
            Decimal("2900.00"),
            Decimal("2950.00"),
        ]
    )

    def validate(self) -> None:
        """Validate configuration constraints."""
        if not 0.0 <= self.fraud_rate <= 1.0:
            raise ValueError(f"Fraud rate {self.fraud_rate} must be between 0.0 and 1.0.")
        if self.total_records <= 0:
            raise ValueError("total_records must be greater than 0.")
        if self.num_users <= 0:
            raise ValueError("num_users must be greater than 0.")
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date.")
