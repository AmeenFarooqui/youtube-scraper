"""
markdown_formatter.py
---------------------
Generates human-readable Markdown reports from YouTube metadata.

WHY MARKDOWN?
  JSON is great for machines. Markdown is great for humans.
  A Markdown report can be:
    - Read directly in terminal
    - Rendered in GitHub, VS Code, Obsidian, etc.
    - Pasted into documentation
    - Converted to HTML or PDF

REPORT SECTIONS:
  For single video:
    1. Video Overview
    2. Channel Information
    3. Statistics
    4. Classification (tags, categories)
    5. Available Formats
    6. Subtitles
    7. Chapters
    8. Availability Status
    9. Extraction Notes

  For playlist:
    1. Playlist Overview
    2. Summary Statistics
    3. Video List
    4. Unavailable Videos
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime

from utils.helpers import (
    format_number,
    format_duration,
    seconds_to_hms,
    safe_get,
    truncate,
    flatten_list,
)


class MarkdownFormatter:
    """
    Generates Markdown reports from video or playlist metadata.

    Usage:
        fmt = MarkdownFormatter()
        md = fmt.format_video(metadata)
        md = fmt.format_playlist(playlist_metadata)

        fmt.save(md, "report.md")
    """

    # ── Public API ────────────────────────────────────────────────────────────

    def format_video(self, data: dict) -> str:
        """Generate a full Markdown report for a single video."""
        sections = [
            self._header_section(data),
            self._stats_section(data),
            self._channel_section(data),
            self._classification_section(data),
            self._formats_section(data),
            self._subtitles_section(data),
            self._chapters_section(data),
            self._availability_section(data),
            self._footer(),
        ]
        return "\n\n".join(s for s in sections if s)

    def format_playlist(self, data: dict) -> str:
        """Generate a full Markdown report for a playlist."""
        sections = [
            self._playlist_header(data),
            self._playlist_summary(data),
            self._playlist_video_table(data),
            self._playlist_errors(data),
            self._footer(),
        ]
        return "\n\n".join(s for s in sections if s)

    def format_batch(self, results: list[dict]) -> str:
        """Generate a summary Markdown report for batch results."""
        lines = [
            "# Batch Scrape Results",
            f"**Total URLs processed:** {len(results)}",
            "",
        ]

        successful = [r for r in results if not r.get("error")]
        failed = [r for r in results if r.get("error")]

        lines.append(f"**Successful:** {len(successful)}  |  **Failed:** {len(failed)}")
        lines.append("")

        if successful:
            lines.append("## Results")
            lines.append("")
            lines.append("| # | Title | Channel | Duration | Views | Upload Date |")
            lines.append("|---|-------|---------|----------|-------|-------------|")
            for i, r in enumerate(successful, 1):
                title = (r.get("title") or "Unknown")[:60].replace("|", "\\|").replace("\n", " ")
                channel = (r.get("channel") or "Unknown")[:30].replace("|", "\\|").replace("\n", " ")
                duration = r.get("duration_string", "N/A")
                views = format_number(r.get("view_count"))
                date = r.get("upload_date_formatted", "Unknown")
                url = r.get("webpage_url", r.get("url", ""))
                lines.append(f"| {i} | [{title}]({url}) | {channel} | {duration} | {views} | {date} |")

        if failed:
            lines.append("")
            lines.append("## Failed URLs")
            lines.append("")
            for r in failed:
                lines.append(f"- **{r.get('url', 'Unknown URL')}**: {r.get('message', 'Unknown error')}")

        lines.append("")
        lines.append(self._footer())
        return "\n".join(lines)

    def save(self, content: str, path: str | Path) -> Path:
        """Write Markdown content to a file."""
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        return output_path

    @staticmethod
    def _cell(text: str | None, max_len: int = 0) -> str:
        """Escape user-controlled text for safe use inside a Markdown table cell."""
        s = str(text) if text is not None else ""
        if max_len:
            s = s[:max_len]
        return s.replace("|", "\\|").replace("\n", " ")

    # ── Video report sections ─────────────────────────────────────────────────

    def _header_section(self, d: dict) -> str:
        title = d.get("title") or "Unknown Title"
        url = d.get("webpage_url") or d.get("url") or ""
        video_id = d.get("id") or ""
        upload_date = d.get("upload_date_formatted") or "Unknown"
        duration = d.get("duration_string") or d.get("duration_formatted") or "Unknown"
        lang = d.get("language") or "Unknown"
        age = d.get("age_limit") or 0

        thumbnail = d.get("thumbnail") or ""
        thumb_line = f"\n![]({thumbnail})\n" if thumbnail else ""

        desc = truncate(d.get("description") or "", 500)
        desc_block = f"\n> {desc.replace(chr(10), chr(10) + '> ')}" if desc else ""

        return f"""# {title}
{thumb_line}
| Field | Value |
|-------|-------|
| **Video ID** | `{video_id}` |
| **URL** | [{url}]({url}) |
| **Upload Date** | {upload_date} |
| **Duration** | {duration} |
| **Language** | {lang} |
| **Age Restriction** | {'Yes (' + str(age) + '+)' if age else 'No'} |

