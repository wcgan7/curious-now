#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import time
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import psycopg

from curious_now.ai.llm_adapter import get_llm_adapter
from curious_now.ai_generation import (
    enrich_stage3_for_clusters,
    generate_deep_dives_for_clusters,
    generate_takeaways_for_clusters,
)
from curious_now.clustering import (
    cluster_unassigned_items,
    load_clustering_config,
    recompute_trending,
)
from curious_now.db import DB
from curious_now.ingestion import ingest_due_feeds
from curious_now.migrations import migrate
from curious_now.article_text_hydration import hydrate_article_text
from curious_now.paper_text_hydration import hydrate_paper_text
from curious_now.settings import get_settings
from curious_now.topic_tagging import tag_recent_clusters, tag_untagged_clusters_llm

logger = logging.getLogger("resilient_sync")

DEFAULT_LOCK_NAMESPACE = 24821
DEFAULT_LOCK_ID = 20260213


@dataclass(frozen=True)
class ThroughputProfile:
    interval_seconds: int
    limit_feeds: int
    max_items_per_feed: int
    hydrate_limit: int
    hydrate_article_limit: int
    cluster_limit_items: int
    tag_limit_clusters: int
    takeaways_limit: int
    deep_dives_limit: int
    enrich_stage3_limit: int


THROUGHPUT_PROFILES: dict[str, ThroughputProfile] = {
    # Early launch / low API budget
    "low": ThroughputProfile(
        interval_seconds=600,
        limit_feeds=10,
        max_items_per_feed=100,
        hydrate_limit=200,
        hydrate_article_limit=200,
        cluster_limit_items=400,
        tag_limit_clusters=80,
        takeaways_limit=60,
        deep_dives_limit=20,
        enrich_stage3_limit=40,
    ),
    # Balanced default for first production rollout
    "balanced": ThroughputProfile(
        interval_seconds=300,
        limit_feeds=25,
        max_items_per_feed=200,
        hydrate_limit=500,
        hydrate_article_limit=500,
        cluster_limit_items=1200,
        tag_limit_clusters=200,
        takeaways_limit=120,
        deep_dives_limit=40,
        enrich_stage3_limit=80,
    ),
    # Higher throughput for larger feeds and faster freshness
    "high": ThroughputProfile(
        interval_seconds=180,
        limit_feeds=50,
        max_items_per_feed=250,
        hydrate_limit=1000,
        hydrate_article_limit=1000,
        cluster_limit_items=2500,
        tag_limit_clusters=500,
        takeaways_limit=250,
        deep_dives_limit=80,
        enrich_stage3_limit=150,
    ),
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a downtime-tolerant local sync loop for ingest -> cluster -> tag -> "
            "takeaway -> deep-dive -> trending."
        )
    )
    parser.add_argument("--loop", action="store_true", default=False, help="Run continuously")
    parser.add_argument(
        "--throughput-profile",
        choices=["low", "balanced", "high"],
        default="balanced",
        help="Preset limits/interval for expected volume (default: balanced)",
    )
    parser.add_argument("--interval-seconds", type=int, default=None, help="Loop interval")
    parser.add_argument("--run-migrations", action="store_true", default=False)
    parser.add_argument("--force-ingest", action="store_true", default=False)

    parser.add_argument("--limit-feeds", type=int, default=None)
    parser.add_argument("--max-items-per-feed", type=int, default=None)
    parser.add_argument("--hydrate-limit", type=int, default=None)
    parser.add_argument("--cluster-limit-items", type=int, default=None)
    parser.add_argument("--clustering-config", type=str, default=None)
    parser.add_argument("--tagging-mode", choices=["untagged", "recent", "both"], default="untagged")
    parser.add_argument("--tag-lookback-days", type=int, default=14)
    parser.add_argument("--tag-limit-clusters", type=int, default=None)
    parser.add_argument("--max-topics-per-cluster", type=int, default=3)
    parser.add_argument("--takeaways-limit", type=int, default=None)
    parser.add_argument("--hydrate-article-limit", type=int, default=None)
    parser.add_argument("--deep-dives-limit", type=int, default=None)
    parser.add_argument("--enrich-stage3-limit", type=int, default=None)
    parser.add_argument("--trending-lookback-days", type=int, default=14)

    parser.add_argument("--step-retries", type=int, default=3, help="Retries per step")
    parser.add_argument("--retry-backoff-seconds", type=float, default=5.0)
    parser.add_argument("--stop-on-error", action="store_true", default=False)
    parser.add_argument("--allow-mock-llm", action="store_true", default=False)
    parser.add_argument("--lock-namespace", type=int, default=DEFAULT_LOCK_NAMESPACE)
    parser.add_argument("--lock-id", type=int, default=DEFAULT_LOCK_ID)
    parser.add_argument("--log-level", type=str, default="INFO")
    args = parser.parse_args()
    _apply_profile_defaults(args)
    return args


