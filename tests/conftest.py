"""Shared pytest fixtures for Basketball-Dash tests."""

import pandas as pd
import pytest

from nba.live_engine import BoxStats, GameState


@pytest.fixture
def basic_box():
    """A representative mid-game box score."""
    return BoxStats(
        player_id=1,
        player_name="Test Player",
        team_id=100,
        position="SG",
        min=24.0,
        pts=18,
        fgm=7,
        fga=14,
        ftm=2,
        fta=3,
        oreb=1,
        dreb=3,
        ast=4,
        stl=2,
        blk=0,
        tov=1,
        pf=2,
        possessions_elapsed=48,
        on_court=True,
    )


@pytest.fixture
def empty_box():
    """A player who hasn't touched the ball yet."""
    return BoxStats(
        player_id=99,
        player_name="Bench Guy",
        team_id=100,
        position="C",
        min=0.0,
        pts=0, fgm=0, fga=0, ftm=0, fta=0,
        oreb=0, dreb=0, ast=0, stl=0, blk=0, tov=0, pf=0,
        possessions_elapsed=0,
        on_court=False,
    )


@pytest.fixture
def game_state():
    return GameState(game_id="test_game", home_team=100, away_team=200)


@pytest.fixture
def season_df():
    """Minimal season DataFrame with GS_PLUS_NORM for two players."""
    return pd.DataFrame({
        "PLAYER_ID": [1, 2],
        "GS_PLUS_NORM": [12.5, 8.0],
    })


@pytest.fixture
def minimal_events_df():
    """Synthetic play-by-play with a made FG (with assist) and a missed FG."""
    return pd.DataFrame([
        {
            "EVENTNUM": 1,
            "PERIOD": 1,
            "PCTIMESTRING": "11:30",
            "EVENTMSGTYPE": 1,        # FG made
            "EVENTMSGACTIONTYPE": 0,  # 2-pointer
            "PLAYER1_ID": 10,
            "PLAYER1_TEAM_ID": 100,
            "PLAYER1_NAME": "Scorer One",
            "PLAYER2_ID": 20,
            "PLAYER2_TEAM_ID": 100,
            "PLAYER2_NAME": "Passer Two",
            "PLAYER2_TEAM_ID": 100,
            "PLAYER3_ID": 0,
            "SCORE": "0 - 2",
            "HOMEDESCRIPTION": "Scorer One 2pt Shot",
            "VISITORDESCRIPTION": "",
            "NEUTRALDESCRIPTION": "",
        },
        {
            "EVENTNUM": 2,
            "PERIOD": 1,
            "PCTIMESTRING": "11:10",
            "EVENTMSGTYPE": 2,        # FG missed
            "EVENTMSGACTIONTYPE": 0,
            "PLAYER1_ID": 30,
            "PLAYER1_TEAM_ID": 200,
            "PLAYER1_NAME": "Shooter Three",
            "PLAYER2_ID": 0,
            "PLAYER2_TEAM_ID": 0,
            "PLAYER2_NAME": "",
            "PLAYER3_ID": 0,
            "SCORE": None,
            "HOMEDESCRIPTION": "",
            "VISITORDESCRIPTION": "Shooter Three MISS 2pt",
            "NEUTRALDESCRIPTION": "",
        },
    ])


@pytest.fixture
def minimal_roster_df():
    """Roster with three players across two teams."""
    return pd.DataFrame([
        {"PLAYER_ID": 10, "TEAM_ID": 100, "PLAYER_NAME": "Scorer One",    "START_POSITION": "SG"},
        {"PLAYER_ID": 20, "TEAM_ID": 100, "PLAYER_NAME": "Passer Two",    "START_POSITION": "PG"},
        {"PLAYER_ID": 30, "TEAM_ID": 200, "PLAYER_NAME": "Shooter Three", "START_POSITION": "SF"},
    ])
