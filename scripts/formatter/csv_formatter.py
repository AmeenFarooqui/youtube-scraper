"""
csv_formatter.py
----------------
Formats metadata dicts into CSV for spreadsheet-friendly export.

WHY CSV IS TRICKY FOR NESTED DATA:
  YouTube metadata is deeply nested (formats, thumbnails, subtitles).
  CSV is inherently flat (rows and columns).

  Our approach:
    - Use the predefined CSV_FIELDS list from config.py for column order
    - Join list fields (tags, categories) into comma-separated strings
    - Nested dicts get flattened or omitted
    - A "description_short" field is used instead of full description

SINGLE vs BATCH:
  Single video  → one data row + header
  Playlist/batch → multiple rows, one per video
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from config import CSV_FIELDS
from utils.helpers import flatten_list, safe_get, truncate


class CsvFormatter:
    """
    Converts extractor output into CSV format.

    Usage (single video):
        fmt = CsvFormatter()
        csv_str = fmt.format(metadata)

    Usage (multiple videos / playlist):
        fmt = CsvFormatter()
        csv_str = fmt.format_many([metadata1, metadata2, ...])
    """

    def __init__(self, fields: list[str] | None = None):
        """
        Args:
            fields: Column names to include. Defaults to CSV_FIELDS from config.
                    Order determines column order in output.
        """
        self.fields = fields or CSV_FIELDS

    def format(self, data: dict) -> str:
        """Format a single video metadata dict as CSV (header + 1 row)."""
        return self._to_csv([data])

    def format_many(self, data_list: list[dict]) -> str:
        """Format multiple video dicts as CSV (header + N rows)."""
        return self._to_csv(data_list)

    def format_playlist(self, playlist_data: dict) -> str:
        """
        Format a playlist result as CSV.
        Flattens the videos list into rows; playlist-level info is dropped
        since it doesn't fit a per-video column structure.
        """
        videos = playlist_data.get("videos", [])
        if not videos:
            return self._to_csv([])
        return self.format_many(videos)

    def save(self, data: dict | list, path: str | Path) -> Path:
        """
        Write CSV to a file.

        Accepts either a single dict or a list of dicts.
        """
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(data, dict):
            # Check if it's a playlist result
            if "videos" in data:
                csv_str = self.format_playlist(data)
            else:
                csv_str = self.format(data)
        else:
            csv_str = self.format_many(data)

        output_path.write_text(csv_str, encoding="utf-8-sig")  # utf-8-sig for Excel compatibility
        return output_path

    def _to_csv(self, rows: list[dict]) -> str:
        """
        Convert a list of metadata dicts to a CSV string.

        Uses StringIO to build the CSV in memory before returning as a string.
        This is more memory-efficient than building a string with concatenation.
        """
        output = io.StringIO()

        writer = csv.DictWriter(
            output,
            fieldnames=self.fields,
            extrasaction="ignore",   # Ignore fields not in self.fields
            lineterminator="\n",
        )

        writer.writeheader()

        for row_data in rows:
            flat_row = self._flatten_for_csv(row_data)
            writer.writerow(flat_row)

        return output.getvalue()

    def _flatten_for_csv(self, data: dict) -> dict:
        """
        Flatten a nested metadata dict into a simple key→string mapping.

        Rules:
          - Lists  → joined with "; " separator
          - Dicts  → JSON stringified or omitted
          - None   → empty string
          - Other  → str()

        Also synthesizes some virtual columns that don't directly exist
        in the raw metadata but are useful in CSV form.
        """
        flat: dict[str, Any] = {}

        for field in self.fields:
            value = data.get(field)

            if value is None:
                flat[field] = ""
            elif isinstance(value, list):
                # Join lists of strings/ints
                flat[field] = "; ".join(str(item) for item in value if item)
            elif isinstance(value, dict):
                # Dicts don't fit in a CSV cell — stringify them
                flat[field] = str(value)
            else:
                flat[field] = str(value)

        # Virtual fields — computed from other fields
        if "description_short" not in data and "description" in data:
            flat["description_short"] = truncate(data.get("description", ""), 200)

        if "subtitle_languages" not in data:
            # Try to build from the subtitles_summary if present
            summary = data.get("subtitles_summary", {})
            if summary:
                flat["subtitle_languages"] = "; ".join(
                    summary.get("all_available_languages", [])
                )
            else:
                # Fallback: combine manual + auto from the top-level lists
                manual = data.get("subtitles_manual", [])
                auto = data.get("subtitles_auto", [])
                all_langs = sorted(set(manual + auto))
                flat["subtitle_languages"] = "; ".join(all_langs)

        if "has_chapters" in data:
            flat["has_chapters"] = "Yes" if data["has_chapters"] else "No"

        if "tags" in data and isinstance(data["tags"], list):
            flat["tags"] = "; ".join(data["tags"][:20])  # Cap at 20 tags

        if "categories" in data and isinstance(data["categories"], list):
            flat["categories"] = "; ".join(data["categories"])

        return flat
