"""
nba/replay.py — Game Replay Engine

Fetches a completed game's play-by-play, reconstructs cumulative per-player
box stats at every event, and returns GS+ snapshots for any moment in the game.

Typical usage
-------------
    events = fetch_play_by_play(game_id)          # cached 1 h
    timeline = build_replay_timeline(events)       # list of ReplayFrame
    frame = timeline[slider_pos]                   # pick a moment
    snaps = get_snapshots_at_frame(frame, sdf)     # GS+ for each player
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)

# ── NBA play-by-play event type constants ─────────────────────────────────────
MSGTYPE_FG_MADE    = 1
MSGTYPE_FG_MISS    = 2
MSGTYPE_FT         = 3
MSGTYPE_REBOUND    = 4
MSGTYPE_TURNOVER   = 5
MSGTYPE_FOUL       = 6
MSGTYPE_VIOLATION  = 7
MSGTYPE_BLOCK      = 11   # appears in FG_MISS rows via PLAYER3
MSGTYPE_STEAL      = 5    # steals are a sub-type of turnover (PLAYER2)


@dataclass
class PlayerAccum:
    """Mutable per-player cumulative stats up to a moment in the game."""
    player_id:   int
    player_name: str
    team_id:     int
    position:    str = ""

    pts:  int = 0
    fgm:  int = 0
    fga:  int = 0
    ftm:  int = 0
    fta:  int = 0
    oreb: int = 0
    dreb: int = 0
    ast:  int = 0
    stl:  int = 0
    blk:  int = 0
    tov:  int = 0
    pf:   int = 0
    # Hustle — not available in play-by-play; left at 0
    deflections:      int = 0
    charges_drawn:    int = 0
    contested_2pt:    int = 0
    contested_3pt:    int = 0
    loose_balls:      int = 0
    rim_fga_defended: int = 0
    rim_fgm_defended: int = 0
    def_boxouts:      int = 0

    minutes_est: float = 0.0   # estimated from clock progression


@dataclass
class ReplayFrame:
    """One moment in the game — associated with a specific event index."""
    event_idx:    int
    period:       int
    clock:        str        # "MM:SS" remaining in period
    description:  str        # last play description
    home_team_id: int
    away_team_id: int
    home_score:   int
    away_score:   int
    # Cumulative stats per player (copy at this frame)
    player_stats: dict[int, PlayerAccum] = field(default_factory=dict)


# ── nba_api fetchers ──────────────────────────────────────────────────────────

def fetch_recent_games(days_back: int = 7) -> list[dict]:
    """
    Return a list of completed games from the last `days_back` days.
    Each dict: {game_id, game_date, home_team, away_team, home_score,
                away_score, home_abbr, away_abbr}
    """
    import datetime
    from nba_api.stats.endpoints import LeagueGameLog

    results: list[dict] = []
    date_from = (datetime.date.today() - datetime.timedelta(days=days_back)).strftime("%m/%d/%Y")
    date_to   = datetime.date.today().strftime("%m/%d/%Y")

    try:
        time.sleep(0.6)
        lg = LeagueGameLog(
            season="2024-25",
            date_from_nullable=date_from,
            date_to_nullable=date_to,
            direction="DESC",
        )
        df = lg.game_log.get_data_frame()
        if df.empty:
            return []

        # LeagueGameLog has one row per team per game; pair them up by GAME_ID
        seen: set[str] = set()
        for gid, grp in df.groupby("GAME_ID"):
            if gid in seen:
                continue
            seen.add(str(gid))
            rows = grp.to_dict("records")
            if len(rows) < 2:
                continue
            # Determine home vs away from MATCHUP ("XXX vs. YYY" = home, "XXX @ YYY" = away)
            home_row = next((r for r in rows if "vs." in str(r.get("MATCHUP", ""))), rows[0])
            away_row = next((r for r in rows if "@"   in str(r.get("MATCHUP", ""))), rows[1])
            results.append({
                "game_id":    str(gid),
                "game_date":  str(home_row.get("GAME_DATE", "")),
                "home_abbr":  str(home_row.get("TEAM_ABBREVIATION", "")),
                "away_abbr":  str(away_row.get("TEAM_ABBREVIATION", "")),
                "home_score": int(home_row.get("PTS", 0) or 0),
                "away_score": int(away_row.get("PTS", 0) or 0),
                "home_team_id": int(home_row.get("TEAM_ID", 0) or 0),
                "away_team_id": int(away_row.get("TEAM_ID", 0) or 0),
            })
    except Exception as e:
        log.warning("fetch_recent_games failed: %s", e)

    return results


def fetch_play_by_play(game_id: str) -> pd.DataFrame:
    """
    Return play-by-play DataFrame for a completed game.
    Columns of interest: EVENTNUM, PERIOD, PCTIMESTRING, EVENTMSGTYPE,
    EVENTMSGACTIONTYPE, PLAYER1_ID, PLAYER1_NAME, PLAYER1_TEAM_ID,
    PLAYER2_ID, PLAYER2_NAME, PLAYER3_ID, PLAYER3_NAME,
    HOMEDESCRIPTION, VISITORDESCRIPTION, SCORE
    """
    from nba_api.stats.endpoints import PlayByPlayV2
    time.sleep(0.6)
    pbp = PlayByPlayV2(game_id=game_id)
    df = pbp.play_by_play.get_data_frame()
    return df


def fetch_box_roster(game_id: str) -> pd.DataFrame:
    """
    Return the final box score player list so we know team_id + position
    for each player even before they've scored.
    """
    from nba_api.stats.endpoints import BoxScoreTraditionalV2
    time.sleep(0.6)
    box = BoxScoreTraditionalV2(game_id=game_id)
    return box.player_stats.get_data_frame()


# ── Timeline builder ──────────────────────────────────────────────────────────

def _clock_to_seconds(clock_str: str, period: int) -> float:
    """Convert 'MM:SS' remaining + period to elapsed seconds."""
    try:
        parts = str(clock_str).split(":")
        rem = int(parts[0]) * 60 + int(parts[1])
        period_secs = 12 * 60 if period <= 4 else 5 * 60
        elapsed_per_period = (period - 1) * 12 * 60 if period <= 4 else 48 * 60 + (period - 5) * 5 * 60
        return elapsed_per_period + (period_secs - rem)
    except Exception:
        return 0.0


def _safe_int(v) -> int:
    try:
        return int(v) if v and str(v) not in ("", "nan", "None") else 0
    except (ValueError, TypeError):
        return 0


def build_replay_timeline(
    events_df: pd.DataFrame,
    roster_df: pd.DataFrame,
) -> list[ReplayFrame]:
    """
    Build a list of ReplayFrame objects, one per play-by-play event,
    each containing cumulative stats up to that moment.

    We sample one frame per event but callers can stride over this list
    to show quarter checkpoints or every N possessions.
    """
    if events_df.empty:
        return []

    # Seed player accumulator from roster (gives us team_id, position, name)
    accum: dict[int, PlayerAccum] = {}
    home_team_id = 0
    away_team_id = 0

    if not roster_df.empty:
        for _, row in roster_df.iterrows():
            pid = _safe_int(row.get("PLAYER_ID"))
            if not pid:
                continue
            tid = _safe_int(row.get("TEAM_ID"))
            accum[pid] = PlayerAccum(
                player_id=pid,
                player_name=str(row.get("PLAYER_NAME", "")),
                team_id=tid,
                position=str(row.get("START_POSITION", "") or ""),
            )

    # Determine home/away team IDs from roster (HOME column or first two team IDs)
    if not roster_df.empty and "TEAM_ID" in roster_df.columns:
        team_ids = roster_df["TEAM_ID"].dropna().unique().tolist()
        if len(team_ids) >= 2:
            home_team_id = int(team_ids[0])
            away_team_id = int(team_ids[1])

    # Fallback: use PLAYER1_TEAM_ID from events
    if home_team_id == 0 and not events_df.empty:
        tids = events_df["PLAYER1_TEAM_ID"].dropna().unique()
        tids = [int(t) for t in tids if t and str(t) not in ("0", "")]
        if len(tids) >= 2:
            home_team_id, away_team_id = tids[0], tids[1]

    home_score = 0
    away_score = 0
    frames: list[ReplayFrame] = []

    for _, row in events_df.iterrows():
        etype  = _safe_int(row.get("EVENTMSGTYPE"))
        eact   = _safe_int(row.get("EVENTMSGACTIONTYPE"))
        p1_id  = _safe_int(row.get("PLAYER1_ID"))
        p1_tid = _safe_int(row.get("PLAYER1_TEAM_ID"))
        p2_id  = _safe_int(row.get("PLAYER2_ID"))
        p2_tid = _safe_int(row.get("PLAYER2_TEAM_ID"))
        p3_id  = _safe_int(row.get("PLAYER3_ID"))
        period = _safe_int(row.get("PERIOD", 1))
        clock  = str(row.get("PCTIMESTRING", "12:00") or "12:00")
        desc_h = str(row.get("HOMEDESCRIPTION") or "")
        desc_v = str(row.get("VISITORDESCRIPTION") or "")
        desc   = desc_h or desc_v or str(row.get("NEUTRALDESCRIPTION") or "")

        # Parse score from SCORE column "HHH - VVV"
        score_str = str(row.get("SCORE") or "")
        if "-" in score_str:
            parts = score_str.split("-")
            try:
                home_score = int(parts[0].strip())
                away_score = int(parts[1].strip())
            except ValueError:
                pass

        # Seed new players encountered in events
        for pid, tid in [(p1_id, p1_tid), (p2_id, p2_tid)]:
            if pid and pid not in accum:
                accum[pid] = PlayerAccum(
                    player_id=pid,
                    player_name=str(row.get("PLAYER1_NAME" if pid == p1_id else "PLAYER2_NAME") or ""),
                    team_id=tid,
                )

        # ── Apply event to accumulator ─────────────────────────────────────
        def acc(pid) -> Optional[PlayerAccum]:
            return accum.get(pid) if pid else None

        if etype == MSGTYPE_FG_MADE:          # field goal made
            p = acc(p1_id)
            if p:
                p.fgm += 1
                p.fga += 1
                # 3-pointer detection: eact in (1=jump3, 2=pullup3, etc.)
                pts = 3 if eact in (1, 2, 3, 27, 30, 58, 72, 76, 77, 79) else 2
                p.pts += pts
            # Assist
            a = acc(p2_id)
            if a:
                a.ast += 1

        elif etype == MSGTYPE_FG_MISS:        # field goal missed
            p = acc(p1_id)
            if p:
                p.fga += 1
            # Block credited to PLAYER3
            blocker = acc(p3_id)
            if blocker:
                blocker.blk += 1

        elif etype == MSGTYPE_FT:             # free throw
            p = acc(p1_id)
            if p:
                p.fta += 1
                # Made FT: eact 10, 12, 15 = made variants
                if eact in (10, 12, 13, 14, 15, 16, 17, 19, 20):
                    p.ftm += 1
                    p.pts += 1

        elif etype == MSGTYPE_REBOUND:        # rebound
            p = acc(p1_id)
            if p:
                # eact 1 = off, 2 = def
                if eact == 1:
                    p.oreb += 1
                else:
                    p.dreb += 1

        elif etype == MSGTYPE_TURNOVER:       # turnover / steal
            p = acc(p1_id)
            if p:
                p.tov += 1
            stealer = acc(p2_id)
            if stealer:
                stealer.stl += 1

        elif etype == MSGTYPE_FOUL:           # foul
            p = acc(p1_id)
            if p:
                p.pf += 1

        # Estimate minutes from clock progression (rough)
        elapsed = _clock_to_seconds(clock, period)
        for pa in accum.values():
            # Very rough: assume players who've appeared play a share of elapsed time
            if pa.fgm + pa.fga + pa.ast + pa.stl + pa.blk + pa.tov + pa.dreb + pa.oreb > 0:
                pa.minutes_est = elapsed / 60.0 * 0.2  # heuristic only

        # Snapshot of accum (deep copy of stats)
        player_snap: dict[int, PlayerAccum] = {}
        import copy
        for pid, pa in accum.items():
            player_snap[pid] = copy.copy(pa)

        frames.append(ReplayFrame(
            event_idx=_safe_int(row.get("EVENTNUM", len(frames))),
            period=period,
            clock=clock,
            description=desc[:80],
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_score=home_score,
            away_score=away_score,
            player_stats=player_snap,
        ))

    return frames


def quarter_checkpoints(frames: list[ReplayFrame]) -> list[tuple[str, int]]:
    """
    Return (label, frame_idx) for quarter-end checkpoints + halftime + final,
    suitable for a Streamlit select_slider.
    """
    if not frames:
        return []

    points: list[tuple[str, int]] = [("Start", 0)]
    last_period = 0
    for i, f in enumerate(frames):
        if f.period != last_period and last_period > 0:
            label = f"Q{last_period} end" if last_period <= 4 else f"OT{last_period - 4} end"
            points.append((label, max(0, i - 1)))
        last_period = f.period
    points.append(("Final", len(frames) - 1))
    return points


def get_snapshots_at_frame(
    frame: ReplayFrame,
    season_df: "pd.DataFrame | None",
    top_n: int = 5,
) -> tuple[list, list]:
    """
    Convert a ReplayFrame into two lists of GSPlusSnapshot (home, away),
    each containing the top-N players by GS+ at that moment.
    """
    from nba.live_engine import (
        BoxStats, GameState, compute_snapshot, get_player_season_norm
    )

    state = GameState(
        game_id="replay",
        home_team=frame.home_team_id,
        away_team=frame.away_team_id,
    )

    home_snaps, away_snaps = [], []

    for pid, pa in frame.player_stats.items():
        # Skip players with zero involvement
        if pa.fgm + pa.fga + pa.ast + pa.stl + pa.blk + pa.tov + pa.dreb + pa.oreb == 0:
            continue

        bs = BoxStats(
            player_id=pa.player_id,
            player_name=pa.player_name,
            team_id=pa.team_id,
            position=pa.position or "",
            min=pa.minutes_est,
            pts=pa.pts,
            fgm=pa.fgm,
            fga=pa.fga,
            ftm=pa.ftm,
            fta=pa.fta,
            oreb=pa.oreb,
            dreb=pa.dreb,
            ast=pa.ast,
            stl=pa.stl,
            blk=pa.blk,
            tov=pa.tov,
            pf=pa.pf,
            possessions_elapsed=max(1, pa.fgm + pa.fga + pa.ast + pa.dreb),
            on_court=True,
        )
        norm = get_player_season_norm(pa.player_id, season_df)
        snap = compute_snapshot(bs, norm, state)

        if pa.team_id == frame.home_team_id:
            home_snaps.append(snap)
        else:
            away_snaps.append(snap)

    # Sort by absolute GS+ contribution, take top N
    home_snaps.sort(key=lambda s: abs(s.raw_gs_plus), reverse=True)
    away_snaps.sort(key=lambda s: abs(s.raw_gs_plus), reverse=True)

    return home_snaps[:top_n], away_snaps[:top_n]
