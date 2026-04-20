"""
nba/analytics.py — Session & visitor tracking for the admin page.

Stores data in a local SQLite database (analytics.db) beside the cache dir.
Thread-safe via WAL mode. Designed for single-server Streamlit deployments.

Tables
------
sessions       (session_id TEXT PK, first_seen REAL, last_seen REAL, page_views INT)
visitors       (visitor_id TEXT PK, first_seen REAL)
page_views     (id INTEGER PK, session_id TEXT, visitor_id TEXT, path TEXT, ts REAL)
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent / "cache" / "analytics.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── Schema ────────────────────────────────────────────────────────────────────

_DDL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    first_seen  REAL NOT NULL,
    last_seen   REAL NOT NULL,
    page_views  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS visitors (
    visitor_id  TEXT PRIMARY KEY,
    first_seen  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS page_views (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    visitor_id  TEXT    NOT NULL,
    path        TEXT    NOT NULL DEFAULT '/',
    ts          REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pv_ts ON page_views(ts);
CREATE INDEX IF NOT EXISTS idx_pv_session ON page_views(session_id);
"""


@contextmanager
def _db():
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_DDL)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Public API ────────────────────────────────────────────────────────────────

def make_session_id() -> str:
    """Generate a fresh session ID (UUID4)."""
    return str(uuid.uuid4())


def fingerprint_visitor(request_headers: dict | None = None) -> str:
    """
    Derive a stable visitor fingerprint from available signals.
    In Streamlit we don't have full HTTP headers, so we hash
    whatever we can glean + a stable salt.  Not perfect but
    good enough for rough unique-visitor counting.
    """
    raw = str(request_headers or {}) + "gs_plus_salt_v1"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def track_page_view(
    session_id: str,
    visitor_id: str,
    path: str = "/",
) -> None:
    """
    Record a page view.  Creates/updates session and visitor rows.
    Safe to call on every Streamlit rerun — deduplication is handled
    upstream by calling only when `path` changes or on first load.
    """
    now = time.time()
    try:
        with _db() as conn:
            # Upsert visitor
            conn.execute(
                """
                INSERT INTO visitors(visitor_id, first_seen)
                VALUES(?, ?)
                ON CONFLICT(visitor_id) DO NOTHING
                """,
                (visitor_id, now),
            )
            # Upsert session
            conn.execute(
                """
                INSERT INTO sessions(session_id, first_seen, last_seen, page_views)
                VALUES(?, ?, ?, 1)
                ON CONFLICT(session_id) DO UPDATE SET
                    last_seen  = excluded.last_seen,
                    page_views = page_views + 1
                """,
                (session_id, now, now),
            )
            # Insert page view
            conn.execute(
                "INSERT INTO page_views(session_id, visitor_id, path, ts) VALUES(?,?,?,?)",
                (session_id, visitor_id, path, now),
            )
    except Exception as e:
        log.warning("analytics.track_page_view failed: %s", e)


# ── Admin stats ───────────────────────────────────────────────────────────────

def get_stats(days: int = 30) -> dict:
    """
    Return a summary dict for the admin dashboard.
    All counts are for the last `days` days.
    """
    cutoff = time.time() - days * 86_400
    stats: dict = {
        "total_sessions":       0,
        "unique_visitors":      0,
        "total_page_views":     0,
        "sessions_today":       0,
        "visitors_today":       0,
        "page_views_today":     0,
        "top_paths":            [],
        "hourly_views":         [],   # last 24 h, list of (hour_label, count)
        "daily_views":          [],   # last N days, list of (date_label, count)
    }
    try:
        today_cutoff = time.time() - 86_400
        with _db() as conn:
            def q(sql, *args):
                return conn.execute(sql, args).fetchone()

            stats["total_sessions"]   = q(
                "SELECT COUNT(*) FROM sessions WHERE first_seen >= ?", cutoff
            )[0]
            stats["unique_visitors"]  = q(
                "SELECT COUNT(*) FROM visitors WHERE first_seen >= ?", cutoff
            )[0]
            stats["total_page_views"] = q(
                "SELECT COUNT(*) FROM page_views WHERE ts >= ?", cutoff
            )[0]
            stats["sessions_today"]   = q(
                "SELECT COUNT(*) FROM sessions WHERE first_seen >= ?", today_cutoff
            )[0]
            stats["visitors_today"]   = q(
                "SELECT COUNT(*) FROM visitors WHERE first_seen >= ?", today_cutoff
            )[0]
            stats["page_views_today"] = q(
                "SELECT COUNT(*) FROM page_views WHERE ts >= ?", today_cutoff
            )[0]

            # Top paths
            rows = conn.execute(
                """
                SELECT path, COUNT(*) as cnt
                FROM page_views WHERE ts >= ?
                GROUP BY path ORDER BY cnt DESC LIMIT 10
                """,
                (cutoff,),
            ).fetchall()
            stats["top_paths"] = [{"path": r["path"], "views": r["cnt"]} for r in rows]

            # Hourly (last 24 h)
            rows = conn.execute(
                """
                SELECT CAST((ts - ?) / 3600 AS INTEGER) as hour_ago, COUNT(*) as cnt
                FROM page_views
                WHERE ts >= ?
                GROUP BY hour_ago
                ORDER BY hour_ago
                """,
                (time.time() - 86_400, time.time() - 86_400),
            ).fetchall()
            stats["hourly_views"] = [
                {"hour_ago": r["hour_ago"], "count": r["cnt"]} for r in rows
            ]

            # Daily (last `days` days)
            import datetime
            rows = conn.execute(
                """
                SELECT CAST((ts - ?) / 86400 AS INTEGER) as day_ago, COUNT(*) as cnt
                FROM page_views
                WHERE ts >= ?
                GROUP BY day_ago
                ORDER BY day_ago
                """,
                (cutoff, cutoff),
            ).fetchall()
            stats["daily_views"] = [
                {
                    "date": (
                        datetime.date.today()
                        - datetime.timedelta(days=days - 1 - r["day_ago"])
                    ).isoformat(),
                    "count": r["cnt"],
                }
                for r in rows
            ]

    except Exception as e:
        log.warning("analytics.get_stats failed: %s", e)

    return stats


def get_recent_sessions(limit: int = 50) -> list[dict]:
    """Return most recent sessions for the admin log."""
    try:
        with _db() as conn:
            rows = conn.execute(
                """
                SELECT session_id, first_seen, last_seen, page_views
                FROM sessions
                ORDER BY last_seen DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            import datetime
            return [
                {
                    "session_id":  r["session_id"][:8] + "…",
                    "first_seen":  datetime.datetime.fromtimestamp(r["first_seen"]).strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                    "last_seen":   datetime.datetime.fromtimestamp(r["last_seen"]).strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                    "page_views":  r["page_views"],
                }
                for r in rows
            ]
    except Exception as e:
        log.warning("analytics.get_recent_sessions failed: %s", e)
        return []
