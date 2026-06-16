#!/usr/bin/env python3
"""
youtube_scraper.py
------------------
Main CLI entry point for the YouTube Scraper.

This is the file you run directly. It parses command-line arguments,
routes to the appropriate extractor, and handles output.

USAGE EXAMPLES:
  # Search YouTube (primary research workflow)
  python youtube_scraper.py --search "claude code tutorial" --search-limit 10

  # Search → get clean URL list (pipe into notebooklm source add)
  python youtube_scraper.py --search "autoresearch" --search-limit 15 --urls-only --output urls.txt

  # Search with filters + full metadata for top results
  python youtube_scraper.py --search "topic" --pipeline --filter-min-views 5000 --pipeline-top 5

  # Single video metadata
  python youtube_scraper.py --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

  # Save as JSON
  python youtube_scraper.py --url "URL" --output results.json

  # Playlist
  python youtube_scraper.py --playlist "https://www.youtube.com/playlist?list=PL..."

  # Batch from file → URLs only
  python youtube_scraper.py --batch urls.txt --urls-only

  # Subtitles (local extraction — NOT for NotebookLM; pass URLs directly instead)
  python youtube_scraper.py --url "URL" --subtitles --subtitle-lang en

  # Download audio (MP3)
  python youtube_scraper.py --url "URL" --download-audio
"""

import sys
import os
import json
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Make sure our packages are on the Python path
# This lets us run the script from any directory
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

# ── Our modules ────────────────────────────────────────────────────────────────
from utils import (
    get_logger,
    is_valid_youtube_url,
    detect_url_type,
    validate_batch_file,
    extract_video_id,
    format_number,
    ScraperError,
    format_error_for_report,
    FailureTracker,
    RYDClient,
    SentimentAnalyzer,
)
from extractor import (
    VideoExtractor, PlaylistExtractor, SubtitleExtractor, Downloader,
    SearchExtractor, PipelineExtractor, ChannelExtractor,
)
from formatter import JsonFormatter, CsvFormatter, MarkdownFormatter
from reports import ReportGenerator
from config import DEFAULT_OUTPUT_DIR, MAX_WORKERS, CACHE_ENABLED, CACHE_TTL_HOURS, CACHE_DIR, RYD_TIMEOUT

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI ARGUMENT PARSER
# ═══════════════════════════════════════════════════════════════════════════════

def _positive_int(value: str) -> int:
    """argparse type: integer >= 1. Used for --workers."""
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--workers must be an integer, got {value!r}")
    if n < 1:
        raise argparse.ArgumentTypeError(f"--workers must be >= 1, got {n}")
    return n


def _add_input_args(parser: argparse.ArgumentParser) -> None:
    """Add input source arguments (mutually exclusive)."""
    input_group = parser.add_argument_group("Input (choose one)")
    source = input_group.add_mutually_exclusive_group(required=True)

    source.add_argument(
        "--url", "-u",
        metavar="URL",
        help="Single YouTube video URL",
    )
    source.add_argument(
        "--playlist", "-p",
        metavar="URL",
        help="YouTube playlist URL",
    )
    source.add_argument(
        "--batch", "-b",
        metavar="FILE",
        help="Path to a text file with one YouTube URL per line",
    )
    source.add_argument(
        "--search",
        metavar="QUERY",
        help='Search YouTube by keyword (e.g. --search "python tutorial")',
    )
    source.add_argument(
        "--search-batch",
        metavar="FILE",
        dest="search_batch",
        help="Path to a text file with one search query per line",
    )
    source.add_argument(
        "--channel", "-c",
        metavar="URL",
        help=(
            "YouTube channel URL (any format: @handle, /channel/ID, /c/Name). "
            "Use --channel-tab to select which tab to fetch."
        ),
    )


def _add_search_pipeline_args(parser: argparse.ArgumentParser) -> None:
    """Add search, pipeline, and filter arguments."""
    search_group = parser.add_argument_group("Search options")
    search_group.add_argument(
        "--search-limit",
        metavar="N",
        dest="search_limit",
        type=int,
        default=10,
        help="Max results to fetch per search query (default: 10)",
    )
    search_group.add_argument(
        "--pipeline",
        action="store_true",
        help=(
            "After searching, fetch full metadata for the top results. "
            "Combines search -> filter -> extract into one command."
        ),
    )
    search_group.add_argument(
        "--pipeline-top",
        metavar="N",
        dest="pipeline_top",
        type=int,
        default=3,
        help="How many results to fully extract after filtering (default: 3)",
    )
    search_group.add_argument(
        "--transcript",
        action="store_true",
        help="Download subtitles and parse them to plain text (requires --pipeline)",
    )

    # ── Filter options (for pipeline and search) ──────────────────────────────
    filter_group = parser.add_argument_group(
        "Filter options",
        "Applied when --pipeline is used to narrow search results before full extraction."
    )
    filter_group.add_argument(
        "--filter-min-duration",
        metavar="SECS",
        dest="filter_min_duration",
        type=int,
        default=None,
        help="Minimum video duration in seconds (e.g. 60 for 1 minute)",
    )
    filter_group.add_argument(
        "--filter-max-duration",
        metavar="SECS",
        dest="filter_max_duration",
        type=int,
        default=None,
        help="Maximum video duration in seconds (e.g. 900 for 15 minutes)",
    )
    filter_group.add_argument(
        "--filter-min-views",
        metavar="N",
        dest="filter_min_views",
        type=int,
        default=None,
        help="Minimum view count (e.g. 1000)",
    )
    filter_group.add_argument(
        "--filter-max-age-days",
        metavar="DAYS",
        dest="filter_max_age_days",
        type=int,
        default=None,
        help="Only include videos uploaded within this many days",
    )


def _add_output_args(parser: argparse.ArgumentParser) -> None:
    """Add output, subtitle, and download arguments."""
    output_group = parser.add_argument_group("Output")
    output_group.add_argument(
        "--output", "-o",
        metavar="PATH",
        help="Save output to this file path (e.g. results.json, report.md)",
    )
    output_group.add_argument(
        "--csv",
        action="store_true",
        help="Export as CSV instead of JSON",
    )
    output_group.add_argument(
        "--report",
        action="store_true",
        help="Generate a Markdown report instead of raw JSON",
    )
    output_group.add_argument(
        "--no-print",
        action="store_true",
        dest="no_print",
        help="Suppress terminal summary output (only save to file)",
    )
    output_group.add_argument(
        "--urls-only",
        action="store_true",
        dest="urls_only",
        help=(
            "Print only the YouTube URLs, one per line. "
            "Ideal for piping into 'notebooklm source add' or a batch file."
        ),
    )
    output_group.add_argument(
        "--detailed-formats",
        action="store_true",
        dest="detailed_formats",
        help=(
            "Include every available video/audio stream in formats_summary. "
            "Disabled by default to keep output and cache entries compact."
        ),
    )

    # ── Subtitle options ──────────────────────────────────────────────────────
    subtitle_group = parser.add_argument_group("Subtitles")
    subtitle_group.add_argument(
        "--subtitles", "-s",
        action="store_true",
        help="Extract subtitle/caption availability info. Use --download-subs to also save files.",
    )
    subtitle_group.add_argument(
        "--download-subs",
        action="store_true",
        dest="download_subs",
        help="Download subtitle files to disk (requires --subtitles)",
    )
    subtitle_group.add_argument(
        "--subtitle-lang",
        metavar="LANG",
        dest="subtitle_lang",
        default="en",
        help='Subtitle language code (default: en). Examples: "en", "es", "fr"',
    )
    subtitle_group.add_argument(
        "--subtitle-format",
        metavar="FMT",
        dest="subtitle_format",
        default="srt",
        choices=["srt", "vtt", "ass"],
        help="Subtitle file format: srt (default), vtt, or ass",
    )

    # ── Download options ──────────────────────────────────────────────────────
    # IMPORTANT: These are intentionally separate from the default workflow.
    download_group = parser.add_argument_group("Downloads (disabled by default)")
    download_group.add_argument(
        "--download-video",
        action="store_true",
        dest="download_video",
        help="Download the video file (default format: MP4)",
    )
    download_group.add_argument(
        "--download-audio",
        action="store_true",
        dest="download_audio",
        help="Download audio only (default format: MP3). Requires ffmpeg.",
    )
    download_group.add_argument(
        "--video-format",
        metavar="FMT",
        dest="video_format",
        default="mp4",
        choices=["mp4", "mkv", "webm"],
        help="Video container format: mp4 (default), mkv, webm",
    )
    download_group.add_argument(
        "--audio-format",
        metavar="FMT",
        dest="audio_format",
        default="mp3",
        choices=["mp3", "m4a", "wav", "flac", "aac"],
        help="Audio format: mp3 (default), m4a, wav, flac, aac",
    )
    download_group.add_argument(
        "--download-dir",
        metavar="DIR",
        dest="download_dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Directory for downloads (default: {DEFAULT_OUTPUT_DIR})",
    )


