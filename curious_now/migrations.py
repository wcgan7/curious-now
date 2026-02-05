from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg

MIGRATION_FILENAME_RE = re.compile(r"^\d{4}_\d{2}_\d{2}_\d{4}_.+\.sql$")
OPS_RUNBOOK_MIGRATION_RE = re.compile(r"design_docs/migrations/([0-9_]+_.+?\.sql)")


@dataclass(frozen=True)
class Migration:
    name: str
    path: Path


def list_migrations(migrations_dir: Path) -> list[Migration]:
    if not migrations_dir.exists():
        return []
    repo_root = migrations_dir.parent.parent
    preferred_order = _ordered_names_from_ops_runbook(repo_root)
    preferred_index = {name: idx for idx, name in enumerate(preferred_order)}

    paths = [
        p
        for p in migrations_dir.iterdir()
        if p.is_file() and MIGRATION_FILENAME_RE.match(p.name)
    ]

    def sort_key(p: Path) -> tuple[int, int, str]:
        idx = preferred_index.get(p.name)
        if idx is None:
            return (1, 0, p.name)
        return (0, idx, p.name)

    paths.sort(key=sort_key)
    return [Migration(name=p.name, path=p) for p in paths]


def _ordered_names_from_ops_runbook(repo_root: Path) -> list[str]:
    ops_path = repo_root / "design_docs" / "ops_runbook.md"
    if not ops_path.exists():
        return []
    text = ops_path.read_text(encoding="utf-8")
    names: list[str] = []
    for m in OPS_RUNBOOK_MIGRATION_RE.finditer(text):
        names.append(m.group(1))

    seen: set[str] = set()
    ordered: list[str] = []
    for n in names:
        if n in seen:
            continue
        seen.add(n)
        ordered.append(n)
    return ordered


def ensure_migrations_table(conn: psycopg.Connection[Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              name TEXT PRIMARY KEY,
              applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )


def applied_migrations(conn: psycopg.Connection[Any]) -> set[str]:
    ensure_migrations_table(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM schema_migrations;")
        out: set[str] = set()
        for row in cur.fetchall():
            if isinstance(row, dict):
                name = row.get("name")
                if name is None:
                    continue
                out.add(str(name))
            else:
                out.add(str(row[0]))
        return out


def apply_migration(conn: psycopg.Connection[Any], migration: Migration) -> None:
    sql = migration.path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute(
            "INSERT INTO schema_migrations(name) VALUES (%s) ON CONFLICT DO NOTHING;",
            (migration.name,),
        )


def migrate(conn: psycopg.Connection[Any], migrations_dir: Path) -> list[str]:
    ensure_migrations_table(conn)
    already = applied_migrations(conn)
    applied: list[str] = []
    for m in list_migrations(migrations_dir):
        if m.name in already:
            continue
        apply_migration(conn, m)
        applied.append(m.name)
    return applied
