"""
multi_search/history.py — Search history storage, retrieval, and analytics.

Implements:
  - SQLite-backed search history (persistent)
  - JSON file storage for analytics data
  - Search trend analysis
  - Popular query tracking
  - Engine performance tracking
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .models import SearchHistoryEntry, SearchAnalytics, SearchEngineType

# ============================================================================
# Database setup
# ============================================================================

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
ANALYTICS_FILE = os.path.join(DB_DIR, "search_analytics.json")


def _get_db_path() -> str:
    os.makedirs(DB_DIR, exist_ok=True)
    return os.path.join(DB_DIR, "search_history.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-8000")          # 8MB cache
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _init_history_db():
    """Create tables if not exists."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS search_history (
            id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            engines_used TEXT DEFAULT '[]',
            result_count INTEGER DEFAULT 0,
            clicked_results TEXT DEFAULT '[]',
            search_time_ms REAL DEFAULT 0.0,
            timestamp TEXT DEFAULT (datetime('now', 'localtime')),
            user_id TEXT DEFAULT 'anonymous'
        );

        CREATE TABLE IF NOT EXISTS click_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            search_id TEXT NOT NULL,
            result_url TEXT NOT NULL,
            result_title TEXT DEFAULT '',
            result_source TEXT DEFAULT '',
            position INTEGER DEFAULT 0,
            timestamp TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (search_id) REFERENCES search_history(id)
        );

        CREATE TABLE IF NOT EXISTS query_suggestions (
            query TEXT PRIMARY KEY,
            count INTEGER DEFAULT 1,
            last_searched TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_history_query ON search_history(query);
        CREATE INDEX IF NOT EXISTS idx_history_timestamp ON search_history(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_history_user ON search_history(user_id);
        CREATE INDEX IF NOT EXISTS idx_click_search ON click_log(search_id);
        CREATE INDEX IF NOT EXISTS idx_click_timestamp ON click_log(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_suggestions_count ON query_suggestions(count DESC);
    """)
    conn.commit()
    conn.close()


# ============================================================================
# History Manager
# ============================================================================

class SearchHistoryManager:
    """Manages search history: save, query, analyze, and auto-complete."""

    def __init__(self, user_id: str = "anonymous"):
        self.user_id = user_id
        _init_history_db()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_search(
        self,
        query: str,
        engines_used: List[str],
        result_count: int = 0,
        search_time_ms: float = 0.0,
    ) -> str:
        """Save a search record, return its ID."""
        search_id = str(uuid.uuid4())
        conn = _get_conn()
        conn.execute(
            """INSERT INTO search_history
               (id, query, engines_used, result_count, search_time_ms, user_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                search_id,
                query,
                json.dumps(engines_used, ensure_ascii=False),
                result_count,
                search_time_ms,
                self.user_id,
            )
        )
        # Update or insert query suggestion counter
        conn.execute(
            """INSERT INTO query_suggestions (query, count, last_searched)
               VALUES (?, 1, datetime('now', 'localtime'))
               ON CONFLICT(query) DO UPDATE SET
                   count = count + 1,
                   last_searched = datetime('now', 'localtime')""",
            (query,)
        )
        conn.commit()
        conn.close()
        return search_id

    def log_click(
        self,
        search_id: str,
        result_url: str,
        result_title: str = "",
        result_source: str = "",
        position: int = 0,
    ):
        """Log a user click on a search result."""
        conn = _get_conn()
        conn.execute(
            """INSERT INTO click_log
               (search_id, result_url, result_title, result_source, position)
               VALUES (?, ?, ?, ?, ?)""",
            (search_id, result_url, result_title, result_source, position)
        )
        # Update click count in search_history
        row = conn.execute(
            "SELECT clicked_results FROM search_history WHERE id=?",
            (search_id,)
        ).fetchone()
        if row:
            clicked = json.loads(row["clicked_results"])
            clicked.append(result_url)
            conn.execute(
                "UPDATE search_history SET clicked_results=? WHERE id=?",
                (json.dumps(clicked, ensure_ascii=False), search_id)
            )
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Query history
    # ------------------------------------------------------------------

    def get_recent_searches(
        self,
        limit: int = 20,
        offset: int = 0,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get recent search history."""
        uid = user_id or self.user_id
        conn = _get_conn()
        rows = conn.execute(
            """SELECT * FROM search_history
               WHERE user_id=?
               ORDER BY timestamp DESC
               LIMIT ? OFFSET ?""",
            (uid, limit, offset)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_history_by_query(
        self,
        search_term: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search history by query text."""
        conn = _get_conn()
        rows = conn.execute(
            """SELECT * FROM search_history
               WHERE query LIKE ? AND user_id=?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (f"%{search_term}%", self.user_id, limit)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_clicks_for_search(self, search_id: str) -> List[Dict[str, Any]]:
        """Get all clicks for a given search."""
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM click_log WHERE search_id=? ORDER BY timestamp",
            (search_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Auto-complete / suggestions
    # ------------------------------------------------------------------

    def get_suggestions(
        self,
        prefix: str,
        limit: int = 8,
    ) -> List[str]:
        """Get query suggestions based on prefix matching and popularity."""
        conn = _get_conn()
        # First: exact prefix match, sorted by count
        rows = conn.execute(
            """SELECT query FROM query_suggestions
               WHERE query LIKE ?
               ORDER BY count DESC, last_searched DESC
               LIMIT ?""",
            (f"{prefix}%", limit)
        ).fetchall()
        results = [r["query"] for r in rows]

        # If not enough, try contains match
        if len(results) < limit:
            rows = conn.execute(
                """SELECT query FROM query_suggestions
                   WHERE query LIKE ? AND query NOT LIKE ?
                   ORDER BY count DESC, last_searched DESC
                   LIMIT ?""",
                (f"%{prefix}%", f"{prefix}%", limit - len(results))
            ).fetchall()
            results.extend([r["query"] for r in rows])

        conn.close()
        return results[:limit]

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def get_analytics(self, days: int = 30) -> SearchAnalytics:
        """Compute search analytics for the given time window.

        Returns: SearchAnalytics with aggregated stats.
        """
        since = (datetime.now() - timedelta(days=days)).isoformat()
        conn = _get_conn()

        # Total searches
        total = conn.execute(
            "SELECT COUNT(*) as c FROM search_history WHERE timestamp >= ?",
            (since,)
        ).fetchone()["c"]

        # Unique queries
        unique = conn.execute(
            "SELECT COUNT(DISTINCT query) as c FROM search_history WHERE timestamp >= ?",
            (since,)
        ).fetchone()["c"]

        # Top queries
        top_rows = conn.execute(
            """SELECT query, COUNT(*) as cnt
               FROM search_history
               WHERE timestamp >= ?
               GROUP BY query
               ORDER BY cnt DESC
               LIMIT 10""",
            (since,)
        ).fetchall()

        # Engine usage
        engine_rows = conn.execute(
            "SELECT engines_used FROM search_history WHERE timestamp >= ?",
            (since,)
        ).fetchall()

        engine_usage: Dict[str, int] = {}
        for row in engine_rows:
            try:
                engines = json.loads(row["engines_used"])
            except Exception:
                engines = []
            for eng in engines:
                engine_usage[eng] = engine_usage.get(eng, 0) + 1

        # Avg response time
        avg_time = conn.execute(
            "SELECT AVG(search_time_ms) as avg FROM search_history WHERE timestamp >= ?",
            (since,)
        ).fetchone()["avg"] or 0.0

        # Daily searches
        daily_rows = conn.execute(
            """SELECT DATE(timestamp) as day, COUNT(*) as cnt
               FROM search_history
               WHERE timestamp >= ?
               GROUP BY DATE(timestamp)
               ORDER BY day""",
            (since,)
        ).fetchall()

        # Top clicked URLs
        click_rows = conn.execute(
            """SELECT result_url, result_title, COUNT(*) as cnt
               FROM click_log
               WHERE timestamp >= ?
               GROUP BY result_url
               ORDER BY cnt DESC
               LIMIT 10""",
            (since,)
        ).fetchall()

        conn.close()

        return SearchAnalytics(
            total_searches=total,
            unique_queries=unique,
            top_queries=[{"query": r["query"], "count": r["cnt"]} for r in top_rows],
            engine_usage=engine_usage,
            avg_response_time_ms=avg_time,
            popular_topics=[r["result_title"] for r in click_rows],
            daily_searches=[{"date": r["day"], "count": r["cnt"]} for r in daily_rows],
        )

    # ------------------------------------------------------------------
    # Export / Maintenance
    # ------------------------------------------------------------------

    def export_history(
        self,
        days: Optional[int] = None,
        fmt: str = "json",
    ) -> str:
        """Export search history as JSON or CSV string."""
        conn = _get_conn()
        if days:
            since = (datetime.now() - timedelta(days=days)).isoformat()
            rows = conn.execute(
                "SELECT * FROM search_history WHERE timestamp >= ? ORDER BY timestamp DESC",
                (since,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM search_history ORDER BY timestamp DESC"
            ).fetchall()
        conn.close()

        data = [dict(r) for r in rows]

        if fmt == "csv":
            if not data:
                return "id,query,result_count,search_time_ms,timestamp\n"
            import io
            import csv
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
            return output.getvalue()

        return json.dumps(data, ensure_ascii=False, indent=2)

    def clear_old_history(self, days: int = 90):
        """Delete history older than specified days."""
        since = (datetime.now() - timedelta(days=days)).isoformat()
        conn = _get_conn()
        conn.execute("DELETE FROM search_history WHERE timestamp < ?", (since,))
        conn.execute("DELETE FROM click_log WHERE timestamp < ?", (since,))
        conn.commit()
        # VACUUM to reclaim space
        conn.execute("PRAGMA optimize")
        conn.close()

    def get_total_count(self) -> int:
        """Get total history entries."""
        conn = _get_conn()
        count = conn.execute("SELECT COUNT(*) as c FROM search_history").fetchone()["c"]
        conn.close()
        return count


# ============================================================================
# Analytics persistence (JSON file based for simplicity)
# ============================================================================

def save_analytics_snapshot(analytics: SearchAnalytics):
    """Save current analytics snapshot to JSON file."""
    os.makedirs(os.path.dirname(ANALYTICS_FILE), exist_ok=True)
    data = {
        "total_searches": analytics.total_searches,
        "unique_queries": analytics.unique_queries,
        "top_queries": analytics.top_queries,
        "engine_usage": analytics.engine_usage,
        "avg_response_time_ms": analytics.avg_response_time_ms,
        "popular_topics": analytics.popular_topics,
        "daily_searches": analytics.daily_searches,
        "snapshot_time": datetime.now().isoformat(),
    }
    with open(ANALYTICS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_analytics_snapshot() -> Optional[Dict[str, Any]]:
    """Load last analytics snapshot."""
    if not os.path.exists(ANALYTICS_FILE):
        return None
    with open(ANALYTICS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


__all__ = [
    "SearchHistoryManager",
    "save_analytics_snapshot",
    "load_analytics_snapshot",
    "_init_history_db",
]