def _add_collection_args(parser: argparse.ArgumentParser) -> None:
    """Add playlist, batch, channel, and shorts/content-type arguments."""
    # ── Playlist options ──────────────────────────────────────────────────────
    playlist_group = parser.add_argument_group("Playlist options")
    playlist_group.add_argument(
        "--full-playlist",
        action="store_true",
        dest="full_playlist",
        help=(
            "Fetch extended metadata per video via individual requests (slow). "
            "Includes more fields than flat mode, but not the full single-video schema. "
            "Default: flat mode (title/duration/views only)."
        ),
    )
    playlist_group.add_argument(
        "--max-videos",
        metavar="N",
        dest="max_videos",
        type=int,
        default=None,
        help="Maximum number of videos to process from a playlist or batch",
    )

    # ── Batch options ─────────────────────────────────────────────────────────
    batch_group = parser.add_argument_group("Batch options")
    batch_group.add_argument(
        "--workers",
        metavar="N",
        type=_positive_int,
        default=MAX_WORKERS,
        help=f"Concurrent workers for batch processing (default: {MAX_WORKERS}). Use 1 for sequential.",
    )

    # ── Channel options ───────────────────────────────────────────────────────
    channel_group = parser.add_argument_group(
        "Channel options",
        "Use with --channel to select which tab to fetch.",
    )
    channel_group.add_argument(
        "--channel-tab",
        metavar="TAB",
        dest="channel_tab",
        default="videos",
        choices=["videos", "shorts", "streams", "all"],
        help=(
            "Channel tab to scrape: videos (default), shorts, streams, or all. "
            "Use 'all' to merge all three tabs into one result."
        ),
    )

    # ── Shorts / content-type filters ────────────────────────────────────────
    shorts_group = parser.add_argument_group(
        "Content-type filters",
        "Filter search / channel results by content type. Mutually exclusive.",
    )
    shorts_ex = shorts_group.add_mutually_exclusive_group()
    shorts_ex.add_argument(
        "--shorts-only",
        action="store_true",
        dest="shorts_only",
        help="Only include YouTube Shorts in results (duration ≤ 60s or /shorts/ URL).",
    )
    shorts_ex.add_argument(
        "--no-shorts",
        action="store_true",
        dest="no_shorts",
        help="Exclude YouTube Shorts from results.",
    )


def _add_comments_args(parser: argparse.ArgumentParser) -> None:
    """Add comments arguments."""
    comments_group = parser.add_argument_group("Comments")
    comments_group.add_argument(
        "--comments",
        action="store_true",
        help=(
            "Fetch video comments (single video or batch). "
            "Uses yt-dlp's built-in comment extraction — no API key needed."
        ),
    )
    comments_group.add_argument(
        "--comments-max",
        metavar="N",
        dest="comments_max",
        type=int,
        default=500,
        help="Maximum comments to include in output (default: 500). yt-dlp fetches up to ~1000.",
    )


def _add_cache_failure_args(parser: argparse.ArgumentParser) -> None:
    """Add cache and failure tracking arguments."""
    cache_group = parser.add_argument_group(
        "Cache options",
        "SQLite metadata cache — avoids re-fetching already-seen videos.",
    )
    cache_group.add_argument(
        "--no-cache",
        action="store_true",
        dest="no_cache",
        help="Disable the metadata cache for this run.",
    )
    cache_group.add_argument(
        "--cache-ttl",
        metavar="HOURS",
        dest="cache_ttl",
        type=float,
        default=CACHE_TTL_HOURS,
        help=f"Cache time-to-live in hours (default: {CACHE_TTL_HOURS}). Expired entries are re-fetched.",
    )
    cache_group.add_argument(
        "--cache-dir",
        metavar="DIR",
        dest="cache_dir",
        default=None,
        help="Directory for the SQLite cache file (default: ~/.cache/youtube_scraper/).",
    )
    cache_group.add_argument(
        "--cache-clear",
        action="store_true",
        dest="cache_clear",
        help="Clear all cached entries before running.",
    )

    # ── Failure log ───────────────────────────────────────────────────────────
    fail_group = parser.add_argument_group(
        "Failure tracking",
        "Log failed URLs to a JSONL file for later inspection or retry.",
    )
    fail_group.add_argument(
        "--failure-log",
        metavar="PATH",
        dest="failure_log",
        default=None,
        help=(
            "Path to a JSONL file where failed URLs will be logged. "
            "Each line is a JSON object with url, error_type, failure_class (permanent/transient), and message."
        ),
    )


