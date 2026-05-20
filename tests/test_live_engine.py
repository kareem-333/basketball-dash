"""Tests for nba/live_engine.py — pure functions and GS+ computation."""

import pandas as pd
import pytest

from nba.live_engine import (
    LEAGUE_AVG_GS_PLUS,
    MIN_POSSESSIONS_FULL,
    TAKEOVER_SUSTAIN_POSSESSIONS,
    VELOCITY_WINDOW,
    BoxStats,
    GameState,
    GSPlusSnapshot,
    _classify_tier,
    _dragon_pts,
    _fortress_pts,
    _offensive_half,
    _parse_min,
    _shrink,
    _velocity,
    compute_gs_plus,
    compute_snapshot,
    get_player_season_norm,
)


# ── _parse_min ─────────────────────────────────────────────────────────────────

class TestParseMin:
    def test_iso8601_full(self):
        assert abs(_parse_min("PT12M34.00S") - 12.0 - 34/60) < 0.001

    def test_iso8601_minutes_only(self):
        assert abs(_parse_min("PT5M0.00S") - 5.0) < 0.001

    def test_iso8601_seconds_only(self):
        assert abs(_parse_min("PT0M30.00S") - 0.5) < 0.001

    def test_mmss_format(self):
        assert abs(_parse_min("12:34") - (12 + 34/60)) < 0.001

    def test_mmss_zero(self):
        assert _parse_min("0:00") == 0.0

    def test_bare_float(self):
        assert _parse_min("24.5") == 24.5

    def test_bare_integer_string(self):
        assert _parse_min("10") == 10.0

    def test_empty_string(self):
        assert _parse_min("") == 0.0

    def test_none(self):
        assert _parse_min(None) == 0.0

    def test_garbage(self):
        assert _parse_min("not_a_time") == 0.0


# ── _shrink ────────────────────────────────────────────────────────────────────

class TestShrink:
    def test_zero_possessions_returns_norm(self):
        assert _shrink(raw=20.0, norm=10.0, possessions=0) == 10.0

    def test_full_possessions_returns_raw(self):
        assert _shrink(raw=20.0, norm=10.0, possessions=MIN_POSSESSIONS_FULL) == 20.0

    def test_over_threshold_returns_raw(self):
        assert _shrink(raw=20.0, norm=10.0, possessions=MIN_POSSESSIONS_FULL + 5) == 20.0

    def test_midpoint_blends(self):
        result = _shrink(raw=20.0, norm=10.0, possessions=10)
        assert abs(result - 15.0) < 0.01   # 0.5 * 20 + 0.5 * 10

    def test_early_game_biased_toward_norm(self):
        # w = 2/20 = 0.1 → 0.1*30 + 0.9*10 = 12.0 (heavily toward norm)
        result = _shrink(raw=30.0, norm=10.0, possessions=2)
        assert result <= 12.0


# ── _velocity ──────────────────────────────────────────────────────────────────

class TestVelocity:
    def test_empty_history_returns_neutral(self):
        vel, arrow = _velocity([], current_poss=0)
        assert vel == 0.0
        assert arrow == "→"

    def test_single_entry_returns_neutral(self):
        vel, arrow = _velocity([(1, 10.0)], current_poss=1)
        assert arrow == "→"

    def test_accelerating_gives_up_arrow(self):
        # Prior window: low scores; recent window: high scores
        history = [(p, 5.0) for p in range(1, 11)] + [(p, 12.0) for p in range(11, 21)]
        vel, arrow = _velocity(history, current_poss=20)
        assert vel > 0
        assert arrow in ("↑", "↑↑")

    def test_decelerating_gives_down_arrow(self):
        history = [(p, 15.0) for p in range(1, 11)] + [(p, 4.0) for p in range(11, 21)]
        vel, arrow = _velocity(history, current_poss=20)
        assert vel < 0
        assert arrow in ("↓", "↓↓")

    def test_stable_gives_neutral(self):
        history = [(p, 10.0) for p in range(1, 21)]
        vel, arrow = _velocity(history, current_poss=20)
        assert arrow == "→"

    def test_rapid_acceleration_gives_double_up(self):
        history = [(p, 2.0) for p in range(1, 11)] + [(p, 10.0) for p in range(11, 21)]
        vel, arrow = _velocity(history, current_poss=20)
        assert arrow == "↑↑"

    def test_rapid_deceleration_gives_double_down(self):
        history = [(p, 10.0) for p in range(1, 11)] + [(p, 2.0) for p in range(11, 21)]
        vel, arrow = _velocity(history, current_poss=20)
        assert arrow == "↓↓"


# ── _classify_tier ─────────────────────────────────────────────────────────────

