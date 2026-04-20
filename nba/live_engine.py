"""
nba/live_engine.py — GS+ Live Momentum Engine (brief v5, sections 2–9)

GS+ = offensive_half + defensive_half
  offensive_half = Hollinger GameScore − STL − BLK − DREB
                 = PTS + 0.4·FGM − 0.7·FGA − 0.4·(FTA−FTM) + 0.7·OREB + 0.7·AST − 0.4·PF − TOV
  defensive_half = 0.7 × (dragon_pts + fortress_pts)

% vs norm = (GS+ − player_season_norm) / max(abs(player_season_norm), 1) × 100

Tiers:
  TAKEOVER  ≥ +35 %   #FF4500
  HOT       +15–35 %  #EB6E1F
  NORMAL    ±15 %     #888888
  COLD      −15–−35 % #4A90D9
  FROZEN    ≤ −35 %   #1E90FF
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── Tier definitions ──────────────────────────────────────────────────────────

TIERS = [
    ("TAKEOVER", 35,   float("inf"), "#FF4500"),
    ("HOT",      15,   35,           "#EB6E1F"),
    ("NORMAL",  -15,   15,           "#888888"),
    ("COLD",    -35,  -15,           "#4A90D9"),
    ("FROZEN",  float("-inf"), -35,  "#1E90FF"),
]

TIER_COLORS = {name: color for name, _, _, color in TIERS}

POSITION_SLOTS = ["PG", "SG", "SF", "PF", "C"]

# Early-game shrinkage: regress toward norm until MIN_POSSESSIONS_FULL
MIN_POSSESSIONS_FULL = 20
TAKEOVER_SUSTAIN_POSSESSIONS = 3   # must hold ≥+35% for this many consecutive possessions

# Velocity window (possessions)
VELOCITY_WINDOW = 10

# Bench decay: if player hasn't accumulated minutes, flag as benched
BENCH_MINUTES_THRESHOLD = 0.5  # less than this → bench state


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class BoxStats:
    """Raw per-player box score at a moment in time."""
    player_id:  int
    player_name: str
    team_id:    int
    position:   str        # PG/SG/SF/PF/C (lineup slot)

    # Traditional box
    min:   float = 0.0
    pts:   int   = 0
    fgm:   int   = 0
    fga:   int   = 0
    ftm:   int   = 0
    fta:   int   = 0
    oreb:  int   = 0
    dreb:  int   = 0
    ast:   int   = 0
    stl:   int   = 0
    blk:   int   = 0
    tov:   int   = 0
    pf:    int   = 0

    # Defensive hustle (for defensive half)
    deflections:         int = 0
    charges_drawn:       int = 0
    contested_2pt:       int = 0
    contested_3pt:       int = 0
    loose_balls:         int = 0

    # Rim tracking (Fortress)
    rim_fga_defended:    int   = 0
    rim_fgm_defended:    int   = 0
    def_boxouts:         int   = 0

    # Game flow
    possessions_elapsed: int  = 0
    on_court:            bool = True
    foul_trouble:        bool = False   # ≥4 fouls in regulation, ≥5 in OT


@dataclass
class GSPlusSnapshot:
    """GS+ computed at one moment."""
    player_id:   int
    player_name: str
    team_id:     int
    position:    str

    raw_gs_plus: float = 0.0
    pct_vs_norm: float = 0.0     # % vs season norm (hero number)
    tier:        str   = "NORMAL"
    tier_color:  str   = "#888888"

    velocity:    float = 0.0     # positive = accelerating, negative = slowing
    velocity_arrow: str = "→"

    takeover_active: bool  = False
    bench_state:     bool  = False
    foul_trouble:    bool  = False

    season_norm:     float = 0.0  # player's season baseline GS+


@dataclass
class GameState:
    """Mutable state for one live game."""
    game_id:    str
    home_team:  int
    away_team:  int

    # Per-player history: list of (possessions_elapsed, gs_plus_raw)
    _history:   dict[int, list[tuple[int, float]]] = field(default_factory=dict)
    # Takeover sustain counter
    _takeover_count: dict[int, int] = field(default_factory=dict)


# ── Scoring math ──────────────────────────────────────────────────────────────

def _offensive_half(b: BoxStats) -> float:
    """Hollinger Game Score minus STL, BLK, DREB."""
    return (
        b.pts
        + 0.4 * b.fgm
        - 0.7 * b.fga
        - 0.4 * (b.fta - b.ftm)
        + 0.7 * b.oreb
        + 0.7 * b.ast
        - 0.4 * b.pf
        - float(b.tov)
    )


def _dragon_pts(b: BoxStats) -> float:
    """Live Dragon contribution (active perimeter disruption)."""
    return (
        0.25 * b.stl
        + 0.25 * b.deflections
        + 0.20 * b.charges_drawn
        + 0.20 * (b.contested_2pt + b.contested_3pt)
        + 0.10 * b.loose_balls
    )


def _fortress_pts(b: BoxStats) -> float:
    """Live Fortress contribution (interior anchoring)."""
    rim_fg_pct_inv = (
        1.0 - (b.rim_fgm_defended / max(b.rim_fga_defended, 1))
        if b.rim_fga_defended > 0 else 0.5
    )
    return (
        0.28 * rim_fg_pct_inv * b.rim_fga_defended  # volume-weighted deterrence
        + 0.22 * b.def_boxouts
        + 0.22 * b.blk
        + 0.18 * b.rim_fga_defended
        + 0.10 * b.oreb   # putback proxy
    )


def compute_gs_plus(b: BoxStats) -> float:
    """Raw GS+ for a single BoxStats."""
    off = _offensive_half(b)
    def_ = 0.7 * (_dragon_pts(b) + _fortress_pts(b))
    return off + def_


# ── Early-game shrinkage (Bayesian regression toward norm) ────────────────────

def _shrink(raw: float, norm: float, possessions: int) -> float:
    """
    Blend raw GS+ toward the player's season norm when few possessions
    have elapsed.  Weight rises linearly from 0 → 1 over MIN_POSSESSIONS_FULL
    possessions.
    """
    if possessions >= MIN_POSSESSIONS_FULL:
        return raw
    w = possessions / MIN_POSSESSIONS_FULL     # 0.0 at start, 1.0 at full
    return w * raw + (1 - w) * norm


# ── Velocity ──────────────────────────────────────────────────────────────────

def _velocity(history: list[tuple[int, float]], current_poss: int) -> tuple[float, str]:
    """
    Compare average GS+ over last VELOCITY_WINDOW possessions
    vs the prior VELOCITY_WINDOW possessions.
    Returns (velocity_score, arrow).
    """
    if len(history) < 2:
        return 0.0, "→"

    recent = [gs for p, gs in history if p > current_poss - VELOCITY_WINDOW]
    prior  = [gs for p, gs in history
              if current_poss - 2 * VELOCITY_WINDOW < p <= current_poss - VELOCITY_WINDOW]

    if not recent:
        return 0.0, "→"

    recent_avg = float(np.mean(recent))
    prior_avg  = float(np.mean(prior)) if prior else recent_avg
    vel        = recent_avg - prior_avg

    if vel > 2:
        arrow = "↑↑"
    elif vel > 0.5:
        arrow = "↑"
    elif vel < -2:
        arrow = "↓↓"
    elif vel < -0.5:
        arrow = "↓"
    else:
        arrow = "→"

    return vel, arrow


# ── Tier classification ───────────────────────────────────────────────────────

def _classify_tier(pct: float) -> tuple[str, str]:
    for name, lo, hi, color in TIERS:
        if lo <= pct < hi:
            return name, color
    return "FROZEN", TIER_COLORS["FROZEN"]


# ── Main computation ──────────────────────────────────────────────────────────

def compute_snapshot(
    box:         BoxStats,
    season_norm: float,
    state:       GameState,
) -> GSPlusSnapshot:
    """
    Compute a full GSPlusSnapshot from a live BoxStats + season baseline.
    Mutates game state (history, takeover counter).
    """
    raw = compute_gs_plus(box)

    # Early-game shrinkage
    shrunk = _shrink(raw, season_norm, box.possessions_elapsed)

    # % vs norm
    pct = (shrunk - season_norm) / max(abs(season_norm), 1.0) * 100.0

    tier, color = _classify_tier(pct)

    # Velocity
    hist = state._history.setdefault(box.player_id, [])
    if box.possessions_elapsed > 0:
        hist.append((box.possessions_elapsed, raw))
    vel, arrow = _velocity(hist, box.possessions_elapsed)

    # Takeover sustain logic
    tc = state._takeover_count
    if tier == "TAKEOVER":
        tc[box.player_id] = tc.get(box.player_id, 0) + 1
    else:
        tc[box.player_id] = 0
    takeover_active = tc.get(box.player_id, 0) >= TAKEOVER_SUSTAIN_POSSESSIONS

    # Bench state
    bench = box.min < BENCH_MINUTES_THRESHOLD and not box.on_court

    return GSPlusSnapshot(
        player_id=box.player_id,
        player_name=box.player_name,
        team_id=box.team_id,
        position=box.position,
        raw_gs_plus=round(shrunk, 2),
        pct_vs_norm=round(pct, 1),
        tier=tier,
        tier_color=color,
        velocity=round(vel, 2),
        velocity_arrow=arrow,
        takeover_active=takeover_active,
        bench_state=bench,
        foul_trouble=box.foul_trouble,
        season_norm=round(season_norm, 2),
    )


# ── nba_api live data fetching ────────────────────────────────────────────────

def _safe_int(v, default: int = 0) -> int:
    try:
        return int(v) if v is not None else default
    except (ValueError, TypeError):
        return default


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (ValueError, TypeError):
        return default


def _parse_min(min_str) -> float:
    """'12:34' → 12.57 minutes."""
    if not min_str:
        return 0.0
    try:
        parts = str(min_str).split(":")
        if len(parts) == 2:
            return int(parts[0]) + int(parts[1]) / 60.0
        return float(min_str)
    except Exception:
        return 0.0


def fetch_live_box_stats(game_id: str) -> list[BoxStats]:
    """
    Pull live traditional + hustle box scores from nba_api.
    Returns a list of BoxStats, one per active player.
    Falls back gracefully if endpoints are unavailable.
    """
    try:
        from nba_api.live.nba.endpoints import boxscore as LiveBoxscore
        box_data = LiveBoxscore.BoxScore(game_id=game_id)
        game = box_data.game.get_dict()
    except Exception as e:
        log.warning("Live boxscore unavailable for %s: %s", game_id, e)
        return []

    results: list[BoxStats] = []

    for team_key in ("homeTeam", "awayTeam"):
        team_info = game.get(team_key, {})
        team_id   = _safe_int(team_info.get("teamId"))
        players   = team_info.get("players", [])

        for p in players:
            pid   = _safe_int(p.get("personId"))
            name  = p.get("name", "Unknown")
            stats = p.get("statistics", {})

            minutes = _parse_min(stats.get("minutesCalculated") or stats.get("minutes"))
            on_court = bool(p.get("oncourt", minutes > 0))

            pf = _safe_int(stats.get("foulsPersonal"))
            # Rough foul trouble heuristic: 4+ fouls in regulation (check period separately if needed)
            foul_trouble = pf >= 4

            bs = BoxStats(
                player_id=pid,
                player_name=name,
                team_id=team_id,
                position=p.get("position", ""),
                min=minutes,
                pts=_safe_int(stats.get("points")),
                fgm=_safe_int(stats.get("fieldGoalsMade")),
                fga=_safe_int(stats.get("fieldGoalsAttempted")),
                ftm=_safe_int(stats.get("freeThrowsMade")),
                fta=_safe_int(stats.get("freeThrowsAttempted")),
                oreb=_safe_int(stats.get("reboundsOffensive")),
                dreb=_safe_int(stats.get("reboundsDefensive")),
                ast=_safe_int(stats.get("assists")),
                stl=_safe_int(stats.get("steals")),
                blk=_safe_int(stats.get("blocks")),
                tov=_safe_int(stats.get("turnovers")),
                pf=pf,
                # Hustle stats may not be in live endpoint; zero-fill
                deflections=_safe_int(stats.get("deflections")),
                charges_drawn=_safe_int(stats.get("chargesDrawn")),
                loose_balls=_safe_int(stats.get("looseBallsRecovered")),
                contested_2pt=_safe_int(stats.get("contestedShots2pt")),
                contested_3pt=_safe_int(stats.get("contestedShots3pt")),
                rim_fga_defended=_safe_int(stats.get("rimDefended", 0)),
                rim_fgm_defended=_safe_int(stats.get("rimFGMDefended", 0)),
                def_boxouts=_safe_int(stats.get("boxOutsDefensive")),
                possessions_elapsed=_safe_int(stats.get("possessionsElapsed", 0))
                    or max(0, int(minutes * 2.0)),   # estimate if unavailable
                on_court=on_court,
                foul_trouble=foul_trouble,
            )
            results.append(bs)

    return results


def get_live_games() -> list[dict]:
    """
    Return list of today's live/recent games from nba_api.
    Each dict: {game_id, home_team_id, away_team_id, home_abbr, away_abbr, status, period, clock}
    """
    try:
        from nba_api.live.nba.endpoints import scoreboard as LiveScoreboard
        sb = LiveScoreboard.ScoreBoard()
        games_raw = sb.games.get_dict()
    except Exception as e:
        log.warning("Live scoreboard unavailable: %s", e)
        return []

    results = []
    for g in games_raw:
        results.append({
            "game_id":      g.get("gameId", ""),
            "home_team_id": _safe_int(g.get("homeTeam", {}).get("teamId")),
            "away_team_id": _safe_int(g.get("awayTeam", {}).get("teamId")),
            "home_abbr":    g.get("homeTeam", {}).get("teamTricode", ""),
            "away_abbr":    g.get("awayTeam", {}).get("teamTricode", ""),
            "home_score":   _safe_int(g.get("homeTeam", {}).get("score")),
            "away_score":   _safe_int(g.get("awayTeam", {}).get("score")),
            "status":       g.get("gameStatusText", ""),
            "period":       _safe_int(g.get("period")),
            "clock":        g.get("gameClock", ""),
        })
    return results


# ── Season norm lookup ────────────────────────────────────────────────────────

# League-wide GS+ average (used when player-specific baseline is unavailable)
LEAGUE_AVG_GS_PLUS = 8.0

_norm_cache: dict[int, float] = {}


def get_player_season_norm(player_id: int, season_df: "pd.DataFrame | None" = None) -> float:
    """
    Return a player's season GS+ baseline.
    Uses season_df if provided (must have PLAYER_ID and GS_PLUS_NORM columns),
    otherwise returns league average.
    """
    if player_id in _norm_cache:
        return _norm_cache[player_id]

    norm = LEAGUE_AVG_GS_PLUS
    if season_df is not None and not season_df.empty:
        if "GS_PLUS_NORM" in season_df.columns and "PLAYER_ID" in season_df.columns:
            row = season_df[season_df["PLAYER_ID"] == player_id]
            if not row.empty:
                norm = float(row.iloc[0]["GS_PLUS_NORM"])

    _norm_cache[player_id] = norm
    return norm


def compute_gs_plus_norm_from_pipeline(pipeline_df: "pd.DataFrame") -> "pd.DataFrame":
    """
    Given the pipeline DataFrame (with traditional season stats),
    approximate each player's season GS+ norm and add GS_PLUS_NORM column.

    Uses season-long totals / GP to get per-game averages, then applies
    the GS+ formula to get a typical per-game value.
    """
    df = pipeline_df.copy()
    required = {"PTS", "FGM", "FGA", "FTA", "FTM", "OREB", "AST", "PF", "TOV", "GP"}
    if not required.issubset(df.columns):
        df["GS_PLUS_NORM"] = LEAGUE_AVG_GS_PLUS
        return df

    gp = df["GP"].clip(lower=1)
    off = (
        df["PTS"] / gp
        + 0.4 * df["FGM"] / gp
        - 0.7 * df["FGA"] / gp
        - 0.4 * (df["FTA"] - df["FTM"]) / gp
        + 0.7 * df["OREB"] / gp
        + 0.7 * df["AST"] / gp
        - 0.4 * df["PF"] / gp
        - df["TOV"] / gp
    )

    # Defensive half: approximate from Dragon/Fortress season values
    def_ = pd.Series(0.0, index=df.index)
    if "DRAGON_INDEX" in df.columns and "FORTRESS_RATING" in df.columns:
        # Dragon/Fortress are 0-100 indices; scale to per-game pts
        def_ = 0.7 * (df["DRAGON_INDEX"] / 10.0 + df["FORTRESS_RATING"] / 10.0)

    df["GS_PLUS_NORM"] = (off + def_).clip(lower=0)
    return df


# ── Lineup slot assignment ────────────────────────────────────────────────────

_POS_PRIORITY: dict[str, int] = {"PG": 1, "SG": 2, "SF": 3, "PF": 4, "C": 5}

def assign_lineup_slots(
    players: list[BoxStats],
    team_id: int,
) -> list[BoxStats]:
    """
    Assign each active on-court player to a canonical slot (PG/SG/SF/PF/C).
    Simple greedy: sort by position priority, assign first-match.
    Falls back to remaining slots in order.
    """
    team_players = [p for p in players if p.team_id == team_id and p.on_court]
    # Sort by listed position
    team_players.sort(key=lambda p: _POS_PRIORITY.get(p.position.upper(), 9))
    slots = list(POSITION_SLOTS)
    assigned: list[BoxStats] = []
    used_slots: set[str] = set()

    # First pass: exact match
    for p in team_players:
        pos = p.position.upper()
        if pos in slots and pos not in used_slots:
            p.position = pos
            used_slots.add(pos)
            assigned.append(p)

    # Second pass: remaining players get remaining slots
    remaining_players = [p for p in team_players if p not in assigned]
    remaining_slots   = [s for s in slots if s not in used_slots]
    for p, s in zip(remaining_players, remaining_slots):
        p.position = s
        assigned.append(p)

    return assigned
