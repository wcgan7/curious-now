.PHONY: venv install dev-up dev-down migrate api test lint typecheck check sync-once sync-loop v2-sources v2-migrate v2-sync-sources v2-ingest v2-hydrate v2-retrieve v2-gate v2-generate v2-corpus-audit v2-fixtures v2-rank v2-test v2-lint v2-typecheck reader-install reader-dev reader-typecheck reader-build v2-check

venv:
	python -m venv .venv

install:
	.venv/bin/pip install ".[dev]"

dev-up:
	docker compose up -d

dev-down:
	docker compose down -v

migrate:
	.venv/bin/python -m curious_now.cli migrate

api:
	.venv/bin/uvicorn curious_now.api.app:app --reload --port 8000

test:
	.venv/bin/python -m pytest

lint:
	.venv/bin/python -m ruff check .

typecheck:
	.venv/bin/python -m mypy curious_now

check: test lint typecheck

sync-once:
	.venv/bin/python scripts/run_resilient_sync.py

sync-loop:
	.venv/bin/python scripts/run_resilient_sync.py --loop

v2-sources:
	.venv/bin/python -m curious_now_v2.cli validate-sources config/v2/sources.json

v2-migrate:
	.venv/bin/python -m curious_now_v2.cli migrate

v2-sync-sources:
	.venv/bin/python -m curious_now_v2.cli sync-sources config/v2/sources.json

v2-ingest:
	.venv/bin/python -m curious_now_v2.cli ingest-once config/v2/sources.json

v2-hydrate:
	.venv/bin/python -m curious_now_v2.cli hydrate

v2-fixtures:
	PYTHONPATH=. .venv/bin/python scripts/v2_capture_fixtures.py

v2-retrieve:
	.venv/bin/python -m curious_now_v2.cli retrieve

v2-corpus-audit:
	CURIOUS_NOW_V2_DATABASE_URL=$$CURIOUS_NOW_V2_DATABASE_URL PYTHONPATH=. .venv/bin/python scripts/v2_corpus_audit.py

v2-generate:
	.venv/bin/python -m curious_now_v2.cli generate

v2-gate:
	.venv/bin/python -m curious_now_v2.cli gate

v2-rank:
	.venv/bin/python -m curious_now_v2.cli rank

v2-test:
	.venv/bin/python -m pytest tests/test_v2_*.py

v2-lint:
	.venv/bin/python -m ruff check curious_now_v2 tests/test_v2_*.py

v2-typecheck:
	.venv/bin/python -m mypy curious_now_v2

reader-install:
	npm --prefix apps/reader ci

reader-dev:
	npm --prefix apps/reader run dev

reader-typecheck:
	npm --prefix apps/reader run typecheck

reader-build:
	npm --prefix apps/reader run build

v2-check: v2-sources v2-test v2-lint v2-typecheck reader-typecheck
