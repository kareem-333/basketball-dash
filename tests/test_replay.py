"""Tests for nba/replay.py — timeline builder, checkpoints, and GS+ snapshots."""

import pandas as pd
import pytest

from nba.live_engine import GameState
from nba.replay import (
    PlayerAccum,
    ReplayFrame,
    build_replay_timeline,
    get_snapshots_at_frame,
    quarter_checkpoints,
)


# ── build_replay_timeline ──────────────────────────────────────────────────────

class TestBuildReplayTimeline:
    def test_empty_events_returns_empty_list(self, minimal_roster_df):
        result = build_replay_timeline(pd.DataFrame(), minimal_roster_df)
        assert result == []

    def test_returns_one_frame_per_event(self, minimal_events_df, minimal_roster_df):
        frames = build_replay_timeline(minimal_events_df, minimal_roster_df)
        assert len(frames) == len(minimal_events_df)

    def test_fg_made_increments_pts_fgm_fga(self, minimal_events_df, minimal_roster_df):
        frames = build_replay_timeline(minimal_events_df, minimal_roster_df)
        # Event 0: player 10 scores 2pts
        first_frame = frames[0]
        scorer = first_frame.player_stats.get(10)
        assert scorer is not None
        assert scorer.pts == 2
        assert scorer.fgm == 1
        assert scorer.fga == 1

    def test_assist_credited_to_player2(self, minimal_events_df, minimal_roster_df):
        frames = build_replay_timeline(minimal_events_df, minimal_roster_df)
        first_frame = frames[0]
        passer = first_frame.player_stats.get(20)
        assert passer is not None
        assert passer.ast == 1

    def test_fg_miss_increments_fga_only(self, minimal_events_df, minimal_roster_df):
        frames = build_replay_timeline(minimal_events_df, minimal_roster_df)
        second_frame = frames[1]
        shooter = second_frame.player_stats.get(30)
        assert shooter is not None
        assert shooter.fga == 1
        assert shooter.fgm == 0
        assert shooter.pts == 0

    def test_stats_are_cumulative(self, minimal_roster_df):
        # Two FG made events for the same player
        events = pd.DataFrame([
            {
                "EVENTNUM": 1, "PERIOD": 1, "PCTIMESTRING": "11:00",
                "EVENTMSGTYPE": 1, "EVENTMSGACTIONTYPE": 0,
                "PLAYER1_ID": 10, "PLAYER1_TEAM_ID": 100, "PLAYER1_NAME": "Scorer",
                "PLAYER2_ID": 0, "PLAYER2_TEAM_ID": 0, "PLAYER2_NAME": "",
                "PLAYER3_ID": 0, "SCORE": "0 - 2",
                "HOMEDESCRIPTION": "", "VISITORDESCRIPTION": "", "NEUTRALDESCRIPTION": "",
            },
            {
                "EVENTNUM": 2, "PERIOD": 1, "PCTIMESTRING": "10:30",
                "EVENTMSGTYPE": 1, "EVENTMSGACTIONTYPE": 0,
                "PLAYER1_ID": 10, "PLAYER1_TEAM_ID": 100, "PLAYER1_NAME": "Scorer",
                "PLAYER2_ID": 0, "PLAYER2_TEAM_ID": 0, "PLAYER2_NAME": "",
                "PLAYER3_ID": 0, "SCORE": "0 - 4",
                "HOMEDESCRIPTION": "", "VISITORDESCRIPTION": "", "NEUTRALDESCRIPTION": "",
            },
        ])
        frames = build_replay_timeline(events, minimal_roster_df)
        assert frames[1].player_stats[10].pts == 4
        assert frames[1].player_stats[10].fgm == 2

    def test_three_pointer_detected(self, minimal_roster_df):
        # eact=79 → 3-pointer
        events = pd.DataFrame([{
            "EVENTNUM": 1, "PERIOD": 1, "PCTIMESTRING": "10:00",
            "EVENTMSGTYPE": 1, "EVENTMSGACTIONTYPE": 79,
            "PLAYER1_ID": 10, "PLAYER1_TEAM_ID": 100, "PLAYER1_NAME": "Scorer",
            "PLAYER2_ID": 0, "PLAYER2_TEAM_ID": 0, "PLAYER2_NAME": "",
            "PLAYER3_ID": 0, "SCORE": "0 - 3",
            "HOMEDESCRIPTION": "", "VISITORDESCRIPTION": "", "NEUTRALDESCRIPTION": "",
        }])
        frames = build_replay_timeline(events, minimal_roster_df)
        assert frames[0].player_stats[10].pts == 3

    def test_free_throw_made_increments_ftm_pts(self, minimal_roster_df):
        events = pd.DataFrame([{
            "EVENTNUM": 1, "PERIOD": 1, "PCTIMESTRING": "10:00",
            "EVENTMSGTYPE": 3, "EVENTMSGACTIONTYPE": 10,  # FT made
            "PLAYER1_ID": 10, "PLAYER1_TEAM_ID": 100, "PLAYER1_NAME": "Scorer",
            "PLAYER2_ID": 0, "PLAYER2_TEAM_ID": 0, "PLAYER2_NAME": "",
            "PLAYER3_ID": 0, "SCORE": None,
            "HOMEDESCRIPTION": "", "VISITORDESCRIPTION": "", "NEUTRALDESCRIPTION": "",
        }])
        frames = build_replay_timeline(events, minimal_roster_df)
        p = frames[0].player_stats[10]
        assert p.ftm == 1
        assert p.fta == 1
        assert p.pts == 1

    def test_turnover_steal_credited_correctly(self, minimal_roster_df):
        events = pd.DataFrame([{
            "EVENTNUM": 1, "PERIOD": 1, "PCTIMESTRING": "9:00",
            "EVENTMSGTYPE": 5, "EVENTMSGACTIONTYPE": 0,
            "PLAYER1_ID": 10, "PLAYER1_TEAM_ID": 100, "PLAYER1_NAME": "Turner",
            "PLAYER2_ID": 30, "PLAYER2_TEAM_ID": 200, "PLAYER2_NAME": "Stealer",
            "PLAYER3_ID": 0, "SCORE": None,
            "HOMEDESCRIPTION": "", "VISITORDESCRIPTION": "", "NEUTRALDESCRIPTION": "",
        }])
        frames = build_replay_timeline(events, minimal_roster_df)
        turner  = frames[0].player_stats.get(10)
        stealer = frames[0].player_stats.get(30)
        assert turner is not None and turner.tov == 1
        assert stealer is not None and stealer.stl == 1

    def test_rebound_oreb_vs_dreb(self, minimal_roster_df):
        events = pd.DataFrame([
            {
                "EVENTNUM": 1, "PERIOD": 1, "PCTIMESTRING": "8:00",
                "EVENTMSGTYPE": 4, "EVENTMSGACTIONTYPE": 1,   # off rebound
                "PLAYER1_ID": 10, "PLAYER1_TEAM_ID": 100, "PLAYER1_NAME": "Rebounder",
                "PLAYER2_ID": 0, "PLAYER2_TEAM_ID": 0, "PLAYER2_NAME": "",
                "PLAYER3_ID": 0, "SCORE": None,
                "HOMEDESCRIPTION": "", "VISITORDESCRIPTION": "", "NEUTRALDESCRIPTION": "",
            },
            {
                "EVENTNUM": 2, "PERIOD": 1, "PCTIMESTRING": "7:45",
                "EVENTMSGTYPE": 4, "EVENTMSGACTIONTYPE": 2,   # def rebound
                "PLAYER1_ID": 10, "PLAYER1_TEAM_ID": 100, "PLAYER1_NAME": "Rebounder",
                "PLAYER2_ID": 0, "PLAYER2_TEAM_ID": 0, "PLAYER2_NAME": "",
                "PLAYER3_ID": 0, "SCORE": None,
                "HOMEDESCRIPTION": "", "VISITORDESCRIPTION": "", "NEUTRALDESCRIPTION": "",
            },
        ])
        frames = build_replay_timeline(events, minimal_roster_df)
        p = frames[1].player_stats[10]
        assert p.oreb == 1
        assert p.dreb == 1

    def test_block_credited_to_player3(self, minimal_roster_df):
        events = pd.DataFrame([{
            "EVENTNUM": 1, "PERIOD": 1, "PCTIMESTRING": "7:00",
            "EVENTMSGTYPE": 2, "EVENTMSGACTIONTYPE": 0,   # FG missed
            "PLAYER1_ID": 10, "PLAYER1_TEAM_ID": 100, "PLAYER1_NAME": "Shooter",
            "PLAYER2_ID": 0, "PLAYER2_TEAM_ID": 0, "PLAYER2_NAME": "",
            "PLAYER3_ID": 30,   # blocker
            "SCORE": None,
            "HOMEDESCRIPTION": "", "VISITORDESCRIPTION": "", "NEUTRALDESCRIPTION": "",
        }])
        frames = build_replay_timeline(events, minimal_roster_df)
        blocker = frames[0].player_stats.get(30)
        assert blocker is not None and blocker.blk == 1

    def test_score_parsed_from_score_column(self, minimal_events_df, minimal_roster_df):
        frames = build_replay_timeline(minimal_events_df, minimal_roster_df)
        # First event has SCORE = "0 - 2"
        assert frames[0].home_score == 0
        assert frames[0].away_score == 2

    def test_period_propagated_to_frame(self, minimal_events_df, minimal_roster_df):
        frames = build_replay_timeline(minimal_events_df, minimal_roster_df)
        assert frames[0].period == 1

    def test_clock_propagated_to_frame(self, minimal_events_df, minimal_roster_df):
        frames = build_replay_timeline(minimal_events_df, minimal_roster_df)
        assert frames[0].clock == "11:30"

    def test_frame_player_stats_are_independent_copies(self, minimal_events_df, minimal_roster_df):
        frames = build_replay_timeline(minimal_events_df, minimal_roster_df)
        # Mutating one frame's player_stats must not affect others
        frames[0].player_stats[10].pts = 999
        assert frames[1].player_stats.get(10, PlayerAccum(10, "", 0)).pts != 999

    def test_empty_roster_still_builds_from_events(self, minimal_events_df):
        frames = build_replay_timeline(minimal_events_df, pd.DataFrame())
        assert len(frames) == len(minimal_events_df)
        # Players seeded from events
        assert 10 in frames[0].player_stats


