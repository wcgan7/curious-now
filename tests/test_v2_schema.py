from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parents[1] / "db" / "v2"
INITIAL_PATH = MIGRATIONS_DIR / "0001_initial.sql"
PRESENTATION_PATH = MIGRATIONS_DIR / "0002_presentation_model.sql"


def combined_sql() -> str:
    return "\n".join(
        path.read_text() for path in sorted(MIGRATIONS_DIR.glob("[0-9]*.sql"))
    )


def table_names(sql: str) -> set[str]:
    return set(re.findall(r"CREATE TABLE ([a-z_]+)", sql))


def test_v2_schema_contains_only_the_initial_product_core() -> None:
    tables = table_names(combined_sql())

    assert {
        "sources",
        "source_feeds",
        "items",
        "papers",
        "stories",
        "story_items",
        "evidence_packets",
        "evidence_claims",
        "claim_evidence",
        "conceptual_spines",
        "display_titles",
        "explanations",
        "topics",
        "concepts",
        "concept_edges",
        "story_concepts",
        "paper_relations",
        "pipeline_runs",
        "feed_fetches",
    } <= tables
    assert not {
        "users",
        "sessions",
        "notifications",
        "experiments",
        "engagement_events",
        "feature_flags",
    } & tables


def test_v2_schema_versions_evidence_and_explanations() -> None:
    sql = INITIAL_PATH.read_text()

    assert "UNIQUE (story_id, version)" in sql
    assert "current_evidence_packet_id UUID" in sql
    assert "claim_id UUID NOT NULL REFERENCES evidence_claims(id)" in sql
    assert "item_id UUID NOT NULL REFERENCES items(id)" in sql


def test_v2_schema_separates_working_and_display_titles() -> None:
    sql = PRESENTATION_PATH.read_text()

    assert "RENAME COLUMN canonical_title TO working_title" in sql
    assert "CREATE TABLE display_titles" in sql
    assert "current_display_title_id UUID" in sql
    # Display titles are versioned per story, never rewritten in place.
    assert "UNIQUE (story_id, version)" in sql


def test_v2_schema_records_the_conceptual_spine_per_presentation() -> None:
    sql = PRESENTATION_PATH.read_text()

    assert "CREATE TABLE conceptual_spines" in sql
    assert "UNIQUE (evidence_packet_id, version)" in sql
    assert "conceptual_spine_id UUID NULL" in sql
    assert "UNIQUE NULLS NOT DISTINCT" in sql


def test_v2_schema_has_no_vector_or_redis_dependency() -> None:
    normalized = combined_sql().casefold()

    assert "create extension if not exists vector" not in normalized
    assert re.search(r"\bvector\s*\(", normalized) is None
    assert "redis" not in normalized