def _add_engagement_sort_args(parser: argparse.ArgumentParser) -> None:
    """Add engagement, sorting, engagement filters, and global options."""
    # ── Engagement options ────────────────────────────────────────────────────
    engage_group = parser.add_argument_group(
        "Engagement",
        "Fetch dislike estimates and run comment sentiment analysis.",
    )
    engage_group.add_argument(
        "--dislikes",
        action="store_true",
        help=(
            "Fetch estimated dislike counts from the Return YouTube Dislike API "
            "(returnyoutubedislikeapi.com). No API key needed. Adds dislike_count, "
            "dislike_count_formatted, and rating_ryd fields."
        ),
    )
    engage_group.add_argument(
        "--sentiment",
        action="store_true",
        help=(
            "Run VADER sentiment analysis on fetched comments. Requires --comments. "
            "Adds sentiment_summary with positive_pct, negative_pct, neutral_pct, compound_avg."
        ),
    )

    # ── Sorting ───────────────────────────────────────────────────────────────
    sort_group = parser.add_argument_group(
        "Sorting",
        "Sort results from search, channel, or batch by any engagement field.",
    )
    sort_group.add_argument(
        "--sort-by",
        metavar="FIELD",
        dest="sort_by",
        default=None,
        choices=["views", "likes", "subscribers", "date", "duration",
                 "dislikes", "positive_ratio", "negative_ratio"],
        help=(
            "Sort results by: views, likes, subscribers, date, duration, dislikes "
            "(requires --dislikes), positive_ratio / negative_ratio (requires --sentiment --comments). "
            "Default: no sort (original order)."
        ),
    )
    sort_group.add_argument(
        "--sort-order",
        metavar="ORDER",
        dest="sort_order",
        default="desc",
        choices=["asc", "desc"],
        help="Sort direction: desc (default, highest first) or asc (lowest first).",
    )

    # ── Engagement filters ────────────────────────────────────────────────────
    eng_filter_group = parser.add_argument_group(
        "Engagement filters",
        "Filter results by engagement metrics. Applied after fetching.",
    )
    eng_filter_group.add_argument(
        "--filter-min-likes",
        metavar="N",
        dest="filter_min_likes",
        type=int,
        default=None,
        help="Minimum like count.",
    )
    eng_filter_group.add_argument(
        "--filter-max-likes",
        metavar="N",
        dest="filter_max_likes",
        type=int,
        default=None,
        help="Maximum like count.",
    )
    eng_filter_group.add_argument(
        "--filter-max-views",
        metavar="N",
        dest="filter_max_views",
        type=int,
        default=None,
        help="Maximum view count.",
    )
    eng_filter_group.add_argument(
        "--filter-min-subscribers",
        metavar="N",
        dest="filter_min_subscribers",
        type=int,
        default=None,
        help="Minimum channel subscriber count.",
    )
    eng_filter_group.add_argument(
        "--filter-max-subscribers",
        metavar="N",
        dest="filter_max_subscribers",
        type=int,
        default=None,
        help="Maximum channel subscriber count.",
    )
    eng_filter_group.add_argument(
        "--filter-min-dislikes",
        metavar="N",
        dest="filter_min_dislikes",
        type=int,
        default=None,
        help="Minimum dislike count (requires --dislikes).",
    )
    eng_filter_group.add_argument(
        "--filter-max-dislikes",
        metavar="N",
        dest="filter_max_dislikes",
        type=int,
        default=None,
        help="Maximum dislike count (requires --dislikes).",
    )
    eng_filter_group.add_argument(
        "--filter-min-positive-ratio",
        metavar="RATIO",
        dest="filter_min_positive_ratio",
        type=float,
        default=None,
        help=(
            "Minimum fraction of positive comments (0.0–1.0). "
            "Requires --comments and --sentiment."
        ),
    )
    eng_filter_group.add_argument(
        "--filter-min-negative-ratio",
        metavar="RATIO",
        dest="filter_min_negative_ratio",
        type=float,
        default=None,
        help=(
            "Minimum fraction of negative comments (0.0–1.0). "
            "Requires --comments and --sentiment."
        ),
    )

    # ── Global options ────────────────────────────────────────────────────────
    global_group = parser.add_argument_group("Global options")
    global_group.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug output",
    )


