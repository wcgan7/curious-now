from __future__ import annotations

from pathlib import Path

from curious_now.migrations import list_migrations


def test_list_migrations_sorted_and_filtered() -> None:
    migrations_dir = Path(__file__).resolve().parents[1] / "design_docs" / "migrations"
    migrations = list_migrations(migrations_dir)
    assert migrations, "expected design_docs/migrations to contain SQL migrations"
    names = [m.name for m in migrations]
    # Ordering follows ops_runbook.md migration order (not lexicographic filename order).
    assert names[0].endswith("_0100_stage1_core.sql")
    assert all(name.endswith(".sql") for name in names)
