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
    ScraperError,
    format_error_for_report,
)
from extractor import (
    VideoExtractor, PlaylistExtractor, SubtitleExtractor, Downloader,
    SearchExtractor, PipelineExtractor,
)
from formatter import JsonFormatter, CsvFormatter, MarkdownFormatter
from reports import ReportGenerator
from config import DEFAULT_OUTPUT_DIR, MAX_WORKERS

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI ARGUMENT PARSER
# ═══════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    """
    Build and return the CLI argument parser.

    We use argparse (Python's built-in CLI library).
    Each argument has a help string explaining what it does.
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

    # ── Input source (mutually exclusive) ────────────────────────────────────
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

    # ── Search & pipeline options ─────────────────────────────────────────────
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

    # ── Output options ────────────────────────────────────────────────────────
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

    # ── Playlist options ──────────────────────────────────────────────────────
    playlist_group = parser.add_argument_group("Playlist options")
    playlist_group.add_argument(
        "--full-playlist",
        action="store_true",
        dest="full_playlist",
        help=(
            "Fetch complete metadata for each video in the playlist "
            "(slow — makes one network request per video). "
            "Default is fast flat mode (title/duration only)."
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
    def _positive_int(value: str) -> int:
        try:
            n = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"--workers must be an integer, got {value!r}")
        if n < 1:
            raise argparse.ArgumentTypeError(f"--workers must be >= 1, got {n}")
        return n

    batch_group = parser.add_argument_group("Batch options")
    batch_group.add_argument(
        "--workers",
        metavar="N",
        type=_positive_int,
        default=MAX_WORKERS,
        help=f"Concurrent workers for batch processing (default: {MAX_WORKERS}). Use 1 for sequential.",
    )

    # ── Global options ────────────────────────────────────────────────────────
    global_group = parser.add_argument_group("Global options")
    global_group.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug output",
    )

    return parser


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTE HANDLERS
# Each function handles one mode (video/playlist/batch/subtitle/download).
# They all return a dict or list that gets passed to the output handler.
# ═══════════════════════════════════════════════════════════════════════════════

def handle_video(args: argparse.Namespace) -> dict:
    """Handle single video metadata extraction."""
    url = args.url

    if not is_valid_youtube_url(url):
        logger.error(f"Not a valid YouTube URL: {url}")
        sys.exit(1)

    extractor = VideoExtractor(verbose=args.verbose)
    return extractor.extract(url)


def handle_playlist(args: argparse.Namespace) -> dict:
    """Handle playlist extraction."""
    url = args.playlist

    extractor = PlaylistExtractor(
        full_details=args.full_playlist,
        max_videos=args.max_videos,
        verbose=args.verbose,
    )
    return extractor.extract(url)


def handle_batch(args: argparse.Namespace) -> list[dict]:
    """
    Handle batch processing of multiple URLs from a file.

    URLs are processed concurrently (up to --workers at a time).
    If a URL fails, we log the error and continue with the rest.
    """
    is_valid, message, urls = validate_batch_file(args.batch)

    if not is_valid:
        logger.error(message)
        sys.exit(1)

    logger.info(message)

    # Apply max_videos limit to batch if set
    if args.max_videos:
        urls = urls[:args.max_videos]
        logger.info(f"Limited to {args.max_videos} URLs")

    results: list[dict] = [None] * len(urls)  # Pre-allocate to preserve order

    extractor = VideoExtractor(verbose=args.verbose)

    def process_url(index_url: tuple[int, str]) -> tuple[int, dict]:
        """Process a single URL and return (index, result)."""
        i, url = index_url
        logger.info(f"[{i+1}/{len(urls)}] Processing: {url}")
        try:
            data = extractor.extract(url)
            return i, data
        except ScraperError as e:
            logger.warning(f"Failed: {url} — {e.user_message}")
            return i, format_error_for_report(e)

    # Process with thread pool for concurrency
    # ThreadPoolExecutor is safe here because yt-dlp releases the GIL for I/O
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

    return [r for r in results if r is not None]


def handle_subtitles(args: argparse.Namespace) -> dict:
    """Handle subtitle extraction (and optional download)."""
    url = args.url

    if not url or not is_valid_youtube_url(url):
        logger.error("--subtitles requires a valid --url")
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

    if not url or not is_valid_youtube_url(url):
        logger.error("--download-video/--download-audio requires a valid --url")
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
            queries = [l.strip() for l in f if l.strip() and not l.startswith("#")]
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
    )


def handle_search(args: argparse.Namespace) -> dict:
    """Handle YouTube keyword search — returns ranked result list."""
    extractor = SearchExtractor(max_results=args.search_limit, verbose=args.verbose)
    return extractor.search(args.search)