def build_parser() -> argparse.ArgumentParser:
    """
    Build and return the CLI argument parser.

    Each _add_*_args() function owns one logical section.
    Edit argument definitions there, not here.
    """
    parser = argparse.ArgumentParser(
        prog="youtube_scraper",
        description=(
            "YouTube Scraper — extract rich metadata, reports, and optional downloads "
            "from YouTube videos, playlists, and batch URL files.\n\n"
            "Default behavior: metadata extraction only (no downloads)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Single video:     python youtube_scraper.py --url "URL"
  Save JSON:        python youtube_scraper.py --url "URL" --output out.json
  Playlist:         python youtube_scraper.py --playlist "URL"
  Batch:            python youtube_scraper.py --batch urls.txt
  Subtitles:        python youtube_scraper.py --url "URL" --subtitles
  Download audio:   python youtube_scraper.py --url "URL" --download-audio
  Download video:   python youtube_scraper.py --url "URL" --download-video
  Full report:      python youtube_scraper.py --url "URL" --report --output report.md
        """,
    )
    _add_input_args(parser)
    _add_search_pipeline_args(parser)
    _add_output_args(parser)
    _add_collection_args(parser)
    _add_comments_args(parser)
    _add_cache_failure_args(parser)
    _add_engagement_sort_args(parser)
    return parser


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTE HANDLERS
# Each function handles one mode (video/playlist/batch/subtitle/download).
# They all return a dict or list that gets passed to the output handler.
# ═══════════════════════════════════════════════════════════════════════════════

def _make_cache(args: argparse.Namespace):
    """Build a CacheManager from CLI args, or return None if caching is disabled."""
    if getattr(args, "no_cache", False) or not CACHE_ENABLED:
        return None
    from cache import CacheManager
    ttl_secs = int(getattr(args, "cache_ttl", CACHE_TTL_HOURS) * 3600)
    return CacheManager(cache_dir=getattr(args, "cache_dir", None) or CACHE_DIR, ttl=ttl_secs)


def _make_failure_tracker(args: argparse.Namespace):
    """Build a FailureTracker if --failure-log was given, else return None."""
    path = getattr(args, "failure_log", None)
    return FailureTracker(path) if path else None


def _compact_format_summary(data: dict) -> dict:
    """Remove legacy detailed stream lists from a cached compact result."""
    summary = data.get("formats_summary")
    if isinstance(summary, dict):
        summary.pop("video_formats", None)
        summary.pop("audio_formats", None)
        summary.pop("combined_formats", None)
    return data


def handle_video(args: argparse.Namespace) -> dict:
    """Handle single video metadata extraction (with cache + optional comments)."""
    url = args.url

    if detect_url_type(url) != "video":
        logger.error(f"--url requires a single video URL (got: {url})")
        sys.exit(1)

    get_comments = getattr(args, "comments", False)

    # Cache: only skip cache when comments are requested (comments won't be cached from a prior run)
    detailed_formats = getattr(args, "detailed_formats", False)
    cache = None if get_comments or detailed_formats else _make_cache(args)
    if cache:
        video_id = extract_video_id(url)
        if video_id:
            cached = cache.get(video_id)
            if cached:
                _compact_format_summary(cached)
                logger.info(f"Cache hit for {video_id} — skipping network fetch")
                if getattr(args, "dislikes", False):
                    cached = _enrich_dislikes_single(cached)
                if getattr(args, "sentiment", False):
                    cached = _enrich_sentiment_single(cached)
                return cached

    extractor = VideoExtractor(
        verbose=args.verbose,
        include_detailed_formats=detailed_formats,
    )
    result = extractor.extract(url, get_comments=get_comments)

    # Apply comments_max cap
    if get_comments and result.get("comments"):
        max_c = getattr(args, "comments_max", 500)
        result["comments"] = result["comments"][:max_c]
        result["comments_fetched"] = len(result["comments"])

    # Store in cache (only when not fetching comments, to keep cache entries lean)
    if cache and not get_comments and result.get("id"):
        cache.put(result["id"], url, result)

    # Optional: fetch dislike estimates from Return YouTube Dislike API
    if getattr(args, "dislikes", False):
        result = _enrich_dislikes_single(result)

    # Optional: run VADER sentiment on fetched comments
    if getattr(args, "sentiment", False):
        result = _enrich_sentiment_single(result)

    return result


def _post_process_items(
    items: list[dict],
    args: argparse.Namespace,
    *,
    apply_shorts: bool = True,
    fetch_comments: bool = False,
    shorts_first: bool = True,
) -> list[dict]:
    """
    Shared post-processing pipeline for all list-producing handlers.

    Step order (all options, shorts_first=True):
      1. Shorts filter
      2. Full metadata + comments fetch
      3. Dislike enrichment (RYD API)
      4. Comment sentiment (VADER)
      5. Engagement filters
      6. Sort

    Parameters:
        apply_shorts:    Apply --no-shorts / --shorts-only. False for handle_pipeline
                         (pipeline already filters internally).
        fetch_comments:  Upgrade stubs to full metadata when --comments is set.
                         False for pipeline/batch (already full metadata).
        shorts_first:    True = shorts filter before enrichment (default).
                         False = shorts filter after enrichment (batch modes).
    """
    if apply_shorts and shorts_first:
        items = _apply_shorts_filter(items, args)
    if fetch_comments and getattr(args, "comments", False):
        logger.info(f"Fetching full metadata + comments for {len(items)} items...")
        items = _fetch_full_metadata(items, args)
    if getattr(args, "dislikes", False):
        items = _enrich_dislikes(items, workers=args.workers)
    if getattr(args, "sentiment", False):
        analyzer = SentimentAnalyzer()
        for item in items:
            if item.get("comments"):
                summary = analyzer.analyze(item["comments"])
                if summary:
                    item["sentiment_summary"] = summary
    if apply_shorts and not shorts_first:
        items = _apply_shorts_filter(items, args)
    items = _apply_engagement_filters(items, args)
    items = _apply_sort(items, args)
    return items


def handle_playlist(args: argparse.Namespace) -> dict:
    """Handle playlist extraction."""
    url = args.playlist

    extractor = PlaylistExtractor(
        full_details=args.full_playlist,
        max_videos=args.max_videos,
        verbose=args.verbose,
    )
    result = extractor.extract(url)

    if result.get("videos"):
        result["videos"] = _post_process_items(
            result["videos"], args, apply_shorts=True, fetch_comments=True
        )
        result["total_videos"] = len(result["videos"])

    return result


def handle_batch(args: argparse.Namespace) -> list[dict]:
    """
    Handle batch processing of multiple URLs from a file.

    URLs are processed concurrently (up to --workers at a time).
    Cache hits skip the network; failures are logged to --failure-log.
    """
    is_valid, message, urls = validate_batch_file(args.batch)

    if not is_valid:
        logger.error(message)
        sys.exit(1)

    logger.info(message)

    # Pre-filter: drop non-video URLs before dedup/limit so they don't consume slots
    _all_urls = urls
    urls = [u for u in _all_urls if detect_url_type(u) == "video"]
    _skipped = len(_all_urls) - len(urls)
    if _skipped:
        logger.warning(f"Skipped {_skipped} non-video URL(s) in batch (playlists/channels not supported)")
    if not urls:
        logger.error("No video URLs remain after filtering batch input.")
        sys.exit(1)

    # Deduplicate by video ID, preserving order
    seen_ids: set[str] = set()
    deduped: list[str] = []
    for u in urls:
        vid_id = extract_video_id(u)
        key = vid_id if vid_id else u
        if key not in seen_ids:
            seen_ids.add(key)
            deduped.append(u)
    if len(deduped) < len(urls):
        logger.info(f"Removed {len(urls) - len(deduped)} duplicate URL(s)")
    urls = deduped

    if args.max_videos:
        urls = urls[:args.max_videos]
        logger.info(f"Limited to {args.max_videos} URLs")

    results: list[dict] = [None] * len(urls)

    cache = _make_cache(args)
    tracker = _make_failure_tracker(args)
    get_comments = getattr(args, "comments", False)
    detailed_formats = getattr(args, "detailed_formats", False)
    _verbose = args.verbose

    def process_url(index_url: tuple[int, str]) -> tuple[int, dict]:
        i, url = index_url
        if detect_url_type(url) != "video":
            logger.warning(f"[{i+1}/{len(urls)}] Skipping non-video URL: {url}")
            return i, {"error": True, "error_type": "InvalidURLError", "message": "Batch mode only supports video URLs.", "url": url}
        logger.info(f"[{i+1}/{len(urls)}] Processing: {url}")
        extractor = VideoExtractor(
            verbose=_verbose,
            include_detailed_formats=detailed_formats,
        )

        # Check cache (skip when fetching comments)
        if cache and not get_comments and not detailed_formats:
            video_id = extract_video_id(url)
            if video_id:
                cached = cache.get(video_id)
                if cached:
                    _compact_format_summary(cached)
                    logger.info(f"Cache hit: {video_id}")
                    return i, cached

        try:
            data = extractor.extract(url, get_comments=get_comments)
            # Store in cache
            if cache and not get_comments and not detailed_formats and data.get("id"):
                cache.put(data["id"], url, data)
            return i, data
        except ScraperError as e:
            if tracker:
                tracker.record(e, url=url)
            logger.warning(f"Failed: {url} — {e.user_message}")
            return i, format_error_for_report(e)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(process_url, (i, url)): i
            for i, url in enumerate(urls)
        }

        try:
            from tqdm import tqdm
            pbar = tqdm(total=len(urls), desc="Scraping", unit="video")
        except ImportError:
            pbar = None

        for future in as_completed(futures):
            i, result = future.result()
            results[i] = result
            if pbar:
                pbar.update(1)

        if pbar:
            pbar.close()

    if tracker and tracker.has_failures:
        s = tracker.summary()
        logger.warning(
            f"Failures: {s['total_failures']} total "
            f"({s['permanent']} permanent, {s['transient']} transient). "
            f"See: {s['log_path']}"
        )

    items = [r for r in results if r is not None]

    # Post-processing: enrich, filter, sort
    items = _post_process_items(
        items, args, apply_shorts=True, fetch_comments=False, shorts_first=False
    )

    return items


def handle_subtitles(args: argparse.Namespace) -> dict:
    """Handle subtitle extraction (and optional download)."""
    url = args.url

    if not url or detect_url_type(url) != "video":
        logger.error("--subtitles requires a single video URL (not a playlist or channel)")
        sys.exit(1)

    extractor = SubtitleExtractor(
        download=args.download_subs,
        langs=[args.subtitle_lang],
        subtitle_format=args.subtitle_format,
        output_dir=args.download_dir,
        verbose=args.verbose,
    )
    return extractor.extract(url)


def handle_download(args: argparse.Namespace) -> dict:
    """Handle file downloads (video or audio)."""
    url = args.url

    if not url or detect_url_type(url) != "video":
        logger.error("--download-video/--download-audio requires a single video URL (not a playlist or channel)")
        sys.exit(1)

    dl = Downloader(output_dir=args.download_dir, verbose=args.verbose)

    if args.download_video:
        return dl.download_video(url, video_format=args.video_format)
    else:
        return dl.download_audio(url, audio_format=args.audio_format)


def _read_query_file(path: str) -> list[str]:
    """Read one search query per line from a text file, skipping blanks and # comments."""
    try:
        with open(path, encoding="utf-8") as f:
            queries = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    except OSError as e:
        logger.error(f"Cannot read file {path}: {e}")
        sys.exit(1)
    if not queries:
        logger.error(f"No queries found in {path}")
        sys.exit(1)
    return queries


def _build_pipeline(args: argparse.Namespace) -> PipelineExtractor:
    """Construct a PipelineExtractor from CLI args."""
    return PipelineExtractor(
        search_limit=args.search_limit,
        top_n=args.pipeline_top,
        min_duration=args.filter_min_duration,
        max_duration=args.filter_max_duration,
        min_views=args.filter_min_views,
        max_age_days=args.filter_max_age_days,
        extract_transcript=args.transcript,
        subtitle_lang=args.subtitle_lang,
        output_dir=args.download_dir,
        workers=args.workers,
        verbose=args.verbose,
        get_comments=getattr(args, "comments", False),
        comments_max=getattr(args, "comments_max", 500),
        include_detailed_formats=getattr(args, "detailed_formats", False),
    )


def _fetch_full_metadata(stubs: list[dict], args: argparse.Namespace) -> list[dict]:
    """
    Re-fetch full video metadata for a list of search stubs.

    Search results are lightweight stubs — they lack like_count, comments, and
    other per-video data. This function upgrades each stub to a full metadata dict
    by making one VideoExtractor call per item, concurrently.

    Used automatically when --comments is set with --search (without --pipeline).
    Falls back to the original stub if the full fetch fails.
    """
    get_comments = getattr(args, "comments", False)
    max_c = getattr(args, "comments_max", 500)
    _verbose = args.verbose
    detailed_formats = getattr(args, "detailed_formats", False)
    # Use cache only when not fetching comments/formats (those aren't cached in stubs)
    cache = _make_cache(args) if not get_comments and not detailed_formats else None

    def _fetch(index_stub: tuple[int, dict]) -> tuple[int, dict]:
        i, stub = index_stub
        url = stub.get("url") or stub.get("webpage_url")
        if not url:
            return i, stub

        if cache:
            video_id = extract_video_id(url)
            if video_id:
                cached = cache.get(video_id)
                if cached:
                    logger.debug(f"Cache hit (full-meta): {video_id}")
                    return i, cached

        extractor = VideoExtractor(
            verbose=_verbose,
            include_detailed_formats=detailed_formats,
        )
        try:
            data = extractor.extract(url, get_comments=get_comments)
            if get_comments and data.get("comments"):
                data["comments"] = data["comments"][:max_c]
                data["comments_fetched"] = len(data["comments"])
            if cache:
                video_id = extract_video_id(url) or data.get("id")
                if video_id:
                    cache.put(video_id, url, data)
            return i, data
        except ScraperError as e:
            logger.warning(f"Failed full fetch for {url}: {e.user_message}")
            return i, stub  # fall back to original stub

    results = _run_ordered(stubs, workers=args.workers, fn=_fetch)
    return [r for r in results if r is not None]


def _enrich_dislikes(items: list[dict], workers: int = 5) -> list[dict]:
    """
    Add RYD dislike data to each item in a list that has a video 'id'.

    Runs concurrently — one API call per item, up to `workers` in parallel.
    Failures are silent — item is left unchanged.
    """
    client = RYDClient(timeout=RYD_TIMEOUT)

    def _enrich_one(item: dict) -> None:
        vid_id = item.get("id") or item.get("video_id")
        if not vid_id:
            return
        ryd = client.get_dislikes(vid_id)
        if ryd:
            item["dislike_count"]           = ryd["dislikes"]
            item["dislike_count_formatted"] = format_number(ryd["dislikes"])
            item["dislike_count_estimated"] = True
            item["rating_ryd"]              = ryd["rating"]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(_enrich_one, items))

    return items


def _enrich_dislikes_single(result: dict) -> dict:
    """Add RYD dislike data to a single video result dict."""
    vid_id = result.get("id")
    if not vid_id:
        return result
    ryd = RYDClient(timeout=RYD_TIMEOUT).get_dislikes(vid_id)
    if ryd:
        result["dislike_count"]           = ryd["dislikes"]
        result["dislike_count_formatted"] = format_number(ryd["dislikes"])
        result["dislike_count_estimated"] = True
        result["rating_ryd"]              = ryd["rating"]
    return result


def _enrich_sentiment_single(result: dict) -> dict:
    """Run VADER sentiment on a single video's fetched comments."""
    comments = result.get("comments") or []
    if not comments:
        return result
    summary = SentimentAnalyzer().analyze(comments)
    if summary:
        result["sentiment_summary"] = summary
    return result


def _apply_engagement_filters(items: list[dict], args: argparse.Namespace) -> list[dict]:
    """
    Filter a list of video dicts by engagement metrics.

    Each filter is a (arg_name, field_key, comparator) triple.
    Items missing the field are excluded when a threshold is set.
    """
    # Fields that may be missing in search stubs (require --comments or --pipeline
    # to be populated); warn the user so they know results may be silently excluded.
    _STUB_FIELDS = {
        "like_count": ("--filter-min-likes / --filter-max-likes", "--comments or --pipeline"),
        "channel_follower_count": ("--filter-min-subscribers / --filter-max-subscribers", "--pipeline"),
    }
    numeric_filters = [
        ("filter_min_views",        "view_count",             lambda v, t: v >= t),
        ("filter_max_views",        "view_count",             lambda v, t: v <= t),
        ("filter_min_likes",        "like_count",             lambda v, t: v >= t),
        ("filter_max_likes",        "like_count",             lambda v, t: v <= t),
        ("filter_min_subscribers",  "channel_follower_count", lambda v, t: v >= t),
        ("filter_max_subscribers",  "channel_follower_count", lambda v, t: v <= t),
        ("filter_min_dislikes",     "dislike_count",          lambda v, t: v >= t),
        ("filter_max_dislikes",     "dislike_count",          lambda v, t: v <= t),
    ]
    for arg_name, field, test in numeric_filters:
        threshold = getattr(args, arg_name, None)
        if threshold is None:
            continue
        if field in _STUB_FIELDS and items:
            _missing = sum(1 for i in items if i.get(field) is None)
            if _missing:
                flag, hint = _STUB_FIELDS[field]
                logger.warning(
                    f"{flag}: {_missing} item(s) have no '{field}' data "
                    f"(search stubs lack this field — use {hint} to populate it) "
                    "and will be excluded"
                )
        items = [
            item for item in items
            if (val := item.get(field)) is not None and test(val, threshold)
        ]

    min_pos = getattr(args, "filter_min_positive_ratio", None)
    if min_pos is not None:
        _no_sent = sum(1 for i in items if not i.get("sentiment_summary"))
        if _no_sent:
            logger.warning(
                f"--filter-min-positive-ratio: {_no_sent} item(s) have no sentiment data "
                "(no comments fetched?) and will be excluded"
            )
        items = [
            i for i in items
            if (s := i.get("sentiment_summary")) and s.get("positive_pct", 0) >= min_pos
        ]

    min_neg = getattr(args, "filter_min_negative_ratio", None)
    if min_neg is not None:
        _no_sent = sum(1 for i in items if not i.get("sentiment_summary"))
        if _no_sent:
            logger.warning(
                f"--filter-min-negative-ratio: {_no_sent} item(s) have no sentiment data "
                "(no comments fetched?) and will be excluded"
            )
        items = [
            i for i in items
            if (s := i.get("sentiment_summary")) and s.get("negative_pct", 0) >= min_neg
        ]

    return items


def _apply_sort(items: list[dict], args: argparse.Namespace) -> list[dict]:
    """
    Sort a list of video dicts by a field.

    Items where the sort field is None/missing are placed at the end.
    """
    sort_by = getattr(args, "sort_by", None)
    if not sort_by or not items:
        return items

    _GETTERS: dict = {
        "views":           lambda i: i.get("view_count"),
        "likes":           lambda i: i.get("like_count"),
        "subscribers":     lambda i: i.get("channel_follower_count"),
        "date":            lambda i: i.get("upload_date"),
        "duration":        lambda i: i.get("duration"),
        "dislikes":        lambda i: i.get("dislike_count"),
        "positive_ratio":  lambda i: (i.get("sentiment_summary") or {}).get("positive_pct"),
        "negative_ratio":  lambda i: (i.get("sentiment_summary") or {}).get("negative_pct"),
    }

    getter = _GETTERS.get(sort_by)
    if not getter:
        return items

    reverse = getattr(args, "sort_order", "desc") == "desc"

    with_val = [(item, getter(item)) for item in items]
    has_val  = [(item, v) for item, v in with_val if v is not None]
    no_val   = [item for item, v in with_val if v is None]

    try:
        has_val.sort(key=lambda x: x[1], reverse=reverse)
    except TypeError:
        has_val.sort(key=lambda x: str(x[1]), reverse=reverse)

    return [item for item, _ in has_val] + no_val


def _apply_shorts_filter(items: list[dict], args: argparse.Namespace) -> list[dict]:
    """
    Filter a list of video dicts by Shorts status.

    --shorts-only: keep only items where is_short is True
    --no-shorts:   keep only items where is_short is False (or not set)
    """
    if getattr(args, "shorts_only", False):
        return [v for v in items if v.get("is_short")]
    if getattr(args, "no_shorts", False):
        return [v for v in items if not v.get("is_short")]
    return items


def handle_channel(args: argparse.Namespace) -> dict:
    """Handle channel tab extraction."""
    extractor = ChannelExtractor(
        tab=args.channel_tab,
        full_details=args.full_playlist,
        max_videos=args.max_videos,
        verbose=args.verbose,
    )
    result = extractor.extract(args.channel)

    if result.get("videos"):
        result["videos"] = _post_process_items(
            result["videos"], args, apply_shorts=True, fetch_comments=True
        )
        result["total_videos"] = len(result["videos"])

    return result


def handle_search(args: argparse.Namespace) -> dict:
    """Handle YouTube keyword search — returns ranked result list."""
    extractor = SearchExtractor(max_results=args.search_limit, verbose=args.verbose)
    result = extractor.search(args.search)

    if result.get("results"):
        result["results"] = _post_process_items(
            result["results"], args, apply_shorts=True, fetch_comments=True
        )
        result["total_results"] = len(result["results"])

    return result


def _run_ordered(items: list, workers: int, fn) -> list:
    """
    Run fn(i, item) concurrently for each item, returning results in original order.

    fn must accept a (int, Any) tuple and return a (int, result) tuple.
    The integer index is used to reassemble results in submission order
    regardless of which futures complete first.
    """
    if not items:
        return []
    results = [None] * len(items)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fn, (i, item)): i for i, item in enumerate(items)}
        for future in as_completed(futures):
            i, result = future.result()
            results[i] = result
    return results


