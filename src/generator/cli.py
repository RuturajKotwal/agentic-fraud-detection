"""Command-line interface for the synthetic transaction generator and benchmark suite."""

import argparse
import sys
import time

import psycopg

from src.generator.config import GeneratorConfig
from src.generator.ingestion import ingest_synthetic_transactions, run_ingestion_benchmark
from src.generator.synthetic_data import generate_transactions


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="High-Throughput Synthetic Transaction Data Generator & Ingestion Tool",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=100_000,
        help="Total number of transaction records to generate.",
    )
    parser.add_argument(
        "-r",
        "--fraud-rate",
        type=float,
        default=0.02,
        help="Fraud pattern injection rate (e.g., 0.02 for 2%%).",
    )
    parser.add_argument(
        "-u",
        "--users",
        type=int,
        default=5_000,
        help="Total number of distinct baseline user profiles.",
    )
    parser.add_argument(
        "-b",
        "--batch-size",
        type=int,
        default=25_000,
        help="Batch size for streaming COPY ingestion chunks.",
    )
    parser.add_argument(
        "-s",
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible dataset generation.",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Truncate the transactions table before ingesting new records.",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run comparative benchmark: PostgreSQL COPY FROM STDIN vs naive row-by-row INSERT.",
    )
    parser.add_argument(
        "--benchmark-size",
        type=int,
        default=5_000,
        help="Number of rows to use for the benchmark comparison run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate records in-memory only without persisting to PostgreSQL.",
    )
    return parser


def main() -> int:
    """Main CLI execution flow."""
    parser = build_parser()
    args = parser.parse_args()

    print("=" * 70)
    print("  AGENT-ACCELERATED FRAUD DETECTION PIPELINE: DATA GENERATOR")
    print("=" * 70)

    if args.benchmark:
        print(f"\n[+] Running Ingestion Benchmark ({args.benchmark_size:,} records)...")
        res = run_ingestion_benchmark(sample_size=args.benchmark_size)

        print("\n" + "-" * 70)
        print("  BENCHMARK RESULTS: COPY FROM STDIN vs NAIVE ROW-BY-ROW INSERT")
        print("-" * 70)
        print(f"  Sample Size:        {res.sample_size:,} records")
        print(
            f"  Naive INSERT Time:  {res.insert_duration_seconds:.4f} s ({res.insert_rows_per_second:,.1f} rows/s)"
        )
        print(
            f"  COPY STDIN Time:    {res.copy_duration_seconds:.4f} s ({res.copy_rows_per_second:,.1f} rows/s)"
        )
        print(f"  Throughput Speedup: {res.speedup_factor:.2f}x faster via COPY")
        print("-" * 70 + "\n")
        return 0

    config = GeneratorConfig(
        total_records=args.count,
        fraud_rate=args.fraud_rate,
        num_users=args.users,
        batch_size=args.batch_size,
        seed=args.seed,
    )

    print(f"  Target Records:   {config.total_records:,}")
    print(f"  Fraud Rate:       {config.fraud_rate * 100:.1f}%")
    print(f"  User Population:  {config.num_users:,}")
    print(
        f"  Partition Window: {config.start_date.strftime('%Y-%m')} to {config.end_date.strftime('%Y-%m')} (24 Months)"
    )
    print(f"  Batch Size:       {config.batch_size:,}")
    print(f"  Random Seed:      {config.seed}")
    print("=" * 70)

    if args.dry_run:
        print("\n[+] Dry-run mode: Generating transactions in-memory...")
        t0 = time.perf_counter()
        total_generated = 0
        for batch in generate_transactions(config):
            total_generated += len(batch)
        dur = time.perf_counter() - t0
        print(
            f"[✓] Generated {total_generated:,} records in {dur:.2f}s ({total_generated / dur:,.0f} rows/s)"
        )
        return 0

    print("\n[+] Starting PostgreSQL streaming COPY ingestion...")
    if args.truncate:
        print("    (Table truncation requested prior to load)")

    try:
        result = ingest_synthetic_transactions(config, truncate_first=args.truncate)
        print("\n" + "=" * 70)
        print("  INGESTION COMPLETE")
        print("=" * 70)
        print(f"  Total Ingested:    {result['total_records']:,} rows")
        print(f"  Total Duration:    {result['duration_seconds']:.2f} seconds")
        print(f"  Throughput:        {result['rows_per_second']:,.1f} rows/second")
        print("=" * 70 + "\n")
        return 0
    except (psycopg.Error, ValueError, RuntimeError) as exc:
        print(f"\n[!] Ingestion failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
