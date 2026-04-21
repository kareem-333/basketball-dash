"""
GS+ Live Momentum Engine — app.py (brief v5)
Run with:  streamlit run app.py
"""

from __future__ import annotations

import hashlib
import os
import time
from typing import Optional

import pandas as pd
import streamlit as st

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="GS+ Live",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Internal imports ──────────────────────────────────────────────────────────
from nba.pipeline import (
    get_all_player_metrics,
    get_team_aggregates,
    get_player_rolling_trend,
    get_play_sequence_stats,
    nba_headshot_url,
    SEASON,
)
from nba.charts import (
    plot_bubble_scatter,
    plot_leaderboard,
    plot_comparison_radar,
    plot_comparison_rolling,
    plot_team_bubbles,
    plot_steal_chain_sankey,
    plot_sequence_comparison,
)
from nba.live_engine import (
    GameState,
    BoxStats,
    GSPlusSnapshot,
    TIER_COLORS,
    POSITION_SLOTS,
    compute_snapshot,
    compute_gs_plus_norm_from_pipeline,
    fetch_live_box_stats,
    get_live_games,
    get_player_season_norm,
    assign_lineup_slots,
)
from nba.court_svg import (
    court_svg_desktop,
    court_svg_mobile,
    DESKTOP_SLOTS,
    MOBILE_SLOTS,
)
import datetime
import nba.analytics as analytics

# ── Streamlit fragment support check (requires ≥ 1.33) ───────────────────────
try:
    _st_ver = tuple(int(x) for x in st.__version__.split(".")[:2])
    _HAS_FRAGMENT = _st_ver >= (1, 33)
except Exception:
    _HAS_FRAGMENT = False

