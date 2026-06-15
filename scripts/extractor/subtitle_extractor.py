"""
subtitle_extractor.py
---------------------
Handles subtitle and caption availability checking and optional downloading.

TWO OPERATIONS:
  1. Check availability (no download):
     - Returns which languages have manual subtitles and auto-captions
     - Fast, no files written

  2. Download subtitles (explicit --subtitles flag required):
     - Downloads .srt/.vtt files to the output directory
     - Supports language selection
     - Includes both manual and auto-generated captions

WHY SEPARATE FROM VideoExtractor?
  VideoExtractor already includes subtitle METADATA (which languages exist).
  This module handles the DOWNLOAD case and provides more detailed subtitle
  info when the user specifically asks for subtitles.
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path
import yt_dlp

from config import BASE_YDL_OPTS, SUBTITLE_YDL_OPTS, DEFAULT_OUTPUT_DIR
from utils.logger import get_logger, YtDlpLogger
from utils.helpers import safe_get
from utils.error_handler import classify_ytdlp_error, SubtitleError

logger = get_logger(__name__)


class SubtitleExtractor:
    """
    Checks subtitle availability and optionally downloads subtitle files.

    Usage (check only):
        extractor = SubtitleExtractor()
        info = extractor.get_subtitle_info("https://youtube.com/watch?v=...")

    Usage (download):
        extractor = SubtitleExtractor(download=True, langs=["en", "es"])
        result = extractor.extract("https://youtube.com/watch?v=...")
    """

    def __init__(
        self,
        download: bool = False,
        langs: list[str] | None = None,
        subtitle_format: str = "srt",
        include_auto: bool = True,
        output_dir: Path | str = DEFAULT_OUTPUT_DIR,
        verbose: bool = False,
    ):
        """
        Args:
            download:       Whether to actually download subtitle files
            langs:          List of language codes to request (e.g. ["en", "fr"])
                            None means "all available"
            subtitle_format: File format — "srt", "vtt", or "ass"
            include_auto:   Whether to include auto-generated captions
            output_dir:     Where to save downloaded subtitle files
        """
        self.download = download
        self.langs = langs or ["en"]  # Default to English
        self.subtitle_format = subtitle_format
        self.include_auto = include_auto
        self.output_dir = Path(output_dir)
        self.verbose = verbose
        self._ydl_logger = YtDlpLogger(get_logger("yt_dlp", verbose=verbose))

    def get_subtitle_info(self, url: str) -> dict:
        """
        Get subtitle availability information WITHOUT downloading any files.

        This is a lightweight check — it fetches video metadata and examines
        the subtitle fields without writing anything to disk.

        Returns a dict describing available subtitles.
        """
        logger.info(f"Checking subtitle availability for: {url}")

        opts = {
            **BASE_YDL_OPTS,
            "logger": self._ydl_logger,
            "listsubtitles": False,  # Don't print subtitle list to stdout
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                raw = ydl.extract_info(url, download=False)
                if raw is None:
                    raise ValueError("No data returned")
                sanitized = ydl.sanitize_info(raw)
        except Exception as e:
            raise classify_ytdlp_error(e, url=url) from e

        return self._shape_subtitle_info(sanitized, url)

    def extract(self, url: str) -> dict:
        """
        Main entry point. Returns subtitle info and optionally downloads files.

        If self.download is True, subtitle files are written to self.output_dir.
        """
        # Always get the info first
        info = self.get_subtitle_info(url)

        if not self.download:
            return info

        # Check if any requested languages are available
        available = (
            set(info["manual_languages"]) | set(info["auto_caption_languages"])
        )
        requested = set(self.langs)
        to_download = requested & available

        if not to_download:
            available_list = sorted(available)
            logger.warning(
                f"None of the requested languages {self.langs} are available. "
                f"Available: {available_list}"
            )
            info["download_attempted"] = False
            info["download_note"] = (
                f"Requested {self.langs}, available: {available_list}"
            )
            return info

        logger.info(f"Downloading subtitles: {sorted(to_download)} from {url}")
        downloaded_files = self._download_subtitles(url)

        info["download_attempted"] = True
        info["downloaded_files"] = downloaded_files
        info["output_dir"] = str(self.output_dir)

        return info

    def _download_subtitles(self, url: str) -> list[str]:
        """
        Perform the actual subtitle download using yt-dlp.

        Returns a list of paths to the downloaded subtitle files.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)

        opts = {
            **BASE_YDL_OPTS,
            "logger": self._ydl_logger,
            "skip_download": True,          # Don't download the video
            "writesubtitles": True,         # Write manual subtitles
            "writeautomaticsub": self.include_auto,
            "subtitleslangs": self.langs,
            "subtitlesformat": self.subtitle_format,
            "outtmpl": str(self.output_dir / "%(title)s [%(id)s].%(ext)s"),
        }

        downloaded: list[str] = []

        # Snapshot existing subtitle files so we only return files from this run
        existing = {
            str(p) for p in self.output_dir.iterdir()
            if p.suffix.lstrip(".") in ("srt", "vtt", "ass", "ttml")
        } if self.output_dir.exists() else set()

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

            # Return only files that are new since the snapshot
            for path in self.output_dir.iterdir():
                ext = path.suffix.lstrip(".")
                if ext in ("srt", "vtt", "ass", "ttml") and str(path) not in existing:
                    downloaded.append(str(path))

            # yt-dlp skipped writing (file already exists) — find by video ID in filename
            if not downloaded:
                import re
                vid_match = re.search(
                    r'[?&]v=([A-Za-z0-9_-]{11})|/(?:shorts|embed|v)/([A-Za-z0-9_-]{11})',
                    url,
                )
                if vid_match:
                    video_id = vid_match.group(1) or vid_match.group(2)
                    for path in self.output_dir.iterdir():
                        ext = path.suffix.lstrip(".")
                        if ext in ("srt", "vtt", "ass", "ttml") and f"[{video_id}]" in path.name:
                            downloaded.append(str(path))
                    if downloaded:
                        logger.info(f"Reusing {len(downloaded)} existing subtitle file(s) for {video_id}")

        except Exception as e:
            raise SubtitleError(
                message=f"Failed to download subtitles: {e}",
                url=url,
                original=e,
            ) from e

        logger.info(f"Downloaded {len(downloaded)} subtitle file(s)")
        return downloaded

    def _shape_subtitle_info(self, raw: dict, url: str) -> dict:
        """
        Build a detailed subtitle availability report from raw yt-dlp data.
        """
        manual_subs = raw.get("subtitles") or {}
        auto_subs = raw.get("automatic_captions") or {}

        manual_langs = sorted(manual_subs.keys())
        auto_langs = sorted(auto_subs.keys())
        all_langs = sorted(set(manual_langs + auto_langs))

        # Detect which requested languages are present
        requested_available = [lang for lang in self.langs if lang in all_langs]
        requested_missing = [lang for lang in self.langs if lang not in all_langs]

        # Build per-language format details
        manual_details = {}
        for lang, formats in manual_subs.items():
            if isinstance(formats, list):
                manual_details[lang] = [
                    {"ext": f.get("ext")}
                    for f in formats
                    if isinstance(f, dict)
                ]

        auto_details = {}
        for lang, formats in auto_subs.items():
            if isinstance(formats, list):
                auto_details[lang] = [
                    {"ext": f.get("ext")}
                    for f in formats
                    if isinstance(f, dict)
                ]

        return {
            "url": url,
            "video_id": raw.get("id"),
            "video_title": raw.get("title"),

            # Availability
            "has_manual_subtitles": len(manual_langs) > 0,
            "has_auto_captions": len(auto_langs) > 0,
            "has_any_subtitles": len(all_langs) > 0,

            # Language lists
            "manual_languages": manual_langs,
            "auto_caption_languages": auto_langs,
            "all_available_languages": all_langs,
            "total_language_count": len(all_langs),

            # Requested language analysis
            "requested_languages": self.langs,
            "requested_available": requested_available,
            "requested_missing": requested_missing,

            # Detailed format info per language
            "manual_subtitle_details": manual_details,
            "auto_caption_details": auto_details,

            # Download will be added by extract() if applicable
            "download_attempted": False,
            "downloaded_files": [],
        }
