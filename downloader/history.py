"""
Download history: SQLite-backed log of completed downloads (title, URL, format, date, output dir).
"""
import os
import sqlite3
from datetime import datetime
from typing import List, Optional, Tuple

_HISTORY_DIR_NAME = "download_history"
_DB_NAME = "history.db"


def _db_path(app_root: str) -> str:
    folder = os.path.join(app_root, _HISTORY_DIR_NAME)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, _DB_NAME)


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            format_type TEXT NOT NULL,
            format_detail TEXT,
            output_dir TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()


def add(
    app_root: str,
    title: str,
    url: str,
    format_type: str,
    format_detail: str = "",
    output_dir: str = "",
) -> None:
    path = _db_path(app_root)
    conn = sqlite3.connect(path)
    try:
        _ensure_table(conn)
        conn.execute(
            "INSERT INTO history (title, url, format_type, format_detail, output_dir, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (title or "Unknown", url or "", format_type or "", format_detail or "", output_dir or "", datetime.utcnow().isoformat() + "Z"),
        )
        conn.commit()
    finally:
        conn.close()


def get_all(app_root: str, limit: int = 500) -> List[Tuple[int, str, str, str, str, str, str]]:
    """Return rows (id, title, url, format_type, format_detail, output_dir, created_at)."""
    path = _db_path(app_root)
    if not os.path.isfile(path):
        return []
    conn = sqlite3.connect(path)
    try:
        _ensure_table(conn)
        cur = conn.execute(
            "SELECT id, title, url, format_type, format_detail, output_dir, created_at FROM history ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return list(cur.fetchall())
    finally:
        conn.close()


def clear(app_root: str) -> None:
    path = _db_path(app_root)
    if not os.path.isfile(path):
        return
    conn = sqlite3.connect(path)
    try:
        conn.execute("DELETE FROM history")
        conn.commit()
    finally:
        conn.close()
