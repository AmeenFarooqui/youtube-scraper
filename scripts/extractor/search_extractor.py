"""
search_extractor.py
-------------------
Searches YouTube by keyword using yt-dlp's built-in ytsearch: URL prefix.

HOW IT WORKS:
  yt-dlp treats "ytsearch10:python tutorial" as a special URL that:
  1. Hits YouTube's search endpoint
  2. Returns the top N results as a playlist-like structure
  3. Each entry has: id, title, url, duration, view_count, uploader, upload_date

  We use extract_flat=True so we get basic info per result without
  fetching individual video pages (fast — one network request total).
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import yt_dlp

from config import BASE_YDL_OPTS
from utils.logger import get_logger, YtDlpLogger
from utils.helpers import format_number, seconds_to_hms, format_date, safe_get
from utils.error_handler import classify_ytdlp_error

logger = get_logger(__name__)


class SearchExtractor:
    """
    Searches YouTube by keyword and returns a ranked list of matching videos.

    Usage:
        extractor = SearchExtractor(max_results=10)
        results = extractor.search("python tutorial")

    The returned dict has:
        query         — the original search string
        total_results — number of results returned
        results       — list of video dicts (position, title, url, channel, duration, views)
    """

    def __init__(self, max_results: int = 10, verbose: bool = False):
        self.max_results = max_results
        self.verbose = verbose
        self._ydl_logger = YtDlpLogger(get_logger("yt_dlp", verbose=verbose))

    def search(self, query: str) -> dict:
        """
        Search YouTube for the given query and return structured results.

        Args:
            query: Search terms (e.g. "python tutorial 2024")

        Returns:
            A dict with 'query', 'results', and 'total_results'

        Raises:
            ScraperError on network or extraction failure
        """
        logger.info(f"Searching YouTube: {query!r} (max {self.max_results} results)")

        # yt-dlp's magic search prefix: "ytsearchN:query"
        # Hits YouTube's search without needing an API key.
        search_url = f"ytsearch{self.max_results}:{query}"

        opts = {
            **BASE_YDL_OPTS,
            "logger": self._ydl_logger,
            "extract_flat": True,   # Fast — basic info only, no per-video page load
            "ignoreerrors": True,
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                raw = ydl.extract_info(search_url, download=False)
                if raw is None:
                    raise ValueError("yt-dlp returned no search results")
                sanitized = ydl.sanitize_info(raw)
        except Exception as e:
            raise classify_ytdlp_error(e, url=search_url) from e

        return self._shape_results(query, sanitized)

    def _shape_results(self, query: str, raw: dict) -> dict:
        """Shape raw yt-dlp search output into a clean structured dict."""
        entries = raw.get("entries") or []

        results = []
        for i, entry in enumerate(entries):
            if entry is None:
                continue
            results.append(self._shape_entry(entry, position=i + 1))

        return {
            "query": query,
            "total_results": len(results),
            "results": results,
            "_extractor": "SearchExtractor",
        }

    def _shape_entry(self, entry: dict, position: int) -> dict:
        """Shape a single search result entry into a consistent dict."""
        g = lambda *keys, default=None: safe_get(entry, *keys, default=default)

        video_id    = g("id")
        duration    = g("duration")
        upload_date = g("upload_date")
        view_count  = g("view_count")

        # In flat mode yt-dlp sometimes returns only the ID, not a full URL
        url = g("url") or (
            f"https://www.youtube.com/watch?v={video_id}" if video_id else None
        )

        return {
            "position":              position,
            "id":                    video_id,
            "title":                 g("title"),
            "url":                   url,
            "uploader":              g("uploader") or g("channel"),
            "duration":              duration,
            "duration_string":       seconds_to_hms(duration),
            "upload_date":           upload_date,
            "upload_date_formatted": format_date(upload_date),
            "view_count":            view_count,
            "view_count_formatted":  format_number(view_count),
            "thumbnail":             g("thumbnail"),
            "description":           g("description"),
        }
