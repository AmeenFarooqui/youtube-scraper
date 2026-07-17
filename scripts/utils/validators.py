"""
validators.py
-------------
URL validation and input sanitization for the YouTube scraper.

Why separate validators?
  - Catch bad input early, before making network calls
  - Provide clear, actionable error messages to the user
  - Centralize all "is this valid?" logic in one place

YouTube URL patterns supported:
  Videos:
    https://www.youtube.com/watch?v=VIDEO_ID
    https://youtu.be/VIDEO_ID
    https://youtube.com/shorts/VIDEO_ID
    https://www.youtube.com/embed/VIDEO_ID
    https://www.youtube.com/v/VIDEO_ID

  Playlists:
    https://www.youtube.com/playlist?list=PLAYLIST_ID
    https://www.youtube.com/watch?v=ID&list=PLAYLIST_ID  (video in a playlist)

  Channels:
    https://www.youtube.com/@ChannelHandle
    https://www.youtube.com/channel/CHANNEL_ID
    https://www.youtube.com/c/ChannelName
    https://www.youtube.com/user/Username
"""

import re
from pathlib import Path
from typing import Literal

# ── URL type definitions ─────────────────────────────────────────────────────
UrlType = Literal["video", "playlist", "channel", "unknown"]

# Patterns are compiled once at import time for performance
_VIDEO_PATTERNS = [
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/v/([a-zA-Z0-9_-]{11})"),
]

_PLAYLIST_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?youtube\.com/playlist\?.*list=([a-zA-Z0-9_-]+)"
)

_CHANNEL_PATTERNS = [
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/@([a-zA-Z0-9_.-]+)"),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/channel/([a-zA-Z0-9_-]+)"),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/c/([a-zA-Z0-9_-]+)"),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/user/([a-zA-Z0-9_-]+)"),
]


def detect_url_type(url: str) -> UrlType:
    """
    Detect what kind of YouTube URL this is.

    Returns one of: "video", "playlist", "channel", "unknown"

    Note: A URL like /watch?v=ID&list=PL... contains both a video ID and
    a playlist ID. We treat list= presence as playlist if no explicit
    /playlist? path, since the user probably wants the full playlist.
    """
    url = url.strip()

    # Playlist check first — watch URLs with &list= should be treated as playlists
    if _PLAYLIST_PATTERN.search(url):
        return "playlist"
    # Also catch /watch?...&list= (video inside a playlist)
    if re.search(r"youtube\.com/watch\?.*list=", url):
        return "playlist"

    # Video check
    for pattern in _VIDEO_PATTERNS:
        if pattern.search(url):
            return "video"

    # Channel check
    for pattern in _CHANNEL_PATTERNS:
        if pattern.search(url):
            return "channel"

    return "unknown"


def is_valid_youtube_url(url: str) -> bool:
    """Return True if the URL is a recognizable YouTube URL of any type."""
    return detect_url_type(url.strip()) != "unknown"


def extract_video_id(url: str) -> str | None:
    """Extract the 11-character video ID from a YouTube video URL."""
    for pattern in _VIDEO_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def validate_batch_file(file_path: str) -> tuple[bool, str, list[str]]:
    """
    Validate a batch file containing YouTube URLs (one per line).

    Args:
        file_path: Path to the text file with URLs

    Returns:
        A tuple of (is_valid, error_message, list_of_valid_urls)
        If is_valid is False, list_of_valid_urls is empty.

    The file format is simple:
      - One URL per line
      - Lines starting with # are comments and ignored
      - Blank lines are ignored
      - Invalid URLs are skipped with a warning (not a fatal error)
    """
    path = Path(file_path)

    if not path.exists():
        return False, f"File not found: {file_path}", []

    if not path.is_file():
        return False, f"Path is not a file: {file_path}", []

    if path.stat().st_size == 0:
        return False, f"File is empty: {file_path}", []

    valid_urls: list[str] = []
    skipped: list[str] = []

    with path.open(encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            if is_valid_youtube_url(line):
                valid_urls.append(line)
            else:
                skipped.append(f"Line {line_num}: {line!r}")

    if not valid_urls:
        return False, f"No valid YouTube URLs found in {file_path}", []

    return True, f"Found {len(valid_urls)} valid URL(s), skipped {len(skipped)}", valid_urls
