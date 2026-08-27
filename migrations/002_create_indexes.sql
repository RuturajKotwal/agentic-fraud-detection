-- Migration 002: Create Indexes on Partitioned transactions Table

-- 1. BRIN Index on transaction_date
-- BRIN (Block Range Index) is optimized for naturally time-ordered data,
-- consuming drastically less space and memory than B-Tree indexes.
CREATE INDEX IF NOT EXISTS idx_transactions_transaction_date_brin
    ON transactions USING brin (transaction_date);

-- 2. B-Tree Index on user_id for point user queries
CREATE INDEX IF NOT EXISTS idx_transactions_user_id
    ON transactions (user_id);

-- 3. Partial B-Tree Index for flagged transactions
-- Investigators only query flagged transactions; a partial index keeps the index
-- size tiny (1-3% of total table) and blazing fast for triage queries.
CREATE INDEX IF NOT EXISTS idx_transactions_flagged
    ON transactions (transaction_id)
    WHERE is_flagged = true;

-- 4. Compound Index on (user_id, transaction_date DESC)
-- Accelerates agent historical queries (e.g. "show user's recent 20 transactions")
CREATE INDEX IF NOT EXISTS idx_transactions_user_date
    ON transactions (user_id, transaction_date DESC);