def handle_search_batch(args: argparse.Namespace) -> dict:
    """Handle batch search — reads one query per line from a file, runs concurrently."""
    queries = _read_query_file(args.search_batch)
    logger.info(f"Running batch search for {len(queries)} queries")
    extractor = SearchExtractor(max_results=args.search_limit, verbose=args.verbose)

    def _search(index_query: tuple[int, str]) -> tuple[int, dict]:
        i, q = index_query
        try:
            return i, extractor.search(q)
        except ScraperError as e:
            logger.warning(f"Search failed for {q!r}: {e.user_message}")
            return i, {"query": q, "error": e.user_message, "results": []}

    results = _run_ordered(queries, workers=args.workers, fn=_search)

    for result in results:
        if not result or not result.get("results"):
            continue
        result["results"] = _post_process_items(
            result["results"], args, apply_shorts=True, fetch_comments=True
        )
        result["total_results"] = len(result["results"])

    return {"total_queries": len(queries), "queries": [r for r in results if r is not None]}


def handle_pipeline(args: argparse.Namespace) -> dict:
    """Handle search → filter → full-extract pipeline for a single query."""
    result = _build_pipeline(args).run(args.search)

    if result.get("videos"):
        result["videos"] = _post_process_items(
            result["videos"], args, apply_shorts=False, fetch_comments=False
        )

    return result


