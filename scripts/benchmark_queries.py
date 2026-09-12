"""EXPLAIN ANALYZE benchmark: before and after index/partition pruning.

Run via:
    docker exec -e PYTHONPATH=/app fraud_detection_api python scripts/benchmark_queries.py
"""

import os

import psycopg

DB_URL = os.getenv(
    "DATABASE_SYNC_URL",
    "postgresql://postgres:postgres@postgres:5432/fraud_detection",
)

OUTPUT_DIR = "/tmp"

QUERIES = {
    "partition_pruning": (
        "SELECT COUNT(*) FROM transactions "
        "WHERE transaction_date >= '2024-06-01' AND transaction_date < '2024-07-01'"
    ),
    "brin_index": (
        "SELECT COUNT(*) FROM transactions "
        "WHERE transaction_date >= '2024-06-15 10:00:00' AND transaction_date < '2024-06-15 11:00:00'"
    ),
    "partial_index_flagged": (
        "SELECT COUNT(*) FROM transactions WHERE is_flagged = TRUE"
    ),
}


def run_explain(conn: psycopg.Connection, query: str, label: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {query}")
        lines = [row[0] for row in cur.fetchall()]
    output = "\n".join(lines)
    path = f"{OUTPUT_DIR}/{label}.txt"
    with open(path, "w") as f:
        f.write(output)
    # Print first two lines (plan + exec time) inline
    summary = "\n".join(lines[:2] + [lines[-1]])
    print(f"  [{label}]\n    {summary}\n")


def main() -> None:
    print("=" * 60)
    print("  PHASE 5 - EXPLAIN ANALYZE BENCHMARK")
    print("=" * 60)

    with psycopg.connect(DB_URL, autocommit=True) as conn:
        # BEFORE: disable partition pruning + drop optional indexes
        print("\n[1/2] BEFORE benchmarks (pruning off, no BRIN/partial indexes)...")
        with conn.cursor() as cur:
            cur.execute("SET enable_partition_pruning = off")
            cur.execute("DROP INDEX IF EXISTS idx_transactions_transaction_date_brin")
            cur.execute("DROP INDEX IF EXISTS idx_transactions_flagged")

        for name, query in QUERIES.items():
            run_explain(conn, query, f"before_{name}")

        # AFTER: re-enable + recreate indexes
        print("[2/2] AFTER benchmarks (pruning on, BRIN + partial indexes present)...")
        with conn.cursor() as cur:
            cur.execute("SET enable_partition_pruning = on")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_transactions_transaction_date_brin "
                "ON transactions USING brin (transaction_date)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_transactions_flagged "
                "ON transactions (transaction_id) WHERE is_flagged = true"
            )

        for name, query in QUERIES.items():
            run_explain(conn, query, f"after_{name}")

    print("[ok] All 6 EXPLAIN ANALYZE outputs saved to /tmp/")


if __name__ == "__main__":
    main()
