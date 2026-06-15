"""
ryd_client.py
-------------
Client for the Return YouTube Dislike API (returnyoutubedislikeapi.com).

YouTube removed public dislike counts in November 2021. The Return YouTube Dislike
project provides crowdsourced + ML-estimated dislike counts via a free public API.
No API key or authentication required.

API endpoint: GET https://returnyoutubedislikeapi.com/votes?videoId=VIDEO_ID

Response fields:
    id          - video ID
    dateCreated - when the entry was created
    likes       - like count (may differ slightly from YouTube's public count)
    dislikes    - estimated dislike count
    rating      - 0.0–5.0 star rating computed from like/dislike ratio
    viewCount   - view count at last update
    deleted     - whether the video has been deleted

Usage:
    client = RYDClient(timeout=5)
    result = client.get_dislikes("dQw4w9WgXcQ")
    # → {"dislikes": 15000, "likes_ryd": 1200000, "rating": 4.5,
    #    "dislike_count_estimated": True}
    # → None on any failure (network error, 404, etc.)
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

_BASE_URL = "https://returnyoutubedislikeapi.com"


class RYDClient:
    """
    Fetches estimated dislike counts from the Return YouTube Dislike API.

    Failures are always silent (returns None) — dislikes are optional enrichment,
    not critical data. The scraper should never fail because RYD is unavailable.
    """

    def __init__(self, timeout: int = 5):
        self.timeout = timeout

    def get_dislikes(self, video_id: str) -> dict | None:
        """
        Fetch dislike data for a YouTube video ID.

        Args:
            video_id: YouTube video ID (e.g. "dQw4w9WgXcQ"), NOT a full URL.

        Returns:
            {
                "dislikes":                int   — estimated dislike count
                "likes_ryd":               int   — like count per RYD
                "rating":                  float — 0.0–5.0 score (like/dislike ratio)
                "dislike_count_estimated": True  — always True (marks the source)
            }
            None if the request fails for any reason.
        """
        if not video_id:
            return None

        url = f"{_BASE_URL}/votes?videoId={video_id}"
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "youtube-scraper/1.0"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8"))

            dislikes = raw.get("dislikes")
            likes    = raw.get("likes")
            rating   = raw.get("rating")

            return {
                "dislikes":                dislikes,
                "likes_ryd":               likes,
                "rating":                  rating,
                "dislike_count_estimated": True,
            }

        except (urllib.error.URLError, urllib.error.HTTPError,
                json.JSONDecodeError, OSError, ValueError) as exc:
            logger.debug(f"RYD request failed for {video_id!r}: {exc}")
            return None