def handle_pipeline_batch(args: argparse.Namespace) -> dict:
    """Handle pipeline for every query in a search-batch file, runs concurrently."""
    queries = _read_query_file(args.search_batch)
    logger.info(f"Running pipeline batch for {len(queries)} queries")
    # Inner pipeline uses workers=1: the outer ThreadPoolExecutor already
    # runs args.workers pipelines concurrently, so allowing each pipeline to
    # spawn its own workers pool would multiply concurrency by args.workers^2.
    pipeline = PipelineExtractor(
        search_limit=args.search_limit,
        top_n=args.pipeline_top,
        min_duration=args.filter_min_duration,
        max_duration=args.filter_max_duration,
        min_views=args.filter_min_views,
        max_age_days=args.filter_max_age_days,
        extract_transcript=args.transcript,
        subtitle_lang=args.subtitle_lang,
        output_dir=args.download_dir,
        workers=1,
        verbose=args.verbose,
        get_comments=getattr(args, "comments", False),
        comments_max=getattr(args, "comments_max", 500),
        include_detailed_formats=getattr(args, "detailed_formats", False),
    )

    def _run(index_query: tuple[int, str]) -> tuple[int, dict]:
        i, q = index_query
        try:
            return i, pipeline.run(q)
        except ScraperError as e:
            logger.warning(f"Pipeline failed for {q!r}: {e.user_message}")
            return i, {"query": q, "error": e.user_message, "videos": []}

    results = _run_ordered(queries, workers=args.workers, fn=_run)

    for result in results:
        if not result or not result.get("videos"):
            continue
        result["videos"] = _post_process_items(
            result["videos"], args, apply_shorts=True, fetch_comments=False, shorts_first=False
        )

    return {"total_queries": len(queries), "queries": [r for r in results if r is not None]}


def _print_search_results(data: dict) -> None:
    """Print search results as a formatted table (or plain list if rich is absent)."""
    query   = data.get("query", "")
    results = data.get("results", [])
    total   = data.get("total_results", 0)

    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(
            title=f'YouTube Search: "{query}" — {total} results',
            show_lines=False,
        )
        table.add_column("#",        style="dim",  width=3)
        table.add_column("Title",    style="bold", max_width=50)
        table.add_column("Channel",  style="cyan", max_width=22)
        table.add_column("Duration", justify="right")
        table.add_column("Views",    justify="right")
        for r in results:
            table.add_row(
                str(r.get("position", "")),
                r.get("title") or "",
                r.get("uploader") or "",
                r.get("duration_string") or "",
                r.get("view_count_formatted") or "",
            )
        console.print(table)
    except ImportError:
        print(f'\nSearch results for: "{query}" ({total} found)\n')
        for r in results:
            print(
                f"  {r['position']:>2}. {r.get('title')} "
                f"— {r.get('uploader')} "
                f"[{r.get('duration_string')}] "
                f"{r.get('view_count_formatted')} views"
            )
            print(f"      {r.get('url')}")


def _print_pipeline_results(data: dict) -> None:
    """Print pipeline results — brief summary per video with transcript word count."""
    query    = data.get("query", "")
    videos   = data.get("videos", [])
    initial  = data.get("initial_result_count", 0)
    filtered = data.get("after_filter_count", 0)

    print(f'\nPipeline: "{query}"')
    print(f"  Searched: {initial}  |  After filter: {filtered}  |  Extracted: {len(videos)}\n")

    for i, v in enumerate(videos, 1):
        if v.get("error"):
            print(f"  {i}. [ERROR] {v.get('url')} — {v.get('error')}")
            continue
        transcript = v.get("transcript")
        transcript_note = (
            f"  ({len(transcript.split())} words)" if transcript else "  (no transcript)"
        )
        print(f"  {i}. {v.get('title')}")
        print(f"     {v.get('channel')} | {v.get('duration_string')} | {v.get('view_count_formatted')} views")
        print(f"     {v.get('webpage_url')}")
        print(f"     Transcript:{transcript_note}")
        print()


# ═══════════════════════════════════════════════════════════════════════════════
# OUTPUT HANDLER
# Decides how to format and where to send the result.
# ═══════════════════════════════════════════════════════════════════════════════

def _result_items(data: dict | list) -> list[dict]:
    """
    Extract the flat list of video/result items from any result shape.

    Covers all extractor output shapes so callers don't repeat shape-detection.
    """
    if isinstance(data, list):
        return data
    if "queries" in data:          # search-batch or pipeline-batch
        items: list[dict] = []
        for q in data.get("queries", []):
            items.extend(q.get("videos") or q.get("results") or [])
        return items
    return (
        data.get("results")        # SearchExtractor
        or data.get("videos")      # Pipeline/Channel/Playlist
        or ([data] if data.get("id") or data.get("title") else [])
    )


