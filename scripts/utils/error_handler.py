"""
error_handler.py
----------------
Custom exceptions and error classification for the YouTube scraper.

Why classify errors?
  When yt-dlp fails, it raises generic exceptions with long error messages.
  This module:
    1. Defines specific exception types (so callers can catch exactly what went wrong)
    2. Classifies raw yt-dlp error messages into those types
    3. Provides human-friendly messages for each error type

Design principle: never crash the whole process because of one bad URL.
The extractors use these to catch errors, log them, and continue.
"""

from __future__ import annotations


# ── Custom exception hierarchy ────────────────────────────────────────────────

class ScraperError(Exception):
    """Base class for all YouTube scraper errors."""

    def __init__(self, message: str, url: str = "", original: Exception | None = None):
        super().__init__(message)
        self.url = url              # The URL that caused this error
        self.original = original    # The underlying yt-dlp exception, if any
        self.user_message = message # A friendly message for display

    def __str__(self) -> str:
        if self.url:
            return f"{self.user_message} (URL: {self.url})"
        return self.user_message


class VideoUnavailableError(ScraperError):
    """Video has been deleted, made private, or is otherwise gone."""
    pass


class PrivateVideoError(ScraperError):
    """Video is private and cannot be accessed without authentication."""
    pass


class AgeRestrictedError(ScraperError):
    """Video is age-restricted and requires sign-in to view."""
    pass


class GeoBlockedError(ScraperError):
    """Video is not available in the current geographic region."""
    pass


class NetworkError(ScraperError):
    """A network-level failure (timeout, DNS, connection refused, etc.)."""
    pass


class RateLimitedError(ScraperError):
    """Too many requests — YouTube is throttling us."""
    pass


class PlaylistError(ScraperError):
    """Error fetching playlist metadata or videos."""
    pass


class SubtitleError(ScraperError):
    """Subtitles not available or could not be fetched."""
    pass


class DownloadError(ScraperError):
    """An error occurred during file download."""
    pass


# ── Error classification ──────────────────────────────────────────────────────

# Maps substrings found in yt-dlp error messages to our exception classes.
# Order matters — more specific patterns should come first.
_ERROR_PATTERNS: list[tuple[str, type[ScraperError], str]] = [
    # (substring_to_match, exception_class, friendly_message)
    (
        "private video",
        PrivateVideoError,
        "This video is private and cannot be accessed.",
    ),
    (
        "this video is private",
        PrivateVideoError,
        "This video is private and cannot be accessed.",
    ),
    (
        "age-restricted",
        AgeRestrictedError,
        "This video is age-restricted. Authentication would be required.",
    ),
    (
        "age restricted",
        AgeRestrictedError,
        "This video is age-restricted. Authentication would be required.",
    ),
    (
        "not available in your country",
        GeoBlockedError,
        "This video is not available in your geographic region.",
    ),
    (
        "geo",
        GeoBlockedError,
        "This video appears to be geo-blocked.",
    ),
    (
        "unavailable",
        VideoUnavailableError,
        "This video is unavailable (possibly deleted or removed).",
    ),
    (
        "video has been removed",
        VideoUnavailableError,
        "This video has been removed by the uploader.",
    ),
    (
        "does not exist",
        VideoUnavailableError,
        "This video does not exist.",
    ),
    (
        "rate limit",
        RateLimitedError,
        "YouTube is rate-limiting requests. Try again later or add a delay.",
    ),
    (
        "too many requests",
        RateLimitedError,
        "YouTube is rate-limiting requests. Try again later or add a delay.",
    ),
    (
        "429",
        RateLimitedError,
        "Too many requests (HTTP 429). Try again later.",
    ),
    (
        "connection",
        NetworkError,
        "Network connection error. Check your internet connection.",
    ),
    (
        "timeout",
        NetworkError,
        "Request timed out. Check your internet connection.",
    ),
    (
        "network",
        NetworkError,
        "A network error occurred.",
    ),
    (
        "http error 403",
        NetworkError,
        "Access forbidden (HTTP 403). YouTube may be blocking this request.",
    ),
]


def classify_ytdlp_error(error: Exception, url: str = "") -> ScraperError:
    """
    Convert a raw yt-dlp exception into one of our typed ScraperError subclasses.

    Usage:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            raise classify_ytdlp_error(e, url=url)

    The function looks for known substrings in the error message (case-insensitive)
    and returns the most appropriate typed exception. If no pattern matches,
    it returns a generic ScraperError.
    """
    error_msg = str(error).lower()

    for pattern, exc_class, friendly_msg in _ERROR_PATTERNS:
        if pattern in error_msg:
            return exc_class(message=friendly_msg, url=url, original=error)

    # Default — wrap the original error in our base class
    return ScraperError(
        message=f"Unexpected error: {str(error)[:200]}",
        url=url,
        original=error,
    )


def format_error_for_report(error: ScraperError) -> dict:
    """
    Convert a ScraperError into a JSON-serializable dict for output reports.

    This is included in batch results so errors don't silently disappear.
    """
    return {
        "error": True,
        "error_type": type(error).__name__,
        "message": error.user_message,
        "url": error.url,
    }