# ── quarter_checkpoints ────────────────────────────────────────────────────────

class TestQuarterCheckpoints:
    def _make_frames(self, periods):
        """Build a minimal list of ReplayFrame objects with the given period sequence."""
        frames = []
        for i, p in enumerate(periods):
            frames.append(ReplayFrame(
                event_idx=i, period=p, clock="10:00", description="",
                home_team_id=100, away_team_id=200,
                home_score=0, away_score=0,
            ))
        return frames

    def test_empty_frames_returns_empty(self):
        assert quarter_checkpoints([]) == []

    def test_always_starts_with_start(self):
        frames = self._make_frames([1, 1, 2])
        cps = quarter_checkpoints(frames)
        assert cps[0] == ("Start", 0)

    def test_always_ends_with_final(self):
        frames = self._make_frames([1, 1, 2])
        cps = quarter_checkpoints(frames)
        assert cps[-1][0] == "Final"
        assert cps[-1][1] == len(frames) - 1

    def test_single_quarter(self):
        frames = self._make_frames([1, 1, 1])
        cps = quarter_checkpoints(frames)
        labels = [c[0] for c in cps]
        assert "Start" in labels
        assert "Final" in labels

    def test_four_quarters_produces_correct_labels(self):
        periods = [1]*10 + [2]*10 + [3]*10 + [4]*10
        frames = self._make_frames(periods)
        cps = quarter_checkpoints(frames)
        labels = [c[0] for c in cps]
        assert "Q1 end" in labels
        assert "Q2 end" in labels
        assert "Q3 end" in labels
        assert "Final" in labels

    def test_overtime_label(self):
        periods = [1]*5 + [2]*5 + [3]*5 + [4]*5 + [5]*5  # period 5 = OT
        frames = self._make_frames(periods)
        cps = quarter_checkpoints(frames)
        labels = [c[0] for c in cps]
        # quarter_checkpoints labels the period being LEFT on each transition.
        # The Q4→OT transition produces "Q4 end"; the OT period ends at "Final".
        assert "Q4 end" in labels
        assert "Final" in labels

    def test_checkpoint_indices_are_in_range(self):
        periods = [1]*10 + [2]*10
        frames = self._make_frames(periods)
        cps = quarter_checkpoints(frames)
        for _, idx in cps:
            assert 0 <= idx < len(frames)


