"""
pipeline_extractor.py
---------------------
Orchestrates a multi-step search → filter → full-extract pipeline.

WORKFLOW:
  1. Search YouTube for a query (fast, extract_flat=True — one request)
  2. Filter by basic criteria available from flat mode:
       - duration range (min/max seconds)
       - minimum view count
       - maximum age (days since upload)
  3. Take the top N results after filtering and fetch full metadata (VideoExtractor)
  4. Optionally download subtitles and parse them to plain text (TranscriptParser)

PURPOSE:
  The prompt-driven workflow: "find beginner videos about X, skip anything
  over 15 minutes or under 1K views, extract full metadata and transcripts
  for the top 3."

  Without this, that workflow requires three separate CLI commands:
    1. --search to get candidates
    2. --url for each chosen video's full metadata
    3. --subtitles + transcript parsing per video

  PipelineExtractor chains all of that into one call.
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from config import DEFAULT_OUTPUT_DIR, MAX_WORKERS
from utils.logger import get_logger
from utils.error_handler import ScraperError, format_error_for_report

from extractor.search_extractor import SearchExtractor
from extractor.video_extractor import VideoExtractor
from extractor.subtitle_extractor import SubtitleExtractor

logger = get_logger(__name__)


class PipelineExtractor:
    """
    Chains search → filter → full metadata extraction into a single call.

    Usage:
        pipeline = PipelineExtractor(
            search_limit=20,
            top_n=3,
            min_duration=60,
            max_duration=900,
            min_views=1000,
            extract_transcript=True,
        )
        result = pipeline.run("python tutorial for beginners")
    """

    def __init__(
        self,
        search_limit: int = 20,
        top_n: int = 3,
        min_duration: int | None = None,
        max_duration: int | None = None,
        min_views: int | None = None,
        max_age_days: int | None = None,
        extract_transcript: bool = False,
        subtitle_lang: str = "en",
        output_dir: Path | str = DEFAULT_OUTPUT_DIR,
        workers: int = MAX_WORKERS,
        verbose: bool = False,
        get_comments: bool = False,
        comments_max: int = 500,
        include_detailed_formats: bool = False,
    ):
        """
        Args:
            search_limit:       How many results to fetch from YouTube search
            top_n:              How many to fully extract after filtering
            min_duration:       Minimum video duration in seconds
            max_duration:       Maximum video duration in seconds
            min_views:          Minimum view count
            max_age_days:       Only include videos uploaded within this many days
            extract_transcript: Download and parse subtitles to plain text
            subtitle_lang:      Language code for transcript extraction (default: "en")
            output_dir:         Where to save subtitle files when extracting transcripts
            workers:            Max concurrent yt-dlp requests (caps pipeline concurrency)
            verbose:            Enable verbose yt-dlp output
            get_comments:       Fetch comments for each video during full extraction
            comments_max:       Cap on number of comments to keep per video
            include_detailed_formats: Include per-format stream details in metadata
        """
        self.search_limit     = search_limit
        self.top_n            = top_n
        self.min_duration     = min_duration
        self.max_duration     = max_duration
        self.min_views        = min_views
        self.max_age_days     = max_age_days
        self.extract_transcript = extract_transcript
        self.subtitle_lang    = subtitle_lang
        self.output_dir       = Path(output_dir)
        self.workers          = workers
        self.verbose          = verbose
        self.get_comments     = get_comments
        self.comments_max     = comments_max
        self.include_detailed_formats = include_detailed_formats
        self._searcher        = SearchExtractor(max_results=search_limit, verbose=verbose)

    def run(self, query: str) -> dict:
        """
        Execute the full pipeline for a single search query.

        Returns:
            {
                "query":                str,
                "filters_applied":      dict,
                "initial_result_count": int,
                "after_filter_count":   int,
                "videos":               list[dict],  # Full metadata, optionally with "transcript"
                "_extractor":           "PipelineExtractor",
            }
        """
        logger.info(f"Running pipeline for: {query!r}")

        # Step 1: Search (fast, flat mode)
        search_result = self._searcher.search(query)
        candidates = search_result["results"]
        initial_count = len(candidates)

        # Step 2: Filter by basic criteria
        filtered = self._apply_filters(candidates)
        logger.info(
            f"Filter: {initial_count} -> {len(filtered)} results for {query!r}"
        )

        # Step 3: Full metadata for top N — fetched concurrently (independent requests)
        top = filtered[: self.top_n]
        videos: list[dict | None] = [None] * len(top)
        extractor = VideoExtractor(
            verbose=self.verbose,
            include_detailed_formats=self.include_detailed_formats,
        )

        def _fetch(index_candidate: tuple[int, dict]) -> tuple[int, dict]:
            i, candidate = index_candidate
            url = candidate.get("url")
            if not url:
                return i, None
            try:
                metadata = extractor.extract(url, get_comments=self.get_comments)
            except ScraperError as e:
                logger.warning(f"Skipping {url}: {e.user_message}")
                error_entry = format_error_for_report(e)
                error_entry["url"] = url
                return i, error_entry

            # Cap comments list if fetched
            if self.get_comments and metadata.get("comments"):
                metadata["comments"] = metadata["comments"][: self.comments_max]
                metadata["comments_fetched"] = len(metadata["comments"])

            # Step 4: Optionally extract transcript
            metadata["transcript"] = (
                self._extract_transcript(url, metadata)
                if self.extract_transcript
                else None
            )
            return i, metadata

        with ThreadPoolExecutor(max_workers=min(max(len(top), 1), self.workers)) as executor:
            futures = {
                executor.submit(_fetch, (i, c)): i for i, c in enumerate(top)
            }
            for future in as_completed(futures):
                i, result = future.result()
                if result is not None:
                    videos[i] = result

        videos = [v for v in videos if v is not None]

        return {
            "query":                query,
            "filters_applied":      self._describe_filters(),
            "initial_result_count": initial_count,
            "after_filter_count":   len(filtered),
            "videos":               videos,
            "_extractor":           "PipelineExtractor",
        }

    # ── Filtering ─────────────────────────────────────────────────────────────

    def _apply_filters(self, results: list[dict]) -> list[dict]:
        """Filter a flat search result list by the configured criteria."""
        today = datetime.now(tz=timezone.utc)
        filtered = []

        for r in results:
            duration    = r.get("duration")
            view_count  = r.get("view_count")
            upload_date = r.get("upload_date")  # "YYYYMMDD" string

            if self.min_duration is not None:
                if duration is None or duration < self.min_duration:
                    continue
            if self.max_duration is not None:
                if duration is None or duration > self.max_duration:
                    continue
            if self.min_views is not None:
                if view_count is None or view_count < self.min_views:
                    continue
            if self.max_age_days is not None:
                if not upload_date:
                    continue  # No date — can't verify age, exclude (fail-closed)
                try:
                    uploaded = datetime.strptime(str(upload_date), "%Y%m%d").replace(
                        tzinfo=timezone.utc
                    )
                    if (today - uploaded).days > self.max_age_days:
                        continue
                except (ValueError, TypeError):
                    continue  # Unparseable date — exclude (fail-closed)

            filtered.append(r)

        return filtered

    def _describe_filters(self) -> dict:
        """Return a summary of active filters (None values are inactive)."""
        return {
            "min_duration_secs": self.min_duration,
            "max_duration_secs": self.max_duration,
            "min_views":         self.min_views,
            "max_age_days":      self.max_age_days,
        }

    # ── Transcript extraction ─────────────────────────────────────────────────

    def _extract_transcript(self, url: str, metadata: dict) -> str | None:
        """
        Download subtitles for a video and parse them to plain text.

        Tries the requested language first. Falls back gracefully if
        no subtitles are available for that language.
        Returns None if the video has no subtitles at all.
        """
        from utils.transcript_parser import parse_subtitle_file

        sub_info = metadata.get("subtitles_summary", {})
        has_manual = sub_info.get("has_manual_subtitles", False)
        has_auto   = sub_info.get("has_auto_captions", False)

        if not has_manual and not has_auto:
            logger.debug(f"No subtitles available for {url}")
            return None

        sub_dir = self.output_dir / "subtitles"
        sub_extractor = SubtitleExtractor(
            download=True,
            langs=[self.subtitle_lang],
            subtitle_format="vtt",   # VTT parses more cleanly than SRT
            include_auto=True,
            output_dir=sub_dir,
            verbose=self.verbose,
        )

        try:
            sub_result = sub_extractor.extract(url)
        except ScraperError as e:
            logger.warning(f"Subtitle download failed for {url}: {e.user_message}")
            return None

        downloaded = sub_result.get("downloaded_files", [])
        if not downloaded:
            return None

        text = parse_subtitle_file(downloaded[0])
        return text if text else None