## Description
{desc_block if desc_block else "_No description available._"}"""

    def _stats_section(self, d: dict) -> str:
        views = d.get("view_count_formatted") or format_number(d.get("view_count"))
        likes = d.get("like_count_formatted") or format_number(d.get("like_count"))
        comments = d.get("comment_count_formatted") or format_number(d.get("comment_count"))
        rating = d.get("average_rating")

        rating_line = f"| **Average Rating** | {rating:.2f} |" if rating else ""

        return f"""## Statistics

| Metric | Value |
|--------|-------|
| **Views** | {views} |
| **Likes** | {likes} |
| **Comments** | {comments} |
{rating_line}"""

    def _channel_section(self, d: dict) -> str:
        channel = self._cell(d.get("channel") or d.get("uploader") or "Unknown")
        channel_id = d.get("channel_id") or "Unknown"
        channel_url = d.get("channel_url") or d.get("uploader_url") or ""
        subscribers = d.get("channel_follower_count_formatted") or format_number(d.get("channel_follower_count"))
        uploader = self._cell(d.get("uploader") or "Unknown")

        channel_link = f"[{channel}]({channel_url})" if channel_url else channel

        return f"""## Channel Information

| Field | Value |
|-------|-------|
| **Channel** | {channel_link} |
| **Channel ID** | `{channel_id}` |
| **Uploader** | {uploader} |
| **Subscribers** | {subscribers} |"""

    def _classification_section(self, d: dict) -> str:
        tags = d.get("tags") or []
        categories = d.get("categories") or []

        tags_str = ", ".join(f"`{t}`" for t in tags[:30]) or "_None_"
        cats_str = ", ".join(categories) or "_None_"

        return f"""## Classification

**Categories:** {cats_str}

**Tags ({len(tags)}):** {tags_str}"""

    def _formats_section(self, d: dict) -> str:
        summary = d.get("formats_summary") or {}
        if not summary:
            return "## Available Formats\n\n_Format data not available._"

        total = summary.get("total_formats", 0)
        video_count = summary.get("video_only_count", 0)
        audio_count = summary.get("audio_only_count", 0)
        combined_count = summary.get("combined_count", 0)
        extensions = ", ".join(sorted(summary.get("available_extensions") or []))

        lines = [
            "## Available Formats",
            "",
            f"| Type | Count |",
            f"|------|-------|",
            f"| **Total Formats** | {total} |",
            f"| Video-only streams | {video_count} |",
            f"| Audio-only streams | {audio_count} |",
            f"| Combined (video+audio) | {combined_count} |",
            f"| Available containers | {extensions} |",
        ]

        # Best video format
        best = summary.get("best_video_format")
        if best:
            lines += [
                "",
                "### Best Video Format",
                "",
                f"| Field | Value |",
                f"|-------|-------|",
                f"| Resolution | {best.get('resolution', 'N/A')} |",
                f"| FPS | {best.get('fps', 'N/A')} |",
                f"| Video Codec | {best.get('vcodec', 'N/A')} |",
                f"| Audio Codec | {best.get('acodec', 'N/A')} |",
                f"| Container | {best.get('ext', 'N/A')} |",
                f"| Est. Size | {best.get('filesize_formatted', 'N/A')} |",
            ]

        return "\n".join(lines)

    def _subtitles_section(self, d: dict) -> str:
        summary = d.get("subtitles_summary") or {}

        manual_langs = d.get("subtitles_manual") or summary.get("manual_languages") or []
        auto_langs = d.get("subtitles_auto") or summary.get("auto_caption_languages") or []

        manual_str = ", ".join(manual_langs) if manual_langs else "_None_"
        auto_str = ", ".join(auto_langs[:20]) if auto_langs else "_None_"  # Cap auto to 20

        return f"""## Subtitles & Captions

