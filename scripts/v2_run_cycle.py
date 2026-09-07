#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from curious_now_v2.pipeline.scheduled_cycle import CycleConfig, run_scheduled_cycle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one locked, budget-paced Curious Now v2 pipeline cycle"
    )
    parser.add_argument(
        "--database-url", default=os.environ.get("CURIOUS_NOW_V2_DATABASE_URL")
    )
    parser.add_argument(
        "--registry", type=Path, default=Path("config/v2/sources.json")
    )
    parser.add_argument("--feed-limit", type=int, default=100)
    parser.add_argument("--hydration-limit", type=int, default=100)
    parser.add_argument("--retrieval-limit", type=int, default=100)
    parser.add_argument("--gate-limit", type=int, default=500)
    parser.add_argument("--generation-limit", type=int, default=25)
    parser.add_argument("--generation-workers", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=float, default=30)
    parser.add_argument("--daily-budget-usd", type=float, default=20)
    parser.add_argument("--reserved-cost-per-story-usd", type=float, default=0.15)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not args.database_url:
        raise SystemExit("set CURIOUS_NOW_V2_DATABASE_URL or pass --database-url")
    positive = (
        args.feed_limit,
        args.hydration_limit,
        args.retrieval_limit,
        args.gate_limit,
        args.generation_limit,
        args.generation_workers,
        args.timeout_seconds,
        args.daily_budget_usd,
        args.reserved_cost_per_story_usd,
    )
    if any(value <= 0 for value in positive):
        raise SystemExit("limits, timeout, budget, and reservation must be positive")
    result = run_scheduled_cycle(
        args.database_url,
        config=CycleConfig(
            registry_path=args.registry.resolve(),
            feed_limit=args.feed_limit,
            hydration_limit=args.hydration_limit,
            retrieval_limit=args.retrieval_limit,
            gate_limit=args.gate_limit,
            generation_limit=args.generation_limit,
            generation_workers=args.generation_workers,
            timeout_seconds=args.timeout_seconds,
            daily_generation_budget_usd=args.daily_budget_usd,
            reserved_cost_per_story_usd=args.reserved_cost_per_story_usd,
        ),
        dry_run=args.dry_run,
    )
    print(json.dumps(asdict(result), indent=2, default=str))  # noqa: T201


if __name__ == "__main__":
    main()
