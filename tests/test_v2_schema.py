from __future__ import annotations

import re
from pathlib import Path

SCHEMA_PATH = Path(__file__).parents[1] / "db" / "v2" / "0001_initial.sql"


def table_names(sql: str) -> set[str]:
    return set(re.findall(r"CREATE TABLE ([a-z_]+)", sql))


def test_v2_schema_contains_only_the_initial_product_core() -> None:
    sql = SCHEMA_PATH.read_text()
    tables = table_names(sql)

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
    sql = SCHEMA_PATH.read_text()

    assert "UNIQUE (story_id, version)" in sql
    assert "current_evidence_packet_id UUID" in sql
    assert "UNIQUE (evidence_packet_id, depth, prompt_version)" in sql
    assert "claim_id UUID NOT NULL REFERENCES evidence_claims(id)" in sql
    assert "item_id UUID NOT NULL REFERENCES items(id)" in sql


def test_v2_schema_has_no_vector_or_redis_dependency() -> None:
    normalized = SCHEMA_PATH.read_text().casefold()

    assert "create extension if not exists vector" not in normalized
    assert re.search(r"\bvector\s*\(", normalized) is None
    assert "redis" not in normalized