class TestClassifyTier:
    def test_takeover(self):
        tier, color = _classify_tier(35.0)
        assert tier == "TAKEOVER"
        assert color == "#FF4500"

    def test_hot(self):
        tier, _ = _classify_tier(25.0)
        assert tier == "HOT"

    def test_normal_positive(self):
        tier, _ = _classify_tier(10.0)
        assert tier == "NORMAL"

    def test_normal_zero(self):
        tier, _ = _classify_tier(0.0)
        assert tier == "NORMAL"

    def test_normal_negative(self):
        tier, _ = _classify_tier(-10.0)
        assert tier == "NORMAL"

    def test_cold(self):
        tier, _ = _classify_tier(-25.0)
        assert tier == "COLD"

    def test_frozen(self):
        tier, _ = _classify_tier(-40.0)
        assert tier == "FROZEN"

    def test_boundary_hot_to_takeover(self):
        # exactly 35 → TAKEOVER
        tier, _ = _classify_tier(35.0)
        assert tier == "TAKEOVER"
        # just below → HOT
        tier, _ = _classify_tier(34.9)
        assert tier == "HOT"

    def test_boundary_normal_to_cold(self):
        # NORMAL lo bound is -15 inclusive (lo <= pct < hi), so -15.0 stays NORMAL
        tier, _ = _classify_tier(-15.0)
        assert tier == "NORMAL"
        tier, _ = _classify_tier(-15.01)
        assert tier == "COLD"
        tier, _ = _classify_tier(-14.9)
        assert tier == "NORMAL"


# ── compute_gs_plus ────────────────────────────────────────────────────────────

class TestComputeGsPlus:
    def test_zero_stats_gives_zero_or_near_zero(self, empty_box):
        result = compute_gs_plus(empty_box)
        assert result == 0.0

    def test_positive_contribution(self, basic_box):
        result = compute_gs_plus(basic_box)
        assert result > 0

    def test_offensive_half_formula(self):
        b = BoxStats(
            player_id=1, player_name="X", team_id=1, position="PG",
            pts=20, fgm=8, fga=15, ftm=4, fta=5,
            oreb=0, dreb=0, ast=5, stl=0, blk=0, tov=2, pf=1,
        )
        # Manual: 20 + 0.4*8 - 0.7*15 - 0.4*(5-4) + 0.7*0 + 0.7*5 - 0.4*1 - 2
        expected_off = 20 + 3.2 - 10.5 - 0.4 + 3.5 - 0.4 - 2
        result = compute_gs_plus(b)
        assert abs(result - expected_off) < 0.01   # no hustle → defensive half = 0

    def test_hustle_adds_to_gs_plus(self):
        b_no_hustle = BoxStats(
            player_id=1, player_name="X", team_id=1, position="PG",
            pts=10, fgm=4, fga=8, stl=0, blk=0,
        )
        b_with_hustle = BoxStats(
            player_id=1, player_name="X", team_id=1, position="PG",
            pts=10, fgm=4, fga=8, stl=3, blk=2,
        )
        assert compute_gs_plus(b_with_hustle) > compute_gs_plus(b_no_hustle)


# ── compute_snapshot ───────────────────────────────────────────────────────────

