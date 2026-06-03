"""
report_generator.py
-------------------
High-level orchestrator that ties extractors and formatters together
to produce complete output reports.

WHY A SEPARATE REPORT GENERATOR?
  The CLI (youtube_scraper.py) handles argument parsing.
  The extractors handle data fetching.
  The formatters handle rendering.

  But someone has to:
    - Decide which extractor to use based on URL type
    - Decide which formatter to use based on --output / --csv / --report flags
    - Print a summary to the terminal (separate from saved output)
    - Handle the output path

  That's what this module does. It's the glue layer.

TERMINAL SUMMARY:
  After any operation, we print a concise human-readable summary to the
  terminal using rich (if available) or plain text. This is separate from
  the saved output and is always shown regardless of output format.
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path
from typing import Literal

from utils.logger import get_logger
from utils.helpers import format_number, seconds_to_hms, format_date, truncate

logger = get_logger(__name__)

OutputFormat = Literal["json", "csv", "markdown"]


class ReportGenerator:
    """
    Orchestrates extraction + formatting + terminal display.

    Usage:
        gen = ReportGenerator()
        gen.run_video(url, output_path="out.json", fmt="json")
        gen.run_playlist(url, output_path="playlist.md", fmt="markdown")
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    # ── Terminal display ──────────────────────────────────────────────────────

    def print_video_summary(self, data: dict) -> None:
        """Print a concise video summary to the terminal."""
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.panel import Panel
            from rich import box

            console = Console()

            # Title panel
            title = data.get("title") or "Unknown"
            url = data.get("webpage_url") or data.get("url") or ""
            console.print(Panel(f"[bold cyan]{title}[/bold cyan]\n[dim]{url}[/dim]", title="YouTube Video"))

            # Key stats table
            table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
            table.add_column("Field", style="bold")
            table.add_column("Value")

            rows = [
                ("Video ID",    data.get("id") or "N/A"),
                ("Channel",     data.get("channel") or data.get("uploader") or "N/A"),
                ("Upload Date", data.get("upload_date_formatted") or "N/A"),
                ("Duration",    data.get("duration_string") or "N/A"),
                ("Views",       data.get("view_count_formatted") or format_number(data.get("view_count"))),
                ("Likes",       data.get("like_count_formatted") or format_number(data.get("like_count"))),
                ("Comments",    data.get("comment_count_formatted") or format_number(data.get("comment_count"))),
                ("Language",    data.get("language") or "N/A"),
                ("Availability", (data.get("availability") or "N/A").title()),
            ]

            for field, value in rows:
                table.add_row(field, str(value))

            console.print(table)

            # Format summary
            fmt_s = data.get("formats_summary") or {}
            if fmt_s:
                console.print(
                    f"[dim]Formats:[/dim] {fmt_s.get('total_formats', 0)} total "
                    f"({fmt_s.get('video_only_count', 0)} video, "
                    f"{fmt_s.get('audio_only_count', 0)} audio, "
                    f"{fmt_s.get('combined_count', 0)} combined)"
                )

            # Subtitles
            sub_s = data.get("subtitles_summary") or {}
            if sub_s:
                langs = sub_s.get("all_available_languages") or []
                if langs:
                    console.print(f"[dim]Subtitles:[/dim] {len(langs)} languages available: {', '.join(langs[:10])}")
                else:
                    console.print("[dim]Subtitles:[/dim] None available")

        except ImportError:
            # rich not installed — plain text fallback
            print(f"\n{'='*60}")
            print(f"Title:    {data.get('title', 'Unknown')}")
            print(f"Channel:  {data.get('channel', data.get('uploader', 'Unknown'))}")
            print(f"Views:    {format_number(data.get('view_count'))}")
            print(f"Duration: {data.get('duration_string', 'N/A')}")
            print(f"Uploaded: {data.get('upload_date_formatted', 'N/A')}")
            print(f"URL:      {data.get('webpage_url', data.get('url', ''))}")
            print(f"{'='*60}\n")

    def print_playlist_summary(self, data: dict) -> None:
        """Print a concise playlist summary to the terminal."""
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.panel import Panel
            from rich import box

            console = Console()
            title = data.get("title") or "Unknown Playlist"
            console.print(Panel(f"[bold cyan]{title}[/bold cyan]", title="YouTube Playlist"))

            s = data.get("summary") or {}
            table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
            table.add_column("Field", style="bold")
            table.add_column("Value")

            rows = [
                ("Uploader",       data.get("uploader") or "N/A"),
                ("Total Videos",   str(data.get("total_videos", 0))),
                ("Available",      str(data.get("available_videos", 0))),
                ("Unavailable",    str(data.get("unavailable_videos", 0))),
                ("Total Duration", s.get("total_duration_formatted", "N/A")),
                ("Avg Duration",   s.get("average_duration_formatted", "N/A")),
                ("Total Views",    s.get("total_views_formatted", "N/A")),
                ("Date Range",     f"{s.get('earliest_upload', '?')} → {s.get('latest_upload', '?')}"),
            ]

            for field, value in rows:
                table.add_row(field, str(value))

            console.print(table)

        except ImportError:
            s = data.get("summary") or {}
            print(f"\n{'='*60}")
            print(f"Playlist: {data.get('title', 'Unknown')}")
            print(f"Videos:   {data.get('available_videos', 0)}/{data.get('total_videos', 0)} available")
            print(f"Duration: {s.get('total_duration_formatted', 'N/A')} total")
            print(f"{'='*60}\n")

    def print_download_result(self, result: dict) -> None:
        """Print download result to terminal."""
        try:
            from rich.console import Console
            console = Console()
            if result.get("success"):
                console.print(f"[green]Downloaded:[/green] {result.get('primary_file', 'Unknown file')}")
                console.print(f"[dim]Size: {result.get('file_size_formatted', 'N/A')}[/dim]")
            else:
                console.print(f"[red]Download failed[/red]")
        except ImportError:
            status = "Success" if result.get("success") else "Failed"
            print(f"Download {status}: {result.get('primary_file', '')}")
            print(f"Size: {result.get('file_size_formatted', 'N/A')}")

    def print_save_confirmation(self, path: Path, fmt: str) -> None:
        """Confirm to the user that a file was saved."""
        try:
            from rich.console import Console
            console = Console()
            console.print(f"\n[green]Saved {fmt.upper()}:[/green] {path}")
        except ImportError:
            print(f"\nSaved {fmt.upper()}: {path}")
