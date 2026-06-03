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

import re
import math
from datetime import datetime, timezone
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


def format_timestamp(timestamp: int | float | None) -> str:
    """
    Convert a Unix timestamp to a readable UTC datetime string.

    Examples:
        1702656000 → "2023-12-15 20:00:00 UTC"
        None       → "Unknown"
    """
    if timestamp is None:
        return "Unknown"
    try:
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (OSError, OverflowError, ValueError):
        return "Unknown"


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


# ── Filename sanitization ─────────────────────────────────────────────────────

def safe_filename(name: str, max_length: int = 200) -> str:
    """
    Convert an arbitrary string into a safe filename.

    Removes or replaces characters that are illegal in filenames on
    Windows, Mac, and Linux. Truncates to max_length to avoid OS limits.

    Examples:
        "My Video: Part 1!" → "My_Video_Part_1"
        "C:/bad/path"       → "C__bad_path"
    """
    # Replace characters illegal in filenames
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    # Collapse multiple underscores/spaces
    safe = re.sub(r"[\s_]+", "_", safe).strip("_. ")
    # Truncate
    return safe[:max_length] or "untitled"


# ── List/dict helpers ─────────────────────────────────────────────────────────

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
