# utils package — shared helpers used across extractors, formatters, and CLI
from .logger import get_logger
from .validators import is_valid_youtube_url, detect_url_type, validate_batch_file
from .helpers import (
    format_duration,
    format_filesize,
    format_number,
    format_date,
    safe_get,
    safe_filename,
    seconds_to_hms,
)
from .error_handler import (
    ScraperError,
    VideoUnavailableError,
    PrivateVideoError,
    AgeRestrictedError,
    GeoBlockedError,
    NetworkError,
    RateLimitedError,
    classify_ytdlp_error,
    format_error_for_report,
)

__all__ = [
    "get_logger",
    "is_valid_youtube_url",
    "detect_url_type",
    "validate_batch_file",
    "format_duration",
    "format_filesize",
    "format_number",
    "format_date",
    "safe_get",
    "safe_filename",
    "seconds_to_hms",
    "ScraperError",
    "VideoUnavailableError",
    "PrivateVideoError",
    "AgeRestrictedError",
    "GeoBlockedError",
    "NetworkError",
    "RateLimitedError",
    "classify_ytdlp_error",
    "format_error_for_report",
]
