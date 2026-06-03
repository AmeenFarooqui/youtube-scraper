"""
json_formatter.py
-----------------
Formats structured metadata dicts into JSON output.

This is the simplest formatter — the metadata dicts from extractors
are already JSON-ready (thanks to ydl.sanitize_info). This module
adds pretty-printing, optional field filtering, and file writing.
"""

from __future__ import annotations

import json
from pathlib import Path

from config import JSON_INDENT


class JsonFormatter:
    """
    Converts extractor output dicts into formatted JSON strings or files.

    Usage:
        fmt = JsonFormatter()
        json_str = fmt.format(metadata)
        fmt.save(metadata, "output.json")
    """

    def __init__(self, indent: int = JSON_INDENT, exclude_raw: bool = True):
        """
        Args:
            indent:      JSON indentation spaces (2 = compact-ish, 4 = very readable)
            exclude_raw: If True, strip the large 'formats_raw' field to keep
                         output focused on the summary. Set False to keep everything.
        """
        self.indent = indent
        self.exclude_raw = exclude_raw

    def format(self, data: dict | list) -> str:
        """
        Serialize data to a JSON string.

        Handles both single video dicts and lists (for batch output).
        """
        cleaned = self._clean(data)
        return json.dumps(cleaned, indent=self.indent, ensure_ascii=False)

    def save(self, data: dict | list, path: str | Path) -> Path:
        """
        Write formatted JSON to a file.

        Args:
            data: The metadata dict or list
            path: Output file path

        Returns:
            The Path object of the written file
        """
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        json_str = self.format(data)
        output_path.write_text(json_str, encoding="utf-8")

        return output_path

    def _clean(self, data: dict | list) -> dict | list:
        """
        Optionally remove large/redundant fields before serialization.

        'formats_raw' contains a huge list of all available format objects
        from yt-dlp. The summary in 'formats_summary' covers the key info,
        so we drop 'formats_raw' by default to keep output manageable.
        """
        if not self.exclude_raw:
            return data

        if isinstance(data, list):
            return [self._clean_dict(item) for item in data]
        if isinstance(data, dict):
            return self._clean_dict(data)
        return data

    def _clean_dict(self, d: dict) -> dict:
        """Remove verbose raw fields from a single metadata dict."""
        # Fields to drop from single-video output
        FIELDS_TO_DROP = {
            "formats_raw",
            "thumbnails_all",
        }

        return {k: v for k, v in d.items() if k not in FIELDS_TO_DROP}