# ── get_snapshots_at_frame ─────────────────────────────────────────────────────

class TestGetSnapshotsAtFrame:
    def _make_frame(self, player_stats):
        return ReplayFrame(
            event_idx=1, period=2, clock="8:00", description="",
            home_team_id=100, away_team_id=200,
            home_score=42, away_score=38,
            player_stats=player_stats,
        )

    def _make_active_accum(self, player_id, team_id, pts=10, fgm=4, fga=8, ast=2):
        p = PlayerAccum(
            player_id=player_id,
            player_name=f"Player {player_id}",
            team_id=team_id,
            position="SG",
        )
        p.pts, p.fgm, p.fga, p.ast = pts, fgm, fga, ast
        p.minutes_est = 20.0
        return p

    def test_returns_two_lists(self, season_df):
        frame = self._make_frame({})
        home, away = get_snapshots_at_frame(frame, season_df)
        assert isinstance(home, list)
        assert isinstance(away, list)

    def test_empty_frame_returns_empty_lists(self, season_df):
        frame = self._make_frame({})
        home, away = get_snapshots_at_frame(frame, season_df)
        assert home == []
        assert away == []

    def test_players_routed_by_team(self, season_df):
        accum = {
            10: self._make_active_accum(10, team_id=100),
            30: self._make_active_accum(30, team_id=200),
        }
        frame = self._make_frame(accum)
        home, away = get_snapshots_at_frame(frame, season_df)
        assert all(s.team_id == 100 for s in home)
        assert all(s.team_id == 200 for s in away)

    def test_top_n_respected(self, season_df):
        accum = {
            i: self._make_active_accum(i, team_id=100, pts=i)
            for i in range(1, 10)
        }
        frame = self._make_frame(accum)
        home, away = get_snapshots_at_frame(frame, season_df, top_n=3)
        assert len(home) <= 3

    def test_players_with_zero_activity_excluded(self, season_df):
        # A player with all zeros should be filtered out
        idle = PlayerAccum(player_id=99, player_name="Idle", team_id=100)
        active = self._make_active_accum(10, team_id=100)
        frame = self._make_frame({99: idle, 10: active})
        home, _ = get_snapshots_at_frame(frame, season_df)
        ids = [s.player_id for s in home]
        assert 99 not in ids
        assert 10 in ids

    def test_sorted_by_absolute_gs_plus(self, season_df):
        accum = {
            10: self._make_active_accum(10, team_id=100, pts=20, fgm=8, fga=12),
            11: self._make_active_accum(11, team_id=100, pts=4, fgm=2, fga=8),
        }
        frame = self._make_frame(accum)
        home, _ = get_snapshots_at_frame(frame, season_df)
        if len(home) >= 2:
            assert abs(home[0].raw_gs_plus) >= abs(home[1].raw_gs_plus)

    def test_accepts_none_season_df(self):
        accum = {10: self._make_active_accum(10, team_id=100)}
        frame = self._make_frame(accum)
        home, away = get_snapshots_at_frame(frame, None)
        assert isinstance(home, list)

    def test_shared_state_accumulates_velocity_history(self, season_df):
        """Passing the same GameState across frames builds velocity history."""
        state = GameState(game_id="replay", home_team=100, away_team=200)

        # Build frames with increasing player activity
        frames = []
        for i in range(1, 25):
            acc = PlayerAccum(player_id=10, player_name="Star", team_id=100)
            acc.pts = i * 2
            acc.fgm, acc.fga, acc.ast = i, i * 2, max(0, i - 1)
            acc.minutes_est = float(i)
            frames.append(self._make_frame({10: acc}))

        for f in frames:
            get_snapshots_at_frame(f, season_df, top_n=1, state=state)

        # After many frames, history should be populated
        assert 10 in state._history
        assert len(state._history[10]) > 0

    def test_fresh_state_per_call_without_state_arg(self, season_df):
        """Without a shared state, each call gets a fresh GameState (no history)."""
        accum = {10: self._make_active_accum(10, team_id=100)}
        frame = self._make_frame(accum)
        # Two independent calls — should not share history
        home1, _ = get_snapshots_at_frame(frame, season_df)
        home2, _ = get_snapshots_at_frame(frame, season_df)
        # Both should work without error
        assert len(home1) == len(home2)
