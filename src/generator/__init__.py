"""Synthetic data generator package exports."""

from src.generator.config import GeneratorConfig
from src.generator.ingestion import (
    BenchmarkResult,
    copy_batch,
    ingest_synthetic_transactions,
    insert_batch_naive,
    run_ingestion_benchmark,
)
from src.generator.patterns import (
    FraudPatternType,
    UserProfile,
    create_user_profiles,
    generate_baseline_transaction,
    inject_amount_deviation,
    inject_geographic_impossibility,
    inject_new_device_high_amount,
    inject_round_number_structuring,
    inject_velocity_fraud,
)
from src.generator.synthetic_data import generate_transactions

__all__ = [
    "BenchmarkResult",
    "FraudPatternType",
    "GeneratorConfig",
    "UserProfile",
    "copy_batch",
    "create_user_profiles",
    "generate_baseline_transaction",
    "generate_transactions",
    "ingest_synthetic_transactions",
    "inject_amount_deviation",
    "inject_geographic_impossibility",
    "inject_new_device_high_amount",
    "inject_round_number_structuring",
    "inject_velocity_fraud",
    "insert_batch_naive",
    "run_ingestion_benchmark",
]
