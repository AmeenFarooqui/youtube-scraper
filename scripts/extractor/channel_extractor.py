"""
channel_extractor.py
--------------------
Extracts videos from a YouTube channel, scoped to a specific tab.

CHANNEL TABS:
  videos   → regular uploaded videos (default)
  shorts   → YouTube Shorts only
  streams  → past live streams / premieres
  all      → fetches all three tabs and merges them into one flat list

HOW IT WORKS:
  yt-dlp natively handles tab URLs as playlist-like objects:
    https://www.youtube.com/@mkbhd/videos
    https://www.youtube.com/@mkbhd/shorts
    https://www.youtube.com/@mkbhd/streams

  We normalize the input channel URL, append the tab suffix, then delegate
  to PlaylistExtractor (which already handles flat/full extraction modes,
  max_videos limits, and error handling).

USAGE:
    extractor = ChannelExtractor(tab="shorts", max_videos=50)
    result = extractor.extract("https://www.youtube.com/@mkbhd")
"""

from __future__ import annotations

import re
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.logger import get_logger
from utils.error_handler import ScraperError
from .playlist_extractor import PlaylistExtractor

logger = get_logger(__name__)

VALID_TABS = ("videos", "shorts", "streams", "all")


def _normalize_channel_url(url: str) -> str:
    """
    Ensure the channel URL is absolute and strip any trailing tab suffix.

    Examples:
        "@mkbhd"                                  → "https://www.youtube.com/@mkbhd"
        "youtube.com/@mkbhd"                      → "https://www.youtube.com/@mkbhd"
        "https://www.youtube.com/@mkbhd/videos"   → "https://www.youtube.com/@mkbhd"
        "https://www.youtube.com/channel/UCxxx"   → unchanged
    """
    url = url.strip()

    # Strip any existing /videos /shorts /streams suffix
    url = re.sub(r"/(videos|shorts|streams)\s*$", "", url, flags=re.IGNORECASE)

    # Make relative @handle absolute
    if url.startswith("@"):
        url = f"https://www.youtube.com/{url}"
    elif not url.startswith("http"):
        url = f"https://www.{url}" if url.startswith("youtube") else f"https://www.youtube.com/{url}"

    return url.rstrip("/")


def _tab_url(channel_url: str, tab: str) -> str:
    """Append a tab path to a channel URL."""
    return f"{channel_url}/{tab}"


class ChannelExtractor:
    """
    Extracts videos from one or all channel tabs.

    Args:
        tab:         One of "videos", "shorts", "streams", or "all".
        full_details: If True, fetch complete per-video metadata (slow).
                      If False, use flat extraction (fast, basic fields only).
        max_videos:  Limit on videos per tab (None = all).
        verbose:     Enable debug logging.
    """

    def __init__(
        self,
        tab: str = "videos",
        full_details: bool = False,
        max_videos: int | None = None,
        verbose: bool = False,
    ):
        if tab not in VALID_TABS:
            raise ValueError(f"Invalid tab {tab!r}. Choose from: {', '.join(VALID_TABS)}")
        self.tab = tab
        self.full_details = full_details
        self.max_videos = max_videos
        self.verbose = verbose

    def extract(self, channel_url: str) -> dict:
        """
        Fetch videos from the channel's selected tab(s).

        Returns a dict that mirrors PlaylistExtractor's output structure,
        with extra fields: channel_url, tab, tabs_fetched.
        For tab="all", all three tabs are fetched and merged.
        """
        base_url = _normalize_channel_url(channel_url)
        logger.info(f"Channel: {base_url}  |  tab: {self.tab}")

        if self.tab == "all":
            return self._extract_all_tabs(base_url)
        else:
            return self._extract_tab(base_url, self.tab)

    def _extract_tab(self, base_url: str, tab: str) -> dict:
        """Fetch a single tab and annotate the result."""
        url = _tab_url(base_url, tab)
        logger.info(f"Fetching tab URL: {url}")

        extractor = PlaylistExtractor(
            full_details=self.full_details,
            max_videos=self.max_videos,
            verbose=self.verbose,
        )
        result = extractor.extract(url)

        # Annotate with channel/tab context
        result["channel_url"] = base_url
        result["tab"] = tab
        result["tabs_fetched"] = [tab]
        result["_extractor"] = "ChannelExtractor"
        return result

    def _extract_all_tabs(self, base_url: str) -> dict:
        """Fetch videos, shorts, and streams concurrently then merge into one result."""
        tabs = ["videos", "shorts", "streams"]
        tab_results: dict[str, dict | None] = {}
        errors: list[dict] = []

        def _fetch_tab(tab: str) -> tuple[str, dict | None]:
            try:
                url = _tab_url(base_url, tab)
                logger.info(f"Fetching tab URL: {url}")
                # Disable per-tab limit — max_videos applied globally after merge
                extractor = PlaylistExtractor(
                    full_details=self.full_details,
                    max_videos=None,
                    verbose=self.verbose,
                )
                result = extractor.extract(url)
                result["channel_url"] = base_url
                result["tab"] = tab
                result["tabs_fetched"] = [tab]
                result["_extractor"] = "ChannelExtractor"
                return tab, result
            except ScraperError as e:
                logger.warning(f"Tab {tab!r} failed: {e.user_message}")
                return tab, None

        with ThreadPoolExecutor(max_workers=len(tabs)) as executor:
            future_to_tab = {executor.submit(_fetch_tab, tab): tab for tab in tabs}
            for future in as_completed(future_to_tab):
                tab, result = future.result()
                tab_results[tab] = result

        all_videos: list[dict] = []
        tab_summaries: dict[str, dict] = {}
        seen_ids: set[str] = set()

        for tab in tabs:
            result = tab_results.get(tab)
            if result is None:
                tab_summaries[tab] = {"error": "fetch failed"}
                continue
            videos = result.get("videos", [])
            errors.extend(result.get("errors", []))
            tab_summaries[tab] = {
                "available_videos": result.get("available_videos", 0),
                "unavailable_videos": result.get("unavailable_videos", 0),
            }
            for v in videos:
                vid_id = v.get("id") or v.get("video_id") or v.get("url")
                if vid_id and vid_id in seen_ids:
                    continue
                if vid_id:
                    seen_ids.add(vid_id)
                v["tab"] = tab
                all_videos.append(v)

        # Apply max_videos globally after dedup (not per-tab)
        if self.max_videos is not None:
            all_videos = all_videos[: self.max_videos]

        # Re-number positions after dedup and limit
        for idx, v in enumerate(all_videos):
            v["position"] = idx + 1

        return {
            "channel_url": base_url,
            "tab": "all",
            "tabs_fetched": tabs,
            "tab_summaries": tab_summaries,
            "total_videos": len(all_videos),
            "available_videos": len(all_videos),
            "unavailable_videos": len(errors),
            "videos": all_videos,
            "errors": errors,
            "_extractor": "ChannelExtractor",
            "_source_url": base_url,
        }
