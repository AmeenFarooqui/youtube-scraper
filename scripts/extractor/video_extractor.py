"""
video_extractor.py
------------------
Core metadata extractor for a single YouTube video.

This is the heart of the scraper. It uses yt-dlp's Python API to fetch
every piece of publicly available data about a video, then shapes it into
a clean, consistent dictionary.

KEY DESIGN DECISIONS:
  1. download=False always — we never download unless explicitly asked
  2. sanitize_info() makes all fields JSON-serializable (removes non-serializable objects)
  3. safe_get() everywhere — yt-dlp fields are inconsistent across video types
  4. The output dict has a stable structure — callers can rely on these keys existing
     (they may be None, but they won't be missing)
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
    format_date,
    format_number,
    format_filesize,
    safe_get,
    flatten_list,
    truncate,
    seconds_to_hms,
    is_youtube_short,
)
from utils.error_handler import classify_ytdlp_error

logger = get_logger(__name__)


class VideoExtractor:
    """
    Extracts rich metadata for a single YouTube video URL.

    Usage:
        extractor = VideoExtractor()
        metadata = extractor.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    The returned dict always has the same top-level keys (values may be None).
    """

    def __init__(self, verbose: bool = False, include_detailed_formats: bool = False):
        self.verbose = verbose
        self.include_detailed_formats = include_detailed_formats
        self._ydl_logger = YtDlpLogger(get_logger("yt_dlp", verbose=verbose))

    def _build_opts(self, get_comments: bool = False) -> dict:
        """Merge base options with this extractor's specific needs."""
        opts = {
            **BASE_YDL_OPTS,
            "logger": self._ydl_logger,
        }
        if get_comments:
            # Instructs yt-dlp to fetch the comments section.
            # Returns up to ~1000 top-level + reply comments from YouTube.
            opts["getcomments"] = True
        return opts

    def extract(self, url: str, get_comments: bool = False, comments_max: int = 10000) -> dict:
        """
        Fetch and return all available metadata for a YouTube video.

        Args:
            url: A valid YouTube video URL

        Returns:
            A structured metadata dict (see _shape_metadata for all fields)

        Raises:
            ScraperError (or a subclass) on failure
        """
        logger.info(f"Extracting metadata for: {url}")

        opts = self._build_opts(get_comments=get_comments)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                # extract_info with download=False fetches metadata only
                raw = ydl.extract_info(url, download=False)

                if raw is None:
                    raise ValueError("yt-dlp returned no data for this URL")

                # sanitize_info removes non-JSON-serializable objects
                sanitized = ydl.sanitize_info(raw)

        except Exception as e:
            raise classify_ytdlp_error(e, url=url) from e

        return self._shape_metadata(sanitized, url)

    def _shape_metadata(self, raw: dict, url: str) -> dict:
        """
        Transform raw yt-dlp output into a clean, stable structure.

        Why shape the data?
          yt-dlp returns a very large dict with hundreds of fields, many of
          which are None, redundant, or not JSON-safe. This function picks
          the fields we care about and organizes them into logical groups
          so the rest of the code has a predictable shape to work with.
        """
        g = lambda *keys, default=None: safe_get(raw, *keys, default=default)

        # ── Basic identification ──────────────────────────────────────────────
        video_id = g("id")
        title = g("title")
        webpage_url = g("webpage_url") or url

        # ── Timing ───────────────────────────────────────────────────────────
        duration_secs = g("duration")
        upload_date_raw = g("upload_date")

        # ── Channel / uploader ────────────────────────────────────────────────
        # yt-dlp uses both "channel" and "uploader" — sometimes they differ
        channel = g("channel") or g("uploader")
        channel_id = g("channel_id")
        channel_url = g("channel_url") or g("uploader_url")
        uploader = g("uploader")
        uploader_id = g("uploader_id")
        uploader_url = g("uploader_url")
        subscriber_count = g("channel_follower_count")

        # ── Statistics ────────────────────────────────────────────────────────
        view_count = g("view_count")
        like_count = g("like_count")
        comment_count = g("comment_count")
        average_rating = g("average_rating")

        # ── Classification ────────────────────────────────────────────────────
        tags = g("tags") or []
        categories = g("categories") or []

        # ── Description ───────────────────────────────────────────────────────
        description = g("description") or ""

        # ── Thumbnail ─────────────────────────────────────────────────────────
        thumbnails = g("thumbnails") or []
        # Best thumbnail is typically the last one (highest resolution)
        best_thumbnail = thumbnails[-1].get("url") if thumbnails else g("thumbnail")

        # ── Format analysis ───────────────────────────────────────────────────
        formats = g("formats") or []
        format_summary = self._analyze_formats(formats)

        # ── Subtitles ─────────────────────────────────────────────────────────
        manual_subs = g("subtitles") or {}
        auto_subs = g("automatic_captions") or {}
        subtitle_summary = self._analyze_subtitles(manual_subs, auto_subs)

        # ── Chapters ─────────────────────────────────────────────────────────
        chapters = g("chapters") or []

        # ── Availability / live status ────────────────────────────────────────
        availability = g("availability")        # "public", "private", "unlisted", etc.
        live_status = g("live_status")          # "not_live", "is_live", "was_live", etc.
        release_timestamp = g("release_timestamp")

        # ── Heatmap (popularity over time) ────────────────────────────────────
        heatmap = g("heatmap") or []

        # ── Shorts detection ──────────────────────────────────────────────────
        is_short = is_youtube_short(webpage_url, duration_secs)
        if is_short:
            content_type = "short"
        elif live_status in ("is_live", "post_live"):
            content_type = "live"
        elif live_status == "was_live":
            content_type = "premiere"
        else:
            content_type = "video"

        # ── Comments (only present when get_comments=True was passed) ─────────
        raw_comments = g("comments") or []

        return {
            # Identification
            "id": video_id,
            "title": title,
            "url": url,
            "webpage_url": webpage_url,
            "upload_date": upload_date_raw,
            "upload_date_formatted": format_date(upload_date_raw),
            "release_timestamp": release_timestamp,

            # Duration
            "duration": duration_secs,
            "duration_string": seconds_to_hms(duration_secs),
            "duration_formatted": format_duration(duration_secs),

            # Description
            "description": description,
            "description_short": truncate(description, 300),

            # Language / content
            "language": g("language"),
            "age_limit": g("age_limit", default=0),

            # Channel metadata
            "channel": channel,
            "channel_id": channel_id,
            "channel_url": channel_url,
            "uploader": uploader,
            "uploader_id": uploader_id,
            "uploader_url": uploader_url,
            "channel_follower_count": subscriber_count,
            "channel_follower_count_formatted": format_number(subscriber_count),

            # Statistics
            "view_count": view_count,
            "view_count_formatted": format_number(view_count),
            "like_count": like_count,
            "like_count_formatted": format_number(like_count),
            "comment_count": comment_count,
            "comment_count_formatted": format_number(comment_count),
            "average_rating": average_rating,

            # Classification
            "tags": tags,
            "tags_string": flatten_list(tags),
            "categories": categories,
            "categories_string": flatten_list(categories),

            # Thumbnail
            "thumbnail": best_thumbnail,
            "thumbnails_all": thumbnails,

            # Formats
            "formats_summary": format_summary,

            # Subtitles
            "subtitles_summary": subtitle_summary,
            "subtitles_manual": list(manual_subs.keys()),   # List of language codes
            "subtitles_auto": list(auto_subs.keys()),

            # Content structure
            "chapters": chapters,
            "has_chapters": len(chapters) > 0,
            "chapter_count": len(chapters),
            "heatmap": heatmap,

            # Availability
            "availability": availability,
            "live_status": live_status,

            # Content type classification
            "is_short": is_short,
            "content_type": content_type,   # "video" | "short" | "live" | "premiere"

            # Comments (populated only when --comments flag is used)
            "comments": self._shape_comments(raw_comments, comments_max),
            "comments_fetched": len(raw_comments),

            # Extractor metadata
            "_extractor": "VideoExtractor",
            "_source_url": url,
        }

    def _shape_comments(self, comments: list, max_comments: int = 500) -> list[dict]:
        """
        Shape raw yt-dlp comment objects into clean, consistent dicts.

        yt-dlp returns comments as a flat list. Top-level comments have
        parent="root"; replies have parent set to the parent comment's ID.

        We cap at max_comments to avoid excessively large JSON outputs.
        """
        shaped = []
        for c in comments[:max_comments]:
            shaped.append({
                "id":                  c.get("id"),
                "text":                c.get("text"),
                "author":              c.get("author"),
                "author_id":           c.get("author_id"),
                "timestamp":           c.get("timestamp"),
                "like_count":          c.get("like_count"),
                "is_favorited":        c.get("is_favorited", False),
                "author_is_uploader":  c.get("author_is_uploader", False),
                "parent":              c.get("parent", "root"),
            })
        return shaped

    def _analyze_formats(self, formats: list) -> dict:
        """
        Summarize available formats into a useful structure.

        yt-dlp returns a list of format dicts. Each one represents a specific
        combination of resolution, codec, container, and bitrate available for download.
        Detailed stream lists are only built when explicitly requested.
        """
        video_formats = []
        audio_formats = []
        combined_formats = []
        video_only_count = 0
        audio_only_count = 0
        combined_count = 0
        best_video = None
        best_height = -1
        best_fps = -1
        best_codec = -1
        best_tbr = -1
        best_hdr = -1
        available_extensions = set()

        for fmt in formats:
            has_video = fmt.get("vcodec", "none") not in ("none", None)
            has_audio = fmt.get("acodec", "none") not in ("none", None)
            ext = fmt.get("ext")
            if ext:
                available_extensions.add(ext)

            if has_video and has_audio:
                combined_count += 1
            elif has_video:
                video_only_count += 1
            elif has_audio:
                audio_only_count += 1

            entry = None
            if self.include_detailed_formats:
                entry = self._format_entry(fmt)
                if has_video and has_audio:
                    combined_formats.append(entry)
                elif has_video:
                    video_formats.append(entry)
                elif has_audio:
                    audio_formats.append(entry)

            if has_video:
                height = fmt.get("height")
                if height is None:
                    resolution = fmt.get("resolution")
                    if resolution and "x" in str(resolution):
                        height = str(resolution).rsplit("x", 1)[-1]
                try:
                    height = int(height) if height is not None else -1
                except (TypeError, ValueError):
                    height = -1
                fps = fmt.get("fps") or -1
                try:
                    fps = int(fps)
                except (TypeError, ValueError):
                    fps = -1
                tbr = fmt.get("tbr") or -1
                try:
                    tbr = float(tbr)
                except (TypeError, ValueError):
                    tbr = -1
                vcodec = (fmt.get("vcodec") or "").lower()
                if vcodec.startswith("av01"):
                    codec_score = 3
                elif vcodec.startswith(("vp9", "vp09")):
                    codec_score = 2
                elif vcodec.startswith(("avc1", "h264")):
                    codec_score = 1
                else:
                    codec_score = 0
                dynamic_range = (fmt.get("dynamic_range") or "").upper()
                hdr_score = 1 if dynamic_range in ("HDR10", "HDR10+", "HLG", "DOLBY_VISION") else 0
                if (height, fps, codec_score, tbr, hdr_score) > (best_height, best_fps, best_codec, best_tbr, best_hdr):
                    best_height = height
                    best_fps = fps
                    best_codec = codec_score
                    best_tbr = tbr
                    best_hdr = hdr_score
                    best_video = entry or self._format_entry(fmt)

        summary = {
            "total_formats": len(formats),
            "video_only_count": video_only_count,
            "audio_only_count": audio_only_count,
            "combined_count": combined_count,
            "best_video_format": best_video,
            "available_extensions": sorted(available_extensions),
        }
        if self.include_detailed_formats:
            summary.update({
                "video_formats": video_formats,
                "audio_formats": audio_formats,
                "combined_formats": combined_formats,
            })
        return summary

    def _format_entry(self, fmt: dict) -> dict:
        """Return the normalized subset of fields exposed for one stream."""
        return {
            "format_id": fmt.get("format_id"),
            "ext": fmt.get("ext"),
            "resolution": fmt.get("resolution") or self._build_resolution(fmt),
            "fps": fmt.get("fps"),
            "vcodec": fmt.get("vcodec"),
            "acodec": fmt.get("acodec"),
            "abr": fmt.get("abr"),
            "vbr": fmt.get("vbr"),
            "tbr": fmt.get("tbr"),
            "filesize": fmt.get("filesize"),
            "filesize_approx": fmt.get("filesize_approx"),
            "filesize_formatted": format_filesize(
                fmt.get("filesize") or fmt.get("filesize_approx")
            ),
            "protocol": fmt.get("protocol"),
            "format_note": fmt.get("format_note"),
        }

    def _analyze_subtitles(self, manual: dict, auto: dict) -> dict:
        """Summarize subtitle availability."""
        manual_langs = sorted(manual.keys())
        auto_langs = sorted(auto.keys())
        all_langs = sorted(set(manual_langs + auto_langs))

        return {
            "has_manual_subtitles": len(manual_langs) > 0,
            "has_auto_captions": len(auto_langs) > 0,
            "manual_languages": manual_langs,
            "auto_caption_languages": auto_langs,
            "all_available_languages": all_langs,
            "total_languages": len(all_langs),
        }

    @staticmethod
    def _build_resolution(fmt: dict) -> str | None:
        """Build a WIDTHxHEIGHT string from width/height fields if resolution is absent."""
        w = fmt.get("width")
        h = fmt.get("height")
        if w and h:
            return f"{w}x{h}"
        return None