def _apply_profile_defaults(args: argparse.Namespace) -> None:
    profile = THROUGHPUT_PROFILES[args.throughput_profile]
    if args.interval_seconds is None:
        args.interval_seconds = profile.interval_seconds
    if args.limit_feeds is None:
        args.limit_feeds = profile.limit_feeds
    if args.max_items_per_feed is None:
        args.max_items_per_feed = profile.max_items_per_feed
    if args.hydrate_limit is None:
        args.hydrate_limit = profile.hydrate_limit
    if args.hydrate_article_limit is None:
        args.hydrate_article_limit = profile.hydrate_article_limit
    if args.cluster_limit_items is None:
        args.cluster_limit_items = profile.cluster_limit_items
    if args.tag_limit_clusters is None:
        args.tag_limit_clusters = profile.tag_limit_clusters
    if args.takeaways_limit is None:
        args.takeaways_limit = profile.takeaways_limit
    if args.deep_dives_limit is None:
        args.deep_dives_limit = profile.deep_dives_limit
    if args.enrich_stage3_limit is None:
        args.enrich_stage3_limit = profile.enrich_stage3_limit


def _row_get(row: Any, key: str, idx: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    return row[idx]


def _format_result(result: Any) -> str:
    if result is None:
        return ""
    if is_dataclass(result):
        payload = asdict(result)
        return ", ".join(f"{k}={v}" for k, v in payload.items())
    return str(result)


def _run_with_retry(
    *,
    name: str,
    step_fn: Callable[[], Any],
    retries: int,
    backoff_seconds: float,
) -> tuple[bool, Any | None]:
    max_attempts = max(1, retries + 1)
    for attempt in range(1, max_attempts + 1):
        try:
            result = step_fn()
            logger.info("Step %s ok (attempt=%s): %s", name, attempt, _format_result(result))
            return True, result
        except Exception as exc:
            if attempt >= max_attempts:
                logger.exception("Step %s failed after %s attempts: %s", name, max_attempts, exc)
                return False, None
            delay = backoff_seconds * (2 ** (attempt - 1))
            logger.warning(
                "Step %s failed (attempt=%s/%s): %s; retrying in %.1fs",
                name,
                attempt,
                max_attempts,
                exc,
                delay,
            )
            time.sleep(delay)
    return False, None


def _try_acquire_lock(conn: psycopg.Connection[Any], *, namespace: int, lock_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_try_advisory_lock(%s, %s) AS locked;",
            (namespace, lock_id),
        )
        row = cur.fetchone()
    return bool(_row_get(row, "locked", 0)) if row is not None else False


def _release_lock(conn: psycopg.Connection[Any], *, namespace: int, lock_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_unlock(%s, %s);", (namespace, lock_id))


def _run_cycle(
    *,
    args: argparse.Namespace,
    db: DB,
    clustering_config_path: Path | None,
) -> bool:
    ok, conn_any = _run_with_retry(
        name="connect_db",
        step_fn=lambda: db.connect(autocommit=True),
        retries=args.step_retries,
        backoff_seconds=args.retry_backoff_seconds,
    )
    if not ok or conn_any is None:
        return False

    conn = conn_any
    try:
        if not _try_acquire_lock(
            conn,
            namespace=args.lock_namespace,
            lock_id=args.lock_id,
        ):
            logger.info(
                "Another resilient sync process holds the advisory lock; skipping this cycle."
            )
            return True

        try:
            now = datetime.now(timezone.utc)

            if args.run_migrations:
                migrations_dir = Path(__file__).resolve().parents[1] / "design_docs" / "migrations"
                ok, _ = _run_with_retry(
                    name="migrate",
                    step_fn=lambda: migrate(conn, migrations_dir),
                    retries=args.step_retries,
                    backoff_seconds=args.retry_backoff_seconds,
                )
                if not ok and args.stop_on_error:
                    return False

            adapter = get_llm_adapter()
            llm_ready = adapter.name != "mock"
            if not llm_ready:
                msg = (
                    "Configured LLM adapter resolved to 'mock'. "
                    "Set CN_LLM_ADAPTER and provider auth, or pass --allow-mock-llm."
                )
                if args.allow_mock_llm:
                    logger.warning("%s LLM-dependent steps will be skipped.", msg)
                else:
                    logger.error(msg)
                    return False

            ok, _ = _run_with_retry(
                name="ingest",
                step_fn=lambda: ingest_due_feeds(
                    conn,
                    now_utc=now,
                    limit_feeds=args.limit_feeds,
                    max_items_per_feed=args.max_items_per_feed,
                    force=args.force_ingest,
                ),
                retries=args.step_retries,
                backoff_seconds=args.retry_backoff_seconds,
            )
            if not ok and args.stop_on_error:
                return False

            ok, _ = _run_with_retry(
                name="hydrate_paper_text",
                step_fn=lambda: hydrate_paper_text(
                    conn,
                    limit=args.hydrate_limit,
                    now_utc=now,
                ),
                retries=args.step_retries,
                backoff_seconds=args.retry_backoff_seconds,
            )
            if not ok and args.stop_on_error:
                return False

            ok, _ = _run_with_retry(
                name="hydrate_article_text",
                step_fn=lambda: hydrate_article_text(
                    conn,
                    limit=args.hydrate_article_limit,
                ),
                retries=args.step_retries,
                backoff_seconds=args.retry_backoff_seconds,
            )
            if not ok and args.stop_on_error:
                return False

            cfg = load_clustering_config(clustering_config_path)
            ok, _ = _run_with_retry(
                name="cluster",
                step_fn=lambda: cluster_unassigned_items(
                    conn,
                    now_utc=now,
                    limit_items=args.cluster_limit_items,
                    cfg=cfg,
                ),
                retries=args.step_retries,
                backoff_seconds=args.retry_backoff_seconds,
            )
            if not ok and args.stop_on_error:
                return False

            if llm_ready:
                if args.tagging_mode in {"untagged", "both"}:
                    ok, _ = _run_with_retry(
                        name="tag_untagged_llm",
                        step_fn=lambda: tag_untagged_clusters_llm(
                            conn,
                            now_utc=now,
                            limit_clusters=args.tag_limit_clusters,
                            max_topics_per_cluster=args.max_topics_per_cluster,
                        ),
                        retries=args.step_retries,
                        backoff_seconds=args.retry_backoff_seconds,
                    )
                    if not ok and args.stop_on_error:
                        return False

                if args.tagging_mode in {"recent", "both"}:
                    ok, _ = _run_with_retry(
                        name="tag_recent",
                        step_fn=lambda: tag_recent_clusters(
                            conn,
                            now_utc=now,
                            lookback_days=args.tag_lookback_days,
                            limit_clusters=args.tag_limit_clusters,
                            max_topics_per_cluster=args.max_topics_per_cluster,
                        ),
                        retries=args.step_retries,
                        backoff_seconds=args.retry_backoff_seconds,
                    )
                    if not ok and args.stop_on_error:
                        return False

                ok, _ = _run_with_retry(
                    name="generate_takeaways",
                    step_fn=lambda: generate_takeaways_for_clusters(
                        conn,
                        limit=args.takeaways_limit,
                        adapter=adapter,
                    ),
                    retries=args.step_retries,
                    backoff_seconds=args.retry_backoff_seconds,
                )
                if not ok and args.stop_on_error:
                    return False

                ok, _ = _run_with_retry(
                    name="generate_deep_dives",
                    step_fn=lambda: generate_deep_dives_for_clusters(
                        conn,
                        limit=args.deep_dives_limit,
                        adapter=adapter,
                    ),
                    retries=args.step_retries,
                    backoff_seconds=args.retry_backoff_seconds,
                )
                if not ok and args.stop_on_error:
                    return False

                ok, _ = _run_with_retry(
                    name="enrich_stage3",
                    step_fn=lambda: enrich_stage3_for_clusters(
                        conn,
                        limit=args.enrich_stage3_limit,
                    ),
                    retries=args.step_retries,
                    backoff_seconds=args.retry_backoff_seconds,
                )
                if not ok and args.stop_on_error:
                    return False

            ok, _ = _run_with_retry(
                name="recompute_trending",
                step_fn=lambda: recompute_trending(
                    conn,
                    now_utc=now,
                    lookback_days=args.trending_lookback_days,
                ),
                retries=args.step_retries,
                backoff_seconds=args.retry_backoff_seconds,
            )
            if not ok and args.stop_on_error:
                return False

            return True
        finally:
            _release_lock(
                conn,
                namespace=args.lock_namespace,
                lock_id=args.lock_id,
            )
    finally:
        conn.close()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info(
        "Throughput profile=%s interval=%ss feeds=%s items_per_feed=%s "
        "hydrate_paper=%s hydrate_article=%s cluster_items=%s tag_clusters=%s "
        "takeaways=%s deep_dives=%s enrich_stage3=%s",
        args.throughput_profile,
        args.interval_seconds,
        args.limit_feeds,
        args.max_items_per_feed,
        args.hydrate_limit,
        args.hydrate_article_limit,
        args.cluster_limit_items,
        args.tag_limit_clusters,
        args.takeaways_limit,
        args.deep_dives_limit,
        args.enrich_stage3_limit,
    )

    settings = get_settings()
    db = DB(settings.database_url, statement_timeout_ms=settings.statement_timeout_ms)
    config_path = Path(args.clustering_config) if args.clustering_config else None

    cycle = 0
    while True:
        cycle += 1
        logger.info("Starting sync cycle #%s", cycle)
        ok = _run_cycle(
            args=args,
            db=db,
            clustering_config_path=config_path,
        )
        if not ok and args.stop_on_error:
            logger.error("Stopping due to --stop-on-error.")
            return 1

        if not args.loop:
            return 0 if ok else 1

        logger.info("Cycle #%s complete. Sleeping %ss.", cycle, args.interval_seconds)
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
