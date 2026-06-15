"""
downloader.py
-------------
Handles actual file downloads: video (MP4) and audio (MP3).

IMPORTANT: This module is only invoked when the user EXPLICITLY passes
--download-video or --download-audio. It is NEVER triggered by default.

HOW DOWNLOADS WORK WITH yt-dlp:
  1. For video: yt-dlp selects the best video + audio streams and merges them
     using ffmpeg into a single MP4 file.
  2. For audio: yt-dlp downloads the best audio stream, then the
     FFmpegExtractAudio post-processor converts it to MP3.
  Both operations require ffmpeg installed on the system.

OUTPUT TEMPLATE:
  Files are saved as: outputs/%(title)s [%(id)s].%(ext)s
  The [%(id)s] part ensures no collisions if two videos have the same title.
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path
import yt_dlp

from config import (
    BASE_YDL_OPTS,
    VIDEO_DOWNLOAD_YDL_OPTS,
    AUDIO_DOWNLOAD_YDL_OPTS,
    DEFAULT_VIDEO_FORMAT,
    DEFAULT_AUDIO_FORMAT,
    DEFAULT_OUTPUT_DIR,
)
from utils.logger import get_logger, YtDlpLogger
from utils.helpers import safe_get, format_filesize
from utils.error_handler import classify_ytdlp_error, DownloadError

logger = get_logger(__name__)


class Downloader:
    """
    Downloads video or audio files from YouTube.

    Usage:
        dl = Downloader(output_dir="./downloads")
        result = dl.download_audio("https://www.youtube.com/watch?v=...")
        result = dl.download_video("https://www.youtube.com/watch?v=...", format="mkv")
    """

    def __init__(
        self,
        output_dir: Path | str = DEFAULT_OUTPUT_DIR,
        verbose: bool = False,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose
        self._ydl_logger = YtDlpLogger(get_logger("yt_dlp", verbose=verbose))

    def _output_template(self) -> str:
        """
        yt-dlp output template string.
        Saves to: outputs/Video Title [dQw4w9WgXcQ].mp4
        The video ID in brackets prevents name collisions.
        """
        return str(self.output_dir / "%(title)s [%(id)s].%(ext)s")

    def download_video(self, url: str, video_format: str = DEFAULT_VIDEO_FORMAT) -> dict:
        """
        Download a video in the specified container format.

        Args:
            url:          YouTube video URL
            video_format: Output container format ("mp4", "mkv", "webm")

        Returns:
            A dict with download result info (file path, size, format, etc.)
        """
        logger.info(f"Downloading video: {url} → {video_format.upper()}")

        opts = {
            **VIDEO_DOWNLOAD_YDL_OPTS,
            "logger": self._ydl_logger,
            "outtmpl": self._output_template(),
            "merge_output_format": video_format,
        }

        return self._run_download(url, opts, mode="video", file_format=video_format)

    def download_audio(self, url: str, audio_format: str = DEFAULT_AUDIO_FORMAT) -> dict:
        """
        Download audio only and convert to the specified format.

        Args:
            url:          YouTube video URL
            audio_format: Output audio format ("mp3", "m4a", "wav", "flac", "aac")

        Returns:
            A dict with download result info

        Note: Requires ffmpeg to be installed for conversion.
        """
        logger.info(f"Downloading audio: {url} → {audio_format.upper()}")

        # Build audio opts with the correct output codec
        opts = {
            **AUDIO_DOWNLOAD_YDL_OPTS,
            "logger": self._ydl_logger,
            "outtmpl": self._output_template(),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
                "preferredquality": "192",
            }],
        }

        return self._run_download(url, opts, mode="audio", file_format=audio_format)

    def _run_download(self, url: str, opts: dict, mode: str, file_format: str) -> dict:
        """
        Core download logic. Runs yt-dlp and returns a result dict.

        This is separated from download_video/download_audio so both methods
        share the same error handling and result shaping.
        """
        # Record files in the output dir before download, to detect new files
        before = set(self.output_dir.iterdir())

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                # extract_info with download=True actually downloads the file
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise ValueError("yt-dlp returned no data")
                sanitized = ydl.sanitize_info(info)
        except yt_dlp.utils.DownloadError as e:
            # Check for ffmpeg-specific error
            if "ffmpeg" in str(e).lower() or "ffprobe" in str(e).lower():
                raise DownloadError(
                    message=(
                        "ffmpeg is required for this operation but was not found. "
                        "Install it: Linux: sudo apt install ffmpeg | "
                        "Mac: brew install ffmpeg | Windows: https://ffmpeg.org"
                    ),
                    url=url,
                    original=e,
                ) from e
            raise classify_ytdlp_error(e, url=url) from e
        except Exception as e:
            raise classify_ytdlp_error(e, url=url) from e

        # Detect the new file(s) written by yt-dlp
        after = set(self.output_dir.iterdir())
        new_files = [str(p) for p in (after - before) if p.is_file()]

        # yt-dlp skipped writing (file already exists) — find by video ID in filename
        if not new_files:
            video_id = safe_get(sanitized, "id") or ""
            if video_id:
                new_files = [
                    str(p) for p in self.output_dir.iterdir()
                    if p.is_file() and f"[{video_id}]" in p.name
                ]
                if new_files:
                    logger.info(f"Download skipped — reusing existing file(s) for {video_id}")

        # Find the primary output file (the one matching our extension)
        primary_file = next(
            (f for f in new_files if f.endswith(f".{file_format}")),
            new_files[0] if new_files else None,
        )

        # Get file size of the primary download
        file_size = None
        if primary_file:
            try:
                file_size = Path(primary_file).stat().st_size
            except OSError:
                pass

        return {
            "success": True,
            "mode": mode,
            "format": file_format,
            "url": url,
            "title": safe_get(sanitized, "title"),
            "video_id": safe_get(sanitized, "id"),
            "output_dir": str(self.output_dir),
            "primary_file": primary_file,
            "all_files": new_files,
            "file_size": file_size,
            "file_size_formatted": format_filesize(file_size),
            "duration": safe_get(sanitized, "duration"),
            "channel": safe_get(sanitized, "channel") or safe_get(sanitized, "uploader"),
        }
