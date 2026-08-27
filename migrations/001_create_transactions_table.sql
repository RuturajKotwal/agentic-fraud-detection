-- Migration 001: Create Partitioned transactions Table and 24 Monthly Partitions

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Root Partitioned Table (Range partitioned by month on transaction_date)
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id UUID NOT NULL,
    user_id BIGINT NOT NULL,
    transaction_date TIMESTAMP NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    merchant_category VARCHAR(50) NOT NULL,
    merchant_country VARCHAR(2) NOT NULL,
    card_present BOOLEAN NOT NULL DEFAULT true,
    device_id VARCHAR(64),
    ip_country VARCHAR(2),
    is_flagged BOOLEAN NOT NULL DEFAULT false,
    flag_reason TEXT,
    fraud_score NUMERIC(5, 4),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (transaction_id, transaction_date)
) PARTITION BY RANGE (transaction_date);

-- Comment on table and partition key
COMMENT ON TABLE transactions IS 'High-scale transactions table partitioned monthly by transaction_date';
COMMENT ON COLUMN transactions.transaction_date IS 'Partition key for range partitioning';

-- 2024 Partitions (12 Months)
CREATE TABLE IF NOT EXISTS transactions_2024_01 PARTITION OF transactions
    FOR VALUES FROM ('2024-01-01 00:00:00') TO ('2024-02-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2024_02 PARTITION OF transactions
    FOR VALUES FROM ('2024-02-01 00:00:00') TO ('2024-03-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2024_03 PARTITION OF transactions
    FOR VALUES FROM ('2024-03-01 00:00:00') TO ('2024-04-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2024_04 PARTITION OF transactions
    FOR VALUES FROM ('2024-04-01 00:00:00') TO ('2024-05-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2024_05 PARTITION OF transactions
    FOR VALUES FROM ('2024-05-01 00:00:00') TO ('2024-06-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2024_06 PARTITION OF transactions
    FOR VALUES FROM ('2024-06-01 00:00:00') TO ('2024-07-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2024_07 PARTITION OF transactions
    FOR VALUES FROM ('2024-07-01 00:00:00') TO ('2024-08-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2024_08 PARTITION OF transactions
    FOR VALUES FROM ('2024-08-01 00:00:00') TO ('2024-09-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2024_09 PARTITION OF transactions
    FOR VALUES FROM ('2024-09-01 00:00:00') TO ('2024-10-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2024_10 PARTITION OF transactions
    FOR VALUES FROM ('2024-10-01 00:00:00') TO ('2024-11-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2024_11 PARTITION OF transactions
    FOR VALUES FROM ('2024-11-01 00:00:00') TO ('2024-12-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2024_12 PARTITION OF transactions
    FOR VALUES FROM ('2024-12-01 00:00:00') TO ('2025-01-01 00:00:00');

-- 2025 Partitions (12 Months)
CREATE TABLE IF NOT EXISTS transactions_2025_01 PARTITION OF transactions
    FOR VALUES FROM ('2025-01-01 00:00:00') TO ('2025-02-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2025_02 PARTITION OF transactions
    FOR VALUES FROM ('2025-02-01 00:00:00') TO ('2025-03-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2025_03 PARTITION OF transactions
    FOR VALUES FROM ('2025-03-01 00:00:00') TO ('2025-04-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2025_04 PARTITION OF transactions
    FOR VALUES FROM ('2025-04-01 00:00:00') TO ('2025-05-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2025_05 PARTITION OF transactions
    FOR VALUES FROM ('2025-05-01 00:00:00') TO ('2025-06-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2025_06 PARTITION OF transactions
    FOR VALUES FROM ('2025-06-01 00:00:00') TO ('2025-07-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2025_07 PARTITION OF transactions
    FOR VALUES FROM ('2025-07-01 00:00:00') TO ('2025-08-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2025_08 PARTITION OF transactions
    FOR VALUES FROM ('2025-08-01 00:00:00') TO ('2025-09-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2025_09 PARTITION OF transactions
    FOR VALUES FROM ('2025-09-01 00:00:00') TO ('2025-10-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2025_10 PARTITION OF transactions
    FOR VALUES FROM ('2025-10-01 00:00:00') TO ('2025-11-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2025_11 PARTITION OF transactions
    FOR VALUES FROM ('2025-11-01 00:00:00') TO ('2025-12-01 00:00:00');

CREATE TABLE IF NOT EXISTS transactions_2025_12 PARTITION OF transactions
    FOR VALUES FROM ('2025-12-01 00:00:00') TO ('2026-01-01 00:00:00');

-- Default Partition for any out-of-range records
CREATE TABLE IF NOT EXISTS transactions_default PARTITION OF transactions DEFAULT;
