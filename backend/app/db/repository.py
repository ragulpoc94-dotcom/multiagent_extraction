"""SQLite persistence for the local PoC.

Each entity is stored as a JSON document plus a few indexed columns. Writes are
serialised with a lock so the background competition runner and API requests
can share one connection safely.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from app.core.errors import NotFoundError
from app.core.utils import utcnow

TABLES = ("requirements", "prompt_runs", "documents", "competitions", "executions", "evaluations")

SCHEMA = "\n".join(
    f"""
CREATE TABLE IF NOT EXISTS {t} (
    id TEXT PRIMARY KEY,
    parent_id TEXT,
    status TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_{t}_parent ON {t}(parent_id);
CREATE INDEX IF NOT EXISTS idx_{t}_status ON {t}(status);
"""
    for t in TABLES
)


class Repository:
    def __init__(self, db_path: Path | str):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            if self.db_path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    @staticmethod
    def _check(table: str) -> None:
        if table not in TABLES:
            raise ValueError(f"unknown table {table}")

    def insert(self, table: str, id: str, data: dict[str, Any], *, parent_id: str | None = None,
               status: str | None = None) -> dict[str, Any]:
        self._check(table)
        now = utcnow()
        data = {**data, "id": id, "created_at": data.get("created_at", now)}
        if status is not None:
            data["status"] = status
        with self._lock:
            self._conn.execute(
                f"INSERT INTO {table}(id,parent_id,status,created_at,updated_at,data) VALUES(?,?,?,?,?,?)",
                (id, parent_id, status, data["created_at"], now, json.dumps(data, default=str)),
            )
            self._conn.commit()
        return data

    def get(self, table: str, id: str) -> dict[str, Any]:
        row = self.find(table, id)
        if row is None:
            raise NotFoundError(f"{table[:-1].replace('_', ' ')} '{id}' not found")
        return row

    def find(self, table: str, id: str) -> dict[str, Any] | None:
        self._check(table)
        with self._lock:
            row = self._conn.execute(f"SELECT data FROM {table} WHERE id=?", (id,)).fetchone()
        return json.loads(row["data"]) if row else None

    def update(self, table: str, id: str, patch: dict[str, Any]) -> dict[str, Any]:
        self._check(table)
        with self._lock:
            current = self.get(table, id)
            current.update(patch)
            current["updated_at"] = utcnow()
            self._conn.execute(
                f"UPDATE {table} SET data=?, status=?, updated_at=? WHERE id=?",
                (json.dumps(current, default=str), current.get("status"), current["updated_at"], id),
            )
            self._conn.commit()
        return current

    def list(self, table: str, *, parent_id: str | None = None, status: str | None = None,
             limit: int = 100, order: str = "DESC") -> list[dict[str, Any]]:
        self._check(table)
        clauses, params = [], []
        if parent_id is not None:
            clauses.append("parent_id=?")
            params.append(parent_id)
        if status is not None:
            clauses.append("status=?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = "ASC" if order.upper() == "ASC" else "DESC"
        with self._lock:
            rows = self._conn.execute(
                f"SELECT data FROM {table} {where} ORDER BY created_at {order}, id LIMIT ?", (*params, limit)
            ).fetchall()
        return [json.loads(r["data"]) for r in rows]

    def delete_children(self, table: str, parent_id: str) -> None:
        self._check(table)
        with self._lock:
            self._conn.execute(f"DELETE FROM {table} WHERE parent_id=?", (parent_id,))
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
