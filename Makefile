.PHONY: venv install dev-up dev-down migrate api test lint typecheck check

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
