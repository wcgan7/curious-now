from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from curious_now.ai_generation import (
    enrich_stage3_for_clusters,
    generate_deep_dives_for_clusters,
    generate_embeddings_for_clusters,
    generate_intuition_for_clusters,
    generate_takeaways_for_clusters,
)
from curious_now.api.schemas import SourcePack
from curious_now.clustering import (
    cluster_unassigned_items,
    load_clustering_config,
    recompute_trending,
)
from curious_now.db import DB
from curious_now.ingestion import ingest_due_feeds
from curious_now.migrations import migrate
from curious_now.notifications import (
    enqueue_cluster_update_jobs,
    enqueue_topic_digest_jobs,
    send_due_notification_jobs,
)
from curious_now.paper_text_hydration import hydrate_paper_text
from curious_now.repo_stage1 import import_source_pack
from curious_now.retention import purge_logs
from curious_now.settings import get_settings
from curious_now.topic_tagging import (
    backfill_topics_v1,
    load_topic_seed_v1,
    quarantine_untaggable_clusters,
    rebuild_empty_search_texts,
    run_tagging_maintenance,
    seed_topics_v1,
    tag_recent_clusters,
    tag_recent_clusters_hybrid,
    tag_untagged_clusters_llm,
)


def cmd_migrate(_: argparse.Namespace) -> int:
    migrations_dir = Path(__file__).resolve().parents[1] / "design_docs" / "migrations"
    settings = get_settings()
    db = DB(settings.database_url)
    with db.connect(autocommit=True) as conn:
        applied = migrate(conn, migrations_dir)
    if applied:
        print("Applied migrations:")
        for name in applied:
            print(f"- {name}")
    else:
        print("No pending migrations.")
    return 0


