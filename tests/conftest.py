from __future__ import annotations

import os
from collections.abc import Generator

import psycopg
import pytest
import redis
from fastapi.testclient import TestClient
from psycopg import sql

from curious_now.api.app import app
from curious_now.cache import clear_redis_client_cache, get_redis_client
from curious_now.settings import clear_settings_cache


def _truncate_public_tables(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
              AND tablename <> 'schema_migrations';
            """
        )
        tables = [row[0] for row in cur.fetchall()]

    if not tables:
        return

    stmt = sql.SQL("TRUNCATE TABLE {} CASCADE;").format(
        sql.SQL(", ").join(sql.Identifier(t) for t in tables)
    )
    with conn.cursor() as cur:
        cur.execute(stmt)


@pytest.fixture(scope="session")
def database_url() -> str:
    # Prefer CN_TEST_DATABASE_URL to avoid accidentally wiping production data
    dsn = os.environ.get("CN_TEST_DATABASE_URL")
    if not dsn:
        # Fall back to CN_DATABASE_URL but verify it's a test database
        dsn = os.environ.get("CN_DATABASE_URL")
    if not dsn:
        pytest.skip("CN_TEST_DATABASE_URL or CN_DATABASE_URL not set")

    # Safety check: refuse to run tests on production database
    if "curious_now_test" not in dsn and "_test" not in dsn:
        pytest.fail(
            f"Refusing to run tests on non-test database: {dsn}\n"
            "Tests truncate all tables! Set CN_TEST_DATABASE_URL to a test database, "
            "or ensure your database name contains '_test'."
        )
    return dsn


@pytest.fixture()
def db_conn(database_url: str) -> Generator[psycopg.Connection, None, None]:
    conn = psycopg.connect(database_url)
    conn.autocommit = True
    try:
        _truncate_public_tables(conn)
        yield conn
    finally:
        conn.close()


@pytest.fixture()
def client(db_conn: psycopg.Connection) -> Generator[TestClient, None, None]:
    # Ensure Settings reads fresh env for tests.
    clear_settings_cache()
    clear_redis_client_cache()
    r = get_redis_client()
    if r:
        try:
            r.flushdb()
        except redis.RedisError:
            pass

    with TestClient(app) as c:
        yield c