def _extract_urls(data: dict | list) -> list[str]:
    """Extract YouTube URLs from any result shape. All extractors normalize to webpage_url."""
    def _u(item: dict) -> str | None:
        return item.get("webpage_url") or item.get("url")
    return [u for item in _result_items(data) if (u := _u(item))]


def handle_output(data: dict | list, args: argparse.Namespace, gen: ReportGenerator) -> None:
    """
    Format and output the result.

    Output routing logic:
      --urls-only → one URL per line (for NotebookLM / batch piping)
      --report    → Markdown formatter
      --csv       → CSV formatter
      (default)   → JSON formatter

    If --output is specified: save to file
    If not: print to stdout (JSON) or terminal (Markdown)
    """
    output_path = Path(args.output) if args.output else None

    # ── URLs-only mode: one URL per line, nothing else ────────────────────────
    if getattr(args, "urls_only", False):
        urls = _extract_urls(data)
        if not urls:
            print("Warning: --urls-only produced 0 URLs. Check your query or input.", file=sys.stderr)
            sys.exit(1)
        output = "\n".join(urls)
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(output + "\n", encoding="utf-8")
            print(f"Saved {len(urls)} URLs to {output_path}")
        else:
            print(output)
        return

    # Detect result type from _extractor tag or structure
    _ext         = data.get("_extractor", "") if isinstance(data, dict) else ""
    is_search    = _ext == "SearchExtractor"
    is_pipeline  = _ext == "PipelineExtractor"
    is_channel   = _ext == "ChannelExtractor"
    is_batch_res = isinstance(data, dict) and "queries" in data  # search/pipeline batch
    is_playlist  = _ext == "PlaylistExtractor"
    is_batch     = isinstance(data, list)

    # ── Print terminal summary (before file output) ───────────────────────────
    if not args.no_print:
        if is_search:
            _print_search_results(data)
        elif is_pipeline:
            _print_pipeline_results(data)
        elif is_channel:
            tab  = data.get("tab", "?")
            n    = data.get("total_videos", len(data.get("videos", [])))
            print(f'\nChannel: {data.get("channel_url")}  |  tab: {tab}  |  {n} videos\n')
        elif is_batch_res:
            for q in data.get("queries", []):
                if q.get("_extractor") == "PipelineExtractor":
                    _print_pipeline_results(q)
                else:
                    _print_search_results(q)
        elif is_playlist:
            gen.print_playlist_summary(data)
        elif is_batch:
            pass  # Batch summary is in the formatted output
        elif isinstance(data, dict) and not data.get("error"):
            if data.get("mode") in ("video", "audio"):
                gen.print_download_result(data)
            elif "title" in data and "download_attempted" not in data:
                gen.print_video_summary(data)

    # ── Determine format ──────────────────────────────────────────────────────
    if args.report:
        fmt = MarkdownFormatter()

        if is_playlist:
            content = fmt.format_playlist(data)
        elif not (is_search or is_pipeline or is_channel or is_batch_res or is_batch):
            content = fmt.format_video(data)
        else:
            content = fmt.format_batch(_result_items(data))

        if output_path:
            saved = fmt.save(content, output_path)
            gen.print_save_confirmation(saved, "markdown")
        else:
            print(content)

    elif args.csv:
        fmt = CsvFormatter()

        def _csv_out(content: str, rows_or_data) -> None:
            if output_path:
                gen.print_save_confirmation(fmt.save(rows_or_data, output_path), "csv")
            else:
                print(content)

        if is_playlist:
            _csv_out(fmt.format_playlist(data), data)
        elif not (is_search or is_pipeline or is_channel or is_batch_res or is_batch):
            _csv_out(fmt.format(data), data)
        else:
            rows = _result_items(data)
            _csv_out(fmt.format_many(rows), rows)

    else:
        # Default: JSON
        fmt = JsonFormatter(exclude_raw=True)

        if output_path:
            saved = fmt.save(data, output_path)
            gen.print_save_confirmation(saved, "json")
        else:
            print(fmt.format(data))


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """
    Validate parsed CLI arguments and call parser.error() for any invalid combination.

    Groups:
      1. Mutually exclusive flags
      2. Dependency rules (X requires Y)
      3. Numeric range bounds
      4. Mode-specific flag restrictions
    """
    if getattr(args, "download_video", False) and getattr(args, "download_audio", False):
        parser.error("--download-video and --download-audio are mutually exclusive. Use one at a time.")
    if getattr(args, "subtitles", False) and (getattr(args, "download_video", False) or getattr(args, "download_audio", False)):
        parser.error("--subtitles cannot be combined with --download-video or --download-audio. Use separate commands.")
    if args.search and args.subtitles:
        parser.error("--search and --subtitles are incompatible. Subtitles require a single video URL (use --url).")
    if args.search and args.url:
        parser.error("--search and --url are mutually exclusive. Use one input mode at a time.")
    if args.batch and args.search:
        parser.error("--batch and --search are mutually exclusive. --batch takes a file of URLs; --search takes a keyword.")
    if getattr(args, "sentiment", False) and not getattr(args, "comments", False):
        parser.error("--sentiment requires --comments to be enabled.")
    if getattr(args, "transcript", False) and not (args.search or args.search_batch):
        parser.error("--transcript requires --search or --search-batch.")
    if getattr(args, "transcript", False) and (args.search or args.search_batch) and not args.pipeline:
        parser.error("--transcript requires --pipeline (e.g. --search --pipeline --transcript).")
    _output_modes = sum([
        bool(getattr(args, "report", False)),
        bool(getattr(args, "csv", False)),
        bool(getattr(args, "urls_only", False)),
    ])
    if _output_modes > 1:
        parser.error("--report, --csv, and --urls-only are mutually exclusive. Use only one.")
    if getattr(args, "download_subs", False) and not getattr(args, "subtitles", False):
        parser.error("--download-subs requires --subtitles.")
    if getattr(args, "sort_by", None) == "dislikes" and not getattr(args, "dislikes", False):
        parser.error("--sort-by dislikes requires --dislikes.")
    if getattr(args, "sort_by", None) in ("positive_ratio", "negative_ratio"):
        if not getattr(args, "sentiment", False):
            parser.error(
                f"--sort-by {args.sort_by} requires --comments and --sentiment."
            )
    if getattr(args, "filter_min_dislikes", None) is not None and not getattr(args, "dislikes", False):
        parser.error("--filter-min-dislikes requires --dislikes.")
    if getattr(args, "filter_max_dislikes", None) is not None and not getattr(args, "dislikes", False):
        parser.error("--filter-max-dislikes requires --dislikes.")
    for _ratio_arg in ("filter_min_positive_ratio", "filter_min_negative_ratio"):
        _val = getattr(args, _ratio_arg, None)
        if _val is not None:
            if not (0.0 <= _val <= 1.0):
                parser.error(f"--{_ratio_arg.replace('_', '-')} must be between 0.0 and 1.0, got {_val}")
            if not getattr(args, "sentiment", False):
                parser.error(f"--{_ratio_arg.replace('_', '-')} requires --comments and --sentiment.")
    for _count_arg, _flag in (
        ("search_limit", "--search-limit"),
        ("pipeline_top", "--pipeline-top"),
        ("comments_max", "--comments-max"),
        ("max_videos", "--max-videos"),
    ):
        _val = getattr(args, _count_arg, None)
        if _val is not None and _val < 1:
            parser.error(f"{_flag} must be >= 1, got {_val}")
    if args.cache_ttl <= 0:
        parser.error(f"--cache-ttl must be > 0, got {args.cache_ttl}")
    if getattr(args, "filter_min_views", None) is not None and args.filter_min_views < 0:
        parser.error("--filter-min-views must be >= 0")
    if getattr(args, "filter_max_views", None) is not None and args.filter_max_views < 0:
        parser.error("--filter-max-views must be >= 0")
    if getattr(args, "filter_max_likes", None) is not None and args.filter_max_likes < 0:
        parser.error("--filter-max-likes must be >= 0")
    if getattr(args, "filter_max_subscribers", None) is not None and args.filter_max_subscribers < 0:
        parser.error("--filter-max-subscribers must be >= 0")
    if getattr(args, "filter_min_likes", None) is not None and args.filter_min_likes < 0:
        parser.error("--filter-min-likes must be >= 0")
    if getattr(args, "filter_min_subscribers", None) is not None and args.filter_min_subscribers < 0:
        parser.error("--filter-min-subscribers must be >= 0")
    if getattr(args, "filter_min_dislikes", None) is not None and args.filter_min_dislikes < 0:
        parser.error("--filter-min-dislikes must be >= 0")
    if getattr(args, "filter_max_dislikes", None) is not None and args.filter_max_dislikes < 0:
        parser.error("--filter-max-dislikes must be >= 0")
    for _vmin_attr, _vmax_attr, _flag_min, _flag_max in [
        ("filter_min_views",       "filter_max_views",       "--filter-min-views",       "--filter-max-views"),
        ("filter_min_likes",       "filter_max_likes",       "--filter-min-likes",       "--filter-max-likes"),
        ("filter_min_subscribers", "filter_max_subscribers", "--filter-min-subscribers", "--filter-max-subscribers"),
        ("filter_min_dislikes",    "filter_max_dislikes",    "--filter-min-dislikes",    "--filter-max-dislikes"),
    ]:
        _vmin = getattr(args, _vmin_attr, None)
        _vmax = getattr(args, _vmax_attr, None)
        if _vmin is not None and _vmax is not None and _vmin > _vmax:
            parser.error(f"{_flag_min} ({_vmin}) must be <= {_flag_max} ({_vmax})")
    if args.search and not getattr(args, "pipeline", False):
        _flat_stub_filters = [
            ("filter_min_likes",       "--filter-min-likes"),
            ("filter_max_likes",       "--filter-max-likes"),
            ("filter_min_subscribers", "--filter-min-subscribers"),
            ("filter_max_subscribers", "--filter-max-subscribers"),
        ]
        for _attr, _flag in _flat_stub_filters:
            if getattr(args, _attr, None) is not None:
                parser.error(
                    f"{_flag} requires --pipeline in search mode: flat search stubs lack "
                    "like_count and channel_follower_count. Add --pipeline to get full metadata."
                )
    if getattr(args, "filter_max_age_days", None) is not None and args.filter_max_age_days < 1:
        parser.error("--filter-max-age-days must be >= 1")
    _min_dur = getattr(args, "filter_min_duration", None)
    _max_dur = getattr(args, "filter_max_duration", None)
    if _min_dur is not None and _min_dur < 0:
        parser.error("--filter-min-duration must be >= 0")
    if _max_dur is not None and _max_dur < 0:
        parser.error("--filter-max-duration must be >= 0")
    if _min_dur is not None and _max_dur is not None and _min_dur > _max_dur:
        parser.error(f"--filter-min-duration ({_min_dur}) must be <= --filter-max-duration ({_max_dur})")
    # Filtering and sorting only apply to list-producing modes.
    # Detect single-video mode: --url set, no list-mode flags.
    _list_mode = any([
        args.search, getattr(args, "search_batch", None),
        args.batch, args.channel, args.playlist,
    ])
    if not _list_mode and args.url:
        _list_only_flags = [
            ("filter_min_views",        "--filter-min-views"),
            ("filter_max_age_days",     "--filter-max-age-days"),
            ("filter_min_duration",     "--filter-min-duration"),
            ("filter_max_duration",     "--filter-max-duration"),
            ("filter_min_likes",        "--filter-min-likes"),
            ("filter_max_likes",        "--filter-max-likes"),
            ("filter_min_subscribers",  "--filter-min-subscribers"),
            ("filter_max_subscribers",  "--filter-max-subscribers"),
            ("filter_min_dislikes",     "--filter-min-dislikes"),
            ("filter_max_dislikes",     "--filter-max-dislikes"),
            ("filter_min_positive_ratio", "--filter-min-positive-ratio"),
            ("filter_min_negative_ratio", "--filter-min-negative-ratio"),
            ("no_shorts",               "--no-shorts"),
            ("sort_by",                 "--sort-by"),
        ]
        for _attr, _flag in _list_only_flags:
            if getattr(args, _attr, None) not in (None, False):
                parser.error(f"{_flag} is only valid in list-producing modes (--search, --batch, --channel, --playlist, --search-batch).")


