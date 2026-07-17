"""
test_formatters.py
------------------
Unit tests for JSON, CSV, and Markdown formatters.

These use mock data (no network calls) so they run instantly.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
import unittest
from formatter import JsonFormatter, CsvFormatter, MarkdownFormatter


# ── Shared test fixture ───────────────────────────────────────────────────────

def make_video_metadata(**overrides) -> dict:
    """Create a minimal but realistic metadata dict for testing."""
    base = {
        "id": "dQw4w9WgXcQ",
        "title": "Rick Astley - Never Gonna Give You Up (Official Video)",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "upload_date": "20091024",
        "upload_date_formatted": "October 24, 2009",
        "duration": 213,
        "duration_string": "3:33",
        "duration_formatted": "3 min 33 sec",
        "description": "Rick Astley's official music video for Never Gonna Give You Up.",
        "description_short": "Rick Astley's official music video.",
        "language": "en",
        "age_limit": 0,
        "channel": "RickAstleyVEVO",
        "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
        "channel_url": "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
        "uploader": "RickAstleyVEVO",
        "uploader_id": "RickAstleyVEVO",
        "uploader_url": "https://www.youtube.com/@RickAstleyVEVO",
        "channel_follower_count": 3_100_000,
        "channel_follower_count_formatted": "3.10M",
        "view_count": 1_500_000_000,
        "view_count_formatted": "1.50B",
        "like_count": 15_000_000,
        "like_count_formatted": "15.00M",
        "comment_count": 2_500_000,
        "comment_count_formatted": "2.50M",
        "average_rating": None,
        "tags": ["rick astley", "never gonna give you up", "rickroll"],
        "tags_string": "rick astley, never gonna give you up, rickroll",
        "categories": ["Music"],
        "categories_string": "Music",
        "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
        "thumbnails_all": [],
        "formats_summary": {
            "total_formats": 20,
            "video_only_count": 8,
            "audio_only_count": 5,
            "combined_count": 7,
            "available_extensions": ["mp4", "webm", "m4a"],
            "best_video_format": {
                "resolution": "1920x1080",
                "fps": 30,
                "vcodec": "avc1",
                "acodec": "mp4a.40.2",
                "ext": "mp4",
                "filesize_formatted": "N/A",
            },
        },
        "thumbnails_all": [],  # Excluded by default in JsonFormatter
        "subtitles_summary": {
            "has_manual_subtitles": True,
            "has_auto_captions": True,
            "manual_languages": ["en"],
            "auto_caption_languages": ["en", "es", "fr"],
            "all_available_languages": ["en", "es", "fr"],
            "total_languages": 3,
        },
        "subtitles_manual": ["en"],
        "subtitles_auto": ["en", "es", "fr"],
        "chapters": [],
        "has_chapters": False,
        "chapter_count": 0,
        "heatmap": [],
        "availability": "public",
        "live_status": "not_live",
        "_extractor": "VideoExtractor",
        "_source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    }
    base.update(overrides)
    return base


class TestJsonFormatter(unittest.TestCase):

    def setUp(self):
        self.fmt = JsonFormatter()
        self.data = make_video_metadata()

    def test_output_is_valid_json(self):
        output = self.fmt.format(self.data)
        parsed = json.loads(output)
        self.assertIsInstance(parsed, dict)

    def test_title_preserved(self):
        output = json.loads(self.fmt.format(self.data))
        self.assertEqual(output["title"], self.data["title"])

    def test_thumbnails_all_excluded_by_default(self):
        output = json.loads(self.fmt.format(self.data))
        self.assertNotIn("thumbnails_all", output)

    def test_thumbnails_all_included_when_requested(self):
        fmt = JsonFormatter(exclude_raw=False)
        output = json.loads(fmt.format(self.data))
        self.assertIn("thumbnails_all", output)

    def test_list_input(self):
        output = self.fmt.format([self.data, self.data])
        parsed = json.loads(output)
        self.assertIsInstance(parsed, list)
        self.assertEqual(len(parsed), 2)

    def test_save_writes_file(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        saved = self.fmt.save(self.data, path)
        self.assertTrue(saved.exists())
        content = json.loads(saved.read_text())
        self.assertEqual(content["id"], "dQw4w9WgXcQ")


class TestCsvFormatter(unittest.TestCase):

    def setUp(self):
        self.fmt = CsvFormatter()
        self.data = make_video_metadata()

    def test_output_has_header(self):
        output = self.fmt.format(self.data)
        first_line = output.split("\n")[0]
        self.assertIn("title", first_line)

    def test_output_has_data_row(self):
        output = self.fmt.format(self.data)
        lines = [l for l in output.split("\n") if l.strip()]
        self.assertGreater(len(lines), 1)  # At least header + 1 data row

    def test_tags_flattened(self):
        output = self.fmt.format(self.data)
        # Tags should be joined (no Python list syntax in CSV)
        self.assertNotIn("[", output)

    def test_format_many(self):
        output = self.fmt.format_many([self.data, self.data])
        lines = [l for l in output.split("\n") if l.strip()]
        self.assertEqual(len(lines), 3)  # header + 2 rows


class TestMarkdownFormatter(unittest.TestCase):

    def setUp(self):
        self.fmt = MarkdownFormatter()
        self.data = make_video_metadata()

    def test_output_starts_with_title(self):
        output = self.fmt.format_video(self.data)
        self.assertTrue(output.startswith("# "))

    def test_output_contains_key_sections(self):
        output = self.fmt.format_video(self.data)
        self.assertIn("## Statistics", output)
        self.assertIn("## Channel Information", output)
        self.assertIn("## Available Formats", output)
        self.assertIn("## Subtitles", output)

    def test_output_contains_video_title(self):
        output = self.fmt.format_video(self.data)
        self.assertIn("Rick Astley", output)

    def test_output_contains_view_count(self):
        output = self.fmt.format_video(self.data)
        self.assertIn("1.50B", output)

    def test_playlist_report(self):
        playlist_data = {
            "id": "PL123",
            "title": "Test Playlist",
            "url": "https://youtube.com/playlist?list=PL123",
            "webpage_url": "https://youtube.com/playlist?list=PL123",
            "uploader": "Test Channel",
            "total_videos": 3,
            "available_videos": 2,
            "unavailable_videos": 1,
            "videos": [
                {
                    "position": 1,
                    "title": "Video 1",
                    "url": "https://youtube.com/watch?v=abc",
                    "duration": 300,
                    "duration_string": "5:00",
                    "view_count": 1000,
                    "upload_date_formatted": "January 01, 2024",
                },
            ],
            "errors": [{"position": 2, "error": "Video unavailable", "url": None}],
            "summary": {
                "total_duration_formatted": "5:00",
                "average_duration_formatted": "5:00",
                "total_views_formatted": "1.0K",
                "earliest_upload": "January 01, 2024",
                "latest_upload": "January 01, 2024",
                "shortest_video": {"title": "Video 1", "duration": "5:00"},
                "longest_video": {"title": "Video 1", "duration": "5:00"},
            },
        }
        output = self.fmt.format_playlist(playlist_data)
        self.assertIn("# Playlist:", output)
        self.assertIn("Test Playlist", output)
        self.assertIn("## Videos", output)


class TestMarkdownPipeEscaping(unittest.TestCase):
    """Finding 32: pipe characters in user-controlled fields must not break tables."""

    def setUp(self):
        self.fmt = MarkdownFormatter()

    def test_batch_title_with_pipe_escaped(self):
        data = make_video_metadata(title="Part 1 | Part 2", channel="Chan|nel")
        output = self.fmt.format_batch([data])
        self.assertIn("Part 1 \\| Part 2", output)
        self.assertIn("Chan\\|nel", output)

    def test_playlist_summary_shortest_title_escaped(self):
        playlist_data = {
            "id": "PL1",
            "title": "Test",
            "url": "https://youtube.com/playlist?list=PL1",
            "webpage_url": "https://youtube.com/playlist?list=PL1",
            "uploader": "Chan|nel",
            "total_videos": 1,
            "available_videos": 1,
            "unavailable_videos": 0,
            "videos": [],
            "errors": [],
            "summary": {
                "total_duration_formatted": "5:00",
                "average_duration_formatted": "5:00",
                "total_views_formatted": "1K",
                "earliest_upload": "Jan 2024",
                "latest_upload": "Jan 2024",
                "shortest_video": {"title": "A | B video", "duration": "1:00"},
                "longest_video": {"title": "C | D video", "duration": "5:00"},
            },
        }
        output = self.fmt.format_playlist(playlist_data)
        self.assertIn("A \\| B video", output)
        self.assertIn("C \\| D video", output)
        self.assertIn("Chan\\|nel", output)

    def test_channel_section_escapes_pipe(self):
        data = make_video_metadata(channel="A|B Channel", uploader="Up|loader")
        output = self.fmt.format_video(data)
        self.assertIn("A\\|B Channel", output)
        self.assertIn("Up\\|loader", output)


class TestEngagementFilterWarning(unittest.TestCase):
    """Finding 11: warn when likes/subscriber filters applied to stubs with None fields."""

    def _make_args(self, **kwargs):
        import argparse
        defaults = dict(
            filter_min_views=None, filter_max_views=None,
            filter_min_likes=None, filter_max_likes=None,
            filter_min_subscribers=None, filter_max_subscribers=None,
            filter_min_dislikes=None, filter_max_dislikes=None,
            filter_min_positive_ratio=None, filter_min_negative_ratio=None,
        )
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_warning_emitted_for_likes_filter_on_stubs(self):
        import youtube_scraper
        items = [
            {"title": "A", "like_count": None},
            {"title": "B", "like_count": None},
        ]
        args = self._make_args(filter_min_likes=100)
        with self.assertLogs("youtube_scraper", level="WARNING") as cm:
            result = youtube_scraper._apply_engagement_filters(items, args)
        self.assertTrue(any("like_count" in msg for msg in cm.output))
        self.assertEqual(result, [])

    def test_no_warning_when_field_present(self):
        import youtube_scraper
        import logging
        items = [
            {"title": "A", "like_count": 500},
            {"title": "B", "like_count": 50},
        ]
        args = self._make_args(filter_min_likes=100)
        with self.assertLogs("youtube_scraper", level="WARNING") as cm:
            # Emit a sentinel so assertLogs doesn't fail if no other warnings appear
            logging.getLogger("youtube_scraper").warning("sentinel")
            result = youtube_scraper._apply_engagement_filters(items, args)
        stub_warnings = [m for m in cm.output if "like_count" in m]
        self.assertEqual(stub_warnings, [])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "A")


if __name__ == "__main__":
    unittest.main(verbosity=2)
