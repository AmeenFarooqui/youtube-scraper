"""
cache_manager.py
----------------
SQLite-backed metadata cache for the YouTube scraper.

WHY:
  Re-fetching the same video repeatedly wastes time and burns through
  YouTube's rate-limit budget. This cache stores the full metadata dict
  per video_id and returns it on subsequent requests until it expires.

SCHEMA (table: videos):
  id         TEXT PRIMARY KEY  — 11-char YouTube video ID
  url        TEXT              — canonical watch URL
  fetched_at REAL              — Unix timestamp of when data was stored
  data       TEXT              — JSON-serialized metadata dict

TTL: 24 hours by default. Expired entries are evicted on read (lazy cleanup).

Usage:
    cache = CacheManager()
    cached = cache.get(video_id)
    if cached is None:
        data = extractor.extract(url)
        cache.put(video_id, url, data)
        return data
    return cached
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


_DEFAULT_TTL_SECS = 24 * 3600   # 24 hours

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS videos (
    id         TEXT PRIMARY KEY,
    url        TEXT,
    fetched_at REAL,
    data       TEXT
);
"""


class CacheManager:
    """
    Read/write video-metadata cache backed by a local SQLite database.

    Args:
        cache_dir: Directory for the SQLite file.
                   Defaults to ~/.cache/youtube_scraper/
        ttl:       Time-to-live in seconds (default 86400 = 24h).
                   Entries older than this are treated as misses.
    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        ttl: int = _DEFAULT_TTL_SECS,
    ):
        if cache_dir is None:
            cache_dir = Path.home() / ".cache" / "youtube_scraper"
        self.cache_dir = Path(cache_dir)
        self.ttl = ttl
        self._db_path = self.cache_dir / "metadata.db"
        self._conn: sqlite3.Connection | None = None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.execute(_CREATE_TABLE_SQL)
            self._conn.commit()
        return self._conn

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self, video_id: str) -> dict | None:
        """
        Return cached metadata for video_id, or None on miss/expiry.

        Expired entries are deleted on access (lazy eviction).
        """
        conn = self._connect()
        row = conn.execute(
            "SELECT fetched_at, data FROM videos WHERE id = ?", (video_id,)
        ).fetchone()

        if row is None:
            return None

        fetched_at, data_json = row
        if time.time() - fetched_at > self.ttl:
            # Entry expired — evict and report miss
            conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))
            conn.commit()
            return None

        return json.loads(data_json)

    def put(self, video_id: str, url: str, data: dict) -> None:
        """Store (or replace) metadata for video_id."""
        conn = self._connect()
        conn.execute(
            """
            INSERT OR REPLACE INTO videos (id, url, fetched_at, data)
            VALUES (?, ?, ?, ?)
            """,
            (video_id, url, time.time(), json.dumps(data, ensure_ascii=False)),
        )
        conn.commit()

    def invalidate(self, video_id: str) -> None:
        """Force-expire a single cached entry."""
        conn = self._connect()
        conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))
        conn.commit()

    def clear(self) -> int:
        """Remove all cached entries. Returns the count removed."""
        conn = self._connect()
        cursor = conn.execute("DELETE FROM videos")
        conn.commit()
        return cursor.rowcount

    def stats(self) -> dict:
        """Return a summary of cache state."""
        conn = self._connect()
        total   = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        expired = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE fetched_at < ?",
            (time.time() - self.ttl,),
        ).fetchone()[0]
        size_bytes = self._db_path.stat().st_size if self._db_path.exists() else 0
        return {
            "db_path":        str(self._db_path),
            "total_entries":  total,
            "fresh_entries":  total - expired,
            "expired_entries": expired,
            "ttl_hours":      round(self.ttl / 3600, 1),
            "db_size_kb":     round(size_bytes / 1024, 1),
        }

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
