"""
config.py
---------
All default settings, constants, and configuration for the YouTube scraper.

Why centralize config?
  - One place to change defaults (e.g., default output format, max retries)
  - Easy to spot and change behaviour without hunting through multiple files
  - Keeps magic numbers and string constants out of business logic

HOW TO CUSTOMIZE:
  Override any value here, or pass settings directly to the extractor classes.
  In the future this could load from a .env file or YAML config file.
"""

import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

# Root of the skills scripts directory (where this file lives)
SCRIPTS_DIR = Path(__file__).parent

# Default directory for downloaded files (created on demand by each writer, not at import time)
DEFAULT_OUTPUT_DIR = SCRIPTS_DIR / "outputs"

# Default log file location (set to None to disable file logging)
DEFAULT_LOG_FILE: str | None = None  # e.g. str(SCRIPTS_DIR / "scraper.log")


# ── Network / retry settings ──────────────────────────────────────────────────

# How many times to retry a failed request before giving up
MAX_RETRIES = 3

# Seconds to wait between retries (yt-dlp handles this internally)
RETRY_SLEEP = 5

# Request timeout in seconds
SOCKET_TIMEOUT = 30

# Max concurrent workers for batch processing
# Set to 1 to process sequentially (safer, less likely to get rate-limited)
MAX_WORKERS = 3


# ── yt-dlp base options ────────────────────────────────────────────────────────
# These are passed directly to yt_dlp.YoutubeDL() as keyword arguments.
# See: https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py
# for the full list of available options.

BASE_YDL_OPTS: dict = {
    # Don't print anything to stdout — we control all output ourselves
    "quiet": True,

    # Don't print progress bars (we use tqdm if needed)
    "no_color": True,

    # Don't abort on errors (e.g., one unavailable video in a playlist)
    # This is critical for batch/playlist operations
    "ignoreerrors": True,

    # Number of retries on transient failures
    "retries": MAX_RETRIES,

    # Timeout for each network connection
    "socket_timeout": SOCKET_TIMEOUT,

    # Don't write any files by default (metadata extraction only)
    "skip_download": True,

    # Do NOT download thumbnails (unless explicitly requested)
    "writethumbnail": False,

    # Do NOT write video description to a file
    "writedescription": False,

    # Do NOT write info JSON alongside downloads
    "writeinfojson": False,

    # Extract flat info for playlists first (faster — gets titles/IDs without fetching each video)
    # Set to False in PlaylistExtractor when we need full video metadata
    "extract_flat": False,
}


# ── Subtitle defaults ─────────────────────────────────────────────────────────

DEFAULT_SUBTITLE_LANGS = ["en"]  # Languages to attempt first
DEFAULT_SUBTITLE_FORMAT = "srt"  # vtt, srt, ass, etc.

SUBTITLE_YDL_OPTS: dict = {
    **BASE_YDL_OPTS,
    "writesubtitles": True,         # Download manually uploaded subtitles
    "writeautomaticsub": True,      # Download auto-generated captions
    "subtitleslangs": DEFAULT_SUBTITLE_LANGS,
    "subtitlesformat": DEFAULT_SUBTITLE_FORMAT,
}


# ── Download defaults ─────────────────────────────────────────────────────────

DEFAULT_VIDEO_FORMAT = "mp4"
DEFAULT_AUDIO_FORMAT = "mp3"

# yt-dlp format string: best video + best audio, preferring mp4/m4a
# This gives the highest quality while keeping the file in a widely compatible format
VIDEO_FORMAT_SELECTOR = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"

# For audio-only downloads, we want the best available audio then convert
AUDIO_FORMAT_SELECTOR = "bestaudio/best"

VIDEO_DOWNLOAD_YDL_OPTS: dict = {
    **BASE_YDL_OPTS,
    "skip_download": False,         # Override: actually download
    "format": VIDEO_FORMAT_SELECTOR,
    "merge_output_format": DEFAULT_VIDEO_FORMAT,
}

AUDIO_DOWNLOAD_YDL_OPTS: dict = {
    **BASE_YDL_OPTS,
    "skip_download": False,         # Override: actually download
    "format": AUDIO_FORMAT_SELECTOR,
    # Post-processor converts the downloaded audio to MP3
    # Requires ffmpeg to be installed on the system
    "postprocessors": [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": DEFAULT_AUDIO_FORMAT,
        "preferredquality": "192",          # Bitrate in kbps
    }],
}


# ── Output format defaults ────────────────────────────────────────────────────

DEFAULT_OUTPUT_FORMAT = "json"      # "json" | "csv" | "markdown"
JSON_INDENT = 2                     # Pretty-print JSON with 2-space indentation


# ── Metadata field config ─────────────────────────────────────────────────────
# Fields to include when generating CSV output (in this column order)
CSV_FIELDS = [
    "id",
    "title",
    "url",
    "upload_date",
    "duration",
    "duration_string",
    "view_count",
    "like_count",
    "comment_count",
    "channel",
    "channel_id",
    "uploader",
    "description_short",
    "tags",
    "categories",
    "language",
    "age_limit",
    "availability",
    "live_status",
    "thumbnail",
    "resolution",
    "fps",
    "audio_codec",
    "video_codec",
    "filesize_approx",
    "subtitle_languages",
    "has_chapters",
    "channel_follower_count",
]
