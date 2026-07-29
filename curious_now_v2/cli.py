from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg

from curious_now_v2.core.source_registry import load_source_registry
from curious_now_v2.db.ingestion import sync_source_registry
from curious_now_v2.db.migrations import apply_migrations
from curious_now_v2.db.ranking import run_ranking
from curious_now_v2.pipeline.run_ingestion import run_ingestion_once


def _database_url(value: str | None) -> str:
    if value:
        return value
    raise SystemExit("set CURIOUS_NOW_V2_DATABASE_URL or pass --database-url")


def _add_database_url_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--database-url",
        default=os.environ.get("CURIOUS_NOW_V2_DATABASE_URL"),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="curious-now-v2")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser(
        "validate-sources",
        help="validate a source registry without mutating the database",
    )
    validate.add_argument("path", type=Path)

    migrate = commands.add_parser(
        "migrate",
        help="apply pending v2 database migrations",
    )
    _add_database_url_argument(migrate)

    sync = commands.add_parser(
        "sync-sources",
        help="upsert a validated source registry",
    )
    sync.add_argument("path", type=Path)
    _add_database_url_argument(sync)

    ingest = commands.add_parser(
        "ingest-once",
        help="sync the registry and fetch due feeds once",
    )
    ingest.add_argument("path", type=Path)
    ingest.add_argument("--limit", type=int, default=25)
    ingest.add_argument("--timeout-seconds", type=float, default=20)
    _add_database_url_argument(ingest)

    rank = commands.add_parser(
        "rank",
        help="score published stories and store inspectable reasons",
    )
    rank.add_argument(
        "--limit",
        type=int,
        default=None,
        help="score only the newest N stories",
    )
    _add_database_url_argument(rank)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.command == "validate-sources":
        registry = load_source_registry(args.path)
        feed_count = sum(len(source.feeds) for source in registry.sources)
        print(  # noqa: T201
            f"valid registry v{registry.version}: "
            f"{len(registry.sources)} sources, {feed_count} feeds"
        )
        return

    if args.command == "migrate":
        applied = apply_migrations(_database_url(args.database_url))
        migration_result = ", ".join(applied) if applied else "already up to date"
        print(f"v2 migrations: {migration_result}")  # noqa: T201
        return

    if args.command == "sync-sources":
        registry = load_source_registry(args.path)
        with psycopg.connect(
            _database_url(args.database_url),
            autocommit=True,
        ) as connection:
            registry_result = sync_source_registry(connection, registry)
        print(  # noqa: T201
            f"synced {registry_result.sources} sources "
            f"and {registry_result.feeds} feeds"
        )
        return

    if args.command == "ingest-once":
        if args.limit < 1:
            raise SystemExit("--limit must be positive")
        registry = load_source_registry(args.path)
        ingestion_result = run_ingestion_once(
            database_url=_database_url(args.database_url),
            registry=registry,
            limit=args.limit,
            timeout_seconds=args.timeout_seconds,
        )
        print(  # noqa: T201
            f"run {ingestion_result.run_id}: "
            f"{ingestion_result.feeds_succeeded}/"
            f"{ingestion_result.feeds_attempted} feeds; "
            f"{ingestion_result.items_inserted} new items; "
            f"{ingestion_result.stories_created} new stories"
        )
        return

    if args.command == "rank":
        if args.limit is not None and args.limit < 1:
            raise SystemExit("--limit must be positive")
        ranking_result = run_ranking(
            _database_url(args.database_url),
            limit=args.limit,
        )
        print(  # noqa: T201
            f"scored {ranking_result.stories_scored} stories; "
            f"top score {ranking_result.top_score:.3f}"
        )
        return

    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    main()
