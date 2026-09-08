import os
import time

import psycopg

from src.rules.engine import evaluate_transaction

DB_URL = os.getenv(
    "DATABASE_SYNC_URL", 
    "postgresql://postgres:postgres@postgres:5432/fraud_detection"
)

def run_batch_job():
    print("[+] Starting Fraud Engine Batch Job...")
    start_time = time.time()
    
    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
            # 1. Load user summaries
            print("[+] Loading user summaries...")
            cur.execute("SELECT user_id, avg_amount, std_amount FROM user_transaction_summary")
            user_summaries = {}
            for row in cur.fetchall():
                user_summaries[row[0]] = {
                    "avg_amount": float(row[1]) if row[1] is not None else 0.0,
                    "std_amount": float(row[2]) if row[2] is not None else 0.0,
                }
                
            # 2. Fetch all transactions ordered by user_id and time
            print("[+] Fetching transactions for evaluation...")
            # We fetch everything we need for the rules
            query = """
                SELECT transaction_id, user_id, transaction_date, amount, 
                       merchant_country, card_present, device_id 
                FROM transactions 
                ORDER BY user_id, transaction_date ASC
            """
            cur.execute(query)
            
            updates = []
            current_user_id = None
            user_history = []
            
            flagged_count = 0
            
            # 3. Evaluate each transaction
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
                
                if tx["user_id"] != current_user_id:
                    current_user_id = tx["user_id"]
                    user_history = []
                    
                summary = user_summaries.get(tx["user_id"], {})
                
                is_flagged, flag_reason, fraud_score = evaluate_transaction(tx, user_history, summary)
                
                # We only need to update the database if the score > 0 to save time
                if fraud_score > 0:
                    updates.append((is_flagged, flag_reason, fraud_score, tx["transaction_id"]))
                    if is_flagged:
                        flagged_count += 1
                        
                # Update rolling history (keep last 50 to bound memory)
                user_history.append(tx)
                if len(user_history) > 50:
                    user_history.pop(0)
                    
            print(f"[+] Evaluation complete. Found {flagged_count} flagged transactions out of {len(updates)} with non-zero scores.")
            
            # 4. Bulk update the database using a temporary table for maximum speed
            print("[+] Bulk updating database...")
            cur.execute("""
                CREATE TEMP TABLE temp_scores (
                    is_flagged BOOLEAN,
                    flag_reason TEXT,
                    fraud_score NUMERIC(5,4),
                    transaction_id UUID
                ) ON COMMIT DROP
            """)
            
            with cur.copy("COPY temp_scores (is_flagged, flag_reason, fraud_score, transaction_id) FROM STDIN") as copy:
                for record in updates:
                    copy.write_row(record)
                    
            cur.execute("""
                UPDATE transactions t
                SET is_flagged = ts.is_flagged,
                    flag_reason = ts.flag_reason,
                    fraud_score = ts.fraud_score
                FROM temp_scores ts
                WHERE t.transaction_id = ts.transaction_id
            """)
            
            conn.commit()
            
    elapsed = time.time() - start_time
    print(f"[+] Batch job completed successfully in {elapsed:.2f} seconds.")


if __name__ == "__main__":
    run_batch_job()
