"""
test_video_extractor.py
-----------------------
Unit tests for VideoExtractor's metadata shaping (no network required).

Regression: _shape_metadata once referenced comments_max without receiving it,
making every single-video extraction crash with NameError.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
from extractor.video_extractor import VideoExtractor


class TestShapeMetadata(unittest.TestCase):
    def setUp(self):
        self.extractor = VideoExtractor()

    def test_shape_minimal_raw_does_not_crash(self):
        result = self.extractor._shape_metadata(
            {"id": "dQw4w9WgXcQ", "title": "Test"},
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        self.assertEqual(result["id"], "dQw4w9WgXcQ")
        self.assertEqual(result["comments"], [])
        self.assertEqual(result["comments_fetched"], 0)

    def test_comments_max_caps_shaped_comments(self):
        raw = {
            "id": "x",
            "comments": [{"id": str(i), "text": f"c{i}"} for i in range(5)],
        }
        result = self.extractor._shape_metadata(raw, "url", comments_max=3)
        self.assertEqual(len(result["comments"]), 3)
        self.assertEqual(result["comments_fetched"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