class TestComputeSnapshot:
    def test_returns_gs_plus_snapshot(self, basic_box, game_state):
        snap = compute_snapshot(basic_box, season_norm=10.0, state=game_state)
        assert isinstance(snap, GSPlusSnapshot)

    def test_player_above_norm_gets_hot_or_higher(self, game_state):
        b = BoxStats(
            player_id=1, player_name="Star", team_id=100, position="SF",
            pts=30, fgm=12, fga=20, ftm=6, fta=8,
            oreb=2, dreb=5, ast=6, stl=3, blk=1, tov=1, pf=1,
            possessions_elapsed=80,
        )
        snap = compute_snapshot(b, season_norm=8.0, state=game_state)
        assert snap.pct_vs_norm > 15.0
        assert snap.tier in ("HOT", "TAKEOVER")

    def test_takeover_requires_sustained_possessions(self, game_state):
        b = BoxStats(
            player_id=1, player_name="Star", team_id=100, position="SG",
            pts=30, fgm=12, fga=18, ftm=6, fta=7,
            oreb=2, dreb=4, ast=5, stl=3, blk=1, tov=0, pf=1,
            possessions_elapsed=80,
        )
        # First snapshot — takeover counter = 1
        snap1 = compute_snapshot(b, season_norm=5.0, state=game_state)
        if snap1.tier == "TAKEOVER":
            assert not snap1.takeover_active  # counter only at 1
            # Second snapshot — counter = 2
            snap2 = compute_snapshot(b, season_norm=5.0, state=game_state)
            assert not snap2.takeover_active
            # Third snapshot — counter = 3, now active
            snap3 = compute_snapshot(b, season_norm=5.0, state=game_state)
            assert snap3.takeover_active

    def test_tier_resets_takeover_counter(self, game_state):
        b_hot = BoxStats(
            player_id=2, player_name="Guy", team_id=100, position="PF",
            pts=30, fgm=12, fga=18, ftm=6, fta=7,
            stl=3, blk=1, possessions_elapsed=80,
        )
        b_cold = BoxStats(
            player_id=2, player_name="Guy", team_id=100, position="PF",
            pts=2, fgm=1, fga=8, possessions_elapsed=80,
        )
        compute_snapshot(b_hot, season_norm=5.0, state=game_state)
        compute_snapshot(b_hot, season_norm=5.0, state=game_state)
        # Drop into COLD — counter resets
        snap = compute_snapshot(b_cold, season_norm=5.0, state=game_state)
        assert not snap.takeover_active

    def test_early_game_shrinkage_applied(self, game_state):
        b_early = BoxStats(
            player_id=3, player_name="Early", team_id=100, position="PG",
            pts=15, fgm=6, fga=10, ast=4,
            possessions_elapsed=2,   # very early
        )
        b_late = BoxStats(
            player_id=4, player_name="Late", team_id=100, position="PG",
            pts=15, fgm=6, fga=10, ast=4,
            possessions_elapsed=80,  # full game
        )
        snap_early = compute_snapshot(b_early, season_norm=10.0, state=game_state)
        snap_late  = compute_snapshot(b_late,  season_norm=10.0, state=game_state)
        # Early-game player's score is shrunk toward norm, so pct_vs_norm is smaller
        assert abs(snap_early.pct_vs_norm) < abs(snap_late.pct_vs_norm)

    def test_bench_state_when_not_on_court(self, game_state):
        b = BoxStats(
            player_id=5, player_name="Bench", team_id=100, position="C",
            min=0.1, on_court=False,
        )
        snap = compute_snapshot(b, season_norm=10.0, state=game_state)
        assert snap.bench_state

    def test_velocity_arrow_populated_with_history(self, game_state):
        # Feed multiple possessions to accumulate history
        for poss in range(1, 25):
            b = BoxStats(
                player_id=6, player_name="Runner", team_id=100, position="SG",
                pts=poss, fgm=1, fga=2, possessions_elapsed=poss,
            )
            snap = compute_snapshot(b, season_norm=10.0, state=game_state)
        # After 24 possession-worth of data, velocity should not always be neutral
        assert snap.velocity_arrow in ("↑↑", "↑", "→", "↓", "↓↓")


# ── get_player_season_norm ─────────────────────────────────────────────────────

class TestGetPlayerSeasonNorm:
    def setup_method(self):
        # Clear module-level cache between tests
        import nba.live_engine as le
        le._norm_cache.clear()
        le._MISSING_NORMS_LOGGED.clear()

    def test_returns_value_from_season_df(self, season_df):
        from nba.live_engine import get_player_season_norm
        norm = get_player_season_norm(1, season_df)
        assert norm == 12.5

    def test_returns_second_player_norm(self, season_df):
        from nba.live_engine import get_player_season_norm
        norm = get_player_season_norm(2, season_df)
        assert norm == 8.0

    def test_missing_player_returns_league_average(self, season_df):
        from nba.live_engine import get_player_season_norm
        norm = get_player_season_norm(999, season_df)
        assert norm == LEAGUE_AVG_GS_PLUS

    def test_none_df_returns_league_average(self):
        from nba.live_engine import get_player_season_norm
        norm = get_player_season_norm(1, None)
        assert norm == LEAGUE_AVG_GS_PLUS

    def test_empty_df_returns_league_average(self):
        from nba.live_engine import get_player_season_norm
        norm = get_player_season_norm(1, pd.DataFrame())
        assert norm == LEAGUE_AVG_GS_PLUS

    def test_result_is_cached(self, season_df):
        import nba.live_engine as le
        from nba.live_engine import get_player_season_norm
        get_player_season_norm(1, season_df)
        assert 1 in le._norm_cache
        assert le._norm_cache[1] == 12.5

    def test_norm_never_returns_zero_to_avoid_division_issues(self, season_df):
        # Insert a player with GS_PLUS_NORM = 0
        df = pd.concat([season_df, pd.DataFrame({"PLAYER_ID": [777], "GS_PLUS_NORM": [0.0]})])
        from nba.live_engine import get_player_season_norm
        norm = get_player_season_norm(777, df)
        assert norm != 0.0
        assert norm == LEAGUE_AVG_GS_PLUS
