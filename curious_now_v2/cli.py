from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg

from curious_now_v2.core import blobs
from curious_now_v2.core.source_registry import load_source_registry
from curious_now_v2.db.generation import run_generation
from curious_now_v2.db.hydration import run_hydration
from curious_now_v2.db.ingestion import sync_source_registry
from curious_now_v2.db.migrations import apply_migrations
from curious_now_v2.db.publication import run_publication_gate
from curious_now_v2.db.ranking import run_ranking
from curious_now_v2.db.retrieval import run_retrieval
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

    hydrate = commands.add_parser(
        "hydrate",
        help="fetch abstracts for papers that have an identifier but no text",
    )
    hydrate.add_argument("--limit", type=int, default=100)
    hydrate.add_argument("--timeout-seconds", type=float, default=30)
    _add_database_url_argument(hydrate)

    retrieve = commands.add_parser(
        "retrieve",
        help="resolve full text for items that do not have any yet",
    )
    retrieve.add_argument("--limit", type=int, default=50)
    retrieve.add_argument("--timeout-seconds", type=float, default=30)
    # The normal queue selects on `full_text IS NULL`, so a fix to an extractor
    # reaches only what arrives afterwards. These reopen what is already stored.
    retrieve.add_argument(
        "--refetch-source",
        help="re-resolve items from this source even if they already have text",
    )
    retrieve.add_argument(
        "--refetch-path",
        help=(
            "re-resolve items whose text came from this path "
            "(article_html, arxiv_html, oa_pdf, ...)"
        ),
    )
    _add_database_url_argument(retrieve)

    generate = commands.add_parser(
        "generate",
        help="extract evidence packets and write the layers they support",
    )
    generate.add_argument("--limit", type=int, default=10)
    generate.add_argument("--model", default=None)
    generate.add_argument(
        "--regenerate",
        action="store_true",
        help="rebuild presentations for stories that already have a valid packet",
    )
    generate.add_argument(
        "--workers",
        type=int,
        default=1,
        help=(
            "stories to generate at once (default 1). Each spends most of its "
            "time waiting on a model, so this is close to a linear speed-up; "
            "raise it until the provider starts refusing."
        ),
    )
    _add_database_url_argument(generate)

    gate = commands.add_parser(
        "gate",
        help="decide which stories have evidence worth opening",
    )
    gate.add_argument(
        "--limit",
        type=int,
        default=None,
        help="evaluate only the least recently gated N stories",
    )
    _add_database_url_argument(gate)

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

    if args.command == "hydrate":
        if args.limit < 1:
            raise SystemExit("--limit must be positive")
        hydration_result = run_hydration(
            _database_url(args.database_url),
            limit=args.limit,
            timeout_seconds=args.timeout_seconds,
        )
        print(  # noqa: T201
            f"hydrated {hydration_result.papers_hydrated}/"
            f"{hydration_result.papers_attempted} papers; "
            f"{hydration_result.items_upgraded} items upgraded; "
            f"{hydration_result.papers_without_abstract} publish no abstract; "
            f"{hydration_result.papers_failed} failed"
        )
        return

    if args.command == "retrieve":
        if args.limit < 1:
            raise SystemExit("--limit must be positive")
        # The blob root is usually an external disk. Checked here so an
        # unmounted drive stops the run at the start, rather than being found
        # out after an hour of fetching whose bodies all went nowhere.
        writable, detail = blobs.usable()
        if not writable:
            raise SystemExit(f"blob store unusable: {detail}")
        print(f"blob store: {detail}")  # noqa: T201
        retrieval = run_retrieval(
            _database_url(args.database_url),
            limit=args.limit,
            timeout_seconds=args.timeout_seconds,
            refetch_source=args.refetch_source,
            refetch_path=args.refetch_path,
        )
        print(  # noqa: T201
            f"resolved {retrieval.retrieved}/{retrieval.attempted} items "
            f"({retrieval.full_text} full text, "
            f"{retrieval.abstract_only} abstract only); "
            f"{retrieval.paywalled} paywalled, {retrieval.blocked} blocked, "
            f"{retrieval.failed} unavailable"
        )
        return

    if args.command == "generate":
        if args.limit < 1:
            raise SystemExit("--limit must be positive")
        result = run_generation(
            _database_url(args.database_url),
            limit=args.limit,
            model=args.model,
            regenerate=args.regenerate,
            workers=args.workers,
        )
        print(  # noqa: T201
            f"generated {result.generated}/{result.attempted} stories "
            f"({result.declined_explain} declined Explain, "
            f"{result.withheld_kind} withheld as not a development); "
            f"{result.invalid} failed validation, {result.failed} errored; "
            f"US${result.cost_usd:.2f}"
        )
        return

    if args.command == "gate":
        if args.limit is not None and args.limit < 1:
            raise SystemExit("--limit must be positive")
        gate_result = run_publication_gate(
            _database_url(args.database_url),
            limit=args.limit,
        )
        depths = ", ".join(
            f"{name} {count}" for name, count in sorted(gate_result.by_depth.items())
        )
        print(  # noqa: T201
            f"gated {gate_result.evaluated} stories: "
            f"{gate_result.eligible} eligible, "
            f"{gate_result.ineligible} ineligible"
            + (f" ({depths})" if depths else "")
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
