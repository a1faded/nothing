"""
savant.py — Baseball Savant / Statcast Integration
====================================================
Uses pybaseball to pull Statcast metrics.

KEY DESIGN: Instead of slow per-player Statcast calls, we use a single
batting_stats() call (FanGraphs season data) which returns barrel%, HardHit%,
and max EV for ALL qualified hitters in one request. We then join to the slate
by player name. This is fast and cache-friendly.

Per-player Statcast pitch-level data is reserved for the Player Deep Dive panel.
"""

import streamlit as st
import pandas as pd
from datetime import date, timedelta

try:
    from pybaseball import (
        statcast_batter,
        playerid_lookup,
        batting_stats,
    )
    from pybaseball import cache as pb_cache
    pb_cache.enable()
    _PB_AVAILABLE = True
except ImportError:
    _PB_AVAILABLE = False


def _pb_ok() -> bool:
    return _PB_AVAILABLE


# ─────────────────────────────────────────────────────────────────────────────
# SEASON STATCAST LEADERS  —  single batch call, join to slate
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=7200)   # 2 hours — season stats don't change minute to minute
def get_season_statcast_df(season: int = None) -> pd.DataFrame:
    """
    Pull FanGraphs season batting stats for all hitters (qual=10 PA).
    Returns DataFrame with columns we need: Name, Barrel%, HardHit%, maxEV, xBA, xSLG.
    Single call — fast. Cache 2h.
    """
    if not _pb_ok():
        return pd.DataFrame()
    if season is None:
        season = date.today().year
    try:
        df = batting_stats(season, season, qual=10)
        if df is None or df.empty:
            return pd.DataFrame()

        # Normalise column names — FanGraphs columns vary slightly by season
        col_map = {}
        for col in df.columns:
            cl = col.lower().replace(' ', '').replace('%', 'pct').replace('/', '_')
            col_map[col] = cl
        df = df.rename(columns=col_map)

        # Keep only what we need, rename to clean labels
        keep = {'name': 'fg_name'}
        candidates = {
            'barrel%': 'Barrel%', 'barrelpct': 'Barrel%',
            'hardhit%': 'HH%', 'hardhitpct': 'HH%',
            'maxev': 'maxEV', 'ev95percent': 'EV95%',
            'xba': 'xBA', 'xslg': 'xSLG',
            'avgexitvelocity': 'AvgEV',
        }
        for raw, clean in candidates.items():
            if raw in df.columns and clean not in keep.values():
                keep[raw] = clean

        available = {k: v for k, v in keep.items() if k in df.columns}
        if 'name' not in available:
            return pd.DataFrame()

        out = df[list(available.keys())].rename(columns=available).copy()
        # Build a last-name lookup key for fuzzy matching
        out['_last'] = out['fg_name'].astype(str).str.split().str[-1].str.lower()
        return out.reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


def join_statcast_to_slate(slate_df: pd.DataFrame) -> pd.DataFrame:
    """
    Left-join Statcast season metrics onto the slate DataFrame.
    Matches on last name. If multiple players share a last name,
    picks the one whose first initial also matches.
    Adds columns: Barrel%, HH%, xBA, xSLG (where available).
    """
    savant_df = get_season_statcast_df()
    if savant_df.empty or slate_df.empty:
        return slate_df

    df = slate_df.copy()
    # Build lookup keys from batter names
    df['_last'] = df['Batter'].astype(str).str.split().str[-1].str.lower()
    df['_first_init'] = df['Batter'].astype(str).str[0].str.lower()

    savant_df['_first_init'] = savant_df['fg_name'].astype(str).str[0].str.lower()

    # Merge on last name
    merged = df.merge(
        savant_df.drop(columns=['fg_name'], errors='ignore'),
        on='_last', how='left', suffixes=('', '_sv')
    )

    # If there are duplicates (same last name), keep row where first initial matches
    if merged.index.duplicated().any():
        init_match = merged['_first_init'] == merged['_first_init_sv']
        merged = merged[~merged.index.duplicated(keep='first') | init_match]

    # Drop helper columns
    drop_cols = [c for c in merged.columns if c.startswith('_')]
    merged.drop(columns=drop_cols, inplace=True, errors='ignore')

    return merged.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# PER-PLAYER STATCAST  —  for Player Deep Dive panel
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_batter_statcast(player_id: int, days_back: int = 30) -> pd.DataFrame:
    """Pitch-level Statcast for a single batter over last N days."""
    if not _pb_ok():
        return pd.DataFrame()
    try:
        end_dt   = date.today().strftime('%Y-%m-%d')
        start_dt = (date.today() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        df = statcast_batter(start_dt, end_dt, player_id)
        return df if df is not None and not df.empty else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def get_batter_quality_metrics(player_id: int, days_back: int = 30) -> dict:
    """
    Summarise quality-of-contact metrics for a single batter.
    Returns: avg_ev, max_ev, barrel_pct, hard_hit_pct, xba, xslg, avg_la, sample_size
    """
    df = get_batter_statcast(player_id, days_back)
    if df.empty:
        return {}
    bb = df[df['launch_speed'].notna()]
    if bb.empty:
        return {}

    barrel_mask   = bb.get('launch_speed_angle', pd.Series()) == 6
    hard_hit_mask = bb['launch_speed'] >= 95

    metrics = {
        'avg_ev':       round(float(bb['launch_speed'].mean()), 1),
        'max_ev':       round(float(bb['launch_speed'].max()), 1),
        'barrel_pct':   round(float(barrel_mask.mean() * 100), 1),
        'hard_hit_pct': round(float(hard_hit_mask.mean() * 100), 1),
        'avg_la':       round(float(bb['launch_angle'].mean()), 1),
        'sample_size':  len(bb),
    }
    if 'estimated_ba_using_speedangle' in df.columns:
        metrics['xba']  = round(float(df['estimated_ba_using_speedangle'].mean()), 3)
    if 'estimated_woba_using_speedangle' in df.columns:
        metrics['xwoba'] = round(float(df['estimated_woba_using_speedangle'].mean()), 3)
    return metrics


@st.cache_data(ttl=86400)
def get_savant_player_id(last_name: str, first_name: str):
    """Look up MLBAM ID via pybaseball playerid_lookup."""
    if not _pb_ok():
        return None
    try:
        result = playerid_lookup(last_name, first_name)
        if not result.empty:
            return int(result.iloc[0]['key_mlbam'])
    except Exception:
        pass
    return None