def _parse_now(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def cmd_enqueue_notifications(args: argparse.Namespace) -> int:
    settings = get_settings()
    db = DB(settings.database_url)
    now = _parse_now(args.now)
    since = now - timedelta(days=int(args.since_days))
    with db.connect(autocommit=True) as conn:
        a = enqueue_cluster_update_jobs(conn, since_utc=since, now_utc=now)
        b = enqueue_topic_digest_jobs(conn, now_utc=now)
    print(f"Enqueued {a} cluster_update jobs; {b} topic_digest jobs.")
    return 0


def cmd_send_notifications(args: argparse.Namespace) -> int:
    settings = get_settings()
    db = DB(settings.database_url)
    now = _parse_now(args.now)
    with db.connect(autocommit=True) as conn:
        sent = send_due_notification_jobs(conn, now_utc=now, limit=int(args.limit))
    print(f"Sent {sent} notification jobs.")
    return 0


def cmd_purge_logs(args: argparse.Namespace) -> int:
    settings = get_settings()
    db = DB(settings.database_url)
    with db.connect(autocommit=True) as conn:
        counts = purge_logs(
            conn,
            keep_days=int(args.keep_days),
            dry_run=not bool(args.apply),
        )
    verb = "Would delete" if not args.apply else "Deleted"
    for k, v in counts.items():
        print(f"{verb} {v} rows from {k}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    settings = get_settings()
    db = DB(settings.database_url)
    now = _parse_now(args.now)
    with db.connect(autocommit=True) as conn:
        result = ingest_due_feeds(
            conn,
            now_utc=now,
            feed_id=args.feed_id,
            limit_feeds=int(args.limit_feeds),
            max_items_per_feed=int(args.max_items_per_feed),
            force=bool(args.force),
        )
    print(
        "Ingestion complete: "
        f"{result.feeds_succeeded}/{result.feeds_attempted} feeds ok; "
        f"{result.items_inserted} inserted; {result.items_updated} updated; "
        f"{result.items_seen} items seen."
    )
    return 0


def cmd_hydrate_paper_text(args: argparse.Namespace) -> int:
    settings = get_settings()
    db = DB(settings.database_url)
    now = _parse_now(args.now)
    with db.connect(autocommit=True) as conn:
        result = hydrate_paper_text(
            conn,
            limit=int(args.limit),
            now_utc=now,
        )
    print(
        "Paper text hydration complete: "
        f"{result.items_hydrated}/{result.items_scanned} hydrated; "
        f"{result.items_failed} failed; {result.items_skipped} skipped."
    )
    return 0


def cmd_import_source_pack(args: argparse.Namespace) -> int:
    settings = get_settings()
    db = DB(settings.database_url)
    p = Path(args.path)
    raw = p.read_text(encoding="utf-8")
    pack = SourcePack.model_validate_json(raw)
    with db.connect(autocommit=True) as conn:
        result = import_source_pack(conn, pack)
    print(
        "Imported source pack: "
        f"{result.sources_upserted} sources; {result.feeds_upserted} feeds."
    )
    return 0


def cmd_cluster(args: argparse.Namespace) -> int:
    settings = get_settings()
    db = DB(settings.database_url)
    now = _parse_now(args.now)
    cfg = load_clustering_config(Path(args.config) if args.config else None)
    with db.connect(autocommit=True) as conn:
        result = cluster_unassigned_items(
            conn,
            now_utc=now,
            limit_items=int(args.limit_items),
            cfg=cfg,
        )
    print(
        "Clustering complete: "
        f"{result.items_processed} processed; {result.items_attached} attached; "
        f"{result.clusters_created} new clusters."
    )
    return 0


def cmd_recompute_trending(args: argparse.Namespace) -> int:
    settings = get_settings()
    db = DB(settings.database_url)
    now = _parse_now(args.now)
    with db.connect(autocommit=True) as conn:
        n = recompute_trending(conn, now_utc=now, lookback_days=int(args.lookback_days))
    print(f"Recomputed trending for {n} clusters.")
    return 0


def cmd_seed_topics(args: argparse.Namespace) -> int:
    """Seed topics from v1 format (legacy command alias)."""
    settings = get_settings()
    db = DB(settings.database_url)
    now = _parse_now(args.now)
    seed = load_topic_seed_v1(Path(args.path) if args.path else None)
    with db.connect(autocommit=True) as conn:
        result = seed_topics_v1(conn, seed=seed, now_utc=now)
    print(
        f"Seeded topics: "
        f"{result.categories_inserted} categories inserted, "
        f"{result.categories_updated} updated; "
        f"{result.subtopics_inserted} subtopics inserted, "
        f"{result.subtopics_updated} updated."
    )
    return 0


def cmd_seed_topics_v1(args: argparse.Namespace) -> int:
    """Seed topics from v1 format (2-layer: categories + subtopics)."""
    settings = get_settings()
    db = DB(settings.database_url)
    now = _parse_now(args.now)
    seed = load_topic_seed_v1(Path(args.path) if args.path else None)
    with db.connect(autocommit=True) as conn:
        result = seed_topics_v1(conn, seed=seed, now_utc=now)
    print(
        f"Seeded v1 topics: "
        f"{result.categories_inserted} categories inserted, "
        f"{result.categories_updated} updated; "
        f"{result.subtopics_inserted} subtopics inserted, "
        f"{result.subtopics_updated} updated."
    )
    return 0


def cmd_backfill_topics_v1(args: argparse.Namespace) -> int:
    """Backfill: seed v1 topics, clear old assignments, re-tag all clusters."""
    settings = get_settings()
    db = DB(settings.database_url)
    now = _parse_now(args.now)
    seed = load_topic_seed_v1(Path(args.path) if args.path else None)
    print("Starting backfill...")
    print(f"  - Loaded {len(seed.categories)} categories, {len(seed.subtopics)} subtopics")
    with db.connect(autocommit=True) as conn:
        result = backfill_topics_v1(
            conn,
            seed=seed,
            now_utc=now,
            limit_clusters=int(args.limit_clusters),
            max_topics_per_cluster=int(args.max_topics_per_cluster),
        )
    print(
        f"Backfill complete:\n"
        f"  - Categories: {result.categories_inserted} inserted, {result.categories_updated} updated\n"
        f"  - Subtopics: {result.subtopics_inserted} inserted, {result.subtopics_updated} updated\n"
        f"  - Old assignments cleared: {result.old_assignments_cleared}\n"
        f"  - Clusters tagged: {result.clusters_tagged}/{result.clusters_scanned}"
    )
    return 0


def cmd_rebuild_search_texts(args: argparse.Namespace) -> int:
    """Rebuild search_text for clusters with empty/short content."""
    settings = get_settings()
    db = DB(settings.database_url)
    with db.connect(autocommit=True) as conn:
        result = rebuild_empty_search_texts(
            conn,
            min_length=int(args.min_length),
            limit_clusters=int(args.limit_clusters),
        )
    print(f"Rebuilt search_text for {result.clusters_rebuilt}/{result.clusters_scanned} clusters.")
    return 0


def cmd_quarantine_untaggable(args: argparse.Namespace) -> int:
    """Quarantine clusters that cannot be meaningfully tagged."""
    settings = get_settings()
    db = DB(settings.database_url)
    with db.connect(autocommit=True) as conn:
        result = quarantine_untaggable_clusters(
            conn,
            min_content_length=int(args.min_length),
            limit_clusters=int(args.limit_clusters),
        )
    print(f"Quarantined {result.clusters_quarantined}/{result.clusters_scanned} clusters.")
    if result.reasons:
        print("Reasons:")
        for reason, count in sorted(result.reasons.items(), key=lambda x: -x[1]):
            print(f"  - {reason}: {count}")
    return 0


def cmd_tagging_maintenance(args: argparse.Namespace) -> int:
    """Run all tagging maintenance: rebuild search_text, re-tag, quarantine."""
    settings = get_settings()
    db = DB(settings.database_url)
    now = _parse_now(args.now)
    print("Running tagging maintenance...")
    with db.connect(autocommit=True) as conn:
        result = run_tagging_maintenance(
            conn,
            now_utc=now,
            min_content_length=int(args.min_length),
            limit_clusters=int(args.limit_clusters),
            max_topics_per_cluster=int(args.max_topics_per_cluster),
        )
    print(
        f"Maintenance complete:\n"
        f"  - Search texts rebuilt: {result.search_text_rebuilt}\n"
        f"  - Clusters tagged: {result.clusters_tagged}\n"
        f"  - Clusters quarantined: {result.clusters_quarantined}"
    )
    if result.quarantine_reasons:
        print("Quarantine reasons:")
        for reason, count in sorted(result.quarantine_reasons.items(), key=lambda x: -x[1]):
            print(f"    - {reason}: {count}")
    return 0


def cmd_tag_topics(args: argparse.Namespace) -> int:
    settings = get_settings()
    db = DB(settings.database_url)
    now = _parse_now(args.now)
    with db.connect(autocommit=True) as conn:
        result = tag_recent_clusters(
            conn,
            now_utc=now,
            lookback_days=int(args.lookback_days),
            limit_clusters=int(args.limit_clusters),
            max_topics_per_cluster=int(args.max_topics_per_cluster),
        )
    print(f"Tagged {result.clusters_updated}/{result.clusters_scanned} clusters.")
    return 0


def cmd_tag_topics_hybrid(args: argparse.Namespace) -> int:
    """Tag topics using hybrid approach (phrase match + LLM fallback)."""
    settings = get_settings()
    db = DB(settings.database_url)
    now = _parse_now(args.now)
    with db.connect(autocommit=True) as conn:
        result = tag_recent_clusters_hybrid(
            conn,
            now_utc=now,
            lookback_days=int(args.lookback_days),
            limit_clusters=int(args.limit_clusters),
            max_topics_per_cluster=int(args.max_topics_per_cluster),
            phrase_match_threshold=float(args.phrase_threshold),
        )
    print(
        f"Tagged {result.clusters_updated}/{result.clusters_scanned} clusters "
        f"(phrase: {result.phrase_match_count}, llm: {result.llm_fallback_count})."
    )
    return 0


def cmd_tag_untagged_llm(args: argparse.Namespace) -> int:
    """Tag untagged clusters using LLM only."""
    settings = get_settings()
    db = DB(settings.database_url)
    now = _parse_now(args.now)
    with db.connect(autocommit=True) as conn:
        result = tag_untagged_clusters_llm(
            conn,
            now_utc=now,
            limit_clusters=int(args.limit_clusters),
            max_topics_per_cluster=int(args.max_topics_per_cluster),
        )
    print(f"LLM-tagged {result.clusters_updated}/{result.clusters_scanned} untagged clusters.")
    return 0


def cmd_pipeline(args: argparse.Namespace) -> int:
    settings = get_settings()
    db = DB(settings.database_url)
    now = _parse_now(args.now)

    if args.source_pack:
        raw = Path(args.source_pack).read_text(encoding="utf-8")
        pack = SourcePack.model_validate_json(raw)
        with db.connect(autocommit=True) as conn:
            result = import_source_pack(conn, pack)
        print(
            "Imported source pack: "
            f"{result.sources_upserted} sources; {result.feeds_upserted} feeds."
        )

    if args.seed_topics:
        seed = load_topic_seed_v1(Path(args.topics_seed) if args.topics_seed else None)
        with db.connect(autocommit=True) as conn:
            result = seed_topics_v1(conn, seed=seed, now_utc=now)
        print(
            "Seeded topics: "
            f"{result.categories_inserted} categories inserted, "
            f"{result.categories_updated} updated; "
            f"{result.subtopics_inserted} subtopics inserted, "
            f"{result.subtopics_updated} updated."
        )

    with db.connect(autocommit=True) as conn:
        ing = ingest_due_feeds(
            conn,
            now_utc=now,
            feed_id=args.feed_id,
            limit_feeds=int(args.limit_feeds),
            max_items_per_feed=int(args.max_items_per_feed),
            force=bool(args.force),
        )
    print(
        "Ingested: "
        f"{ing.feeds_succeeded}/{ing.feeds_attempted} feeds ok; "
        f"{ing.items_inserted} inserted; {ing.items_updated} updated; "
        f"{ing.items_seen} items seen."
    )
    if bool(args.hydrate_paper_text):
        with db.connect(autocommit=True) as conn:
            hydrated = hydrate_paper_text(
                conn,
                limit=int(args.hydrate_limit),
                now_utc=now,
            )
        print(
            "Hydrated papers: "
            f"{hydrated.items_hydrated}/{hydrated.items_scanned} hydrated; "
            f"{hydrated.items_failed} failed; {hydrated.items_skipped} skipped."
        )

    cfg = load_clustering_config(Path(args.clustering_config) if args.clustering_config else None)
    with db.connect(autocommit=True) as conn:
        clustered = cluster_unassigned_items(
            conn,
            now_utc=now,
            limit_items=int(args.cluster_limit_items),
            cfg=cfg,
        )
    print(
        "Clustered: "
        f"{clustered.items_processed} processed; {clustered.items_attached} attached; "
        f"{clustered.clusters_created} new clusters."
    )

    with db.connect(autocommit=True) as conn:
        tagged = tag_recent_clusters(
            conn,
            now_utc=now,
            lookback_days=int(args.tag_lookback_days),
            limit_clusters=int(args.tag_limit_clusters),
            max_topics_per_cluster=int(args.tag_max_topics_per_cluster),
        )
    print(f"Tagged: {tagged.clusters_updated}/{tagged.clusters_scanned} clusters.")

    with db.connect(autocommit=True) as conn:
        n = recompute_trending(conn, now_utc=now, lookback_days=int(args.trending_lookback_days))
    print(f"Recomputed trending for {n} clusters.")
    return 0


def cmd_generate_takeaways(args: argparse.Namespace) -> int:
    settings = get_settings()
    db = DB(settings.database_url)
    with db.connect(autocommit=True) as conn:
        result = generate_takeaways_for_clusters(
            conn,
            limit=int(args.limit),
        )
    print(
        f"Takeaway generation complete: "
        f"{result.clusters_succeeded}/{result.clusters_processed} succeeded; "
        f"{result.clusters_failed} failed."
    )
    return 0


def cmd_generate_embeddings(args: argparse.Namespace) -> int:
    settings = get_settings()
    db = DB(settings.database_url)
    with db.connect(autocommit=True) as conn:
        result = generate_embeddings_for_clusters(
            conn,
            limit=int(args.limit),
            force=bool(args.force),
            provider_name=args.provider,
        )
    print(
        f"Embedding generation complete: "
        f"{result.clusters_succeeded}/{result.clusters_processed} succeeded; "
        f"{result.clusters_failed} failed; {result.clusters_skipped} skipped."
    )
    return 0


def cmd_enrich_stage3(args: argparse.Namespace) -> int:
    """Generate Stage 3 enrichment (intuition, deep-dive, anti-hype flags)."""
    settings = get_settings()
    db = DB(settings.database_url)
    with db.connect(autocommit=True) as conn:
        result = enrich_stage3_for_clusters(
            conn,
            limit=int(args.limit),
        )
    print(
        f"Stage 3 enrichment complete: "
        f"{result.clusters_succeeded}/{result.clusters_processed} succeeded; "
        f"{result.clusters_failed} failed."
    )
    if result.clusters_succeeded > 0:
        print("Generated: intuition, deep-dive, and anti-hype flags.")
    return 0


def cmd_generate_intuition(args: argparse.Namespace) -> int:
    """Generate layered intuition (ELI20 -> ELI5) for clusters."""
    settings = get_settings()
    db = DB(settings.database_url)
    with db.connect(autocommit=True) as conn:
        result = generate_intuition_for_clusters(
            conn,
            limit=int(args.limit),
        )
    print(
        f"Intuition generation complete: "
        f"{result.clusters_succeeded}/{result.clusters_processed} succeeded; "
        f"{result.clusters_failed} failed; {result.clusters_skipped} skipped."
    )
    return 0


def cmd_generate_deep_dives(args: argparse.Namespace) -> int:
    """Generate deep dives for paper-based clusters only."""
    settings = get_settings()
    db = DB(settings.database_url)
    with db.connect(autocommit=True) as conn:
        result = generate_deep_dives_for_clusters(
            conn,
            limit=int(args.limit),
        )
    print(
        f"Deep dive generation complete: "
        f"{result.clusters_succeeded}/{result.clusters_processed} succeeded; "
        f"{result.clusters_failed} failed; {result.clusters_skipped} skipped."
    )
    if result.clusters_processed == 0:
        print("Note: Deep dives only apply to preprints and peer-reviewed papers.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="curious-now")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_migrate = sub.add_parser("migrate", help="Apply SQL migrations from design_docs/migrations")
    p_migrate.set_defaults(func=cmd_migrate)

    p_enqueue = sub.add_parser("enqueue-notifications", help="Enqueue Stage 6 notification jobs")
    p_enqueue.add_argument("--since-days", type=int, default=7)
    p_enqueue.add_argument("--now", type=str, default=None, help="Override current time (ISO-8601)")
    p_enqueue.set_defaults(func=cmd_enqueue_notifications)

    p_send = sub.add_parser("send-notifications", help="Send due notification jobs (dev sender)")
    p_send.add_argument("--limit", type=int, default=50)
    p_send.add_argument("--now", type=str, default=None, help="Override current time (ISO-8601)")
    p_send.set_defaults(func=cmd_send_notifications)

    p_purge = sub.add_parser("purge-logs", help="Purge high-volume logs/events by retention policy")
    p_purge.add_argument("--keep-days", type=int, default=90)
    p_purge.add_argument("--apply", action="store_true", default=False)
    p_purge.set_defaults(func=cmd_purge_logs)

    p_ingest = sub.add_parser("ingest", help="Fetch due feeds and upsert items (Stage 1)")
    p_ingest.add_argument("--feed-id", type=UUID, default=None)
    p_ingest.add_argument("--limit-feeds", type=int, default=25)
    p_ingest.add_argument("--max-items-per-feed", type=int, default=200)
    p_ingest.add_argument("--force", action="store_true", default=False)
    p_ingest.add_argument("--now", type=str, default=None, help="Override current time (ISO-8601)")
    p_ingest.set_defaults(func=cmd_ingest)

    p_hydrate = sub.add_parser(
        "hydrate-paper-text",
        help="Hydrate full text for paper items (preprint, peer-reviewed)"
    )
    p_hydrate.add_argument(
        "--limit", type=int, default=200, help="Max items to hydrate"
    )
    p_hydrate.add_argument("--now", type=str, default=None, help="Override current time (ISO-8601)")
    p_hydrate.set_defaults(func=cmd_hydrate_paper_text)

    p_source_pack = sub.add_parser(
        "import-source-pack", help="Import a source pack JSON (idempotent upsert)"
    )
    p_source_pack.add_argument("path", type=str)
    p_source_pack.set_defaults(func=cmd_import_source_pack)

    p_cluster = sub.add_parser("cluster", help="Cluster items into story clusters (Stage 2)")
    p_cluster.add_argument("--limit-items", type=int, default=500)
    p_cluster.add_argument("--config", type=str, default=None, help="Path to clustering.v0.json")
    p_cluster.add_argument("--now", type=str, default=None, help="Override current time (ISO-8601)")
    p_cluster.set_defaults(func=cmd_cluster)

    p_trending = sub.add_parser(
        "recompute-trending", help="Recompute trending metrics for clusters"
    )
    p_trending.add_argument("--lookback-days", type=int, default=14)
    p_trending.add_argument(
        "--now", type=str, default=None, help="Override current time (ISO-8601)"
    )
    p_trending.set_defaults(func=cmd_recompute_trending)

    p_seed_topics = sub.add_parser(
        "seed-topics",
        help="Seed topics from v1 format (alias of seed-topics-v1)",
    )
    p_seed_topics.add_argument("--path", type=str, default=None, help="Path to topics.seed.v1.json")
    p_seed_topics.add_argument(
        "--now", type=str, default=None, help="Override current time (ISO-8601)"
    )
    p_seed_topics.set_defaults(func=cmd_seed_topics)

    p_seed_topics_v1 = sub.add_parser(
        "seed-topics-v1",
        help="Seed topics from v1 format (2-layer: categories + subtopics)",
    )
    p_seed_topics_v1.add_argument(
        "--path", type=str, default=None, help="Path to topics.seed.v1.json"
    )
    p_seed_topics_v1.add_argument(
        "--now", type=str, default=None, help="Override current time (ISO-8601)"
    )
    p_seed_topics_v1.set_defaults(func=cmd_seed_topics_v1)

    p_backfill_v1 = sub.add_parser(
        "backfill-topics-v1",
        help="Backfill: seed v1 topics, clear old assignments, re-tag all clusters",
    )
    p_backfill_v1.add_argument(
        "--path", type=str, default=None, help="Path to topics.seed.v1.json"
    )
    p_backfill_v1.add_argument("--limit-clusters", type=int, default=10000)
    p_backfill_v1.add_argument("--max-topics-per-cluster", type=int, default=3)
    p_backfill_v1.add_argument(
        "--now", type=str, default=None, help="Override current time (ISO-8601)"
    )
    p_backfill_v1.set_defaults(func=cmd_backfill_topics_v1)

    p_rebuild_search = sub.add_parser(
        "rebuild-search-texts",
        help="Rebuild search_text for clusters with empty/short content",
    )
    p_rebuild_search.add_argument(
        "--min-length", type=int, default=100, help="Minimum content length threshold"
    )
    p_rebuild_search.add_argument("--limit-clusters", type=int, default=1000)
    p_rebuild_search.set_defaults(func=cmd_rebuild_search_texts)

    p_quarantine = sub.add_parser(
        "quarantine-untaggable",
        help="Quarantine clusters that cannot be meaningfully tagged",
    )
    p_quarantine.add_argument(
        "--min-length", type=int, default=100, help="Minimum content length threshold"
    )
    p_quarantine.add_argument("--limit-clusters", type=int, default=500)
    p_quarantine.set_defaults(func=cmd_quarantine_untaggable)

    p_maintenance = sub.add_parser(
        "tagging-maintenance",
        help="Run all tagging maintenance: rebuild search_text, re-tag, quarantine",
    )
    p_maintenance.add_argument(
        "--min-length", type=int, default=100, help="Minimum content length threshold"
    )
    p_maintenance.add_argument("--limit-clusters", type=int, default=500)
    p_maintenance.add_argument("--max-topics-per-cluster", type=int, default=3)
    p_maintenance.add_argument(
        "--now", type=str, default=None, help="Override current time (ISO-8601)"
    )
    p_maintenance.set_defaults(func=cmd_tagging_maintenance)

    p_tag_topics = sub.add_parser(
        "tag-topics", help="Auto-tag recent clusters with topics (Stage 2)"
    )
    p_tag_topics.add_argument("--lookback-days", type=int, default=14)
    p_tag_topics.add_argument("--limit-clusters", type=int, default=500)
    p_tag_topics.add_argument("--max-topics-per-cluster", type=int, default=3)
    p_tag_topics.add_argument(
        "--now", type=str, default=None, help="Override current time (ISO-8601)"
    )
    p_tag_topics.set_defaults(func=cmd_tag_topics)

    p_tag_hybrid = sub.add_parser(
        "tag-topics-hybrid",
        help="Tag topics using hybrid approach (phrase match + LLM fallback)",
    )
    p_tag_hybrid.add_argument("--lookback-days", type=int, default=14)
    p_tag_hybrid.add_argument("--limit-clusters", type=int, default=500)
    p_tag_hybrid.add_argument("--max-topics-per-cluster", type=int, default=3)
    p_tag_hybrid.add_argument(
        "--phrase-threshold",
        type=float,
        default=0.5,
        help="Minimum phrase match score before LLM fallback (default: 0.5)",
    )
    p_tag_hybrid.add_argument(
        "--now", type=str, default=None, help="Override current time (ISO-8601)"
    )
    p_tag_hybrid.set_defaults(func=cmd_tag_topics_hybrid)

    p_tag_llm = sub.add_parser(
        "tag-untagged-llm",
        help="Tag untagged clusters using LLM only (backfill)",
    )
    p_tag_llm.add_argument("--limit-clusters", type=int, default=100)
    p_tag_llm.add_argument("--max-topics-per-cluster", type=int, default=3)
    p_tag_llm.add_argument(
        "--now", type=str, default=None, help="Override current time (ISO-8601)"
    )
    p_tag_llm.set_defaults(func=cmd_tag_untagged_llm)

    p_pipeline = sub.add_parser(
        "pipeline", help="Run ingest → cluster → tag → trending (end-to-end)"
    )
    p_pipeline.add_argument("--source-pack", type=str, default=None)
    p_pipeline.add_argument("--seed-topics", action="store_true", default=False)
    p_pipeline.add_argument(
        "--topics-seed",
        type=str,
        default=None,
        help="Path to topics.seed.v1.json (used with --seed-topics)",
    )
    p_pipeline.add_argument("--feed-id", type=UUID, default=None)
    p_pipeline.add_argument("--limit-feeds", type=int, default=25)
    p_pipeline.add_argument("--max-items-per-feed", type=int, default=200)
    p_pipeline.add_argument("--force", action="store_true", default=False)
    p_pipeline.add_argument(
        "--hydrate-paper-text",
        action="store_true",
        default=True,
        help="Hydrate paper full text after ingestion (default: enabled)",
    )
    p_pipeline.add_argument(
        "--no-hydrate-paper-text",
        dest="hydrate_paper_text",
        action="store_false",
        help="Skip paper text hydration during pipeline run",
    )
    p_pipeline.add_argument(
        "--hydrate-limit",
        type=int,
        default=500,
        help="Max paper items to hydrate in pipeline",
    )
    p_pipeline.add_argument("--cluster-limit-items", type=int, default=2000)
    p_pipeline.add_argument("--clustering-config", type=str, default=None)
    p_pipeline.add_argument("--tag-lookback-days", type=int, default=14)
    p_pipeline.add_argument("--tag-limit-clusters", type=int, default=500)
    p_pipeline.add_argument("--tag-max-topics-per-cluster", type=int, default=3)
    p_pipeline.add_argument("--trending-lookback-days", type=int, default=14)
    p_pipeline.add_argument(
        "--now", type=str, default=None, help="Override current time (ISO-8601)"
    )
    p_pipeline.set_defaults(func=cmd_pipeline)

    p_takeaways = sub.add_parser(
        "generate-takeaways", help="Generate AI takeaways for clusters without them"
    )
    p_takeaways.add_argument(
        "--limit", type=int, default=100, help="Max clusters to process"
    )
    p_takeaways.set_defaults(func=cmd_generate_takeaways)

    p_embeddings = sub.add_parser(
        "generate-embeddings", help="Generate embeddings for clusters"
    )
    p_embeddings.add_argument(
        "--limit", type=int, default=100, help="Max clusters to process"
    )
    p_embeddings.add_argument(
        "--force", action="store_true", default=False,
        help="Regenerate embeddings even if they exist"
    )
    p_embeddings.add_argument(
        "--provider", type=str, default=None,
        help="Embedding provider (ollama, sentence-transformers, mock)"
    )
    p_embeddings.set_defaults(func=cmd_generate_embeddings)

    p_enrich = sub.add_parser(
        "enrich-stage3",
        help="[Legacy] Generate deep-dives, intuition, anti-hype flags"
    )
    p_enrich.add_argument(
        "--limit", type=int, default=50, help="Max clusters to process"
    )
    p_enrich.set_defaults(func=cmd_enrich_stage3)

    p_intuition = sub.add_parser(
        "generate-intuition",
        help="Generate layered intuition (ELI20, ELI5) for all clusters"
    )
    p_intuition.add_argument(
        "--limit", type=int, default=100, help="Max clusters to process"
    )
    p_intuition.set_defaults(func=cmd_generate_intuition)

    p_deep_dives = sub.add_parser(
        "generate-deep-dives",
        help="Generate deep dives for papers only (preprints, peer-reviewed)"
    )
    p_deep_dives.add_argument(
        "--limit", type=int, default=50, help="Max clusters to process"
    )
    p_deep_dives.set_defaults(func=cmd_generate_deep_dives)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
