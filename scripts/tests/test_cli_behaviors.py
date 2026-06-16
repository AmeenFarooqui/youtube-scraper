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


class TestRunOrdered(unittest.TestCase):
    """Tests for the _run_ordered concurrent ordered-map helper."""

    def test_results_in_original_order(self):
        import time, random

        def slow_fn(index_item):
            i, val = index_item
            time.sleep(random.uniform(0, 0.02))
            return i, val * 10

        results = youtube_scraper._run_ordered([1, 2, 3, 4, 5], workers=5, fn=slow_fn)
        self.assertEqual(results, [10, 20, 30, 40, 50])

    def test_all_items_processed(self):
        def identity(index_item):
            i, val = index_item
            return i, val

        results = youtube_scraper._run_ordered(["a", "b", "c"], workers=2, fn=identity)
        self.assertEqual(results, ["a", "b", "c"])

    def test_empty_input(self):
        results = youtube_scraper._run_ordered([], workers=4, fn=lambda x: x)
        self.assertEqual(results, [])


class TestPostProcessItems(unittest.TestCase):
    """Tests for _post_process_items — verifies call order and parameter routing."""

    def _args(self, **kwargs):
        defaults = dict(
            comments=False, dislikes=False, sentiment=False,
            no_shorts=False, shorts_only=False, workers=2,
            filter_min_views=None, filter_max_views=None,
            filter_min_likes=None, filter_max_likes=None,
            filter_min_subscribers=None, filter_max_subscribers=None,
            filter_min_dislikes=None, filter_max_dislikes=None,
            filter_min_positive_ratio=None, filter_min_negative_ratio=None,
            sort_by=None, sort_order="desc",
        )
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    @patch("youtube_scraper._apply_sort", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_engagement_filters", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_shorts_filter", side_effect=lambda items, _: items)
    def test_defaults_run_shorts_filter_and_pass_through(self, mock_s, mock_f, mock_sort):
        items = [{"id": "a"}]
        result = youtube_scraper._post_process_items(items, self._args())
        mock_s.assert_called_once()
        mock_f.assert_called_once()
        mock_sort.assert_called_once()
        self.assertEqual(result, items)

    @patch("youtube_scraper._apply_sort", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_engagement_filters", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_shorts_filter", side_effect=lambda items, _: items)
    @patch("youtube_scraper._fetch_full_metadata", side_effect=lambda items, _: items)
    def test_fetch_comments_true_with_comments_calls_fetch(self, mock_fetch, *_):
        youtube_scraper._post_process_items([{"id": "a"}], self._args(comments=True), fetch_comments=True)
        mock_fetch.assert_called_once()

    @patch("youtube_scraper._apply_sort", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_engagement_filters", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_shorts_filter", side_effect=lambda items, _: items)
    @patch("youtube_scraper._fetch_full_metadata", side_effect=lambda items, _: items)
    def test_fetch_comments_false_never_fetches(self, mock_fetch, *_):
        youtube_scraper._post_process_items([{"id": "a"}], self._args(comments=True), fetch_comments=False)
        mock_fetch.assert_not_called()

    @patch("youtube_scraper._apply_sort", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_engagement_filters", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_shorts_filter", side_effect=lambda items, _: items)
    @patch("youtube_scraper._enrich_dislikes", side_effect=lambda items, **kw: items)
    def test_dislikes_enabled_calls_enrich(self, mock_enrich, *_):
        youtube_scraper._post_process_items([{"id": "a"}], self._args(dislikes=True))
        mock_enrich.assert_called_once()

    @patch("youtube_scraper._apply_sort", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_engagement_filters", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_shorts_filter", side_effect=lambda items, _: items)
    def test_apply_shorts_false_skips_filter(self, mock_s, *_):
        youtube_scraper._post_process_items([{"id": "a"}], self._args(), apply_shorts=False)
        mock_s.assert_not_called()

    @patch("youtube_scraper._apply_sort", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_engagement_filters", side_effect=lambda items, _: items)
    @patch("youtube_scraper._enrich_dislikes", side_effect=lambda items, **kw: items)
    @patch("youtube_scraper._apply_shorts_filter", side_effect=lambda items, _: items)
    def test_shorts_first_false_runs_after_dislikes(self, mock_s, mock_enrich, *_):
        """shorts_first=False means shorts filter executes after enrichment."""
        call_order = []
        mock_s.side_effect = lambda items, _: (call_order.append("shorts"), items)[1]
        mock_enrich.side_effect = lambda items, **kw: (call_order.append("dislikes"), items)[1]

        youtube_scraper._post_process_items(
            [{"id": "a"}], self._args(dislikes=True),
            apply_shorts=True, shorts_first=False,
        )
        self.assertEqual(call_order, ["dislikes", "shorts"])


if __name__ == "__main__":
    unittest.main()
