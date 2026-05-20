"""Tests for nba/pipeline.py — season string derivation."""

import datetime
from unittest.mock import patch

import pytest


def _season(month, year=2026):
    """Helper: call _current_nba_season() with a mocked date."""
    from nba.pipeline import _current_nba_season
    fake_today = datetime.date(year, month, 15)
    with patch("nba.pipeline._dt") as mock_dt:
        mock_dt.date.today.return_value = fake_today
        return _current_nba_season()


class TestCurrentNbaSeason:
    def test_january_is_second_half(self):
        # Jan 2026 → 2025-26 season (2026 is the second year)
        assert _season(month=1, year=2026) == "2025-26"

    def test_april_is_second_half(self):
        assert _season(month=4, year=2026) == "2025-26"

    def test_june_is_second_half(self):
        assert _season(month=6, year=2026) == "2025-26"

    def test_august_is_second_half(self):
        # Aug is off-season but still treated as second half
        assert _season(month=8, year=2026) == "2025-26"

    def test_september_is_first_half(self):
        # Sep 2026 → 2026-27 season (2026 is the first year)
        assert _season(month=9, year=2026) == "2026-27"

    def test_october_is_first_half(self):
        assert _season(month=10, year=2026) == "2026-27"

    def test_december_is_first_half(self):
        assert _season(month=12, year=2025) == "2025-26"

    def test_format_two_digit_suffix(self):
        # The suffix must be exactly 2 digits
        result = _season(month=1, year=2026)
        parts = result.split("-")
        assert len(parts) == 2
        assert len(parts[1]) == 2

    def test_returns_string(self):
        result = _season(month=5, year=2026)
        assert isinstance(result, str)

    def test_season_constant_is_string(self):
        from nba.pipeline import SEASON
        assert isinstance(SEASON, str)
        assert "-" in SEASON
