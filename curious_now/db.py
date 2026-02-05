from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row


@dataclass(frozen=True)
class DB:
    dsn: str

    def connect(self, *, autocommit: bool = False) -> psycopg.Connection[Any]:
        conn = psycopg.connect(self.dsn, row_factory=dict_row)
        conn.autocommit = autocommit
        return conn
