"""
sentiment_analyzer.py
---------------------
Comment sentiment analysis using VADER (Valence Aware Dictionary and sEntiment Reasoner).

VADER is specifically tuned for social media text — it handles emoticons, slang,
capitalization, and punctuation emphasis much better than generic NLP models.
No training data needed. No heavy dependencies. Fast.

VADER thresholds (standard):
  compound >= 0.05  → positive
  compound <= -0.05 → negative
  otherwise         → neutral

Install:
    pip install vaderSentiment

Usage:
    analyzer = SentimentAnalyzer()
    summary = analyzer.analyze(comments)   # comments = list of dicts with "text" key
    # → {"positive_pct": 0.72, "negative_pct": 0.08, "neutral_pct": 0.20,
    #    "compound_avg": 0.41, "total_analyzed": 250}
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """
    Run VADER sentiment analysis on a list of comment dicts.

    Each comment dict must have a "text" key (other keys are ignored).

    Returns:
        {
            "positive_pct":   float (0.0–1.0) — fraction of positive comments
            "negative_pct":   float (0.0–1.0) — fraction of negative comments
            "neutral_pct":    float (0.0–1.0) — fraction of neutral comments
            "compound_avg":   float (-1.0–1.0) — average compound score
            "total_analyzed": int  — comments that had text (empty comments skipped)
        }
    """

    def __init__(self):
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            self._vader = SentimentIntensityAnalyzer()
        except ImportError:
            self._vader = None
            logger.warning(
                "vaderSentiment not installed — sentiment analysis disabled. "
                "Run: pip install vaderSentiment"
            )

    @property
    def available(self) -> bool:
        """True if VADER is installed and ready."""
        return self._vader is not None

    def analyze(self, comments: list[dict]) -> dict:
        """
        Analyze sentiment of a list of comment dicts.

        Args:
            comments: List of dicts, each expected to have a "text" key.

        Returns:
            Sentiment summary dict. Returns empty dict if VADER is unavailable.
            Returns zeroed dict if no comments have text.
        """
        if not self._vader:
            return {}

        texts = [c.get("text") or "" for c in comments if c.get("text")]
        if not texts:
            return {
                "positive_pct":   0.0,
                "negative_pct":   0.0,
                "neutral_pct":    0.0,
                "compound_avg":   0.0,
                "total_analyzed": 0,
            }

        pos = neg = neu = 0
        compound_sum = 0.0

        for text in texts:
            scores = self._vader.polarity_scores(text)
            compound = scores["compound"]
            compound_sum += compound
            if compound >= 0.05:
                pos += 1
            elif compound <= -0.05:
                neg += 1
            else:
                neu += 1

        n = len(texts)
        return {
            "positive_pct":   round(pos / n, 4),
            "negative_pct":   round(neg / n, 4),
            "neutral_pct":    round(neu / n, 4),
            "compound_avg":   round(compound_sum / n, 4),
            "total_analyzed": n,
        }
