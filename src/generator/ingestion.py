"""PostgreSQL bulk data ingestion using psycopg COPY FROM STDIN mechanism and benchmark suite."""

import time
from dataclasses import dataclass
from typing import Any

import psycopg

from src.config import settings
from src.generator.config import GeneratorConfig
from src.generator.synthetic_data import generate_transactions

COPY_COLUMNS = (
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
)

COPY_SQL = f"COPY transactions ({', '.join(COPY_COLUMNS)}) FROM STDIN"

INSERT_SQL = f"""
INSERT INTO transactions ({", ".join(COPY_COLUMNS)})
VALUES ({", ".join(["%s"] * len(COPY_COLUMNS))})
"""


@dataclass
class BenchmarkResult:
    """Benchmark performance metrics comparing COPY vs naive row-by-row INSERT."""

    sample_size: int
    insert_duration_seconds: float
    insert_rows_per_second: float
    copy_duration_seconds: float
    copy_rows_per_second: float
    speedup_factor: float


def get_sync_connection(db_url: str | None = None) -> psycopg.Connection:
    """Establish a direct synchronous psycopg connection for bulk ingestion."""
    url = db_url or settings.DATABASE_SYNC_URL
    return psycopg.connect(url, autocommit=False)


def copy_batch(cursor: psycopg.Cursor, batch: list[dict[str, Any]]) -> int:
    """Stream a batch of transactions into PostgreSQL using psycopg 3 COPY FROM STDIN."""
    with cursor.copy(COPY_SQL) as copy:
        for row in batch:
            row_tuple = (
                str(row["transaction_id"]),
                row["user_id"],
                row["transaction_date"],
                row["amount"],
                row["currency"],
                row["merchant_category"],
                row["merchant_country"],
                row["card_present"],
                row["device_id"],
                row["ip_country"],
                row["is_flagged"],
                row["flag_reason"],
                row["fraud_score"],
                row["created_at"],
            )
            copy.write_row(row_tuple)
    return len(batch)


def insert_batch_naive(cursor: psycopg.Cursor, batch: list[dict[str, Any]]) -> int:
    """Insert records one-by-one via individual execute calls (naive baseline for benchmarking)."""
    for row in batch:
        row_tuple = (
            str(row["transaction_id"]),
            row["user_id"],
            row["transaction_date"],
            row["amount"],
            row["currency"],
            row["merchant_category"],
            row["merchant_country"],
            row["card_present"],
            row["device_id"],
            row["ip_country"],
            row["is_flagged"],
            row["flag_reason"],
            row["fraud_score"],
            row["created_at"],
        )
        cursor.execute(INSERT_SQL, row_tuple)
    return len(batch)


def ingest_synthetic_transactions(
    config: GeneratorConfig,
    db_url: str | None = None,
    truncate_first: bool = False,
) -> dict[str, Any]:
    """Generate and ingest synthetic transactions in streaming batches via PostgreSQL COPY."""
    start_time = time.perf_counter()
    total_inserted = 0

    with get_sync_connection(db_url) as conn, conn.cursor() as cursor:
        if truncate_first:
            cursor.execute("TRUNCATE TABLE transactions CASCADE;")
            conn.commit()

        for batch in generate_transactions(config):
            inserted = copy_batch(cursor, batch)
            conn.commit()
            total_inserted += inserted

    duration = time.perf_counter() - start_time
    throughput = total_inserted / duration if duration > 0 else 0.0

    return {
        "total_records": total_inserted,
        "duration_seconds": round(duration, 3),
        "rows_per_second": round(throughput, 1),
    }


def run_ingestion_benchmark(
    sample_size: int = 5_000,
    db_url: str | None = None,
) -> BenchmarkResult:
    """Run a comparative benchmark between naive row-by-row INSERT and COPY FROM STDIN."""
    config = GeneratorConfig(
        total_records=sample_size,
        fraud_rate=0.02,
        batch_size=sample_size,
        seed=12345,
    )
    test_batch = next(generate_transactions(config))

    with get_sync_connection(db_url) as conn, conn.cursor() as cursor:
        # 1. Benchmark Naive Row-by-Row INSERT
        start_insert = time.perf_counter()
        insert_batch_naive(cursor, test_batch)
        conn.commit()
        insert_duration = time.perf_counter() - start_insert
        insert_throughput = sample_size / insert_duration if insert_duration > 0 else 0.0

        # Clean up test rows from naive run
        cursor.execute("TRUNCATE TABLE transactions CASCADE;")
        conn.commit()

        # 2. Benchmark COPY FROM STDIN
        start_copy = time.perf_counter()
        copy_batch(cursor, test_batch)
        conn.commit()
        copy_duration = time.perf_counter() - start_copy
        copy_throughput = sample_size / copy_duration if copy_duration > 0 else 0.0

        # Clean up test rows
        cursor.execute("TRUNCATE TABLE transactions CASCADE;")
        conn.commit()

    speedup = copy_throughput / insert_throughput if insert_throughput > 0 else 1.0

    return BenchmarkResult(
        sample_size=sample_size,
        insert_duration_seconds=round(insert_duration, 4),
        insert_rows_per_second=round(insert_throughput, 1),
        copy_duration_seconds=round(copy_duration, 4),
        copy_rows_per_second=round(copy_throughput, 1),
        speedup_factor=round(speedup, 2),
    )