# ── Admin password hash ───────────────────────────────────────────────────────
_ADMIN_PW_HASH = hashlib.sha256(
    os.environ.get("ADMIN_PASSWORD", "gsplus2025").encode()
).hexdigest()

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Base ──────────────────────────────────────────────────────────────── */
body, [data-testid="stAppViewContainer"] {
  background: #0a0a0f !important;
  color: #e0e0e0;
  font-family: 'Inter', 'Segoe UI', sans-serif;
}
[data-testid="stSidebar"] { background: #0e0e18 !important; }

/* ── Court wrapper ──────────────────────────────────────────────────────── */
.court-wrap {
  position: relative;
  width: 100%;
  max-width: 1100px;
  margin: 12px auto;
  aspect-ratio: 94 / 50;
  user-select: none;
}
.court-svg-layer {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.card-anchor {
  position: absolute;
  transform: translate(-50%, -50%);
  width: 17%;
  min-width: 100px;
  max-width: 160px;
  z-index: 2;
}
@media (max-width: 767px) {
  .court-wrap { aspect-ratio: 50 / 94; max-width: 380px; }
}

/* ── Player cards ────────────────────────────────────────────────────────── */
.card-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
  margin: 10px 0 4px;
}
.card-grid-away {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
  margin: 4px 0 10px;
}
.gs-card {
  position: relative;
  background: rgba(14,14,24,0.88);
  border: 1px solid #2a2a3a;
  border-radius: 8px;
  padding: 8px 10px 7px;
  cursor: pointer;
  transition: transform 0.12s ease, border-color 0.12s ease;
  text-decoration: none;
  display: block;
  min-width: 90px;
}
.gs-card:hover { transform: translateY(-2px); border-color: #EB6E1F88; }

.gs-card.takeover {
  border: 2px solid #FF4500;
  box-shadow: 0 0 12px #FF450055;
}
.gs-card.bench { opacity: 0.55; }

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 2px;
}
.card-name  { font-size: 10px; font-weight: 500; color: #ffffff; }
.card-raw   { font-size: 8px;  color: #666; }
.card-pct   { font-size: 20px; font-weight: 500; text-align: center; margin: 2px 0; line-height: 1.1; }
.card-label { font-size: 7px;  color: #555; text-align: center; margin-top: 1px; }

.takeover-pill {
  position: absolute;
  top: -12px; left: 50%; transform: translateX(-50%);
  background: #FF4500;
  color: #fff;
  font-size: 7px; font-weight: 700;
  padding: 1px 6px;
  border-radius: 8px;
  white-space: nowrap;
}
.foul-icon  { position: absolute; top: 3px; left: 3px; font-size: 9px; }
.bench-icon { position: absolute; top: 3px; right: 3px; font-size: 9px; }

/* ── Game selector bar ───────────────────────────────────────────────────── */
.game-bar {
  display: flex; gap: 8px; flex-wrap: wrap;
  margin-bottom: 10px;
}
.game-chip {
  background: #1a1a2e;
  border: 1px solid #2a2a4a;
  border-radius: 20px;
  padding: 4px 14px;
  font-size: 12px;
  color: #aaa;
  cursor: pointer;
  white-space: nowrap;
}
.game-chip.active {
  background: #EB6E1F22;
  border-color: #EB6E1F;
  color: #EB6E1F;
  font-weight: 700;
}

/* ── Team label strip ────────────────────────────────────────────────────── */
.team-strip {
  display: flex; justify-content: space-between;
  align-items: center;
  font-size: 13px; font-weight: 600;
  color: #ccc;
  margin-bottom: 4px;
  padding: 0 2px;
}
.team-strip .score { font-size: 20px; font-weight: 700; color: #fff; }
.team-strip .clock { font-size: 11px; color: #777; }

/* ── Bio page ────────────────────────────────────────────────────────────── */
.bio-back { font-size: 13px; color: #EB6E1F; cursor: pointer; margin-bottom: 16px; display: inline-block; }
.bio-back:hover { text-decoration: underline; }

.bio-header {
  display: flex; align-items: flex-start; gap: 18px;
  margin-bottom: 18px;
}
.bio-headshot {
  border-radius: 8px;
  width: 100px; height: 120px;
  object-fit: cover;
  background: #1a1a2e;
}
.bio-name   { font-size: 22px; font-weight: 700; color: #fff; margin-bottom: 3px; }
.bio-meta   { font-size: 13px; color: #888; margin-bottom: 2px; }
.bio-detail { font-size: 11px; color: #666; }

.bio-ctx-cards { display: flex; gap: 12px; margin-bottom: 18px; }
.bio-ctx-card {
  background: #12121e;
  border: 1px solid #2a2a3a;
  border-radius: 8px;
  padding: 10px 16px;
  min-width: 120px;
}
.bio-ctx-card.live { border-color: #EB6E1F; }
.bio-ctx-label { font-size: 9px; color: #666; text-transform: uppercase; letter-spacing: 1px; }
.bio-ctx-value { font-size: 22px; font-weight: 600; margin: 2px 0; }
.bio-ctx-sub   { font-size: 10px; color: #888; }

.stat-strip {
  display: flex; gap: 10px; flex-wrap: wrap;
  margin-bottom: 18px;
}
.stat-box {
  background: #12121e;
  border: 1px solid #1e1e30;
  border-radius: 6px;
  padding: 8px 12px;
  text-align: center;
  min-width: 62px;
}
.stat-val { font-size: 18px; font-weight: 600; color: #fff; }
.stat-lbl { font-size: 8px; color: #666; text-transform: uppercase; margin-top: 1px; }

.df-index-row { display: flex; gap: 12px; margin-bottom: 18px; }
.df-card {
  flex: 1;
  background: #12121e;
  border: 1px solid #1e1e30;
  border-radius: 8px;
  padding: 12px 16px;
}
.df-card-label { font-size: 9px; color: #666; text-transform: uppercase; letter-spacing: 1px; }
.df-card-value { font-size: 28px; font-weight: 700; color: #EB6E1F; }
.df-card-rank  { font-size: 11px; color: #888; }
.df-card-qual  { font-size: 10px; color: #aaa; margin-top: 4px; font-style: italic; }

/* ── Metric pill (reused from season) ───────────────────────────────────── */
.metric-pill {
  display: inline-block; background: #1a2a4a;
  border-radius: 8px; padding: 4px 14px;
  font-size: 0.82rem; font-weight: 700; color: #e0e0e0;
  margin: 2px 4px;
}
.dragon-pill   { background: #8B1A1A; }
.fortress-pill { background: #1A3A5C; }
.sec-hdr {
  font-size: 0.9rem; font-weight: 700; color: #EB6E1F;
  border-bottom: 1px solid #EB6E1F44;
  margin-bottom: 0.4rem; padding-bottom: 2px;
}

/* ── TAKEOVER pulse animation ─────────────────────────────────────────────── */
@keyframes takeover-pulse {
  0%, 100% { box-shadow: 0 0 8px #FF450055; }
  50%       { box-shadow: 0 0 22px #FF4500cc; }
}
.gs-card.takeover { animation: takeover-pulse 1.4s ease-in-out infinite; }

/* ── FROZEN shimmer ─────────────────────────────────────────────────────── */
@keyframes frozen-shimmer {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.7; }
}
.gs-card.frozen { animation: frozen-shimmer 2s ease-in-out infinite; }

/* ── Admin ───────────────────────────────────────────────────────────────── */
.admin-metric {
  background: #12121e; border: 1px solid #2a2a3a;
  border-radius: 8px; padding: 12px 20px; text-align: center;
}
.admin-metric .val { font-size: 28px; font-weight: 700; color: #EB6E1F; }
.admin-metric .lbl { font-size: 10px; color: #666; text-transform: uppercase; }
</style>
""", unsafe_allow_html=True)

# ── Session / analytics bootstrap ────────────────────────────────────────────
if "session_id" not in st.session_state:
    st.session_state["session_id"] = analytics.make_session_id()
if "visitor_id" not in st.session_state:
    st.session_state["visitor_id"] = analytics.fingerprint_visitor()

analytics.track_page_view(
    st.session_state["session_id"],
    st.session_state["visitor_id"],
    path=st.session_state.get("active_player_id") and "/bio" or "/",
)

# ── Session state defaults ────────────────────────────────────────────────────
_NAV_OPTIONS = ["🏠 Live Court", "🎬 Replay", "📊 Season", "🔧 Admin"]

for key, default in [
    ("active_player_id", None),
    ("selected_game_id", None),
    ("compare_ids", []),
    ("admin_auth", False),
    ("nav", "🏠 Live Court"),   # free key — NOT bound to any widget
    ("debug_mode", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ══════════════════════════════════════════════════════════════════════════════
# Helper: season data (cached)
# ══════════════════════════════════════════════════════════════════════════════

def _season_hash(df: pd.DataFrame) -> str:
    """Quick fingerprint of season_df for cache invalidation (FIX 5)."""
    if df is None or df.empty:
        return "empty"
    try:
        if "GS_PLUS_NORM" in df.columns:
            return hashlib.md5(
                f"{len(df)}_{df['GS_PLUS_NORM'].sum():.2f}".encode()
            ).hexdigest()[:12]
    except Exception:
        pass
    return hashlib.md5(f"{len(df)}".encode()).hexdigest()[:12]


@st.cache_data(ttl=3_600, show_spinner=False)
def _games_for_date(d: datetime.date) -> list[dict]:
    """Fetch all games for a specific past date (FIX 4)."""
    try:
        from nba_api.stats.endpoints import scoreboardv2
        time.sleep(0.5)
        sb = scoreboardv2.ScoreboardV2(game_date=d.strftime("%m/%d/%Y"))
        df = sb.game_header.get_data_frame()
        ls = sb.line_score.get_data_frame()
        out = []
        for _, r in df.iterrows():
            gid = str(r["GAME_ID"])
            # Pull team abbreviations from line_score
            ls_game = ls[ls["GAME_ID"] == gid] if "GAME_ID" in ls.columns else pd.DataFrame()
            abbrs = ls_game["TEAM_ABBREVIATION"].tolist() if not ls_game.empty else ["", ""]
            away_abbr = abbrs[0] if len(abbrs) > 0 else ""
            home_abbr = abbrs[1] if len(abbrs) > 1 else ""
            away_pts = int(ls_game.iloc[0]["PTS"] if not ls_game.empty else 0)
            home_pts = int(ls_game.iloc[1]["PTS"] if len(ls_game) > 1 else 0)
            out.append({
                "game_id":      gid,
                "home_team_id": int(r.get("HOME_TEAM_ID", 0) or 0),
                "away_team_id": int(r.get("VISITOR_TEAM_ID", 0) or 0),
                "home_abbr":    home_abbr,
                "away_abbr":    away_abbr,
                "home_score":   home_pts,
                "away_score":   away_pts,
                "period":       4,
                "clock":        "Final",
                "status":       "Final",
                "is_live":      False,
            })
        return out
    except Exception:
        return []


@st.cache_data(ttl=86_400, show_spinner=False)
def _season_df() -> pd.DataFrame:
    try:
        df = get_all_player_metrics()
        if df is not None and not df.empty:
            result = compute_gs_plus_norm_from_pipeline(df)
            # FIX 5 — sanity check
            if "GS_PLUS_NORM" not in result.columns or result["GS_PLUS_NORM"].isna().all():
                st.toast("⚠️ Season norms not computed — cards will use league fallback", icon="⚠️")
            return result
    except Exception:
        pass
    return pd.DataFrame()


@st.cache_data(ttl=86_400, show_spinner=False)
def _player_bio(player_id: int) -> dict:
    """Fetch player info from nba_api commonplayerinfo."""
    info: dict = {}
    try:
        from nba_api.stats.endpoints import CommonPlayerInfo
        time.sleep(0.5)
        cpi = CommonPlayerInfo(player_id=player_id)
        row = cpi.common_player_info.get_data_frame().iloc[0]
        info = {
            "jersey":   str(row.get("JERSEY", "")),
            "position": str(row.get("POSITION", "")),
            "team":     str(row.get("TEAM_ABBREVIATION", "")),
            "height":   str(row.get("HEIGHT", "")),
            "weight":   str(row.get("WEIGHT", "")),
            "age":      str(row.get("AGE", "")),
            "exp":      str(row.get("SEASON_EXP", "")),
            "name":     str(row.get("DISPLAY_FIRST_LAST", "")),
        }
    except Exception:
        pass
    return info


@st.cache_data(ttl=86_400, show_spinner=False)
def _season_averages(player_id: int) -> dict:
    """Per-game season averages for bio page."""
    avgs: dict = {}
    try:
        from nba_api.stats.endpoints import PlayerCareerStats
        time.sleep(0.5)
        pcs = PlayerCareerStats(player_id=player_id, per_mode36="PerGame")
        df = pcs.season_totals_regular_season.get_data_frame()
        if df.empty:
            return avgs
        row = df[df["SEASON_ID"] == SEASON]
        if row.empty:
            row = df.iloc[-1:]
        row = row.iloc[0]
        avgs = {
            "PPG":  round(float(row.get("PTS", 0)), 1),
            "APG":  round(float(row.get("AST", 0)), 1),
            "RPG":  round(float(row.get("REB", 0)), 1),
            "SPG":  round(float(row.get("STL", 0)), 1),
            "BPG":  round(float(row.get("BLK", 0)), 1),
            "FG%":  round(float(row.get("FG_PCT", 0)) * 100, 1),
            "3P%":  round(float(row.get("FG3_PCT", 0)) * 100, 1),
            "FT%":  round(float(row.get("FT_PCT", 0)) * 100, 1),
            "MPG":  round(float(row.get("MIN", 0)), 1),
        }
    except Exception:
        pass
    return avgs


@st.cache_data(ttl=3_600, show_spinner=False)
def _last5_games(player_id: int, season_df: pd.DataFrame) -> list[dict]:
    """Last 5 game logs with GS+ and % vs norm."""
    games: list[dict] = []
    try:
        from nba_api.stats.endpoints import PlayerGameLog
        time.sleep(0.5)
        pgl = PlayerGameLog(player_id=player_id, season=SEASON, season_type_all_star="Regular Season")
        df = pgl.player_game_log.get_data_frame().head(5)
        norm = get_player_season_norm(player_id, season_df)
        for _, r in df.iterrows():
            bs = BoxStats(
                player_id=player_id,
                player_name="",
                team_id=0,
                position="",
                min=float(str(r.get("MIN", "0")).split(":")[0]) if r.get("MIN") else 0,
                pts=int(r.get("PTS", 0)),
                fgm=int(r.get("FGM", 0)),
                fga=int(r.get("FGA", 0)),
                ftm=int(r.get("FTM", 0)),
                fta=int(r.get("FTA", 0)),
                oreb=int(r.get("OREB", 0)),
                dreb=int(r.get("DREB", 0)),
                ast=int(r.get("AST", 0)),
                stl=int(r.get("STL", 0)),
                blk=int(r.get("BLK", 0)),
                tov=int(r.get("TOV", 0)),
                pf=int(r.get("PF", 0)),
                possessions_elapsed=100,  # full game
            )
            from nba.live_engine import compute_gs_plus, _classify_tier
            raw = compute_gs_plus(bs)
            pct = (raw - norm) / max(abs(norm), 1) * 100
            tier, color = _classify_tier(pct)
            games.append({
                "date":   str(r.get("GAME_DATE", "")),
                "opp":    str(r.get("MATCHUP", "")).split()[-1],
                "result": str(r.get("WL", "")),
                "min":    str(r.get("MIN", "")),
                "pts":    int(r.get("PTS", 0)),
                "ast":    int(r.get("AST", 0)),
                "reb":    int(r.get("REB", 0)),
                "gs_raw": round(raw, 1),
                "gs_pct": round(pct, 1),
                "color":  color,
            })
    except Exception:
        pass
    return games


# ══════════════════════════════════════════════════════════════════════════════
# LIVE DATA helpers
# ══════════════════════════════════════════════════════════════════════════════

from nba.replay import (
    fetch_recent_games,
    fetch_play_by_play,
    fetch_box_roster,
    build_replay_timeline,
    quarter_checkpoints,
    get_snapshots_at_frame,
)

_LIVE_STATUS_KEYWORDS = ("q1", "q2", "q3", "q4", "ot", "halftime", "end of")


@st.cache_data(ttl=30, show_spinner=False)
def _live_games() -> list[dict]:
    games = get_live_games()
    for g in games:
        status_lower = str(g.get("status", "")).lower()
        g["is_live"] = any(kw in status_lower for kw in _LIVE_STATUS_KEYWORDS)
    return games


# ── Replay cached fetchers ────────────────────────────────────────────────────

@st.cache_data(ttl=3_600, show_spinner=False)
def _recent_games(days_back: int = 7) -> list[dict]:
    try:
        return fetch_recent_games(days_back)
    except Exception:
        return []


@st.cache_data(ttl=3_600, show_spinner=False)
def _replay_timeline(game_id: str):
    """Build full replay timeline for a completed game. Cached 1 h."""
    try:
        pbp    = fetch_play_by_play(game_id)
        roster = fetch_box_roster(game_id)
        return build_replay_timeline(pbp, roster)
    except Exception as e:
        return []


def _enrich_hustle(b: "BoxStats", season_df: "pd.DataFrame") -> "BoxStats":
    """Fill zero hustle fields with season averages scaled by possession fraction.

    The live boxscore endpoint doesn't include hustle stats (deflections, contested
    shots, rim stats), so the defensive half of GS+ would be ~0 without this.
    We use season per-game averages scaled by how much of the game has been played.
    """
    if season_df is None or season_df.empty or "PLAYER_ID" not in season_df.columns:
        return b
    row = season_df[season_df["PLAYER_ID"] == b.player_id]
    if row.empty:
        return b
    r = row.iloc[0]
    # ~96 half-court possessions per game; clamp to [0, 1]
    scale = min(b.possessions_elapsed / 96.0, 1.0) if b.possessions_elapsed > 0 else 0.5

    def _fill(live_val: int, col: str) -> int:
        if live_val > 0:
            return live_val
        return int(round(float(r.get(col, 0) or 0) * scale))

    from dataclasses import replace as _replace
    return _replace(b,
        deflections=_fill(b.deflections, "DEFLECTIONS"),
        charges_drawn=_fill(b.charges_drawn, "CHARGES_DRAWN"),
        contested_2pt=_fill(b.contested_2pt, "CONTESTED_SHOTS_2PT"),
        contested_3pt=_fill(b.contested_3pt, "CONTESTED_SHOTS_3PT"),
        loose_balls=_fill(b.loose_balls, "DEF_LOOSE_BALLS_RECOVERED"),
        def_boxouts=_fill(b.def_boxouts, "DEF_BOXOUTS"),
        rim_fga_defended=_fill(b.rim_fga_defended, "DEF_RIM_FGA"),
        rim_fgm_defended=_fill(b.rim_fgm_defended, "DEF_RIM_FGM"),
    )


@st.cache_data(ttl=30, show_spinner=False)
def _live_snapshots(game_id: str, season_df_hash: str) -> list[GSPlusSnapshot]:
    """Compute GS+ snapshots for all players in a game. Cache 30 s."""
    sdf = _season_df()
    boxes = fetch_live_box_stats(game_id)
    if not boxes:
        return []

    # Build a minimal GameState per game (not persisted across cache hits)
    state = GameState(game_id=game_id, home_team=0, away_team=0)

    snaps: list[GSPlusSnapshot] = []
    for b in boxes:
        b = _enrich_hustle(b, sdf)
        norm = get_player_season_norm(b.player_id, sdf)
        snap = compute_snapshot(b, norm, state)
        snaps.append(snap)
    return snaps


# ══════════════════════════════════════════════════════════════════════════════
# CARD HTML builder
# ══════════════════════════════════════════════════════════════════════════════

def _card_html(snap: GSPlusSnapshot, debug_mode: bool = False) -> str:
    sign     = "+" if snap.pct_vs_norm >= 0 else ""
    pct_str  = f"{sign}{snap.pct_vs_norm:.0f}%"
    raw_str  = f"{snap.raw_gs_plus:+.1f}"

    css_cls  = "gs-card"
    if snap.takeover_active:
        css_cls += " takeover"
    elif snap.tier == "FROZEN":
        css_cls += " frozen"
    if snap.bench_state:
        css_cls += " bench"

    takeover_pill = (
        '<span class="takeover-pill">🔥 TAKEOVER</span>'
        if snap.takeover_active else ""
    )
    foul_icon  = '<span class="foul-icon">⚠️</span>' if snap.foul_trouble else ""
    bench_icon = '<span class="bench-icon">🪑</span>' if snap.bench_state else ""

    arrow = snap.velocity_arrow

    # FIX 5 — optional debug row showing norm and raw GS+
    debug_row = (
        f'<div class="card-raw" style="color:#EB6E1F88;margin-top:2px;">'
        f'norm {snap.season_norm:.1f} | raw {snap.raw_gs_plus:.1f}</div>'
        if debug_mode else ""
    )

    # Clicking the card sets active_player in session state via a query param hack
    # (Streamlit doesn't support onclick easily; we use st.button workarounds upstream)
    return f"""
<div class="{css_cls}" data-player-id="{snap.player_id}"
     onclick="window.location.href='?player={snap.player_id}'"
     title="Click for {snap.player_name} bio">
  {takeover_pill}{foul_icon}{bench_icon}
  <div class="card-top">
    <span class="card-name">{snap.player_name.split()[-1]}</span>
    <span class="card-raw">{raw_str}</span>
  </div>
  <div class="card-pct" style="color:{snap.tier_color}">
    {pct_str} {arrow}
  </div>
  <div class="card-label">vs. norm</div>
  {debug_row}
</div>
"""


# ══════════════════════════════════════════════════════════════════════════════
# PLAYER BIO PAGE
# ══════════════════════════════════════════════════════════════════════════════

def render_bio_page(player_id: int, season_df: pd.DataFrame) -> None:
    if st.button("← Back to court", key="bio_back"):
        st.session_state["active_player_id"] = None
        st.rerun()

    with st.spinner("Loading player data…"):
        bio   = _player_bio(player_id)
        avgs  = _season_averages(player_id)
        last5 = _last5_games(player_id, season_df)

    player_name = bio.get("name", f"Player {player_id}")
    headshot    = nba_headshot_url(player_id).replace("1040x760", "260x190")

    # ── Dragon / Fortress from season_df ──────────────────────────────────
    dragon_val = fortress_val = dragon_rank = fortress_rank = None
    if not season_df.empty and "PLAYER_ID" in season_df.columns:
        prow = season_df[season_df["PLAYER_ID"] == player_id]
        if not prow.empty:
            dragon_val   = prow.iloc[0].get("DRAGON_INDEX")
            fortress_val = prow.iloc[0].get("FORTRESS_RATING")
            if dragon_val is not None:
                dragon_rank   = int((season_df["DRAGON_INDEX"] > dragon_val).sum() + 1)
            if fortress_val is not None:
                fortress_rank = int((season_df["FORTRESS_RATING"] > fortress_val).sum() + 1)
    norm = get_player_season_norm(player_id, season_df)

    # ── Identity header ───────────────────────────────────────────────────
    col_img, col_info = st.columns([1, 4])
    with col_img:
        st.image(headshot, width=100)
    with col_info:
        st.subheader(player_name)
        jersey, position, team = bio.get("jersey",""), bio.get("position",""), bio.get("team","")
        st.caption(f"#{jersey} · {position} · {team}")
        height, weight, age, exp = bio.get("height",""), bio.get("weight",""), bio.get("age",""), bio.get("exp","")
        st.caption(f"{height} · {weight} lbs · Age {age} · {exp} yr exp")

    st.divider()

    # ── Context metrics row ───────────────────────────────────────────────
    ctx_cols = st.columns(3)
    ctx_cols[0].metric("Season GS+ Norm", f"{norm:+.1f}", help="Per-game baseline GS+")
    if dragon_val is not None:
        ctx_cols[1].metric("🐉 Dragon Index", f"{dragon_val:.1f}", f"#{dragon_rank} league")
    if fortress_val is not None:
        ctx_cols[2].metric("🏰 Fortress Rating", f"{fortress_val:.1f}", f"#{fortress_rank} league")

    # ── Season averages ───────────────────────────────────────────────────
    if avgs:
        st.markdown("**Season averages**")
        stat_keys = ["PPG", "APG", "RPG", "SPG", "FG%", "3P%", "FT%", "MPG"]
        avg_cols = st.columns(len(stat_keys))
        for col, k in zip(avg_cols, stat_keys):
            val = avgs.get(k, "—")
            suffix = "%" if "%" in k else ""
            col.metric(k, f"{val}{suffix}")

    st.divider()

    # ── Dragon + Fortress qualitative labels ──────────────────────────────
    if dragon_val is not None or fortress_val is not None:
        def _dragon_label(v):
            if v >= 75: return "Elite perimeter disruptor"
            if v >= 55: return "Active perimeter disruptor"
            if v >= 35: return "Moderate perimeter disruptor"
            return "Limited perimeter presence"

        def _fortress_label(v):
            if v >= 75: return "Elite rim protector"
            if v >= 55: return "Reliable paint anchor"
            if v >= 35: return "Moderate interior presence"
            return "Not a paint anchor"

        df_cols = st.columns(2)
        if dragon_val is not None:
            with df_cols[0]:
                st.markdown("**🐉 Dragon Index**")
                st.metric("Score", f"{dragon_val:.1f}", f"#{dragon_rank} league-wide")
                st.caption(_dragon_label(dragon_val))
        if fortress_val is not None:
            with df_cols[1]:
                st.markdown("**🏰 Fortress Rating**")
                st.metric("Score", f"{fortress_val:.1f}", f"#{fortress_rank} league-wide")
                st.caption(_fortress_label(fortress_val))

    # ── Last 5 games table ────────────────────────────────────────────────
    st.markdown("**Last 5 games**")
    if last5:
        rows = []
        for g in last5:
            sign = "+" if g["gs_pct"] >= 0 else ""
            rows.append({
                "Date":     g["date"],
                "Opp":      g["opp"],
                "W/L":      g["result"],
                "Min":      g["min"],
                "Pts":      g["pts"],
                "Ast":      g["ast"],
                "Reb":      g["reb"],
                "GS+":      f"{g['gs_raw']:+.1f}",
                "vs Norm":  f"{sign}{g['gs_pct']:.0f}%",
            })
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "vs Norm": st.column_config.TextColumn("vs Norm"),
            },
        )
    else:
        st.caption("Game log unavailable.")

    # ── Tonight's live GS+ (if applicable) ───────────────────────────────
    live_games = _live_games()
    for g in live_games:
        for s in _live_snapshots(g["game_id"], _season_hash(season_df)):
            if s.player_id == player_id:
                st.divider()
                st.markdown("**Tonight — live GS+**")
                lc1, lc2, lc3 = st.columns(3)
                sign = "+" if s.pct_vs_norm >= 0 else ""
                lc1.metric("vs Norm", f"{sign}{s.pct_vs_norm:.0f}%")
                lc2.metric("Raw GS+", f"{s.raw_gs_plus:+.1f}")
                lc3.metric("Tier", s.tier)
                break


# ══════════════════════════════════════════════════════════════════════════════
# COURT + CARDS RENDERER (FIX 3)
# ══════════════════════════════════════════════════════════════════════════════

def _render_court_with_cards(
    home_top5: "list[GSPlusSnapshot]",
    away_top5: "list[GSPlusSnapshot]",
    home_abbr: str,
    away_abbr: str,
    debug_mode: bool = False,
) -> None:
    """
    Render the basketball court SVG with 10 player cards absolutely positioned
    over it in the negative space (FIX 3).

    Away team occupies the LEFT half, home team occupies the RIGHT half.
    Slot coords are (left%, top%) as percentage of the .court-wrap container.
    """
    # Slot definitions matching DESKTOP_SLOTS from court_svg.py
    LEFT_SLOTS  = {
        "PG": (28, 50),
        "SG": (15, 22),
        "SF": (15, 78),
        "PF": ( 4, 18),
        "C":  ( 4, 82),
    }
    RIGHT_SLOTS = {
        "PG": (72, 50),
        "SG": (85, 22),
        "SF": (85, 78),
        "PF": (96, 18),
        "C":  (96, 82),
    }
    POSITIONS = ["PG", "SG", "SF", "PF", "C"]

    def _anchor(left_pct: float, top_pct: float, card_html: str) -> str:
        return (
            f'<div class="card-anchor" style="left:{left_pct}%;top:{top_pct}%;">'
            f'{card_html}</div>'
        )

    # Build card HTML for all 10 slots
    away_html = ""
    for i, snap in enumerate(away_top5[:5]):
        pos  = POSITIONS[i] if i < len(POSITIONS) else "PG"
        slot = LEFT_SLOTS.get(pos, (10, 50))
        away_html += _anchor(*slot, _card_html(snap, debug_mode=debug_mode))

    home_html = ""
    for i, snap in enumerate(home_top5[:5]):
        pos  = POSITIONS[i] if i < len(POSITIONS) else "PG"
        slot = RIGHT_SLOTS.get(pos, (90, 50))
        home_html += _anchor(*slot, _card_html(snap, debug_mode=debug_mode))

    svg_content = court_svg_desktop()

    # Team label overlay (top corners of the wrapper)
    away_label_html = (
        f'<div style="position:absolute;left:1%;top:2%;'
        f'font-size:11px;font-weight:700;color:#ccc;z-index:3;">{away_abbr}</div>'
    )
    home_label_html = (
        f'<div style="position:absolute;right:1%;top:2%;'
        f'font-size:11px;font-weight:700;color:#ccc;z-index:3;">{home_abbr}</div>'
    )

    html = (
        '<div class="court-wrap">'
        f'  <div class="court-svg-layer">{svg_content}</div>'
        f'  {away_label_html}'
        f'  {home_label_html}'
        f'  {away_html}'
        f'  {home_html}'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# HOMEPAGE — court + cards
# ══════════════════════════════════════════════════════════════════════════════

def render_homepage(season_df: pd.DataFrame) -> None:
    # ── Handle ?player= query param (card click → bio routing) ─────────────
    try:
        params = st.query_params
        qp = params.get("player")
        if qp:
            pid = int(qp)
            st.session_state["active_player_id"] = pid
            st.query_params.clear()
            st.rerun()
    except Exception:
        pass

    # ── Date picker (FIX 4) ───────────────────────────────────────────────
    date_col, info_col = st.columns([1, 4])
    with date_col:
        selected_date = st.date_input(
            "Date",
            value=datetime.date.today(),
            max_value=datetime.date.today(),
            key="homepage_date",
            label_visibility="collapsed",
        )
    is_today = (selected_date == datetime.date.today())

    if is_today:
        games = _live_games()
    else:
        with st.spinner(f"Loading games for {selected_date}…"):
            games = _games_for_date(selected_date)
        if games:
            info_col.info(
                f"📅 {selected_date.strftime('%b %d, %Y')} — replay mode. "
                "Pick a game, then use 🎬 Replay for the full scrubber."
            )

    st.markdown("### 🏀 GS+ Live Momentum")

    if not games:
        msg = (
            "No live games right now. The court populates automatically when a game starts."
            if is_today else f"No games found for {selected_date}."
        )
        st.info(msg)
        _render_season_tabs(season_df)
        return

    # ── Game selector ─────────────────────────────────────────────────────
    game_labels = {
        g["game_id"]: (
            f"{'🔴 ' if g.get('is_live') else ''}"
            f"{g['away_abbr']} @ {g['home_abbr']}  "
            f"{g['away_score']}–{g['home_score']}  {g['status']}"
        )
        for g in games
    }
    game_ids = list(game_labels.keys())

    if st.session_state["selected_game_id"] not in game_ids:
        st.session_state["selected_game_id"] = game_ids[0]

    sel = st.radio(
        "Game",
        game_ids,
        format_func=lambda gid: game_labels[gid],
        horizontal=True,
        key="game_radio",
        label_visibility="collapsed",
    )
    st.session_state["selected_game_id"] = sel
    game = next(g for g in games if g["game_id"] == sel)

    # Past date → shortcut to replay
    if not is_today and not game.get("is_live"):
        if st.button("🎬 Open in Replay", key="open_replay"):
            st.session_state["nav"] = "🎬 Replay"
            st.session_state["replay_game_sel"] = sel
            st.rerun()

    # ── Team strip ────────────────────────────────────────────────────────
    period_lbl = f"Q{game['period']}" if game["period"] <= 4 else f"OT{game['period']-4}"
    st.markdown(
        f'<div class="team-strip">'
        f'<span>{game["away_abbr"]}</span>'
        f'<span class="score">{game["away_score"]} – {game["home_score"]}</span>'
        f'<span class="clock">{period_lbl}  {game["clock"]}</span>'
        f'<span>{game["home_abbr"]}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Cards on court — fragment auto-refreshes only while live (FIX 1) ──
    run_interval = "30s" if game.get("is_live") else None

    debug_mode = st.session_state.get("debug_mode", False)

    if _HAS_FRAGMENT:
        @st.fragment(run_every=run_interval)
        def _live_card_block():
            snaps = _live_snapshots(game["game_id"], _season_hash(season_df))
            pos_order = {p: i for i, p in enumerate(POSITION_SLOTS)}
            home_snaps = sorted(
                [s for s in snaps if s.team_id == game["home_team_id"]],
                key=lambda s: pos_order.get(s.position, 9),
            )
            away_snaps = sorted(
                [s for s in snaps if s.team_id == game["away_team_id"]],
                key=lambda s: pos_order.get(s.position, 9),
            )
            _render_court_with_cards(
                home_top5=home_snaps[:5],
                away_top5=away_snaps[:5],
                home_abbr=game["home_abbr"],
                away_abbr=game["away_abbr"],
                debug_mode=debug_mode,
            )

        _live_card_block()
    else:
        # Fallback for Streamlit < 1.33 (no fragment support)
        snaps = _live_snapshots(game["game_id"], _season_hash(season_df))
        pos_order = {p: i for i, p in enumerate(POSITION_SLOTS)}
        home_snaps = sorted(
            [s for s in snaps if s.team_id == game["home_team_id"]],
            key=lambda s: pos_order.get(s.position, 9),
        )
        away_snaps = sorted(
            [s for s in snaps if s.team_id == game["away_team_id"]],
            key=lambda s: pos_order.get(s.position, 9),
        )
        _render_court_with_cards(
            home_top5=home_snaps[:5],
            away_top5=away_snaps[:5],
            home_abbr=game["home_abbr"],
            away_abbr=game["away_abbr"],
            debug_mode=debug_mode,
        )


# ══════════════════════════════════════════════════════════════════════════════
# SEASON ANALYTICS (moved from old app.py into a function)
# ══════════════════════════════════════════════════════════════════════════════

def _render_season_tabs(nba_df: pd.DataFrame) -> None:
    if nba_df.empty:
        st.warning("Season data unavailable — check nba_api connection.")
        return

    pos_opts   = ["All", "Guards", "Wings", "Bigs"]
    pos_map    = {"All": None, "Guards": "Guard", "Wings": "Wing", "Bigs": "Big"}
    sel_pos    = st.radio("Position Filter", pos_opts, horizontal=True, key="pos_filter_season")
    pos_filter = pos_map[sel_pos]

    # Aggregate banner
    if "COMBINED_SCORE" in nba_df.columns:
        filt_df = nba_df if pos_filter is None else nba_df[nba_df.get("POSITION", pd.Series()) == pos_filter]
        if not filt_df.empty and "DRAGON_INDEX" in filt_df.columns:
            top_dragon   = filt_df.nlargest(1, "DRAGON_INDEX").iloc[0]
            top_fortress = filt_df.nlargest(1, "FORTRESS_RATING").iloc[0]
            top_combined = filt_df.nlargest(1, "COMBINED_SCORE").iloc[0]
            b1, b2, b3, b4 = st.columns(4)
            b1.metric("Players loaded", len(filt_df))
            b2.metric("🐉 Dragon #1",   top_dragon.get("PLAYER_NAME", "").split()[-1],
                      f"{top_dragon['DRAGON_INDEX']:.1f}")
            b3.metric("🏰 Fortress #1", top_fortress.get("PLAYER_NAME", "").split()[-1],
                      f"{top_fortress['FORTRESS_RATING']:.1f}")
            b4.metric("⭐ Best Combined", top_combined.get("PLAYER_NAME", "").split()[-1],
                      f"{top_combined['COMBINED_SCORE']:.1f}")

    st.markdown("---")

    if "compare_ids" not in st.session_state:
        st.session_state["compare_ids"] = []

    (tab_bubble, tab_dragon, tab_fortress,
     tab_compare, tab_teams) = st.tabs([
        "🫧 Bubble Scatter", "🐉 Dragon LB", "🏰 Fortress LB",
        "⚔️ Compare", "🏟️ Team View",
    ])

    # ── Bubble Scatter ────────────────────────────────────────────────────
    with tab_bubble:
        st.markdown("#### Dragon Index vs Fortress Rating")
        st.caption("Bubble size ∝ minutes · click any bubble to queue for comparison")
        highlight_ids = st.session_state.get("compare_ids", [])
        bubble_fig    = plot_bubble_scatter(nba_df, position_filter=pos_filter,
                                            highlight_ids=highlight_ids)
        event = st.plotly_chart(bubble_fig, use_container_width=True,
                                on_select="rerun", key="bubble_chart")
        try:
            if event and event.get("selection", {}).get("points"):
                for pt in event["selection"]["points"]:
                    cd  = pt.get("customdata") or []
                    pid = int(cd[6]) if len(cd) > 6 else None
                    if pid and pid not in st.session_state["compare_ids"]:
                        if len(st.session_state["compare_ids"]) >= 3:
                            st.session_state["compare_ids"].pop(0)
                        st.session_state["compare_ids"].append(pid)
                st.rerun()
        except Exception:
            pass

        if st.session_state["compare_ids"]:
            cids  = st.session_state["compare_ids"]
            names = (nba_df[nba_df["PLAYER_ID"].isin(cids)]["PLAYER_NAME"].tolist()
                     if "PLAYER_NAME" in nba_df.columns else [str(i) for i in cids])
            st.caption(f"**Compare queue:** {', '.join(names)}  →  go to ⚔️ Compare tab")
            if st.button("Clear selection", key="clear_sel"):
                st.session_state["compare_ids"] = []
                st.rerun()

        with st.expander("Top 10 — Combined Score"):
            if "COMBINED_SCORE" in nba_df.columns:
                show_cols = [c for c in ["PLAYER_NAME", "TEAM_ABBREVIATION",
                    "DRAGON_INDEX", "FORTRESS_RATING", "COMBINED_SCORE", "MIN"]
                    if c in nba_df.columns]
                st.dataframe(nba_df.nlargest(10, "COMBINED_SCORE")[show_cols].round(1),
                             use_container_width=True, hide_index=True)

    # ── Dragon Leaderboard ────────────────────────────────────────────────
    with tab_dragon:
        st.markdown("#### Dragon Index — Top 20 Disruptors")
        if "DRAGON_INDEX" in nba_df.columns:
            st.plotly_chart(plot_leaderboard(nba_df, metric="DRAGON_INDEX", n=20),
                            use_container_width=True)
            with st.expander("Full Dragon Index table — Top 50"):
                dcols = [c for c in ["PLAYER_NAME", "TEAM_ABBREVIATION", "POSITION",
                    "DRAGON_INDEX", "STL", "DEFLECTIONS", "CHARGES_DRAWN", "MIN"]
                    if c in nba_df.columns]
                st.dataframe(nba_df.nlargest(50, "DRAGON_INDEX")[dcols].round(2),
                             use_container_width=True, hide_index=True)
        with st.expander("How Dragon Index is computed"):
            st.markdown("""
| Component | Weight | Why |
|---|---|---|
| Steals | 25% | Direct possession change |
| Deflections | 25% | Forces bad passes |
| Charges drawn | 20% | Elite anticipation |
| Perimeter contests | 20% | Mid-range + 3pt contests |
| Loose balls | 10% | Effort plays |
            """)

    # ── Fortress Leaderboard ──────────────────────────────────────────────
    with tab_fortress:
        st.markdown("#### Fortress Rating — Top 20 Interior Anchors")
        if "FORTRESS_RATING" in nba_df.columns:
            st.plotly_chart(plot_leaderboard(nba_df, metric="FORTRESS_RATING", n=20),
                            use_container_width=True)
            with st.expander("Full Fortress table — Top 50"):
                fcols = [c for c in ["PLAYER_NAME", "TEAM_ABBREVIATION", "POSITION",
                    "FORTRESS_RATING", "BLK", "DREB", "TRK_DEF_RIM_FG_PCT",
                    "DEF_BOXOUTS", "MIN"] if c in nba_df.columns]
                st.dataframe(nba_df.nlargest(50, "FORTRESS_RATING")[fcols].round(2),
                             use_container_width=True, hide_index=True)
        with st.expander("How Fortress Rating is computed"):
            st.markdown("""
| Component | Weight | Why |
|---|---|---|
| Rim FG% allowed (inv.) | 28% | Paint deterrence |
| Box-out rate | 22% | Contested rebounds |
| Blocks per game | 22% | Shot rejection |
| Rim contest rate | 18% | Paint volume |
| Putback contribution | 10% | Offensive rebound leverage |
            """)

    # ── Compare ───────────────────────────────────────────────────────────
    with tab_compare:
        st.markdown("#### Player Comparison")
        player_names = (sorted(nba_df["PLAYER_NAME"].dropna().tolist())
                        if "PLAYER_NAME" in nba_df.columns else [])
        presel = []
        if st.session_state["compare_ids"] and "PLAYER_NAME" in nba_df.columns:
            presel = nba_df[nba_df["PLAYER_ID"].isin(st.session_state["compare_ids"])][
                "PLAYER_NAME"].tolist()
        comp_sel = st.multiselect("Select up to 3 players",
                                  player_names, default=presel[:3],
                                  max_selections=3, key="comp_sel")
        if len(comp_sel) >= 2:
            comp_df = nba_df[nba_df["PLAYER_NAME"].isin(comp_sel)]
            c_rad, c_roll = st.columns(2)
            with c_rad:
                st.plotly_chart(plot_comparison_radar(comp_df), use_container_width=True)
            with c_roll:
                roll_metric = st.selectbox("Rolling metric",
                                           ["DRAGON_INDEX", "FORTRESS_RATING"],
                                           key="roll_metric")
                rolling_data = {}
                for pname in comp_sel:
                    pid_row = nba_df[nba_df["PLAYER_NAME"] == pname]
                    if not pid_row.empty:
                        pid = int(pid_row.iloc[0]["PLAYER_ID"])
                        with st.spinner(f"Loading {pname}…"):
                            rolling_data[pname] = get_player_rolling_trend(
                                pid, metric=roll_metric)
                if rolling_data:
                    st.plotly_chart(plot_comparison_rolling(rolling_data, metric=roll_metric),
                                    use_container_width=True)
            st.markdown("---")
            stat_cols = [c for c in ["PLAYER_NAME", "TEAM_ABBREVIATION", "POSITION",
                "DRAGON_INDEX", "FORTRESS_RATING", "COMBINED_SCORE",
                "STL", "BLK", "DREB", "MIN"] if c in comp_df.columns]
            st.dataframe(comp_df[stat_cols].round(2), use_container_width=True, hide_index=True)

            # Steal-chain Sankey — one chart per selected player
            st.markdown("---")
            st.markdown("#### Steal-chain analysis")
            st.caption(
                "Sankey shows how steal-to-transition sequences originate and terminate "
                "for each selected player (sample from season play sequences)."
            )
            for pname in comp_sel:
                pid_row = nba_df[nba_df["PLAYER_NAME"] == pname]
                if pid_row.empty:
                    continue
                pid = int(pid_row.iloc[0]["PLAYER_ID"])
                with st.spinner(f"Loading steal chains for {pname}…"):
                    seq = get_play_sequence_stats(pid, n_games=10)
                try:
                    sankey_fig = plot_steal_chain_sankey(seq, pname)
                    st.plotly_chart(sankey_fig, use_container_width=True)
                except Exception as _e:
                    st.caption(f"{pname} — steal-chain data unavailable: {_e}")

        else:
            st.info("Select 2–3 players or click bubbles on the Scatter tab.")

    # ── Team View ─────────────────────────────────────────────────────────
    with tab_teams:
        st.markdown("#### Team Aggregate Defensive Metrics")
        try:
            team_df = get_team_aggregates(nba_df)
            if not team_df.empty:
                st.plotly_chart(plot_team_bubbles(team_df), use_container_width=True)
                with st.expander("Team data table"):
                    tcols = [c for c in ["TEAM_ABBREVIATION", "TEAM_NAME",
                        "DRAGON_INDEX", "FORTRESS_RATING", "COMBINED_SCORE", "PLAYER_COUNT"]
                        if c in team_df.columns]
                    st.dataframe(
                        team_df.sort_values("COMBINED_SCORE", ascending=False)[tcols].round(1),
                        use_container_width=True, hide_index=True)
            else:
                st.info("No team data — refresh.")
        except Exception as e:
            st.error(f"Team aggregates error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# GAME REPLAY
# ══════════════════════════════════════════════════════════════════════════════

def render_replay(season_df: pd.DataFrame) -> None:
    """
    Replay viewer: pick a completed game from the last 7 days,
    scrub through it possession-by-possession, and watch GS+ cards update.
    """
    st.markdown("## 🎬 Game Replay")
    st.caption(
        "Select any completed game from the past week. "
        "Use the scrubber to jump to any moment and see each player's GS+ at that point."
    )

    # ── Game picker ───────────────────────────────────────────────────────
    with st.spinner("Fetching recent games…"):
        games = _recent_games(days_back=7)

    if not games:
        st.info("No completed games found in the last 7 days. Try refreshing.")
        return

    # Build label map
    game_labels = {
        g["game_id"]: f"{g['game_date']}  ·  {g['away_abbr']} @ {g['home_abbr']}  "
                      f"{g['away_score']}–{g['home_score']}"
        for g in games
    }
    sel_id = st.selectbox(
        "Pick a game",
        list(game_labels.keys()),
        format_func=lambda gid: game_labels[gid],
        key="replay_game_sel",
    )
    sel_game = next(g for g in games if g["game_id"] == sel_id)

    st.markdown(
        f"**{sel_game['away_abbr']}** {sel_game['away_score']} — "
        f"{sel_game['home_score']} **{sel_game['home_abbr']}**  ·  {sel_game['game_date']}"
    )

    # ── Load timeline ─────────────────────────────────────────────────────
    with st.spinner("Loading play-by-play (cached 1 h)…"):
        timeline = _replay_timeline(sel_id)

    if not timeline:
        st.warning("Play-by-play unavailable for this game. Try another.")
        return

    checkpoints = quarter_checkpoints(timeline)   # [(label, frame_idx), ...]
    cp_labels   = [c[0] for c in checkpoints]
    cp_indices  = [c[1] for c in checkpoints]

    # ── Quarter-jump buttons ──────────────────────────────────────────────
    st.markdown("**Jump to:**")
    btn_cols = st.columns(len(checkpoints))
    for col, (label, idx) in zip(btn_cols, checkpoints):
        if col.button(label, key=f"cp_{label}_{sel_id}"):
            st.session_state["replay_frame_idx"] = idx

    if "replay_frame_idx" not in st.session_state:
        st.session_state["replay_frame_idx"] = 0

    # ── Fine-grained scrubber ─────────────────────────────────────────────
    frame_idx = st.slider(
        "Scrub through game",
        min_value=0,
        max_value=len(timeline) - 1,
        value=st.session_state["replay_frame_idx"],
        step=1,
        key="replay_slider",
        help="Move left → right to advance through the game event by event",
    )
    st.session_state["replay_frame_idx"] = frame_idx

    frame = timeline[frame_idx]

    # ── Game clock display ────────────────────────────────────────────────
    period_label = f"Q{frame.period}" if frame.period <= 4 else f"OT{frame.period - 4}"
    cl1, cl2, cl3 = st.columns([1, 2, 1])
    cl1.metric("Period", period_label)
    cl2.metric(
        "Score",
        f"{sel_game['away_abbr']} {frame.away_score}  –  {frame.home_score} {sel_game['home_abbr']}",
    )
    cl3.metric("Clock", frame.clock)

    # Last play description
    if frame.description:
        st.info(f"▶ {frame.description}")

    st.divider()

    # ── GS+ cards at this moment ──────────────────────────────────────────
    home_snaps, away_snaps = get_snapshots_at_frame(frame, season_df, top_n=5)

    away_label = sel_game["away_abbr"]
    home_label = sel_game["home_abbr"]

    for team_label, snaps in [(away_label, away_snaps), (home_label, home_snaps)]:
        st.markdown(f"**{team_label}**")
        if snaps:
            card_html = '<div class="card-grid">'
            for snap in snaps:
                card_html += _card_html(snap)
            card_html += "</div>"
            st.markdown(card_html, unsafe_allow_html=True)
        else:
            st.caption("No stat activity yet at this point in the game.")

    # ── GS+ sparkline — top contributor per team ──────────────────────────
    import plotly.graph_objects as go

    st.divider()
    st.markdown("**GS+ arc — top contributors through this moment**")

    # Build per-player history across all frames up to current
    player_history: dict[int, list[float]] = {}
    player_names_map: dict[int, str] = {}
    sample_step = max(1, len(timeline) // 150)   # at most 150 points

    for i in range(0, frame_idx + 1, sample_step):
        f = timeline[i]
        h_snaps, a_snaps = get_snapshots_at_frame(f, season_df, top_n=3)
        for s in h_snaps + a_snaps:
            player_history.setdefault(s.player_id, []).append(s.pct_vs_norm)
            player_names_map[s.player_id] = s.player_name.split()[-1]

    if player_history:
        fig = go.Figure()
        # Draw season-norm reference line at 0%
        fig.add_hline(y=0, line_dash="dot", line_color="#555", annotation_text="season norm")
        colors = ["#EB6E1F", "#4A90D9", "#2ecc71", "#e74c3c", "#9b59b6",
                  "#f39c12", "#1abc9c", "#e67e22", "#3498db", "#95a5a6"]
        for i, (pid, vals) in enumerate(player_history.items()):
            fig.add_trace(go.Scatter(
                y=vals,
                mode="lines",
                name=player_names_map.get(pid, str(pid)),
                line=dict(color=colors[i % len(colors)], width=2),
                hovertemplate="%{y:+.0f}%<extra>" + player_names_map.get(pid, "") + "</extra>",
            ))
        fig.update_layout(
            paper_bgcolor="#0a0a0f",
            plot_bgcolor="#0d0d1a",
            font_color="#aaa",
            margin=dict(l=0, r=0, t=10, b=0),
            height=260,
            yaxis_title="% vs norm",
            xaxis_title="event (sampled)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            yaxis=dict(zeroline=False, gridcolor="#1a1a2e"),
            xaxis=dict(gridcolor="#1a1a2e"),
        )
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN PAGE
# ══════════════════════════════════════════════════════════════════════════════

def render_admin() -> None:
    st.markdown("## 🔒 Admin Dashboard")

    if not st.session_state.get("admin_auth"):
        pw = st.text_input("Password", type="password", key="admin_pw")
        if st.button("Unlock", key="admin_unlock"):
            if hashlib.sha256(pw.encode()).hexdigest() == _ADMIN_PW_HASH:
                st.session_state["admin_auth"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
        return

    # Logged in
    if st.button("🔓 Lock", key="admin_lock"):
        st.session_state["admin_auth"] = False
        st.rerun()

    stats = analytics.get_stats(days=30)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    metrics = [
        ("Sessions (30d)",   stats["total_sessions"]),
        ("Unique visitors",  stats["unique_visitors"]),
        ("Page views (30d)", stats["total_page_views"]),
        ("Sessions today",   stats["sessions_today"]),
        ("Visitors today",   stats["visitors_today"]),
        ("Views today",      stats["page_views_today"]),
    ]
    for col, (label, val) in zip([c1, c2, c3, c4, c5, c6], metrics):
        col.markdown(
            f'<div class="admin-metric"><div class="val">{val}</div>'
            f'<div class="lbl">{label}</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    col_paths, col_daily = st.columns(2)

    with col_paths:
        st.markdown("**Top paths (30d)**")
        if stats["top_paths"]:
            st.dataframe(
                pd.DataFrame(stats["top_paths"]),
                use_container_width=True, hide_index=True,
            )

    with col_daily:
        st.markdown("**Daily views (30d)**")
        if stats["daily_views"]:
            import plotly.graph_objects as go
            daily = pd.DataFrame(stats["daily_views"])
            fig = go.Figure(go.Bar(
                x=daily["date"], y=daily["count"],
                marker_color="#EB6E1F",
            ))
            fig.update_layout(
                paper_bgcolor="#0a0a0f", plot_bgcolor="#0a0a0f",
                font_color="#aaa", margin=dict(l=0, r=0, t=10, b=0),
                height=200,
            )
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Recent sessions**")
    sessions = analytics.get_recent_sessions(50)
    if sessions:
        st.dataframe(pd.DataFrame(sessions), use_container_width=True, hide_index=True)
    else:
        st.caption("No session data yet.")


# ══════════════════════════════════════════════════════════════════════════════
# TOP-LEVEL NAV + ROUTING
# ══════════════════════════════════════════════════════════════════════════════

# ── Sidebar nav ───────────────────────────────────────────────────────────────
# "nav" is a FREE session-state key (not bound to any widget) so other parts
# of the app can write st.session_state["nav"] = "..." without triggering
# StreamlitAPIException.  The radio uses index= to stay in sync.
with st.sidebar:
    st.markdown("## 🏀 GS+ Live")
    st.markdown(f"*Season {SEASON}*")
    st.markdown("---")
    _nav_idx = (
        _NAV_OPTIONS.index(st.session_state["nav"])
        if st.session_state["nav"] in _NAV_OPTIONS
        else 0
    )
    _nav_sel = st.radio(
        "Navigate",
        _NAV_OPTIONS,
        index=_nav_idx,
        key="_nav_radio",          # internal widget key — never written to externally
        label_visibility="collapsed",
    )
    # Keep the free "nav" key in sync with what the user clicked
    st.session_state["nav"] = _nav_sel
    nav = _nav_sel

    st.markdown("---")
    if st.button("🔄 Refresh data"):
        st.cache_data.clear()
        st.rerun()
    # FIX 5 — debug toggle: shows norm X.X | raw X.X line on each card
    st.session_state["debug_mode"] = st.checkbox(
        "🔧 Debug card values",
        value=st.session_state.get("debug_mode", False),
        key="debug_mode_cb",
        help="Show season norm and raw GS+ under each player card",
    )
    st.caption("GS+ data refreshes every 30 s · Season analytics cached 24 h")

# Load season data (non-blocking)
with st.spinner("Loading season data (cached 24 h)…"):
    try:
        sdf = _season_df()
    except Exception:
        sdf = pd.DataFrame()

# ── Player bio override (highest priority) ────────────────────────────────────
if st.session_state.get("active_player_id") is not None:
    render_bio_page(int(st.session_state["active_player_id"]), sdf)

elif nav == "🏠 Live Court":
    render_homepage(sdf)

elif nav == "🎬 Replay":
    render_replay(sdf)

elif nav == "📊 Season":
    st.markdown("# 📊 Season Analytics")
    st.markdown(
        '<span class="metric-pill dragon-pill">🐉 Dragon Index</span>'
        '<span class="metric-pill fortress-pill">🏰 Fortress Rating</span>',
        unsafe_allow_html=True,
    )
    st.markdown("")
    _render_season_tabs(sdf)

elif nav == "🔧 Admin":
    render_admin()

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    f"GS+ Live Momentum Engine · Season {SEASON} · "
    "nba_api · Cached 30 s live / 24 h season"
)
