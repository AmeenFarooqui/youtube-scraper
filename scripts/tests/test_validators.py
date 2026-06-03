"""
test_validators.py
------------------
Unit tests for URL validation logic.

Run with: python -m pytest tests/ -v
Or:        python tests/test_validators.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
from utils.validators import (
    detect_url_type,
    is_valid_youtube_url,
    extract_video_id,
    extract_playlist_id,
    validate_batch_file,
)


class TestDetectUrlType(unittest.TestCase):
    """Tests for detect_url_type()"""

    # ── Video URLs ────────────────────────────────────────────────────────────

    def test_standard_watch_url(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.assertEqual(detect_url_type(url), "video")

    def test_short_youtu_be_url(self):
        url = "https://youtu.be/dQw4w9WgXcQ"
        self.assertEqual(detect_url_type(url), "video")

    def test_shorts_url(self):
        url = "https://www.youtube.com/shorts/dQw4w9WgXcQ"
        self.assertEqual(detect_url_type(url), "video")

    def test_embed_url(self):
        url = "https://www.youtube.com/embed/dQw4w9WgXcQ"
        self.assertEqual(detect_url_type(url), "video")

    def test_url_without_https(self):
        url = "youtube.com/watch?v=dQw4w9WgXcQ"
        self.assertEqual(detect_url_type(url), "video")

    # ── Playlist URLs ─────────────────────────────────────────────────────────

    def test_playlist_url(self):
        url = "https://www.youtube.com/playlist?list=PLbpi6ZahtOH6Ar_3GPy3workVBHSmknAZB"
        self.assertEqual(detect_url_type(url), "playlist")

    def test_video_with_playlist_is_playlist(self):
        # When a URL has both v= and list=, we treat it as a playlist
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLbpi6ZahtOH6Ar_3GPy3workVBHSmknAZB"
        self.assertEqual(detect_url_type(url), "playlist")

    # ── Channel URLs ──────────────────────────────────────────────────────────

    def test_channel_handle_url(self):
        url = "https://www.youtube.com/@RickAstleyVEVO"
        self.assertEqual(detect_url_type(url), "channel")

    def test_channel_id_url(self):
        url = "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"
        self.assertEqual(detect_url_type(url), "channel")

    def test_channel_c_url(self):
        url = "https://www.youtube.com/c/RickAstleyVEVO"
        self.assertEqual(detect_url_type(url), "channel")

    # ── Invalid URLs ──────────────────────────────────────────────────────────

    def test_non_youtube_url(self):
        self.assertEqual(detect_url_type("https://vimeo.com/123456"), "unknown")

    def test_plain_string(self):
        self.assertEqual(detect_url_type("not a url"), "unknown")

    def test_empty_string(self):
        self.assertEqual(detect_url_type(""), "unknown")

    def test_google_url(self):
        self.assertEqual(detect_url_type("https://google.com"), "unknown")


class TestIsValidYoutubeUrl(unittest.TestCase):
    """Tests for is_valid_youtube_url()"""

    def test_valid_video(self):
        self.assertTrue(is_valid_youtube_url("https://youtube.com/watch?v=dQw4w9WgXcQ"))

    def test_valid_playlist(self):
        self.assertTrue(is_valid_youtube_url("https://www.youtube.com/playlist?list=PL123"))

    def test_valid_channel(self):
        self.assertTrue(is_valid_youtube_url("https://www.youtube.com/@handle"))

    def test_invalid(self):
        self.assertFalse(is_valid_youtube_url("https://twitter.com/video"))

    def test_empty(self):
        self.assertFalse(is_valid_youtube_url(""))


class TestExtractVideoId(unittest.TestCase):
    """Tests for extract_video_id()"""

    def test_watch_url(self):
        vid_id = extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(vid_id, "dQw4w9WgXcQ")

    def test_youtu_be(self):
        vid_id = extract_video_id("https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual(vid_id, "dQw4w9WgXcQ")

    def test_shorts(self):
        vid_id = extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ")
        self.assertEqual(vid_id, "dQw4w9WgXcQ")

    def test_invalid(self):
        self.assertIsNone(extract_video_id("https://google.com"))


class TestExtractPlaylistId(unittest.TestCase):
    """Tests for extract_playlist_id()"""

    def test_playlist_url(self):
        pl_id = extract_playlist_id(
            "https://www.youtube.com/playlist?list=PLbpi6ZahtOH6Ar_3GPy3workVBHSmknAZB"
        )
        self.assertEqual(pl_id, "PLbpi6ZahtOH6Ar_3GPy3workVBHSmknAZB")

    def test_watch_with_list(self):
        pl_id = extract_playlist_id(
            "https://www.youtube.com/watch?v=abc123&list=PLbpi6ZahtOH6Ar_3GPy3workVBHSmknAZB"
        )
        self.assertEqual(pl_id, "PLbpi6ZahtOH6Ar_3GPy3workVBHSmknAZB")

    def test_no_playlist(self):
        self.assertIsNone(extract_playlist_id("https://youtube.com/watch?v=dQw4w9WgXcQ"))


if __name__ == "__main__":
    # Can also run directly: python tests/test_validators.py
    unittest.main(verbosity=2)
