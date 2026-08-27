from pathlib import Path

import psycopg

from src.config import settings


def run_migrations():
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        print(f"No SQL migration files found in {migrations_dir}")
        return

    print(
        f"Connecting to database: {settings.POSTGRES_DB} on "
        f"{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}..."
    )

    with (
        psycopg.connect(settings.DATABASE_SYNC_URL, autocommit=True) as conn,
        conn.cursor() as cur,
    ):
        for sql_file in migration_files:
            print(f"Applying migration: {sql_file.name}...")
            sql_content = sql_file.read_text(encoding="utf-8")
            cur.execute(sql_content)
            print(f"Applied: {sql_file.name}")

    print("All migrations applied successfully!")


if __name__ == "__main__":
    run_migrations()