| Type | Languages |
|------|-----------|
| **Manual Subtitles** | {manual_str} |
| **Auto-generated Captions** | {auto_str} |"""

    def _chapters_section(self, d: dict) -> str:
        chapters = d.get("chapters") or []
        if not chapters:
            return "## Chapters\n\n_This video has no chapters._"

        lines = [
            "## Chapters",
            "",
            f"_{len(chapters)} chapters_",
            "",
            "| # | Title | Start |",
            "|---|-------|-------|",
        ]
        for i, ch in enumerate(chapters, 1):
            ch_title = (ch.get("title") or f"Chapter {i}").replace("|", "\\|").replace("\n", " ")
            start = seconds_to_hms(ch.get("start_time", 0))
            lines.append(f"| {i} | {ch_title} | {start} |")

        return "\n".join(lines)

    def _availability_section(self, d: dict) -> str:
        availability = d.get("availability") or "Unknown"
        live_status = d.get("live_status") or "not_live"

        live_display = {
            "not_live": "Not a live stream",
            "is_live": "CURRENTLY LIVE",
            "was_live": "Was a live stream (archived)",
            "is_upcoming": "Upcoming premiere/livestream",
            "post_live": "Post-live",
        }.get(live_status, live_status)

        return f"""## Availability

| Field | Value |
|-------|-------|
| **Privacy Status** | {availability.title()} |
| **Live Status** | {live_display} |"""

    # ── Playlist report sections ──────────────────────────────────────────────

    def _playlist_header(self, d: dict) -> str:
        title = d.get("title") or "Unknown Playlist"
        url = d.get("webpage_url") or d.get("url") or ""
        uploader = self._cell(d.get("uploader") or "Unknown")
        total = d.get("total_videos", 0)
        available = d.get("available_videos", 0)
        unavailable = d.get("unavailable_videos", 0)

        return f"""# Playlist: {title}

| Field | Value |
|-------|-------|
| **URL** | [{url}]({url}) |
| **Uploader** | {uploader} |
| **Total Videos** | {total} |
| **Available** | {available} |
| **Unavailable** | {unavailable} |"""

    def _playlist_summary(self, d: dict) -> str:
        s = d.get("summary") or {}
        if not s:
            return ""

        return f"""## Playlist Summary

| Metric | Value |
|--------|-------|
| **Total Duration** | {s.get("total_duration_formatted", "N/A")} |
| **Average Duration** | {s.get("average_duration_formatted", "N/A")} |
| **Total Views** | {s.get("total_views_formatted", "N/A")} |
| **Earliest Upload** | {s.get("earliest_upload", "N/A")} |
| **Latest Upload** | {s.get("latest_upload", "N/A")} |
| **Shortest Video** | {self._cell((s.get("shortest_video") or {}).get("title", "N/A"))} ({(s.get("shortest_video") or {}).get("duration", "N/A")}) |
| **Longest Video** | {self._cell((s.get("longest_video") or {}).get("title", "N/A"))} ({(s.get("longest_video") or {}).get("duration", "N/A")}) |"""

    def _playlist_video_table(self, d: dict) -> str:
        videos = d.get("videos") or []
        if not videos:
            return "## Videos\n\n_No videos available._"

        lines = [
            "## Videos",
            "",
            "| # | Title | Duration | Views | Upload Date |",
            "|---|-------|----------|-------|-------------|",
        ]

        for v in videos:
            pos = v.get("position", "?")
            title = (v.get("title") or "Unknown")[:60].replace("|", "\\|").replace("\n", " ")
            url = v.get("url") or ""
            duration = v.get("duration_string", "N/A")
            views = format_number(v.get("view_count"))
            date = v.get("upload_date_formatted", "Unknown")
            title_link = f"[{title}]({url})" if url else title
            lines.append(f"| {pos} | {title_link} | {duration} | {views} | {date} |")

        return "\n".join(lines)

    def _playlist_errors(self, d: dict) -> str:
        errors = d.get("errors") or []
        if not errors:
            return ""

        lines = [
            "## Unavailable Videos",
            "",
            f"_{len(errors)} video(s) could not be accessed:_",
            "",
        ]
        for e in errors:
            pos = e.get("position", "?")
            msg = e.get("error", "Unknown reason")
            url = e.get("url") or ""
            url_part = f" — {url}" if url else ""
            lines.append(f"- **Position {pos}**: {msg}{url_part}")

        return "\n".join(lines)

    # ── Footer ────────────────────────────────────────────────────────────────

    def _footer(self) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"---\n_Report generated on {now} using youtube-scraper (yt-dlp)_"