def main() -> None:
    """
    Parse arguments and route to the appropriate handler.

    The routing priority is:
      1. Download video/audio  (most explicit — user said "download X")
      2. Subtitles             (user asked for subtitle info)
      3. Playlist              (URL is a playlist)
      4. Batch                 (multiple URLs from file)
      5. Single video          (default)
    """
    # Ensure UTF-8 output on Windows consoles that default to cp1252/cp850.
    # errors="replace" prevents UnicodeEncodeError for characters the console can't render.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = build_parser()
    args = parser.parse_args()

    _validate_args(parser, args)

    # Set up logger verbosity based on --verbose flag
    logger = get_logger("youtube_scraper", verbose=args.verbose)
    gen = ReportGenerator(verbose=args.verbose)

    # ── Cache: optional pre-run clear ─────────────────────────────────────────
    if getattr(args, "cache_clear", False):
        from cache import CacheManager
        cache = CacheManager(
            cache_dir=getattr(args, "cache_dir", None) or CACHE_DIR,
            ttl=int(getattr(args, "cache_ttl", CACHE_TTL_HOURS) * 3600),
        )
        removed = cache.clear()
        logger.info(f"Cache cleared: {removed} entries removed from {cache._db_path}")

    try:
        # ── Route to handler ──────────────────────────────────────────────────
        if args.download_video or args.download_audio:
            result = handle_download(args)

        elif args.subtitles:
            result = handle_subtitles(args)

        elif args.playlist:
            result = handle_playlist(args)

        elif args.batch:
            result = handle_batch(args)

        elif args.channel:
            result = handle_channel(args)

        elif args.search:
            if args.pipeline:
                result = handle_pipeline(args)
            else:
                result = handle_search(args)

        elif args.search_batch:
            if args.pipeline:
                result = handle_pipeline_batch(args)
            else:
                result = handle_search_batch(args)

        else:
            # Default: single video metadata
            result = handle_video(args)

        # ── Output ────────────────────────────────────────────────────────────
        handle_output(result, args, gen)

        # Exit non-zero when every batch URL / search-batch / pipeline-batch failed
        if args.batch and isinstance(result, list) and result and all(r.get("error") for r in result):
            sys.exit(1)
        if getattr(args, "search_batch", None) and isinstance(result, dict):
            _queries = result.get("queries", [])
            if _queries and all(q.get("error") for q in _queries):
                sys.exit(1)

    except ScraperError as e:
        # Typed errors from our classification system
        logger.error(f"{type(e).__name__}: {e.user_message}")
        if args.verbose and e.original:
            logger.debug(f"Original error: {e.original}")
        sys.exit(1)

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(130)

    except Exception as e:
        # Unexpected errors — show more detail to help with debugging
        logger.error(f"Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