def handle_search_batch(args: argparse.Namespace) -> dict:
    """Handle batch search — reads one query per line from a file, runs concurrently."""
    queries = _read_query_file(args.search_batch)
    logger.info(f"Running batch search for {len(queries)} queries")
    extractor = SearchExtractor(max_results=args.search_limit, verbose=args.verbose)

    results: list[dict | None] = [None] * len(queries)

    def _search(index_query: tuple[int, str]) -> tuple[int, dict]:
        i, q = index_query
        try:
            return i, extractor.search(q)
        except ScraperError as e:
            logger.warning(f"Search failed for {q!r}: {e.user_message}")
            return i, {"query": q, "error": e.user_message, "results": []}

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_search, (i, q)): i for i, q in enumerate(queries)}
        for future in as_completed(futures):
            i, result = future.result()
            results[i] = result

    return {"total_queries": len(queries), "queries": [r for r in results if r is not None]}


def handle_pipeline(args: argparse.Namespace) -> dict:
    """Handle search → filter → full-extract pipeline for a single query."""
    return _build_pipeline(args).run(args.search)


def handle_pipeline_batch(args: argparse.Namespace) -> dict:
    """Handle pipeline for every query in a search-batch file, runs concurrently."""
    queries = _read_query_file(args.search_batch)
    logger.info(f"Running pipeline batch for {len(queries)} queries")
    pipeline = _build_pipeline(args)

    results: list[dict | None] = [None] * len(queries)

    def _run(index_query: tuple[int, str]) -> tuple[int, dict]:
        i, q = index_query
        try:
            return i, pipeline.run(q)
        except ScraperError as e:
            logger.warning(f"Pipeline failed for {q!r}: {e.user_message}")
            return i, {"query": q, "error": e.user_message, "videos": []}

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_run, (i, q)): i for i, q in enumerate(queries)}
        for future in as_completed(futures):
            i, result = future.result()
            results[i] = result

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

def _extract_urls(data: dict | list) -> list[str]:
    """Extract YouTube URLs from any result shape. All extractors normalize to webpage_url."""
    def _u(item: dict) -> str | None:
        return item.get("webpage_url") or item.get("url")

    urls = []
    if isinstance(data, list):
        for item in data:
            if u := _u(item):
                urls.append(u)
    elif isinstance(data, dict):
        _ext = data.get("_extractor", "")
        if _ext == "SearchExtractor":
            for r in data.get("results", []):
                if u := _u(r):
                    urls.append(u)
        elif _ext == "PipelineExtractor":
            for v in data.get("videos", []):
                if u := _u(v):
                    urls.append(u)
        elif "queries" in data:
            for q in data.get("queries", []):
                for item in q.get("videos") or q.get("results") or []:
                    if u := _u(item):
                        urls.append(u)
        elif "playlist_id" in data:
            for v in data.get("entries", []):
                if v and (u := _u(v)):
                    urls.append(u)
        else:
            if u := _u(data):
                urls.append(u)
    return urls


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
    is_batch_res = isinstance(data, dict) and "queries" in data  # search/pipeline batch
    is_playlist  = isinstance(data, dict) and "playlist_id" in data
    is_batch     = isinstance(data, list)

    # ── Print terminal summary (before file output) ───────────────────────────
    if not args.no_print:
        if is_search:
            _print_search_results(data)
        elif is_pipeline:
            _print_pipeline_results(data)
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

        if is_search:
            # Format search results as a batch (list of result entries)
            content = fmt.format_batch(data.get("results", []))
        elif is_pipeline:
            content = fmt.format_batch(data.get("videos", []))
        elif is_batch_res:
            all_videos = []
            for q in data.get("queries", []):
                all_videos.extend(q.get("videos") or q.get("results") or [])
            content = fmt.format_batch(all_videos)
        elif is_playlist:
            content = fmt.format_playlist(data)
        elif is_batch:
            content = fmt.format_batch(data)
        else:
            content = fmt.format_video(data)

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

        if is_search:
            rows = data.get("results", [])
            _csv_out(fmt.format_many(rows), rows)
        elif is_pipeline:
            rows = data.get("videos", [])
            _csv_out(fmt.format_many(rows), rows)
        elif is_batch_res:
            rows = []
            for q in data.get("queries", []):
                rows.extend(q.get("videos") or q.get("results") or [])
            _csv_out(fmt.format_many(rows), rows)
        elif is_playlist:
            _csv_out(fmt.format_playlist(data), data)
        elif is_batch:
            _csv_out(fmt.format_many(data), data)
        else:
            _csv_out(fmt.format(data), data)

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

    # ── Fast-fail: incompatible flag combinations ─────────────────────────────
    if args.search and args.subtitles:
        parser.error("--search and --subtitles are incompatible. Subtitles require a single video URL (use --url).")
    if args.search and args.url:
        parser.error("--search and --url are mutually exclusive. Use one input mode at a time.")
    if args.batch and args.search:
        parser.error("--batch and --search are mutually exclusive. --batch takes a file of URLs; --search takes a keyword.")

    # Set up logger verbosity based on --verbose flag
    logger = get_logger("youtube_scraper", verbose=args.verbose)
    gen = ReportGenerator(verbose=args.verbose)

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
