from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg.rows import dict_row

try:
    from psycopg_pool import ConnectionPool
except ImportError:  # pragma: no cover - dependency is installed in runtime
    ConnectionPool = None  # type: ignore[assignment,misc]


@dataclass
class DB:
    dsn: str
    pool_enabled: bool = False
    pool_min_size: int = 1
    pool_max_size: int = 10
    pool_timeout_seconds: float = 10.0
    statement_timeout_ms: int = 0  # 0 = no timeout
    _pool: Any | None = field(default=None, init=False, repr=False)

    def connect(self, *, autocommit: bool = False) -> psycopg.Connection[Any]:
        conn = psycopg.connect(self.dsn, row_factory=dict_row)
        conn.autocommit = autocommit
        if self.statement_timeout_ms > 0:
            conn.execute(f"SET statement_timeout = {self.statement_timeout_ms}")
        return conn

    def open_pool(self) -> None:
        if not self.pool_enabled:
            return
        if self._pool is not None:
            return
        if ConnectionPool is None:  # pragma: no cover
            raise RuntimeError(
                "psycopg-pool is not installed but pool_enabled=True. "
                "Install it with: pip install psycopg-pool"
            )

        self._pool = ConnectionPool(
            conninfo=self.dsn,
            min_size=self.pool_min_size,
            max_size=self.pool_max_size,
            timeout=self.pool_timeout_seconds,
            kwargs={"row_factory": dict_row},
        )

    def close_pool(self) -> None:
        if self._pool is None:
            return
        self._pool.close()
        self._pool = None

    @contextmanager
    def connection(self, *, autocommit: bool = False) -> Any:
        if self._pool is None:
            conn = self.connect(autocommit=autocommit)
            try:
                yield conn
            finally:
                conn.close()
            return

        with self._pool.connection() as conn:
            conn.autocommit = autocommit
            if self.statement_timeout_ms > 0:
                conn.execute(f"SET statement_timeout = {self.statement_timeout_ms}")
            yield conn

    def is_ready(self) -> bool:
        try:
            with self.connection(autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    cur.fetchone()
        except Exception:
            return False
        return True
