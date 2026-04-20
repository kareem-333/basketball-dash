"""
nba — GS+ Live Momentum Engine + NBA Defensive Analytics.

Modules
-------
pipeline    : Season data fetching — Dragon Index, Fortress Rating.
charts      : Plotly visualisations (season analytics).
live_engine : GS+ real-time computation (brief v5).
analytics   : Session + unique-visitor tracking (admin page).
court_svg   : Basketball court SVG generator (desktop + mobile).
"""

from nba.pipeline import (
    get_all_player_metrics,
    get_team_aggregates,
    get_player_rolling_trend,
    get_play_sequence_stats,
    team_color,
    nba_logo_url,
    nba_headshot_url,
    DRAGON_WEIGHTS,
    FORTRESS_WEIGHTS,
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
    BoxStats,
    GSPlusSnapshot,
    GameState,
    TIERS,
    TIER_COLORS,
    POSITION_SLOTS,
    compute_gs_plus,
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

__all__ = [
    # pipeline
    "get_all_player_metrics", "get_team_aggregates",
    "get_player_rolling_trend", "get_play_sequence_stats",
    "team_color", "nba_logo_url", "nba_headshot_url",
    "DRAGON_WEIGHTS", "FORTRESS_WEIGHTS", "SEASON",
    # charts
    "plot_bubble_scatter", "plot_leaderboard",
    "plot_comparison_radar", "plot_comparison_rolling",
    "plot_team_bubbles", "plot_steal_chain_sankey",
    "plot_sequence_comparison",
    # live_engine
    "BoxStats", "GSPlusSnapshot", "GameState",
    "TIERS", "TIER_COLORS", "POSITION_SLOTS",
    "compute_gs_plus", "compute_snapshot",
    "compute_gs_plus_norm_from_pipeline",
    "fetch_live_box_stats", "get_live_games",
    "get_player_season_norm", "assign_lineup_slots",
    # court_svg
    "court_svg_desktop", "court_svg_mobile",
    "DESKTOP_SLOTS", "MOBILE_SLOTS",
]
