import sqlite3
import json
from datetime import datetime
from typing import Optional

from paths import DB_PATH


class DB:
    def __init__(self, path=DB_PATH):
        self.path = path
        self._init()

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._conn() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS datasets (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                path TEXT NOT NULL,
                n_rows INTEGER,
                n_cols INTEGER,
                columns TEXT,
                source TEXT DEFAULT 'upload',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                dataset_id TEXT,
                target TEXT,
                config TEXT,
                summary TEXT,
                created_at TEXT NOT NULL,
                note TEXT DEFAULT ''
            );
            """)
            # Backward-compatible migration: add aliases column if missing
            try:
                c.execute("ALTER TABLE datasets ADD COLUMN aliases TEXT DEFAULT '{}'")
            except sqlite3.OperationalError:
                pass

    def add_dataset(self, info: dict, source: str = "upload"):
        with self._conn() as c:
            c.execute(
                "INSERT INTO datasets (id, filename, path, n_rows, n_cols, columns, source, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (info["id"], info["filename"], info["path"],
                 info["n_rows"], info["n_cols"],
                 json.dumps(info["columns"]),
                 source, datetime.now().isoformat()),
            )

    def list_datasets(self):
        with self._conn() as c:
            rows = c.execute("SELECT * FROM datasets ORDER BY created_at DESC").fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["columns"] = json.loads(d["columns"])
                d["aliases"] = json.loads(d.get("aliases") or "{}")
                result.append(d)
            return result

    def get_dataset(self, dataset_id: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM datasets WHERE id=?", (dataset_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["columns"] = json.loads(d["columns"])
            d["aliases"] = json.loads(d.get("aliases") or "{}")
            return d

    def update_aliases(self, dataset_id: str, aliases: dict):
        with self._conn() as c:
            c.execute("UPDATE datasets SET aliases=? WHERE id=?",
                      (json.dumps(aliases), dataset_id))

    def delete_dataset(self, dataset_id: str):
        with self._conn() as c:
            c.execute("DELETE FROM datasets WHERE id=?", (dataset_id,))

    def add_run(self, run_id: str, dataset_id: str, target: str,
                config: dict, summary: list, note: str = ""):
        with self._conn() as c:
            c.execute(
                "INSERT INTO runs (id, dataset_id, target, config, summary, created_at, note) "
                "VALUES (?,?,?,?,?,?,?)",
                (run_id, dataset_id, target,
                 json.dumps(config), json.dumps(summary),
                 datetime.now().isoformat(), note),
            )

    def list_runs(self):
        with self._conn() as c:
            rows = c.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    def get_run(self, run_id: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            return dict(row) if row else None

    def delete_run(self, run_id: str):
        with self._conn() as c:
            c.execute("DELETE FROM runs WHERE id=?", (run_id,))


db = DB()
