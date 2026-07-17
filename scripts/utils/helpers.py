"""
helpers.py
----------
Pure utility functions used across the entire codebase.

These are small, focused functions with no external dependencies.
They handle things like formatting numbers, durations, and file sizes
into human-readable strings.

"Pure" means each function takes input and returns output with no side effects —
they don't log, write files, or make network calls.
"""

import math
from datetime import datetime
from typing import Any


# ── Duration formatting ───────────────────────────────────────────────────────

def seconds_to_hms(total_seconds: int | float | None) -> str:
    """
    Convert a number of seconds to a human-readable H:MM:SS or M:SS string.

    Examples:
        90   → "1:30"
        3661 → "1:01:01"
        None → "Unknown"
    """
    if total_seconds is None:
        return "Unknown"

    total_seconds = int(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def format_duration(total_seconds: int | float | None) -> str:
    """
    Format seconds into a verbose human-readable string.

    Examples:
        90   → "1 min 30 sec"
        3661 → "1 hr 1 min 1 sec"
        None → "Unknown"
    """
    if total_seconds is None:
        return "Unknown"

    total_seconds = int(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if hours:
        parts.append(f"{hours} hr")
    if minutes:
        parts.append(f"{minutes} min")
    if seconds or not parts:
        parts.append(f"{seconds} sec")

    return " ".join(parts)


# ── Number formatting ─────────────────────────────────────────────────────────

def format_number(n: int | float | None, suffix: str = "") -> str:
    """
    Format a large number with K/M/B suffix for readability.

    Examples:
        1_234_567 → "1.23M"
        45_000    → "45.0K"
        999       → "999"
        None      → "N/A"
    """
    if n is None:
        return "N/A"

    n = float(n)

    if abs(n) >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B{suffix}"
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.2f}M{suffix}"
    if abs(n) >= 1_000:
        return f"{n / 1_000:.1f}K{suffix}"
    return f"{int(n)}{suffix}"


def format_filesize(size_bytes: int | None) -> str:
    """
    Format bytes into a human-readable file size.

    Examples:
        1_048_576 → "1.00 MB"
        512       → "512.00 B"
        None      → "N/A"
    """
    if size_bytes is None:
        return "N/A"
    if size_bytes == 0:
        return "0 B"

    size_names = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(abs(size_bytes), 1024)))
    i = min(i, len(size_names) - 1)
    p = math.pow(1024, i)
    s = size_bytes / p
    return f"{s:.2f} {size_names[i]}"


# ── Date formatting ───────────────────────────────────────────────────────────

def format_date(date_str: str | None) -> str:
    """
    Convert yt-dlp's YYYYMMDD date format to a readable "Month DD, YYYY" string.

    yt-dlp returns dates as "20231215" (no separators).

    Examples:
        "20231215" → "December 15, 2023"
        None       → "Unknown"
    """
    if not date_str:
        return "Unknown"
    try:
        dt = datetime.strptime(str(date_str), "%Y%m%d")
        return dt.strftime("%B %d, %Y")
    except (ValueError, TypeError):
        return str(date_str)


# ── Safe data access ──────────────────────────────────────────────────────────

def safe_get(data: dict, *keys: str, default: Any = None) -> Any:
    """
    Safely get a nested value from a dict without raising KeyError.

    Why this exists:
        yt-dlp metadata dicts can be inconsistent — some fields exist for
        some videos but not others. Rather than sprinkling try/except or
        .get() chains everywhere, use this function.

    Examples:
        safe_get(info, "uploader_url")                → value or None
        safe_get(info, "thumbnails", 0, "url")        → nested access
        safe_get(info, "missing_key", default="N/A")  → "N/A"
    """
    current = data
    for key in keys:
        if current is None:
            return default
        try:
            if isinstance(current, dict):
                current = current.get(key, default)
            elif isinstance(current, (list, tuple)):
                current = current[key]
            else:
                return default
        except (KeyError, IndexError, TypeError):
            return default
    return current if current is not None else default


# ── List/dict helpers ─────────────────────────────────────────────────────────

def is_youtube_short(url: str | None, duration: int | None = None) -> bool:
    """
    Detect if a video is a YouTube Short.

    Primary signal:  URL contains '/shorts/' (reliable)
    Secondary signal: duration <= 60 seconds (heuristic — may misclassify short
                      normal videos; only applied when URL-based detection fails)
    """
    if url and "/shorts/" in str(url):
        return True
    if duration is not None and 0 < duration <= 60:
        return True
    return False


def flatten_list(nested: list | None, separator: str = ", ") -> str:
    """
    Join a list of strings into a single string, or return "None" if empty.

    Useful for fields like tags and categories which yt-dlp returns as lists.
    """
    if not nested:
        return ""
    return separator.join(str(item) for item in nested if item)


def truncate(text: str | None, max_chars: int = 500) -> str:
    """
    Truncate a long string with ellipsis. Useful for descriptions in reports.
    """
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."
