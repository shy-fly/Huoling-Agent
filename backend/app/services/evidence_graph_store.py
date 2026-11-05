"""Atomic replacement of a bounded graph snapshot in a separate SQLite index."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS graph_snapshots (
    graphId TEXT PRIMARY KEY, payload TEXT NOT NULL
)
"""


def saveGraph(path: Path, graphId: str, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    with closing(sqlite3.connect(path)) as db, db:
        db.execute(_SCHEMA)
        db.execute("INSERT INTO graph_snapshots VALUES (?, ?) ON CONFLICT (graphId) "
                   "DO UPDATE SET payload=excluded.payload", (graphId, serialized))


def loadGraph(path: Path, graphId: str) -> dict | None:
    if not path.is_file():
        return None
    with closing(sqlite3.connect(path)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='graph_snapshots'").fetchone():
            return None
        row = db.execute("SELECT payload FROM graph_snapshots WHERE graphId=?", (graphId,)).fetchone()
    return json.loads(row[0]) if row else None
