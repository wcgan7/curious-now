from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import psycopg

# Migrations required for /v1/feed and homepage rendering.
# Intentionally excludes Stage 8/10 migrations, which depend on tables not yet
# present in this repo's migration set.
MIGRATIONS = [
    "design_docs/migrations/2026_02_03_0100_stage1_core.sql",
    "design_docs/migrations/2026_01_29_0201_stage2_clusters.sql",
    "design_docs/migrations/2026_01_29_0202_stage2_topics.sql",
    "design_docs/migrations/2026_01_29_0203_stage2_search.sql",
    "design_docs/migrations/2026_02_03_0204_stage2_cluster_redirects.sql",
    "design_docs/migrations/2026_02_03_0200_stage3_understanding_glossary.sql",
    "design_docs/migrations/2026_02_03_0300_stage4_updates_lineage.sql",
    "design_docs/migrations/2026_02_07_0100_stage1_image_url.sql",
    "design_docs/migrations/2026_02_07_0200_stage3_deep_dive_skip_reason.sql",
    "design_docs/migrations/2026_02_10_0200_drop_confidence_band.sql",
    "design_docs/migrations/2026_02_10_0300_stage3_high_impact.sql",
]


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    dsn = os.environ.get("CN_DATABASE_URL")
    if not dsn:
        raise RuntimeError("CN_DATABASE_URL is required")

    repo_root = Path(__file__).resolve().parents[1]
    now = datetime.now(timezone.utc)

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            for rel_path in MIGRATIONS:
                sql = (repo_root / rel_path).read_text(encoding="utf-8")
                cur.execute(sql)

            source_id = uuid4()
            item_id = uuid4()
            cluster_id = uuid4()
            url = f"https://example.com/ci-story/{item_id}"

            cur.execute(
                """
                INSERT INTO sources(id, name, source_type, active)
                VALUES (%s, %s, %s, %s);
                """,
                (source_id, "CI Source", "journalism", True),
            )
            cur.execute(
                """
                INSERT INTO items(
                  id, source_id, url, canonical_url, title, published_at, fetched_at,
                  content_type, language, title_hash, canonical_hash
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    item_id,
                    source_id,
                    url,
                    url,
                    "CI smoke headline",
                    now,
                    now,
                    "news",
                    "en",
                    _sha256_hex("CI smoke headline"),
                    _sha256_hex(url),
                ),
            )
            cur.execute(
                """
                INSERT INTO story_clusters(
                  id, status, canonical_title, representative_item_id,
                  distinct_source_count, distinct_source_type_count, item_count,
                  velocity_6h, velocity_24h, trending_score, recency_score
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    cluster_id,
                    "active",
                    "CI smoke cluster",
                    item_id,
                    1,
                    1,
                    1,
                    1,
                    1,
                    10.0,
                    1.0,
                ),
            )
            cur.execute(
                """
                INSERT INTO cluster_items(cluster_id, item_id, role)
                VALUES (%s, %s, %s);
                """,
                (cluster_id, item_id, "primary"),
            )

    print("Prepared DB for homepage smoke test.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
