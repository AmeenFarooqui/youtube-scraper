"""
test_helpers.py
---------------
Unit tests for helper functions.

These functions have no external dependencies so they're fast and reliable.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
from utils.helpers import (
    seconds_to_hms,
    format_duration,
    format_number,
    format_filesize,
    format_date,
    safe_get,
    safe_filename,
    truncate,
)


class TestSecondsToHms(unittest.TestCase):

    def test_under_one_minute(self):
        self.assertEqual(seconds_to_hms(45), "0:45")

    def test_one_minute_thirty(self):
        self.assertEqual(seconds_to_hms(90), "1:30")

    def test_one_hour(self):
        self.assertEqual(seconds_to_hms(3600), "1:00:00")

    def test_one_hour_one_minute_one_second(self):
        self.assertEqual(seconds_to_hms(3661), "1:01:01")

    def test_none_returns_unknown(self):
        self.assertEqual(seconds_to_hms(None), "Unknown")

    def test_zero(self):
        self.assertEqual(seconds_to_hms(0), "0:00")


class TestFormatNumber(unittest.TestCase):

    def test_billions(self):
        self.assertEqual(format_number(1_234_567_890), "1.23B")

    def test_millions(self):
        self.assertEqual(format_number(1_500_000), "1.50M")

    def test_thousands(self):
        self.assertEqual(format_number(50_000), "50.0K")

    def test_under_thousand(self):
        self.assertEqual(format_number(999), "999")

    def test_none(self):
        self.assertEqual(format_number(None), "N/A")

    def test_zero(self):
        self.assertEqual(format_number(0), "0")


class TestFormatFilesize(unittest.TestCase):

    def test_gigabyte(self):
        self.assertIn("GB", format_filesize(2 * 1024 ** 3))

    def test_megabyte(self):
        self.assertIn("MB", format_filesize(5 * 1024 ** 2))

    def test_zero(self):
        self.assertEqual(format_filesize(0), "0 B")

    def test_none(self):
        self.assertEqual(format_filesize(None), "N/A")


class TestFormatDate(unittest.TestCase):

    def test_valid_date(self):
        self.assertEqual(format_date("20231215"), "December 15, 2023")

    def test_none(self):
        self.assertEqual(format_date(None), "Unknown")

    def test_invalid_format(self):
        result = format_date("not-a-date")
        self.assertIsNotNone(result)  # Should not crash


class TestSafeGet(unittest.TestCase):

    def test_simple_key(self):
        d = {"a": 1}
        self.assertEqual(safe_get(d, "a"), 1)

    def test_missing_key_returns_default(self):
        d = {"a": 1}
        self.assertIsNone(safe_get(d, "b"))

    def test_custom_default(self):
        d = {"a": 1}
        self.assertEqual(safe_get(d, "b", default="N/A"), "N/A")

    def test_nested_missing(self):
        d = {"a": {"b": 1}}
        self.assertIsNone(safe_get(d, "a", "c"))

    def test_none_dict(self):
        self.assertIsNone(safe_get(None, "key"))

    def test_list_index(self):
        d = {"items": ["x", "y", "z"]}
        self.assertEqual(safe_get(d, "items", 1), "y")

    def test_list_out_of_bounds(self):
        d = {"items": ["x"]}
        self.assertIsNone(safe_get(d, "items", 99))


class TestSafeFilename(unittest.TestCase):

    def test_normal_string(self):
        result = safe_filename("My Video Title")
        self.assertIn("My", result)
        self.assertNotIn(" ", result)

    def test_removes_illegal_chars(self):
        result = safe_filename('Video: "Part 1" <test>')
        for illegal in [':', '"', '<', '>']:
            self.assertNotIn(illegal, result)

    def test_max_length(self):
        long_name = "a" * 500
        result = safe_filename(long_name, max_length=100)
        self.assertLessEqual(len(result), 100)

    def test_empty_becomes_untitled(self):
        self.assertEqual(safe_filename(""), "untitled")


class TestTruncate(unittest.TestCase):

    def test_short_string_unchanged(self):
        self.assertEqual(truncate("hello", 100), "hello")

    def test_long_string_truncated(self):
        result = truncate("a" * 600, 500)
        self.assertLessEqual(len(result), 510)  # Account for "..."
        self.assertTrue(result.endswith("..."))

    def test_none(self):
        self.assertEqual(truncate(None), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
