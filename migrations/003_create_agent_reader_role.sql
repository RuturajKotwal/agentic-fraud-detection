-- Migration 003: Create Dedicated Read-Only Role for LangGraph Agent
-- Defense-in-depth safety layer enforcing read-only permissions and 5-second statement timeout

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_reader') THEN
        CREATE ROLE agent_reader WITH LOGIN PASSWORD 'agent_reader_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
END
$$;

-- Enforce a strict 5-second query timeout on the agent role
ALTER ROLE agent_reader SET statement_timeout = '5s';

-- Grant read-only access to schema and tables
GRANT CONNECT ON DATABASE fraud_detection TO agent_reader;
GRANT USAGE ON SCHEMA public TO agent_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO agent_reader;

-- Ensure future tables in public schema are also readable by agent_reader
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO agent_reader;
