"""Rules engine hit-rate evaluator.

Uses a server-side cursor to stream 10 million rows in batches of 10,000
rather than loading the entire result set into Python memory.
"""

import argparse
import os
import time
from collections import defaultdict

import psycopg

from src.rules.engine import evaluate_transaction

DB_URL = os.getenv(
    "DATABASE_SYNC_URL",
    "postgresql://postgres:postgres@postgres:5432/fraud_detection",
)

BATCH_SIZE = 10_000


def run_evaluation(history_window: int = 50, geo_mode: str = "speed") -> None:
    print(f"[+] Starting Engine Evaluation against Ground Truth (history_window={history_window}, geo_mode={geo_mode})...")
    start_time = time.time()

    with psycopg.connect(DB_URL) as conn:
        # Load user summaries (small table — fetchall is fine here)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, avg_amount, std_amount FROM user_transaction_summary"
            )
            user_summaries: dict = {}
            for row in cur.fetchall():
                user_summaries[row[0]] = {
                    "avg_amount": float(row[1]) if row[1] is not None else 0.0,
                    "std_amount": float(row[2]) if row[2] is not None else 0.0,
                }

        print(f"[+] Loaded {len(user_summaries):,} user summaries.")

        tp = fp = tn = fn = 0
        missed_patterns: dict = defaultdict(int)
        false_positive_reasons: dict = defaultdict(int)

        current_user_id = None
        user_history: list = []
        processed = 0

        # Server-side named cursor — streams rows in BATCH_SIZE chunks
        query = """
            SELECT transaction_id, user_id, transaction_date, amount,
                   merchant_country, card_present, device_id, is_flagged, flag_reason
            FROM transactions
            ORDER BY user_id, transaction_date ASC
        """
        with conn.cursor(name="eval_cursor", scrollable=False) as cur:
            cur.itersize = BATCH_SIZE
            cur.execute(query)

            for row in cur:
                tx = {
                    "transaction_id": row[0],
                    "user_id": row[1],
                    "transaction_date": row[2],
                    "amount": float(row[3]),
                    "merchant_country": row[4],
                    "card_present": row[5],
                    "device_id": row[6],
                }

                gt_is_flagged = row[7]
                gt_reason = row[8]

                if tx["user_id"] != current_user_id:
                    current_user_id = tx["user_id"]
                    user_history = []

                summary = user_summaries.get(tx["user_id"], {})
                pred_is_flagged, pred_reason, _ = evaluate_transaction(
                    tx, user_history, summary, geo_mode=geo_mode
                )

                if gt_is_flagged and pred_is_flagged:
                    tp += 1
                elif not gt_is_flagged and not pred_is_flagged:
                    tn += 1
                elif not gt_is_flagged and pred_is_flagged:
                    fp += 1
                    false_positive_reasons[pred_reason] += 1
                else:  # gt_is_flagged and not pred_is_flagged
                    fn += 1
                    missed_patterns[gt_reason] += 1

                # Rolling per-user history (last history_window transactions)
                user_history.append(tx)
                if len(user_history) > history_window:
                    user_history.pop(0)

                processed += 1
                if processed % 500_000 == 0:
                    print(f"    ... processed {processed:,} rows", flush=True)

    elapsed = time.time() - start_time
    print("=" * 50)
    print("  ENGINE EVALUATION RESULTS")
    print("=" * 50)
    print(f"Geo Impossibility Mode: {geo_mode}")
    print(f"History Window Size:    {history_window}")
    print(f"Total Transactions:     {tp + fp + tn + fn:,}")
    print(f"Ground Truth Fraud:     {tp + fn:,}")
    print(f"Engine Flagged:         {tp + fp:,}")
    print("-" * 50)
    print(f"True Positives (TP):    {tp:,}")
    print(f"True Negatives (TN):    {tn:,}")
    print(f"False Positives (FP):   {fp:,}")
    print(f"False Negatives (FN):   {fn:,}")
    print("-" * 50)

    recall = (tp / (tp + fn)) * 100 if (tp + fn) > 0 else 0.0
    precision = (tp / (tp + fp)) * 100 if (tp + fp) > 0 else 0.0

    print(f"Hit Rate (Recall):   {recall:.2f}% (Found {tp:,} out of {tp + fn:,} frauds)")
    print(f"Precision:           {precision:.2f}% ({tp:,} valid flags out of {tp + fp:,} total flags)")
    print(f"Execution Runtime:   {elapsed:.2f}s")

    if fn > 0:
        print("Missed Fraud Patterns (False Negatives):")
        for reason, count in missed_patterns.items():
            print(f"  - {reason}: {count:,}")

    if fp > 0:
        print("False Positive Trigger Reasons:")
        for reason, count in false_positive_reasons.items():
            print(f"  - {reason}: {count:,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Rules engine hit-rate evaluator.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--history-window",
        type=int,
        default=50,
        help="Per-user rolling transaction history window size.",
    )
    parser.add_argument(
        "--geo-mode",
        type=str,
        choices=["speed", "fixed_window"],
        default=os.getenv("GEO_IMPOSSIBILITY_MODE", "speed"),
        help="Geographic impossibility mode: 'speed' (physical plausibility) or 'fixed_window' (legacy 8h window).",
    )
    args = parser.parse_args()
    run_evaluation(history_window=args.history_window, geo_mode=args.geo_mode)
