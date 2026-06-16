"""
Regression tests for CLI validation, batch handling, and format summaries.
"""

import argparse
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import youtube_scraper
from extractor.video_extractor import VideoExtractor


class TestBatchValidation(unittest.TestCase):

    @patch(
        "youtube_scraper.validate_batch_file",
        return_value=(
            True,
            "Loaded 2 URLs",
            [
                "https://www.youtube.com/playlist?list=PL123",
                "https://www.youtube.com/@example",
            ],
        ),
    )
    def test_all_non_video_batch_exits_with_failure(self, _validate):
        args = argparse.Namespace(batch="urls.txt", max_videos=None)

        with self.assertRaises(SystemExit) as raised:
            youtube_scraper.handle_batch(args)

        self.assertEqual(raised.exception.code, 1)


class TestCliRelationships(unittest.TestCase):

    def assert_cli_error(self, *arguments):
        with patch.object(sys, "argv", ["youtube_scraper.py", *arguments]):
            with self.assertRaises(SystemExit) as raised:
                youtube_scraper.main()
        self.assertEqual(raised.exception.code, 2)

    def test_transcript_requires_pipeline(self):
        self.assert_cli_error("--search", "topic", "--transcript")

    def test_download_subs_requires_subtitles(self):
        self.assert_cli_error(
            "--url",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "--download-subs",
        )

    def test_dislike_sort_requires_dislikes(self):
        self.assert_cli_error("--search", "topic", "--sort-by", "dislikes")

    def test_sentiment_sort_requires_sentiment(self):
        self.assert_cli_error("--search", "topic", "--sort-by", "positive_ratio")


class TestFormatSummary(unittest.TestCase):

    formats = [
        {
            "format_id": "audio",
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "mp4a",
            "abr": 128,
        },
        {
            "format_id": "720p",
            "ext": "mp4",
            "vcodec": "avc1",
            "acodec": "none",
            "width": 1280,
            "height": 720,
        },
        {
            "format_id": "1080p",
            "ext": "webm",
            "vcodec": "vp9",
            "acodec": "opus",
            "width": 1920,
            "height": 1080,
        },
    ]

    def test_default_summary_is_compact(self):
        summary = VideoExtractor()._analyze_formats(self.formats)

        self.assertEqual(summary["total_formats"], 3)
        self.assertEqual(summary["video_only_count"], 1)
        self.assertEqual(summary["audio_only_count"], 1)
        self.assertEqual(summary["combined_count"], 1)
        self.assertEqual(summary["best_video_format"]["format_id"], "1080p")
        self.assertNotIn("video_formats", summary)
        self.assertNotIn("audio_formats", summary)
        self.assertNotIn("combined_formats", summary)

    def test_detailed_summary_includes_stream_lists(self):
        summary = VideoExtractor(
            include_detailed_formats=True
        )._analyze_formats(self.formats)

        self.assertEqual(len(summary["video_formats"]), 1)
        self.assertEqual(len(summary["audio_formats"]), 1)
        self.assertEqual(len(summary["combined_formats"]), 1)

    def test_parser_exposes_detailed_formats_opt_in(self):
        args = youtube_scraper.build_parser().parse_args([
            "--url",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "--detailed-formats",
        ])

        self.assertTrue(args.detailed_formats)

    def test_compact_cache_hit_removes_legacy_stream_lists(self):
        cached = {
            "formats_summary": {
                "total_formats": 3,
                "video_formats": [{}],
                "audio_formats": [{}],
                "combined_formats": [{}],
            }
        }

        youtube_scraper._compact_format_summary(cached)

        self.assertEqual(cached["formats_summary"], {"total_formats": 3})


class TestResultItems(unittest.TestCase):
    """Tests for the _result_items(data) shape-normalizer."""

    def test_list_returned_as_is(self):
        items = [{"id": "a"}, {"id": "b"}]
        self.assertEqual(youtube_scraper._result_items(items), items)

    def test_search_extractor(self):
        data = {"_extractor": "SearchExtractor", "results": [{"id": "x"}]}
        self.assertEqual(youtube_scraper._result_items(data), [{"id": "x"}])

    def test_pipeline_extractor(self):
        data = {"_extractor": "PipelineExtractor", "videos": [{"id": "y"}]}
        self.assertEqual(youtube_scraper._result_items(data), [{"id": "y"}])

    def test_channel_extractor(self):
        data = {"_extractor": "ChannelExtractor", "videos": [{"id": "z"}]}
        self.assertEqual(youtube_scraper._result_items(data), [{"id": "z"}])

    def test_playlist_extractor(self):
        data = {"_extractor": "PlaylistExtractor", "videos": [{"id": "p"}]}
        self.assertEqual(youtube_scraper._result_items(data), [{"id": "p"}])

    def test_batch_queries_flattened(self):
        data = {
            "total_queries": 2,
            "queries": [
                {"results": [{"id": "a"}, {"id": "b"}]},
                {"videos": [{"id": "c"}]},
            ],
        }
        self.assertEqual([i["id"] for i in youtube_scraper._result_items(data)], ["a", "b", "c"])

    def test_single_video_dict(self):
        data = {"_extractor": "VideoExtractor", "id": "abc", "title": "T"}
        self.assertEqual(youtube_scraper._result_items(data), [data])

    def test_empty_list(self):
        self.assertEqual(youtube_scraper._result_items([]), [])


if __name__ == "__main__":
    unittest.main()
