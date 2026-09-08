import os
import psycopg
from collections import defaultdict
from typing import Any

from src.rules.engine import evaluate_transaction

DB_URL = os.getenv(
    "DATABASE_SYNC_URL", 
    "postgresql://postgres:postgres@postgres:5432/fraud_detection"
)

def run_evaluation():
    print("[+] Starting Engine Evaluation against Ground Truth...")
    
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            # Load user summaries
            cur.execute("SELECT user_id, avg_amount, std_amount FROM user_transaction_summary")
            user_summaries = {}
            for row in cur.fetchall():
                user_summaries[row[0]] = {
                    "avg_amount": float(row[1]) if row[1] is not None else 0.0,
                    "std_amount": float(row[2]) if row[2] is not None else 0.0,
                }
                
            # Fetch transactions WITH ground truth
            query = """
                SELECT transaction_id, user_id, transaction_date, amount, 
                       merchant_country, card_present, device_id, is_flagged, flag_reason
                FROM transactions 
                ORDER BY user_id, transaction_date ASC
            """
            cur.execute(query)
            
            current_user_id = None
            user_history = []
            
            tp = 0
            fp = 0
            tn = 0
            fn = 0
            
            # Detailed breakdown
            missed_patterns = defaultdict(int)
            false_positive_reasons = defaultdict(int)
            
            for row in cur.fetchall():
                tx = {
                    "transaction_id": row[0],
                    "user_id": row[1],
                    "transaction_date": row[2],
                    "amount": float(row[3]),
                    "merchant_country": row[4],
                    "card_present": row[5],
                    "device_id": row[6],
                }
                
                # Ground truth
                gt_is_flagged = row[7]
                gt_reason = row[8]
                
                if tx["user_id"] != current_user_id:
                    current_user_id = tx["user_id"]
                    user_history = []
                    
                summary = user_summaries.get(tx["user_id"], {})
                
                # Predict
                pred_is_flagged, pred_reason, _ = evaluate_transaction(tx, user_history, summary)
                
                # Compare
                if gt_is_flagged and pred_is_flagged:
                    tp += 1
                elif not gt_is_flagged and not pred_is_flagged:
                    tn += 1
                elif not gt_is_flagged and pred_is_flagged:
                    fp += 1
                    false_positive_reasons[pred_reason] += 1
                elif gt_is_flagged and not pred_is_flagged:
                    fn += 1
                    missed_patterns[gt_reason] += 1
                        
                # Update rolling history (keep last 50)
                user_history.append(tx)
                if len(user_history) > 50:
                    user_history.pop(0)
                    
    print("\n" + "="*50)
    print("  ENGINE EVALUATION RESULTS")
    print("="*50)
    print(f"Total Transactions: {tp + fp + tn + fn}")
    print(f"Ground Truth Fraud: {tp + fn}")
    print(f"Engine Flagged:     {tp + fp}")
    print("-" * 50)
    print(f"True Positives (TP):  {tp}")
    print(f"True Negatives (TN):  {tn}")
    print(f"False Positives (FP): {fp}")
    print(f"False Negatives (FN): {fn}")
    print("-" * 50)
    
    recall = (tp / (tp + fn)) * 100 if (tp + fn) > 0 else 0
    precision = (tp / (tp + fp)) * 100 if (tp + fp) > 0 else 0
    
    print(f"Hit Rate (Recall): {recall:.2f}% (Found {tp} out of {tp + fn} frauds)")
    print(f"Precision:         {precision:.2f}% ({tp} valid flags out of {tp + fp} total flags)")
    
    if fn > 0:
        print("\nMissed Fraud Patterns (False Negatives):")
        for reason, count in missed_patterns.items():
            print(f"  - {reason}: {count}")
            
    if fp > 0:
        print("\nFalse Positive Trigger Reasons:")
        for reason, count in false_positive_reasons.items():
            print(f"  - {reason}: {count}")

if __name__ == "__main__":
    run_evaluation()
