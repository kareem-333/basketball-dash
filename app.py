"""
NBA Defensive Analytics Dashboard
Standalone Streamlit app — Dragon Index & Fortress Rating

Run with:
    streamlit run app.py
"""

import streamlit as st
import pandas as pd

from nba.pipeline import (
    get_all_player_metrics,
    get_team_aggregates,
    get_player_rolling_trend,
    get_play_sequence_stats,
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

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NBA Defensive Analytics",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .metric-pill {
    display: inline-block;
    background: #1a2a4a;
    border-radius: 8px;
    padding: 4px 14px;
    font-size: 0.82rem;
    font-weight: 700;
    color: #e0e0e0;
    margin: 2px 4px;
  }
  .dragon-pill  { background: #8B1A1A; }
  .fortress-pill { background: #1A3A5C; }
  .sec-hdr {
    font-size: 0.9rem; font-weight: 700; color: #EB6E1F;
    border-bottom: 1px solid #EB6E1F44;
    margin-bottom: 0.4rem; padding-bottom: 2px;
  }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏀 NBA Defense")
    st.markdown(f"**Season:** {SEASON}")
    st.markdown("---")

    st.markdown("""
    **Dragon Index** 🐉
    Active perimeter disruption — steals, deflections, charges drawn,
    perimeter contests, loose balls.

    **Fortress Rating** 🏰
    Interior anchoring — rim FG% allowed, box-out rate, blocks,
    rim contest rate, putbacks.
    """)

    st.markdown("---")
    if st.button("🔄 Refresh Data"):
        get_all_player_metrics.clear()
        st.rerun()
    st.caption("Data cached 24 h · Source: nba_api")

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("# 🏀 NBA Defensive Analytics")
st.markdown(
    '<span class="metric-pill dragon-pill">🐉 Dragon Index — Active Disruption</span>'
    '<span class="metric-pill fortress-pill">🏰 Fortress Rating — Interior Anchor</span>',
    unsafe_allow_html=True,
)
st.markdown("")

# ── Data loading ──────────────────────────────────────────────────────────────
with st.spinner("Loading NBA defensive metrics (cached 24 h)…"):
    try:
        nba_df      = get_all_player_metrics()
        nba_load_ok = nba_df is not None and not nba_df.empty
    except Exception as e:
        st.error(f"Failed to load NBA data: {e}")
        nba_load_ok = False

if not nba_load_ok:
    st.info(
        "NBA data unavailable. nba_api sometimes rate-limits — "
        "wait a moment and hit **🔄 Refresh Data** in the sidebar."
    )
    st.stop()

# ── Position filter (shared across tabs) ──────────────────────────────────────
pos_opts   = ["All", "Guards", "Wings", "Bigs"]
pos_map    = {"All": None, "Guards": "Guard", "Wings": "Wing", "Bigs": "Big"}
sel_pos    = st.radio("Position Filter", pos_opts, horizontal=True, key="pos_filter")
pos_filter = pos_map[sel_pos]

# ── Aggregate metrics banner ──────────────────────────────────────────────────
if "COMBINED_SCORE" in nba_df.columns:
    filt_df  = nba_df if pos_filter is None else nba_df[nba_df.get("POSITION", "") == pos_filter]
    if not filt_df.empty and "DRAGON_INDEX" in filt_df.columns:
        top_dragon  = filt_df.nlargest(1, "DRAGON_INDEX").iloc[0]
        top_fortress= filt_df.nlargest(1, "FORTRESS_RATING").iloc[0]
        top_combined= filt_df.nlargest(1, "COMBINED_SCORE").iloc[0]
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Players loaded", len(filt_df))
        b2.metric("🐉 Dragon #1",
                  f"{top_dragon.get('PLAYER_NAME','').split()[-1]}",
                  f"{top_dragon['DRAGON_INDEX']:.1f}")
        b3.metric("🏰 Fortress #1",
                  f"{top_fortress.get('PLAYER_NAME','').split()[-1]}",
                  f"{top_fortress['FORTRESS_RATING']:.1f}")
        b4.metric("⭐ Best Combined",
                  f"{top_combined.get('PLAYER_NAME','').split()[-1]}",
                  f"{top_combined['COMBINED_SCORE']:.1f}")

st.markdown("---")

# ── Session state for click-to-compare ───────────────────────────────────────
if "compare_ids" not in st.session_state:
    st.session_state["compare_ids"] = []

# ── Main tabs ─────────────────────────────────────────────────────────────────
(tab_bubble, tab_dragon, tab_fortress,
 tab_compare, tab_teams) = st.tabs([
    "🫧 Bubble Scatter", "🐉 Dragon LB", "🏰 Fortress LB",
    "⚔️ Compare", "🏟️ Team View",
])


# ═══════════════════════════════════════════════════════════════════════════════
# 🫧 BUBBLE SCATTER
# ═══════════════════════════════════════════════════════════════════════════════
with tab_bubble:
    st.markdown("#### Dragon Index vs Fortress Rating")
    st.caption(
        "Bubble size ∝ minutes played · "
        "**Click any bubble** to add that player to the ⚔️ Compare queue"
    )

    highlight_ids = st.session_state.get("compare_ids", [])
    bubble_fig    = plot_bubble_scatter(
        nba_df, position_filter=pos_filter, highlight_ids=highlight_ids
    )
    event = st.plotly_chart(
        bubble_fig, use_container_width=True,
        on_select="rerun", key="bubble_chart",
    )

    # Click-to-compare handler
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

    # Compare queue status
    if st.session_state["compare_ids"]:
        cids  = st.session_state["compare_ids"]
        names = (
            nba_df[nba_df["PLAYER_ID"].isin(cids)]["PLAYER_NAME"].tolist()
            if "PLAYER_NAME" in nba_df.columns else [str(i) for i in cids]
        )
        st.caption(f"**Compare queue:** {', '.join(names)}  →  go to ⚔️ Compare tab")
        if st.button("Clear selection"):
            st.session_state["compare_ids"] = []
            st.rerun()

    # Top-10 table
    with st.expander("Top 10 — Combined Score (Dragon + Fortress)"):
        if "COMBINED_SCORE" in nba_df.columns:
            show_cols = [c for c in [
                "PLAYER_NAME", "TEAM_ABBREVIATION",
                "DRAGON_INDEX", "FORTRESS_RATING", "COMBINED_SCORE", "MIN",
            ] if c in nba_df.columns]
            st.dataframe(
                nba_df.nlargest(10, "COMBINED_SCORE")[show_cols].round(1),
                use_container_width=True, hide_index=True,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 🐉 DRAGON LEADERBOARD
# ═══════════════════════════════════════════════════════════════════════════════
with tab_dragon:
    st.markdown("#### Dragon Index — Top 20 Disruptors")
    st.caption(
        "Active disruption: steals, deflections, charges drawn, "
        "perimeter contests (excl. rim), loose balls recovered"
    )

    if "DRAGON_INDEX" in nba_df.columns:
        dragon_fig = plot_leaderboard(nba_df, metric="DRAGON_INDEX", n=20)
        st.plotly_chart(dragon_fig, use_container_width=True)

        with st.expander("Full Dragon Index table — Top 50"):
            dcols = [c for c in [
                "PLAYER_NAME", "TEAM_ABBREVIATION", "POSITION",
                "DRAGON_INDEX", "STL", "DEFLECTIONS",
                "CHARGES_DRAWN", "MIN",
            ] if c in nba_df.columns]
            st.dataframe(
                nba_df.nlargest(50, "DRAGON_INDEX")[dcols].round(2),
                use_container_width=True, hide_index=True,
            )
    else:
        st.warning("Dragon Index not found — refresh data.")

    # Component weight explainer
    with st.expander("How Dragon Index is computed"):
        st.markdown("""
        | Component | Weight | Why |
        |---|---|---|
        | Steals | 25% | Direct possession change |
        | Deflections | 25% | Forces bad passes / turnovers |
        | Charges drawn | 20% | Elite anticipation & positioning |
        | Perimeter contests | 20% | Closest defender on mid-range + 3pt shots (rim excluded) |
        | Loose balls recovered | 10% | Effort plays in transition |

        Raw scores are min-max normalised per component, then weighted.
        A usage-rate and opponent-turnover-quality multiplier (0.6–1.0) rewards players
        who produce disruption against high-usage opponents.
        """)


# ═══════════════════════════════════════════════════════════════════════════════
# 🏰 FORTRESS LEADERBOARD
# ═══════════════════════════════════════════════════════════════════════════════
with tab_fortress:
    st.markdown("#### Fortress Rating — Top 20 Interior Anchors")
    st.caption(
        "Paint protection: rim FG% allowed, box-out rate, blocks, "
        "rim contest rate, offensive rebound putbacks"
    )

    if "FORTRESS_RATING" in nba_df.columns:
        fortress_fig = plot_leaderboard(nba_df, metric="FORTRESS_RATING", n=20)
        st.plotly_chart(fortress_fig, use_container_width=True)

        with st.expander("Full Fortress Rating table — Top 50"):
            fcols = [c for c in [
                "PLAYER_NAME", "TEAM_ABBREVIATION", "POSITION",
                "FORTRESS_RATING", "BLK", "DREB",
                "TRK_DEF_RIM_FG_PCT", "DEF_BOXOUTS", "MIN",
            ] if c in nba_df.columns]
            st.dataframe(
                nba_df.nlargest(50, "FORTRESS_RATING")[fcols].round(2),
                use_container_width=True, hide_index=True,
            )
    else:
        st.warning("Fortress Rating not found — refresh data.")

    with st.expander("How Fortress Rating is computed"):
        st.markdown("""
        | Component | Weight | Why |
        |---|---|---|
        | Rim FG% allowed (inverted) | 28% | Core measure of paint deterrence |
        | Box-out rate | 22% | Contested rebound positioning |
        | Blocks per game | 22% | Direct shot rejection |
        | Rim contest rate (per 36 min) | 18% | Volume of rim presence |
        | Putback contribution | 10% | Offensive rebound leverage |

        Normalised scores are multiplied by a paint-weight factor that rewards
        players whose blocks + defensive rebounds rank highly relative to the league.
        """)


# ═══════════════════════════════════════════════════════════════════════════════
# ⚔️ PLAYER COMPARISON
# ═══════════════════════════════════════════════════════════════════════════════
with tab_compare:
    st.markdown("#### Player Comparison")
    st.caption("Select 2–3 players to compare across all defensive components")

    player_names = (
        sorted(nba_df["PLAYER_NAME"].dropna().tolist())
        if "PLAYER_NAME" in nba_df.columns else []
    )

    # Pre-populate from bubble-click session state
    presel = []
    if st.session_state["compare_ids"] and "PLAYER_NAME" in nba_df.columns:
        presel = nba_df[
            nba_df["PLAYER_ID"].isin(st.session_state["compare_ids"])
        ]["PLAYER_NAME"].tolist()

    comp_sel = st.multiselect(
        "Select up to 3 players (or click bubbles on the Scatter tab)",
        player_names,
        default=presel[:3],
        max_selections=3,
        key="comp_sel",
    )

    if len(comp_sel) >= 2:
        comp_df = nba_df[nba_df["PLAYER_NAME"].isin(comp_sel)]

        # Radar + rolling trend side-by-side
        c_rad, c_roll = st.columns(2)
        with c_rad:
            radar_fig = plot_comparison_radar(comp_df)
            st.plotly_chart(radar_fig, use_container_width=True)

        with c_roll:
            roll_metric = st.selectbox(
                "Rolling trend metric",
                ["DRAGON_INDEX", "FORTRESS_RATING"],
                key="roll_metric",
            )
            rolling_data = {}
            for pname in comp_sel:
                pid_row = nba_df[nba_df["PLAYER_NAME"] == pname]
                if not pid_row.empty:
                    pid = int(pid_row.iloc[0]["PLAYER_ID"])
                    with st.spinner(f"Loading rolling data for {pname}…"):
                        rolling_data[pname] = get_player_rolling_trend(
                            pid, metric=roll_metric
                        )
            if rolling_data:
                roll_fig = plot_comparison_rolling(rolling_data, metric=roll_metric)
                st.plotly_chart(roll_fig, use_container_width=True)

        # Raw stat table
        st.markdown("---")
        stat_cols = [c for c in [
            "PLAYER_NAME", "TEAM_ABBREVIATION", "POSITION",
            "DRAGON_INDEX", "FORTRESS_RATING", "COMBINED_SCORE",
            "STL", "BLK", "DREB", "MIN", "USG_PCT", "DEF_RATING",
        ] if c in comp_df.columns]
        st.markdown('<div class="sec-hdr">Season Stats Comparison</div>',
                    unsafe_allow_html=True)
        st.dataframe(comp_df[stat_cols].round(2), use_container_width=True, hide_index=True)

        # ── Play Sequence Impact (steal → points chain) ───────────────────────
        st.markdown("---")
        st.markdown("#### Steal → Points Chain Analysis")
        st.caption(
            "Every steal in the last N games is traced through play-by-play data. "
            "We record whether the team scored, how quickly (fast break = within 2 plays), "
            "and how many points were generated."
        )

        n_games_seq = st.slider(
            "Games to analyse", min_value=5, max_value=20, value=10, step=5,
            key="seq_games",
        )

        seq_data:   dict[str, dict] = {}
        seq_colors: list[str]       = ["#EB6E1F", "#3498db", "#2ecc71", "#e74c3c"]

        for pname in comp_sel:
            pid_row = nba_df[nba_df["PLAYER_NAME"] == pname]
            if pid_row.empty:
                continue
            pid = int(pid_row.iloc[0]["PLAYER_ID"])
            with st.spinner(f"Tracing steal chains for {pname} ({n_games_seq} games)…"):
                seq_data[pname] = get_play_sequence_stats(pid, n_games=n_games_seq)

        if seq_data:
            # Per-player Sankey diagrams
            sank_cols = st.columns(len(seq_data))
            for col, (pname, sdata) in zip(sank_cols, seq_data.items()):
                with col:
                    sank_fig = plot_steal_chain_sankey(sdata, pname)
                    st.plotly_chart(sank_fig, use_container_width=True)

            # Summary table
            rows = []
            for pname, sdata in seq_data.items():
                rows.append({
                    "Player":         pname,
                    "Steals Traced":  sdata.get("total_steals", 0),
                    "Scored %":       f"{sdata.get('conversion_pct', 0):.0f}%",
                    "Fast Break %":   f"{sdata.get('fast_break_pct', 0):.0f}%",
                    "Pts / Steal":    f"{sdata.get('pts_per_steal', 0):.2f}",
                    "Total Pts Gen.": sdata.get("total_pts", 0),
                    "Games":          sdata.get("games_analyzed", 0),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            # Multi-player comparison bars
            if len(seq_data) > 1:
                comp_seq_fig = plot_sequence_comparison(seq_data, colors=seq_colors)
                st.plotly_chart(comp_seq_fig, use_container_width=True)

    else:
        st.info(
            "Select 2 or 3 players from the dropdown above, "
            "or click player bubbles on the 🫧 Bubble Scatter tab to queue them."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 🏟️ TEAM VIEW
# ═══════════════════════════════════════════════════════════════════════════════
with tab_teams:
    st.markdown("#### Team Aggregate Defensive Metrics")
    st.caption(
        "Average Dragon Index & Fortress Rating across all qualifying players "
        "(≥ 10 GP) per team"
    )

    try:
        team_df = get_team_aggregates(nba_df)
        if not team_df.empty:
            team_fig = plot_team_bubbles(team_df)
            st.plotly_chart(team_fig, use_container_width=True)

            with st.expander("Team data table"):
                tcols = [c for c in [
                    "TEAM_ABBREVIATION", "TEAM_NAME",
                    "DRAGON_INDEX", "FORTRESS_RATING",
                    "COMBINED_SCORE", "PLAYER_COUNT",
                ] if c in team_df.columns]
                st.dataframe(
                    team_df.sort_values("COMBINED_SCORE", ascending=False)[tcols].round(1),
                    use_container_width=True, hide_index=True,
                )
        else:
            st.info("No team aggregate data — refresh data first.")
    except Exception as e:
        st.error(f"Could not compute team aggregates: {e}")

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    f"Season: **{SEASON}** · Data: nba_api (official NBA stats) · "
    "Cached 24 h to disk · Min 10 GP to qualify"
)
