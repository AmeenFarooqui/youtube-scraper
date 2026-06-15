"""
playlist_extractor.py
---------------------
Extracts metadata for YouTube playlists.

HOW PLAYLIST EXTRACTION WORKS:
  yt-dlp handles playlists the same way as single videos — you pass the URL
  and it returns a dict with _type="playlist" and an "entries" list.

  There are two modes:
    1. Flat extraction (extract_flat=True):
       - Very fast — only fetches the playlist index page
       - Returns basic info: title, ID, duration, uploader per video
       - Does NOT fetch individual video pages
       - Best for: "how many videos", "list of titles", large playlists

    2. Full extraction (extract_flat=False):
       - Fetches every individual video page
       - Returns complete VideoExtractor-level data per video
       - Slow for large playlists (many network requests)
       - Best for: detailed analysis, subtitle checking, format inspection

  We default to flat extraction and offer --full-playlist for deep mode.
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import yt_dlp

from config import BASE_YDL_OPTS
from utils.logger import get_logger, YtDlpLogger
from utils.helpers import (
    format_duration,
    format_number,
    format_date,
    flatten_list,
    safe_get,
    seconds_to_hms,
    truncate,
    is_youtube_short,
)
from utils.error_handler import classify_ytdlp_error, format_error_for_report

logger = get_logger(__name__)


class PlaylistExtractor:
    """
    Extracts metadata for a YouTube playlist URL.

    Usage:
        extractor = PlaylistExtractor()
        result = extractor.extract("https://www.youtube.com/playlist?list=PL...")

    Args:
        full_details: If True, fetch complete metadata for each video (slow).
                      If False, use flat extraction (fast, basic fields only).
        max_videos:   Limit how many videos to process (None = all).
    """

    def __init__(self, full_details: bool = False, max_videos: int | None = None, verbose: bool = False):
        self.full_details = full_details
        self.max_videos = max_videos
        self.verbose = verbose
        self._ydl_logger = YtDlpLogger(get_logger("yt_dlp", verbose=verbose))

    def _build_opts(self) -> dict:
        opts = {
            **BASE_YDL_OPTS,
            "logger": self._ydl_logger,
            "extract_flat": not self.full_details,  # Flat = fast; False = full per-video fetch
            "ignoreerrors": True,   # Continue if individual videos are unavailable
        }

        # Limit the number of videos processed
        if self.max_videos:
            opts["playlistend"] = self.max_videos

        return opts

    def extract(self, url: str) -> dict:
        """
        Fetch and return all available metadata for a YouTube playlist.

        Args:
            url: A valid YouTube playlist URL

        Returns:
            Structured dict with playlist metadata, video list, and summary stats
        """
        logger.info(f"Extracting playlist: {url}")
        logger.info(f"Mode: {'full video details' if self.full_details else 'flat (fast)'}")

        opts = self._build_opts()

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                raw = ydl.extract_info(url, download=False)
                if raw is None:
                    raise ValueError("yt-dlp returned no data for this URL")
                sanitized = ydl.sanitize_info(raw)
        except Exception as e:
            raise classify_ytdlp_error(e, url=url) from e

        return self._shape_playlist(sanitized, url)

    def _shape_playlist(self, raw: dict, url: str) -> dict:
        """
        Shape raw yt-dlp playlist data into a clean structured dict.
        Also generates summary statistics.
        """
        g = lambda *keys, default=None: safe_get(raw, *keys, default=default)

        # ── Playlist-level metadata ───────────────────────────────────────────
        playlist_id = g("id")
        title = g("title")
        description = g("description") or ""
        uploader = g("uploader") or g("channel")
        uploader_url = g("uploader_url") or g("channel_url")
        webpage_url = g("webpage_url") or url

        # ── Videos ───────────────────────────────────────────────────────────
        entries = g("entries") or []
        videos, errors = self._process_entries(entries)

        # ── Summary statistics ────────────────────────────────────────────────
        summary = self._compute_summary(videos)

        return {
            # Playlist identification
            "id": playlist_id,
            "title": title,
            "url": url,
            "webpage_url": webpage_url,
            "description": description,
            "uploader": uploader,
            "uploader_url": uploader_url,

            # Counts
            "total_videos": len(entries),
            "available_videos": len(videos),
            "unavailable_videos": len(errors),
            "errors": errors,

            # Video list
            "videos": videos,

            # Summary stats
            "summary": summary,

            # Extractor metadata
            "_extractor": "PlaylistExtractor",
            "_mode": "full" if self.full_details else "flat",
            "_source_url": url,
        }

    def _process_entries(self, entries: list) -> tuple[list[dict], list[dict]]:
        """
        Process each entry in the playlist.

        Returns:
            (videos, errors) — two lists:
            - videos: successfully processed video dicts
            - errors: dicts describing videos that failed
        """
        videos = []
        errors = []

        for i, entry in enumerate(entries):
            if entry is None:
                # yt-dlp sets an entry to None when a video is unavailable
                errors.append({
                    "position": i + 1,
                    "error": "Video unavailable (deleted or private)",
                    "url": None,
                })
                continue

            try:
                video = self._shape_video_entry(entry, position=i + 1)
                videos.append(video)
            except Exception as e:
                errors.append({
                    "position": i + 1,
                    "error": str(e),
                    "url": safe_get(entry, "url") or safe_get(entry, "webpage_url"),
                })

        return videos, errors

    def _shape_video_entry(self, entry: dict, position: int) -> dict:
        """
        Shape a single video entry from the playlist.

        In flat mode, entries have fewer fields (no formats, no detailed stats).
        In full mode, they have the complete set.
        """
        g = lambda *keys, default=None: safe_get(entry, *keys, default=default)

        duration_secs = g("duration")
        upload_date = g("upload_date")
        url = g("url") or g("webpage_url")
        is_short = is_youtube_short(url, duration_secs)

        thumbnails = g("thumbnails") or []
        best_thumbnail = thumbnails[-1].get("url") if thumbnails else g("thumbnail")
        tags = g("tags") or []
        categories = g("categories") or []
        chapters = g("chapters") or []

        return {
            "position": position,
            "id": g("id"),
            "title": g("title"),
            "url": url,
            "webpage_url": g("webpage_url") or url,
            "uploader": g("uploader") or g("channel"),
            "channel": g("channel") or g("uploader"),
            "duration": duration_secs,
            "duration_string": seconds_to_hms(duration_secs),
            "duration_formatted": format_duration(duration_secs),
            "upload_date": upload_date,
            "upload_date_formatted": format_date(upload_date),
            "view_count": g("view_count"),
            "view_count_formatted": format_number(g("view_count")),
            "availability": g("availability"),
            "thumbnail": best_thumbnail,
            "thumbnails": thumbnails,
            # Full-mode extras (None in flat mode)
            "like_count": g("like_count"),
            "like_count_formatted": format_number(g("like_count")),
            "comment_count": g("comment_count"),
            "comment_count_formatted": format_number(g("comment_count")),
            "average_rating": g("average_rating"),
            "tags": tags,
            "tags_string": flatten_list(tags),
            "categories": categories,
            "categories_string": flatten_list(categories),
            "description": g("description"),
            "description_short": truncate(g("description") or "", 300),
            "live_status": g("live_status"),
            "is_short": is_short,
            "content_type": "short" if is_short else "video",
            "chapters": chapters,
            "has_chapters": len(chapters) > 0,
            "chapter_count": len(chapters),
            "heatmap": g("heatmap") or [],
            # Extended fields: populated in full-details mode, None in flat mode
            "channel_id": g("channel_id"),
            "channel_url": g("channel_url") or g("uploader_url"),
            "channel_follower_count": g("channel_follower_count"),
            "channel_follower_count_formatted": format_number(g("channel_follower_count")),
            "uploader_id": g("uploader_id"),
            "uploader_url": g("uploader_url"),
            "age_limit": g("age_limit"),
            "language": g("language"),
            "subtitles_manual": list((g("subtitles") or {}).keys()),
            "subtitles_auto": list((g("automatic_captions") or {}).keys()),
        }

    def _compute_summary(self, videos: list[dict]) -> dict:
        """
        Compute aggregate statistics across all videos in the playlist.

        These are the kind of insights that help you understand a playlist
        at a glance: total runtime, average video length, upload patterns.
        """
        if not videos:
            return {
                "total_duration_seconds": 0,
                "total_duration_formatted": "0:00",
                "average_duration_seconds": 0,
                "average_duration_formatted": "0:00",
                "shortest_video": None,
                "longest_video": None,
                "total_views": 0,
                "total_views_formatted": "0",
                "upload_dates": [],
            }

        # Duration stats — skip videos where duration is unknown
        durations = [v["duration"] for v in videos if v.get("duration")]
        total_duration = sum(durations) if durations else 0
        avg_duration = total_duration / len(durations) if durations else 0

        # Find shortest and longest by duration
        videos_with_duration = [v for v in videos if v.get("duration")]
        shortest = min(videos_with_duration, key=lambda v: v["duration"], default=None)
        longest = max(videos_with_duration, key=lambda v: v["duration"], default=None)

        # View count totals
        views = [v["view_count"] for v in videos if v.get("view_count")]
        total_views = sum(views) if views else 0

        # Upload dates for frequency analysis
        upload_dates = sorted(
            [v["upload_date"] for v in videos if v.get("upload_date")]
        )

        return {
            "total_duration_seconds": total_duration,
            "total_duration_formatted": seconds_to_hms(total_duration),
            "average_duration_seconds": round(avg_duration),
            "average_duration_formatted": seconds_to_hms(avg_duration),
            "shortest_video": {
                "title": shortest["title"],
                "duration": seconds_to_hms(shortest["duration"]),
            } if shortest else None,
            "longest_video": {
                "title": longest["title"],
                "duration": seconds_to_hms(longest["duration"]),
            } if longest else None,
            "total_views": total_views,
            "total_views_formatted": format_number(total_views),
            "upload_dates": upload_dates,
            "earliest_upload": format_date(upload_dates[0]) if upload_dates else None,
            "latest_upload": format_date(upload_dates[-1]) if upload_dates else None,
        }
