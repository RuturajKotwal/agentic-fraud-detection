-- Migration 004: Create user_transaction_summary table for fast agent context lookup

CREATE TABLE IF NOT EXISTS user_transaction_summary (
    user_id BIGINT PRIMARY KEY,
    total_transactions INT NOT NULL DEFAULT 0,
    avg_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    std_amount NUMERIC(14, 2) DEFAULT 0.00,
    min_amount NUMERIC(14, 2) DEFAULT 0.00,
    max_amount NUMERIC(14, 2) DEFAULT 0.00,
    frequent_merchant_categories TEXT[] DEFAULT '{}',
    frequent_countries TEXT[] DEFAULT '{}',
    first_transaction_date TIMESTAMP,
    last_transaction_date TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE user_transaction_summary IS 'Precomputed per-user transaction aggregates for fast agent historical context lookup';

-- Grant SELECT permissions to read-only agent role
GRANT SELECT ON user_transaction_summary TO agent_reader;
