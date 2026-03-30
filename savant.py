"""
data/savant.py — Baseball Savant / Statcast Integration
=========================================================
Uses the pybaseball package to pull Statcast data from Baseball Savant.
Provides: barrel%, xSLG, EV, launch angle, pitch-level data.

These supplement (not replace) BallPark Pal simulation data.
They are the data points BallPark Pal CSVs don't cover —
Statcast quality-of-contact metrics that inform HR/XB confidence.

Install: pip install pybaseball
"""

import streamlit as st
import pandas as pd
from datetime import date, timedelta

try:
    from pybaseball import (
        statcast_batter,
        statcast_pitcher,
        playerid_lookup,
        batting_stats,
        pitching_stats,
    )
    from pybaseball import cache as pb_cache
    pb_cache.enable()
    _PYBASEBALL_AVAILABLE = True
except ImportError:
    _PYBASEBALL_AVAILABLE = False


def _check_available():
    if not _PYBASEBALL_AVAILABLE:
        st.warning("⚠️ pybaseball not installed. Run: pip install pybaseball")
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# PLAYER ID LOOKUP (Savant uses MLBAM IDs same as Stats API)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400)  # 24 hours — IDs don't change
def get_savant_player_id(last_name: str, first_name: str) -> int | None:
    """Look up a player's MLBAM ID via pybaseball."""
    if not _check_available():
        return None
    try:
        result = playerid_lookup(last_name, first_name)
        if not result.empty:
            return int(result.iloc[0]['key_mlbam'])
    except Exception as e:
        st.warning(f"⚠️ Player ID lookup failed for {first_name} {last_name}: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# BATTER STATCAST (recent pitch-level data)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_batter_statcast(player_id: int, days_back: int = 30) -> pd.DataFrame:
    """
    Pull Statcast pitch-level data for a batter over the last N days.
    Returns DataFrame with: launch_speed, launch_angle, estimated_ba_using_speedangle,
    estimated_woba_using_speedangle, bb_type, events, pitch_type, etc.
    """
    if not _check_available():
        return pd.DataFrame()
    try:
        end_dt   = date.today().strftime('%Y-%m-%d')
        start_dt = (date.today() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        df = statcast_batter(start_dt, end_dt, player_id)
        return df if df is not None else pd.DataFrame()
    except Exception as e:
        st.warning(f"⚠️ Statcast batter data failed for player {player_id}: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def get_batter_quality_metrics(player_id: int, days_back: int = 30) -> dict:
    """
    Summarise a batter's Statcast quality-of-contact metrics.
    Returns: { avg_ev, max_ev, barrel_pct, hard_hit_pct, xba, xslg, launch_angle }
    """
    df = get_batter_statcast(player_id, days_back)
    if df.empty:
        return {}

    batted_balls = df[df['launch_speed'].notna()]
    if batted_balls.empty:
        return {}

    barrel_mask   = batted_balls['launch_speed_angle'] == 6  # Statcast barrel code
    hard_hit_mask = batted_balls['launch_speed'] >= 95

    return {
        'avg_ev':       round(batted_balls['launch_speed'].mean(), 1),
        'max_ev':       round(batted_balls['launch_speed'].max(), 1),
        'barrel_pct':   round(barrel_mask.mean() * 100, 1),
        'hard_hit_pct': round(hard_hit_mask.mean() * 100, 1),
        'xba':          round(df['estimated_ba_using_speedangle'].mean(), 3) if 'estimated_ba_using_speedangle' in df.columns else None,
        'xslg':         round(df['estimated_woba_using_speedangle'].mean(), 3) if 'estimated_woba_using_speedangle' in df.columns else None,
        'avg_la':       round(batted_balls['launch_angle'].mean(), 1),
        'sample_size':  len(batted_balls),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PITCHER STATCAST
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_pitcher_statcast(player_id: int, days_back: int = 30) -> pd.DataFrame:
    """Pull Statcast pitch-level data for a pitcher."""
    if not _check_available():
        return pd.DataFrame()
    try:
        end_dt   = date.today().strftime('%Y-%m-%d')
        start_dt = (date.today() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        df = statcast_pitcher(start_dt, end_dt, player_id)
        return df if df is not None else pd.DataFrame()
    except Exception as e:
        st.warning(f"⚠️ Statcast pitcher data failed for player {player_id}: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def get_pitcher_arsenal(player_id: int, days_back: int = 30) -> pd.DataFrame:
    """
    Summarise a pitcher's arsenal: pitch type, usage%, avg velo, avg spin.
    Returns DataFrame with one row per pitch type.
    """
    df = get_pitcher_statcast(player_id, days_back)
    if df.empty or 'pitch_type' not in df.columns:
        return pd.DataFrame()

    pitches = df[df['pitch_type'].notna()].copy()
    total   = len(pitches)
    summary = pitches.groupby('pitch_name').agg(
        count         = ('pitch_type', 'count'),
        avg_velo      = ('release_speed', 'mean'),
        avg_spin      = ('release_spin_rate', 'mean'),
    ).reset_index()
    summary['usage_pct'] = (summary['count'] / total * 100).round(1)
    summary['avg_velo']  = summary['avg_velo'].round(1)
    summary['avg_spin']  = summary['avg_spin'].round(0)
    return summary.sort_values('usage_pct', ascending=False)


# ─────────────────────────────────────────────────────────────────────────────
# SEASON LEADERBOARDS (FanGraphs via pybaseball)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=7200)  # 2 hours
def get_season_batting_stats(season: int = None) -> pd.DataFrame:
    """
    Pull season-level FanGraphs batting stats for all qualified hitters.
    Includes: AVG, OBP, SLG, wOBA, xFIP, barrel%, HardHit%, etc.
    """
    if not _check_available():
        return pd.DataFrame()
    if season is None:
        season = date.today().year
    try:
        df = batting_stats(season, season, qual=50)
        return df if df is not None else pd.DataFrame()
    except Exception as e:
        st.warning(f"⚠️ Could not fetch season batting stats: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=7200)
def get_season_pitching_stats(season: int = None) -> pd.DataFrame:
    """Pull season-level FanGraphs pitching stats."""
    if not _check_available():
        return pd.DataFrame()
    if season is None:
        season = date.today().year
    try:
        df = pitching_stats(season, season, qual=10)
        return df if df is not None else pd.DataFrame()
    except Exception as e:
        st.warning(f"⚠️ Could not fetch season pitching stats: {e}")
        return pd.DataFrame()
