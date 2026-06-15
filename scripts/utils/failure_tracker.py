"""
failure_tracker.py
------------------
Tracks and persists failed URL extractions to a JSONL log file.

Classifies each failure as:
  permanent — video gone, private, age-restricted, geo-blocked
              No point retrying these.
  transient — network error, rate-limited
              Worth retrying later.
  unknown   — anything else

Usage:
    tracker = FailureTracker("failures.jsonl")
    try:
        result = extractor.extract(url)
    except ScraperError as e:
        tracker.record(e, url=url)

    print(tracker.summary())
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from .error_handler import (
    ScraperError,
    VideoUnavailableError,
    PrivateVideoError,
    AgeRestrictedError,
    GeoBlockedError,
    NetworkError,
    RateLimitedError,
)

_PERMANENT = (VideoUnavailableError, PrivateVideoError, AgeRestrictedError, GeoBlockedError)
_TRANSIENT  = (NetworkError, RateLimitedError)


def _classify(error: ScraperError) -> str:
    if isinstance(error, _PERMANENT):
        return "permanent"
    if isinstance(error, _TRANSIENT):
        return "transient"
    return "unknown"


class FailureTracker:
    """
    Appends one JSONL record per failure to a log file.

    Each record looks like:
        {
          "timestamp": "2025-06-15T12:00:00+00:00",
          "url": "https://...",
          "error_type": "VideoUnavailableError",
          "failure_class": "permanent",
          "message": "This video is unavailable ..."
        }
    """

    def __init__(self, log_path: str | Path):
        self.log_path = Path(log_path)
        self._records: list[dict] = []
        self._lock = threading.Lock()

    def record(self, error: ScraperError, url: str = "") -> None:
        """Append one failure record to the log file and memory."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": url or error.url,
            "error_type": type(error).__name__,
            "failure_class": _classify(error),
            "message": error.user_message,
        }
        with self._lock:
            self._records.append(entry)
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    def summary(self) -> dict:
        """Return counts of recorded failures by class."""
        permanent = sum(1 for r in self._records if r["failure_class"] == "permanent")
        transient = sum(1 for r in self._records if r["failure_class"] == "transient")
        unknown   = sum(1 for r in self._records if r["failure_class"] == "unknown")
        return {
            "total_failures": len(self._records),
            "permanent": permanent,
            "transient": transient,
            "unknown": unknown,
            "log_path": str(self.log_path),
        }

    @property
    def has_failures(self) -> bool:
        return len(self._records) > 0
