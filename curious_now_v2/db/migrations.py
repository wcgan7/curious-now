from __future__ import annotations

from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).parents[2] / "db" / "v2"


def migration_files() -> tuple[Path, ...]:
    return tuple(sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql")))


def apply_migrations(database_url: str) -> tuple[str, ...]:
    """Apply pending v2 migrations and return the versions applied."""

    applied: list[str] = []
    with psycopg.connect(database_url, autocommit=True) as connection:
        for path in migration_files():
            version = path.stem
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('public.schema_migrations');")
                migrations_table = cursor.fetchone()
                table_exists = bool(migrations_table and migrations_table[0])
                if table_exists:
                    cursor.execute(
                        "SELECT 1 FROM schema_migrations WHERE version = %s;",
                        (version,),
                    )
                    if cursor.fetchone():
                        continue

                cursor.execute(path.read_text())
                applied.append(version)
    return tuple(applied)
