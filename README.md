# Agentic Fraud Detection

A production-style fraud detection pipeline built with Python, PostgreSQL, FastAPI, and LangGraph. The system generates 10 million synthetic transactions, applies a rules-based flagging engine, and exposes a REST API that can trigger an autonomous LangGraph agent to investigate individual flagged transactions using LLM-generated SQL queries.

## Architecture

```
synthetic data
generator
     |
     v
PostgreSQL 16
(partitioned by month,
 10M rows)
     |
     v
Rules Engine                   FastAPI Backend
- velocity_fraud            GET /transactions/flagged
- geographic_impossibility  GET /transactions/{id}
- amount_deviation          POST /transactions/{id}/investigate
- new_device_high_amount         |
- round_number_structuring       |
                                 v
                        LangGraph Agent
                        +-----------------------------------------+
                        | context_gathering -> query_planning     |
                        | -> sql_generation -> sql_validation     |
                        |    (reject & retry up to 3 times)       |
                        | -> execution (agent_reader role)        |
                        | -> summarization (LLM narrative + score)|
                        +-----------------------------------------+
```

### Key Components

| Layer | Technology | Purpose |
|---|---|---|
| Database | PostgreSQL 16, range-partitioned by month | Store 10M transactions, fast date-range queries |
| ORM / Driver | SQLAlchemy 2 async + asyncpg | Async connection pooling |
| API | FastAPI + Uvicorn | REST endpoints, auto-generated Swagger docs |
| Rules Engine | Pure Python | Deterministic fraud flagging, five rule types |
| Agent | LangGraph + LangChain | Multi-step SQL investigation workflow |
| LLM | Anthropic / OpenAI (configurable) | Query planning, SQL generation, summarization |
| Lint / Test | Ruff, pytest, pytest-asyncio | CI quality gates |
| CI | GitHub Actions | Lint + migrations + test on every push |

### Agent Safety Design

The agent that executes LLM-generated SQL is built with three independent safety layers:

1. **Read-only database role** (`agent_reader`) - provisioned via `migrations/003_create_agent_reader_role.sql` with `GRANT SELECT` only and `statement_timeout = '5s'`.
2. **SQL allowlist validator** (`src/agent/sql_validator.py`) - rejects any query that does not start with `SELECT`, contains blocked keywords (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `GRANT`), or uses semicolons. Auto-injects `LIMIT 500` when absent.
3. **Retry loop with hard cap** - validation failures route back to `query_planning` with the rejection reason included in context; the loop terminates unconditionally after 3 attempts.

All rejected queries are recorded in `queries_run` alongside successful ones, making the validation layer auditable rather than just trusted.

### Rules Engine Performance (10M rows)

| Metric | Value |
|---|---|
| Total transactions | 10,000,000 |
| Ground truth fraud | 427,941 |
| Engine flagged | 325,239 |
| True positives | 315,421 |
| False positives | 9,818 |
| False negatives | 112,520 |
| Hit rate (recall) | 73.71% |
| Precision | 96.98% |

The geographic impossibility rule supports two modes switchable at runtime via `GEO_IMPOSSIBILITY_MODE`:
- `speed` (default) - flags only if implied travel speed exceeds 900 km/h between consecutive transactions
- `fixed_window` - legacy fixed time-window check

## Project Structure

```
.
├── migrations/                  # SQL migrations applied in order at startup
│   ├── 001_create_transactions_table.sql
│   ├── 002_create_indexes.sql
│   ├── 003_create_agent_reader_role.sql
│   └── 004_create_user_transaction_summary.sql
├── scripts/
│   ├── run_migrations.py        # Applies migrations with connection retry
│   ├── generate_data.py         # Generates and ingests synthetic data
│   └── evaluate_hit_rate.py     # Offline precision/recall evaluation
├── src/
│   ├── agent/                   # LangGraph agent
│   │   ├── graph.py             # StateGraph assembly
│   │   ├── nodes.py             # All 6 graph nodes + router
│   │   ├── sql_validator.py     # SQL allowlist validator
│   │   ├── llm.py               # LLM factory + prompts
│   │   ├── db.py                # agent_reader execution helper
│   │   └── state.py             # AgentState TypedDict
│   ├── api/                     # FastAPI application
│   │   ├── main.py
│   │   ├── schemas.py
│   │   └── routes/transactions.py
│   ├── db/                      # SQLAlchemy models + session factories
│   ├── generator/               # Synthetic data generation
│   ├── rules/                   # Rules engine
│   └── config.py                # Pydantic settings
├── tests/                       # pytest test suite (75 tests)
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

## Local Setup

### Prerequisites

- Docker and Docker Compose
- Python 3.11 (for running scripts outside the container)

### 1. Clone and start the stack

```bash
git clone https://github.com/RuturajKotwal/agentic-fraud-detection.git
cd agentic-fraud-detection
docker compose up --build -d
```

This starts:
- `fraud_detection_postgres` on port `5433`
- `fraud_detection_api` on port `8000`

Migrations in `./migrations/` are applied automatically by PostgreSQL at first startup.

### 2. Generate synthetic data

```bash
docker exec -e PYTHONPATH=/app fraud_detection_api python scripts/generate_data.py
```

This inserts approximately 10 million transactions using `COPY FROM STDIN` via `psycopg`, then applies the rules engine to set `is_flagged`, `flag_reason`, and `fraud_score`.

### 3. Explore the API

Swagger UI: http://localhost:8000/docs

```bash
# List flagged transactions (paginated)
curl http://localhost:8000/transactions/flagged?limit=5

# Fetch a single transaction
curl http://localhost:8000/transactions/<transaction_id>

# Trigger agent investigation
curl -X POST http://localhost:8000/transactions/<transaction_id>/investigate
```

### 4. Configure an LLM (optional)

Without API keys the agent uses a deterministic heuristic fallback, so all endpoints work offline. To enable real LLM reasoning, set one of the following in a `.env` file or as environment variables before starting the stack:

```bash
ANTHROPIC_API_KEY=sk-ant-...
# or
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o   # optional, defaults to claude-3-5-sonnet-20241022
```

Then restart the API container:

```bash
docker compose restart api
```

### 5. Run tests

```bash
docker exec -e PYTHONPATH=/app fraud_detection_api pytest tests/ -v
```

75 tests covering the rules engine, SQL validator, agent graph, and FastAPI endpoints.

## CI

GitHub Actions runs on every push to `main`, `master`, or `develop`:

1. Ruff lint check
2. Database migrations against a live PostgreSQL service container
3. Full pytest suite

See `.github/workflows/ci.yml`.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | asyncpg localhost:5433 | Main app read-write connection |
| `DATABASE_SYNC_URL` | psycopg localhost:5433 | Sync connection for migrations |
| `AGENT_DATABASE_URL` | asyncpg agent_reader@localhost:5433 | Agent read-only connection |
| `AGENT_DB_USER` | `agent_reader` | Postgres role for agent queries |
| `AGENT_DB_PASSWORD` | `agent_reader_password` | Password for agent role |
| `ANTHROPIC_API_KEY` | _(empty)_ | Enables Anthropic LLM |
| `OPENAI_API_KEY` | _(empty)_ | Enables OpenAI LLM |
| `LLM_MODEL` | `claude-3-5-sonnet-20241022` | Model name |
| `GEO_IMPOSSIBILITY_MODE` | `speed` | `speed` or `fixed_window` |
| `GEO_MAX_SPEED_KMH` | `900.0` | Threshold for speed-based geo rule |
