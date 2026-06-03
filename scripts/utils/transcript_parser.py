"""
transcript_parser.py
--------------------
Parse subtitle files (SRT, VTT, ASS) into clean plain text.

SRT format:
  1
  00:00:01,000 --> 00:00:04,000
  Hello, world.

VTT format:
  WEBVTT

  00:00:01.000 --> 00:00:04.000
  Hello, world.

We strip sequence numbers, timestamps, HTML/VTT tags, and deduplicate
repeated lines (YouTube auto-captions frequently repeat the same text).
Returns a single clean string suitable for reading or embedding in reports.
"""

from __future__ import annotations

import re
from pathlib import Path


# ── Regex patterns ────────────────────────────────────────────────────────────

_SRT_TIMESTAMP = re.compile(r"^\d{1,2}:\d{2}:\d{2}[,\.]\d+ -->")
_VTT_TIMESTAMP = re.compile(r"^\d{1,2}:\d{2}:\d{2}[\.,]\d+ -->|^\d{2}:\d{2}[\.,]\d+ -->")
_SEQUENCE_NUM  = re.compile(r"^\d+$")
_HTML_TAGS     = re.compile(r"<[^>]+>")
_VTT_HEADERS   = re.compile(r"^(WEBVTT|NOTE|STYLE|REGION)(\s|$)")
_CUE_SETTINGS  = re.compile(r"^(align|position|size|line|vertical):\S+")


def parse_srt(text: str) -> str:
    """Parse SRT subtitle content into clean plain text."""
    cleaned: list[str] = []
    seen: set[str] = set()

    for line in text.splitlines():
        line = line.strip()
        if not line or _SEQUENCE_NUM.match(line) or _SRT_TIMESTAMP.match(line):
            continue
        line = _HTML_TAGS.sub("", line).strip()
        if line and line not in seen:
            seen.add(line)
            cleaned.append(line)

    return " ".join(cleaned)


def parse_vtt(text: str) -> str:
    """Parse WebVTT subtitle content into clean plain text."""
    cleaned: list[str] = []
    seen: set[str] = set()
    in_header_block = False

    for line in text.splitlines():
        line = line.strip()
        if not line:
            in_header_block = False
            continue
        if _VTT_HEADERS.match(line):
            in_header_block = True
            continue
        if in_header_block or _VTT_TIMESTAMP.match(line) or _CUE_SETTINGS.match(line):
            continue
        line = _HTML_TAGS.sub("", line).strip()
        if line and line not in seen:
            seen.add(line)
            cleaned.append(line)

    return " ".join(cleaned)


def _parse_ass(text: str) -> str:
    """Basic ASS/SSA parser — extracts Dialogue lines only."""
    lines = []
    for line in text.splitlines():
        if line.startswith("Dialogue:"):
            parts = line.split(",", 9)
            if len(parts) == 10:
                dialogue = re.sub(r"\{[^}]*\}", "", parts[9]).strip()
                if dialogue:
                    lines.append(dialogue)
    return " ".join(lines)


def parse_subtitle_file(path: str | Path) -> str:
    """
    Read a subtitle file and return clean plain text.

    Auto-detects format from file extension (.srt, .vtt, .ass).
    Returns an empty string if the file can't be read or parsed.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

    ext = path.suffix.lower().lstrip(".")
    if ext in ("vtt", "webvtt"):
        return parse_vtt(text)
    elif ext == "ass":
        return _parse_ass(text)
    else:
        return parse_srt(text)


def parse_subtitle_content(content: str, fmt: str = "srt") -> str:
    """
    Parse subtitle content from a string (not a file).

    Args:
        content: Raw subtitle text
        fmt:     Format hint — "srt", "vtt", or "ass"
    """
    fmt = fmt.lower()
    if fmt in ("vtt", "webvtt"):
        return parse_vtt(content)
    elif fmt == "ass":
        return _parse_ass(content)
    else:
        return parse_srt(content)
