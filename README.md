# NBA Defensive Analytics — Dragon Index & Fortress Rating

A live Streamlit dashboard that measures NBA defensive impact the way fans actually watch the game — who disrupts, who anchors, and what happens after a steal.

**Live app:** [nba-tracker.streamlit.app](https://nba-tracker.streamlit.app)

---

## The Problem

Defensive impact is the hardest thing to measure in basketball. The box score captures steals and blocks, but it misses almost everything that actually decides a possession — deflections that force bad passes, charges drawn on anticipation, contested shots that never get tracked as a "stop," and the downstream point value of a turnover forced.

This project attempts to close that gap with two composite metrics and a play-sequence tracer.

---

## What It Does

**Dragon Index** — active perimeter disruption

A weighted composite of steals, deflections, charges drawn, perimeter contests, and loose balls recovered. Players like Dyson Daniels, Draymond Green, and Marcus Smart rank highly.

**Fortress Rating** — interior anchoring

A weighted composite of rim FG% allowed (inverted), box-out rate, blocks, rim contest rate, and offensive rebound putbacks. Players like Rudy Gobert, Jaren Jackson Jr., and Victor Wembanyama rank highly.

**Complete Defender Quadrant** — the 2×2

Plotting both indices on a bubble scatter surfaces the rare players strong in both dimensions. Wembanyama sits isolated in the top right. That's the point.

**Steal → Points Chain Analysis**

For any selected player, the app traces every steal in their last N games through play-by-play data and outputs a Sankey diagram showing:

- How often the steal converted to points
- Whether the score came in transition (within 2 plays) or half-court
- Total points generated and points per steal

This measures the *downstream value* of a defensive event, not just the event itself.

---

## How the Metrics Are Built

### Dragon Index

| Component | Weight | Rationale |
|---|---|---|
| Steals | 25% | Direct possession change |
| Deflections | 25% | Forces bad passes and turnovers |
| Charges drawn | 20% | Elite anticipation and positioning |
| Perimeter contests | 20% | Closest defender on mid-range and 3pt shots (rim excluded) |
| Loose balls recovered | 10% | Effort plays in transition |

Raw components are min-max normalized, then weighted. A usage-rate and opponent-turnover-quality multiplier (0.6–1.0) rewards players who produce disruption against high-usage opponents.

### Fortress Rating

| Component | Weight | Rationale |
|---|---|---|
| Rim FG% allowed (inverted) | 28% | Core measure of paint deterrence |
| Box-out rate | 22% | Contested rebound positioning |
| Blocks per game | 22% | Direct shot rejection |
| Rim contest rate (per 36) | 18% | Volume of rim presence |
| Putback contribution | 10% | Offensive rebound leverage |

Normalized scores are multiplied by a paint-weight factor that rewards players whose blocks plus defensive rebounds rank highly relative to the league.

### Defender Distance Tiers

Throughout all calculations, defender proximity is weighted on the NBA's 4-tier system:

- **0–2 ft** — Very Tight (highest defensive credit)
- **2–4 ft** — Tight (strong credit)
- **4–6 ft** — Open (minimal credit)
- **6 ft+** — Wide Open (no credit)

---

## App Structure

Five tabs, built to tell a story rather than dump data:

1. **Bubble Scatter** — Dragon Index (x) vs Fortress Rating (y), with team-colored bubbles and headshots. Click any bubble to add a player to the compare queue.
2. **Dragon Leaderboard** — Top 20 disruptors with component breakdown
3. **Fortress Leaderboard** — Top 20 interior anchors with component breakdown
4. **Compare** — Side-by-side radar chart, 15-game rolling trend, and steal-chain Sankey for up to 3 players
5. **Team View** — Aggregate team defensive identity on the same 2×2

---

## Stack

- **Python** — data pipeline and metric computation
- **Streamlit** — app framework and UI
- **Plotly** — interactive visualizations (bubble scatter, radar, Sankey, leaderboards)
- **Pandas + NumPy** — data manipulation
- **nba_api** — official NBA stats endpoints, cached 24h to disk

---

## Running Locally

```bash
git clone https://github.com/kareem-333/basketball-dash.git
cd basketball-dash
pip install -r requirements.txt
streamlit run app.py
```

Data is cached for 24 hours. Use the **🔄 Refresh Data** button in the sidebar to force a reload.

---

## Beyond Basketball

The architecture is sport-agnostic. Any environment with granular event data fits the same pattern:

| Basketball concept | Generalized application |
|---|---|
| Dragon Index | Composite disruption/anomaly score |
| Fortress Rating | Composite stability/anchor score |
| Steal → Points Sankey | Downstream event propagation |
| Defender distance tiers | Proximity-weighted event credit |
| Rolling 15-game trend | Rolling performance drift detection |

The obvious next domain is manufacturing IoT, where sensor event data has comparable granularity. Marketing attribution and operational process mining are similar fits.

---

## Known Limitations

- Component weights are intuition-based starting points, not yet calibrated against an outcome variable (e.g. opponent points per possession). Sensitivity analysis is a planned improvement.
- Rolling trend chart currently has a game-number alignment issue for players on different schedules.
- Live game engine (GS+, Heat Tiers, Momentum Meter) is spec'd but not yet built — in development.

---

## Author

Built by [Kareem](https://github.com/kareem-333) as a sandbox for live, API-connected analytical products.
