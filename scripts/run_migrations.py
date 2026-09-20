import time
from pathlib import Path

import psycopg

from src.config import settings


def run_migrations():
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    if not migrations_dir.exists():
        migrations_dir = Path("migrations").resolve()
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        raise FileNotFoundError(f"No SQL migration files found in {migrations_dir}")

    print(
        f"Connecting to database: {settings.POSTGRES_DB} on "
        f"{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}..."
    )

    conn = None
    for attempt in range(1, 11):
        try:
            conn = psycopg.connect(settings.DATABASE_SYNC_URL, autocommit=True)
            break
        except psycopg.OperationalError as exc:
            if attempt == 10:
                raise
            print(f"Waiting for database to be ready (attempt {attempt}/10): {exc}")
            time.sleep(2)

    with conn, conn.cursor() as cur:
        for sql_file in migration_files:
            print(f"Applying migration: {sql_file.name}...")
            sql_content = sql_file.read_text(encoding="utf-8")
            cur.execute(sql_content)
            print(f"Applied: {sql_file.name}")

    print("All migrations applied successfully!")


if __name__ == "__main__":
    run_migrations()
