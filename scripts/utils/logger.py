"""
logger.py
---------
Centralized logging for the YouTube scraper.

Uses Python's built-in `logging` module with optional `rich` formatting
for beautiful colored output in the terminal.

Why centralize logging?
  - One place to control verbosity (--verbose / --quiet flags)
  - Consistent format across all modules
  - Easy to redirect to a file alongside terminal output
"""

import logging
import sys
from pathlib import Path


def get_logger(name: str = "youtube_scraper", log_file: str | None = None, verbose: bool = False) -> logging.Logger:
    """
    Create and return a configured logger instance.

    Args:
        name:     Logger name (shows up in log output — use __name__ in modules)
        log_file: Optional path to write logs to a file in addition to terminal
        verbose:  If True, set level to DEBUG; otherwise INFO

    Returns:
        A configured logging.Logger ready to use
    """
    logger = logging.getLogger(name)
    level = logging.DEBUG if verbose else logging.INFO

    # Avoid adding duplicate console handlers if this logger was already set up.
    # Always update the level so --verbose takes effect even after module-level init.
    # File handler: add if a new log_file path is requested and not already attached.
    if logger.handlers:
        logger.setLevel(level)
        if log_file:
            log_path = Path(log_file).resolve()
            existing_paths = {
                Path(h.baseFilename).resolve()
                for h in logger.handlers
                if isinstance(h, logging.FileHandler)
            }
            if log_path not in existing_paths:
                fh = logging.FileHandler(log_path, encoding="utf-8")
                fh.setLevel(logging.DEBUG)
                fh.setFormatter(logging.Formatter(
                    fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                ))
                logger.addHandler(fh)
        return logger

    logger.setLevel(level)

    # ── Terminal handler ──────────────────────────────────────────────────────
    # Try to use rich for pretty colored output. Fall back to plain if not installed.
    try:
        from rich.logging import RichHandler
        console_handler = RichHandler(
            rich_tracebacks=True,       # Pretty exception tracebacks
            show_time=False,            # Don't clutter output with timestamps in terminal
            show_path=False,            # Don't show file path in every line
            markup=True,               # Enable [bold], [red] etc. in log messages
        )
        console_handler.setLevel(level)
        logger.addHandler(console_handler)
    except ImportError:
        # rich not installed — use plain stderr handler
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(level)
        fmt = logging.Formatter(
            fmt="%(levelname)s | %(message)s",
        )
        stderr_handler.setFormatter(fmt)
        logger.addHandler(stderr_handler)

    # ── File handler (optional) ───────────────────────────────────────────────
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)  # Always verbose in the file

        file_fmt = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_fmt)
        logger.addHandler(file_handler)

    # Don't bubble up to the root logger (avoids duplicate messages)
    logger.propagate = False

    return logger


# ── yt-dlp logger adapter ────────────────────────────────────────────────────
# yt-dlp uses its own internal logging that we need to route through ours.
# Pass an instance of this class as the 'logger' option to YoutubeDL.

class YtDlpLogger:
    """
    Adapts yt-dlp's internal log messages to our standard Python logger.
    yt-dlp calls debug(), warning(), and error() on this object.
    """

    def __init__(self, logger: logging.Logger | None = None):
        self._log = logger or get_logger("yt_dlp")

    def debug(self, msg: str) -> None:
        # yt-dlp sends noisy download progress as debug messages — filter them
        if msg.startswith("[debug]") or "ETA" in msg or "%" in msg:
            return
        self._log.debug(msg)

    def warning(self, msg: str) -> None:
        self._log.warning(msg)

    def error(self, msg: str) -> None:
        self._log.error(msg)
