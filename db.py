"""SQLite 매핑 저장소 — Figma↔Confluence 페어 관리."""
import json
import os
import sqlite3
from datetime import datetime
from typing import Optional

DB_PATH = "mappings.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS pairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    file_key TEXT NOT NULL,
    page_name TEXT NOT NULL,
    filter_type TEXT NOT NULL CHECK(filter_type IN ('frame_name', 'frame_prefix', 'layer_prefix')),
    filter_values TEXT NOT NULL,
    confluence_domain TEXT NOT NULL,
    page_id TEXT NOT NULL,
    table_type TEXT NOT NULL CHECK(table_type IN ('2col', '5col')),
    last_sync_at TEXT,
    last_sync_status TEXT,
    last_sync_new_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pairs_unique
    ON pairs(file_key, page_name, page_id);
"""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as c:
        c.executescript(SCHEMA)
    _migrate_from_config_if_needed()


def _migrate_from_config_if_needed() -> None:
    """config.json 의 jobs 가 있고 DB 가 비어있으면 한 번 이전한다."""
    if not os.path.exists("config.json"):
        return
    if list_pairs():
        return  # 이미 데이터 있음
    try:
        with open("config.json", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return

    domain = cfg.get("confluence_domain")
    jobs = cfg.get("jobs", [])
    if not domain or not jobs:
        return

    for job in jobs:
        try:
            add_pair(
                name=job.get("name") or "(migrated)",
                file_key=job["figma"]["file_key"],
                page_name=job["figma"]["page_name"],
                filter_type=job["figma"]["filter"].get("type", "frame_name"),
                filter_values=job["figma"]["filter"].get("values", []),
                confluence_domain=domain,
                page_id=job["confluence"]["page_id"],
                table_type=job["confluence"]["table_type"],
            )
        except sqlite3.IntegrityError:
            pass


def add_pair(
    name: str,
    file_key: str,
    page_name: str,
    filter_type: str,
    filter_values: list[str],
    confluence_domain: str,
    page_id: str,
    table_type: str,
) -> int:
    with _conn() as c:
        cur = c.execute(
            """
            INSERT INTO pairs (
                name, file_key, page_name, filter_type, filter_values,
                confluence_domain, page_id, table_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                file_key,
                page_name,
                filter_type,
                json.dumps(filter_values, ensure_ascii=False),
                confluence_domain,
                page_id,
                table_type,
            ),
        )
        return cur.lastrowid


def list_pairs() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM pairs ORDER BY id").fetchall()
    return [_row_to_dict(r) for r in rows]


def get_pair(pair_id: int) -> Optional[dict]:
    with _conn() as c:
        r = c.execute("SELECT * FROM pairs WHERE id = ?", (pair_id,)).fetchone()
    return _row_to_dict(r) if r else None


def delete_pair(pair_id: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM pairs WHERE id = ?", (pair_id,))


def update_last_sync(pair_id: int, status: str, new_count: int) -> None:
    with _conn() as c:
        c.execute(
            """
            UPDATE pairs
            SET last_sync_at = ?, last_sync_status = ?, last_sync_new_count = ?
            WHERE id = ?
            """,
            (datetime.now().isoformat(timespec="seconds"), status, new_count, pair_id),
        )


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["filter_values"] = json.loads(d["filter_values"])
    return d
