#!/usr/bin/env python3
"""
youtube_scraper.py
------------------
Main CLI entry point for the YouTube Scraper.

This is the file you run directly. It parses command-line arguments,
routes to the appropriate extractor, and handles output.

USAGE EXAMPLES:
  # Single video metadata
  python youtube_scraper.py --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

  # Save as JSON
  python youtube_scraper.py --url "URL" --output results.json

  # Export as CSV
  python youtube_scraper.py --url "URL" --csv --output results.csv

  # Generate Markdown report
  python youtube_scraper.py --url "URL" --report --output report.md

  # Playlist
  python youtube_scraper.py --playlist "https://www.youtube.com/playlist?list=PL..."

  # Batch from file
  python youtube_scraper.py --batch urls.txt --output batch_results.json

  # Subtitles
  python youtube_scraper.py --url "URL" --subtitles --subtitle-lang en

  # Download audio (MP3)
  python youtube_scraper.py --url "URL" --download-audio

  # Download video (MP4)
  python youtube_scraper.py --url "URL" --download-video

  # Verbose mode
  python youtube_scraper.py --url "URL" --verbose
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
from extractor import VideoExtractor, PlaylistExtractor, SubtitleExtractor, Downloader
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
    batch_group = parser.add_argument_group("Batch options")
    batch_group.add_argument(
        "--workers",
        metavar="N",
        type=int,
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


# ═══════════════════════════════════════════════════════════════════════════════
# OUTPUT HANDLER
# Decides how to format and where to send the result.
# ═══════════════════════════════════════════════════════════════════════════════

def handle_output(data: dict | list, args: argparse.Namespace, gen: ReportGenerator) -> None:
    """
    Format and output the result.

    Output routing logic:
      --report    → Markdown formatter
      --csv       → CSV formatter
      (default)   → JSON formatter

    If --output is specified: save to file
    If not: print to stdout (JSON) or terminal (Markdown)
    """
    output_path = Path(args.output) if args.output else None
    is_playlist = isinstance(data, dict) and "videos" in data
    is_batch = isinstance(data, list)

    # ── Print terminal summary (before file output) ───────────────────────────
    if not args.no_print:
        if is_playlist:
            gen.print_playlist_summary(data)
        elif is_batch:
            pass  # Batch summary is in the formatted output
        elif isinstance(data, dict) and not data.get("error"):
            # Check if this is a download result
            if data.get("mode") in ("video", "audio"):
                gen.print_download_result(data)
            elif not data.get("download_attempted") is False or data.get("url"):
                # Regular video metadata
                if "title" in data:
                    gen.print_video_summary(data)

    # ── Determine format ──────────────────────────────────────────────────────
    if args.report:
        fmt = MarkdownFormatter()

        if is_playlist:
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

        if is_playlist:
            content = fmt.format_playlist(data)
        elif is_batch:
            content = fmt.format_many(data)
        else:
            content = fmt.format(data)

        if output_path:
            saved = fmt.save(data, output_path)
            gen.print_save_confirmation(saved, "csv")
        else:
            print(content)

    else:
        # Default: JSON
        fmt = JsonFormatter(exclude_raw=True)

        if output_path:
            saved = fmt.save(data, output_path)
            gen.print_save_confirmation(saved, "json")
        else:
            # Pretty-print to stdout
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
    parser = build_parser()
    args = parser.parse_args()

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
