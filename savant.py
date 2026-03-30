"""
savant.py — Baseball Savant / Statcast Integration
====================================================
Single batch call via pybaseball batting_stats() for season Statcast metrics.
Falls back to prior season when current season < 50 qualified hitters.

Key design decisions:
- Zero values (Barrel%=0, HH%=0) from failed joins → treated as NaN not real stats
- Last name + first initial matching to avoid duplicates
- Per-player pitch-level data available for Player Profile deep dive
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, timedelta

try:
    from pybaseball import statcast_batter, playerid_lookup, batting_stats
    from pybaseball import cache as pb_cache
    pb_cache.enable()
    _PB_AVAILABLE = True
except ImportError:
    _PB_AVAILABLE = False


def _pb_ok() -> bool:
    return _PB_AVAILABLE


# ─────────────────────────────────────────────────────────────────────────────
# SEASON BATCH FETCH  (single call, join to slate)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=7200)
def get_season_statcast_df(season: int = None) -> pd.DataFrame:
    """
    Pull FanGraphs season batting stats. Falls back to prior season
    if current season has fewer than 50 qualified hitters.
    Returns clean DataFrame ready for joining.
    """
    if not _pb_ok():
        return pd.DataFrame()
    if season is None:
        season = date.today().year
    try:
        df = batting_stats(season, season, qual=10)
        if df is None or len(df) < 50:
            df = batting_stats(season - 1, season - 1, qual=100)
        if df is None or df.empty:
            return pd.DataFrame()

        # Normalise column names
        col_map = {}
        for col in df.columns:
            cl = col.lower().replace(' ', '').replace('%', 'pct').replace('/', '_')
            col_map[col] = cl
        df = df.rename(columns=col_map)

        # Map to clean labels
        keep   = {'name': 'fg_name'}
        lookup = {
            'barrel%': 'Barrel%', 'barrelpct': 'Barrel%',
            'hardhit%': 'HH%',   'hardhitpct': 'HH%',
            'maxev': 'maxEV',
            'avgexitvelocity': 'AvgEV',
            'xba': 'xBA',
            'xslg': 'xSLG',
            'obp': 'OBP',
            'slg': 'SLG',
            'ops': 'OPS',
            'avg': 'fg_AVG',
            'hr': 'fg_HR',
            'k%': 'fg_Kpct', 'kpct': 'fg_Kpct',
            'bb%': 'fg_BBpct', 'bbpct': 'fg_BBpct',
        }
        for raw, label in lookup.items():
            if raw in df.columns and label not in keep.values():
                keep[raw] = label

        available = {k: v for k, v in keep.items() if k in df.columns}
        if 'name' not in available:
            return pd.DataFrame()

        out = df[list(available.keys())].rename(columns=available).copy()

        # Build join keys
        out['_last']       = out['fg_name'].astype(str).str.split().str[-1].str.lower()
        out['_first_init'] = out['fg_name'].astype(str).str[0].str.lower()

        # Replace zero Barrel%/HH% with NaN — zeros from failed matches, not real stats
        for col in ['Barrel%', 'HH%', 'AvgEV', 'maxEV']:
            if col in out.columns:
                out[col] = out[col].replace(0, np.nan)

        return out.reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


def join_statcast_to_slate(slate_df: pd.DataFrame) -> pd.DataFrame:
    """
    Left-join Statcast season metrics onto the slate DataFrame.
    Matches on last name + first initial to avoid duplicates.
    """
    savant_df = get_season_statcast_df()
    if savant_df.empty or slate_df.empty:
        return slate_df

    df = slate_df.copy()
    df['_last']       = df['Batter'].astype(str).str.split().str[-1].str.lower()
    df['_first_init'] = df['Batter'].astype(str).str[0].str.lower()

    # Merge on last name first
    merged = df.merge(
        savant_df.drop(columns=['fg_name'], errors='ignore'),
        on='_last', how='left', suffixes=('', '_sv')
    )

    # Where multiple rows returned (same last name), keep only where first initial matches
    dup_mask = merged.duplicated(subset=df.index.name or merged.index, keep=False)
    if dup_mask.any():
        init_col = '_first_init_sv' if '_first_init_sv' in merged.columns else '_first_init'
        keep_mask = (
            ~merged.duplicated(subset=['Batter', 'Game'], keep=False) |
            (merged['_first_init'] == merged[init_col])
        )
        merged = merged[keep_mask]

    # Final dedup — one row per (Batter, Game)
    merged = merged.drop_duplicates(subset=['Batter', 'Game']).reset_index(drop=True)

    # Drop all helper columns
    drop_cols = [c for c in merged.columns if c.startswith('_')]
    merged.drop(columns=drop_cols, inplace=True, errors='ignore')

    # Zero-out any remaining zeros that slipped through
    for col in ['Barrel%', 'HH%', 'AvgEV', 'maxEV']:
        if col in merged.columns:
            merged[col] = merged[col].replace(0, np.nan)

    return merged


# ─────────────────────────────────────────────────────────────────────────────
# PER-PLAYER STATCAST  (Player Profile deep dive)
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
    Returns: avg_ev, max_ev, barrel_pct, hard_hit_pct, xba, xwoba, avg_la, sample_size
    """
    df = get_batter_statcast(player_id, days_back)
    if df.empty:
        return {}
    bb = df[df['launch_speed'].notna()].copy()
    if bb.empty:
        return {}

    hard_hit_mask = bb['launch_speed'] >= 95
    # Barrel: launch_speed_angle == 6 is Statcast's barrel code
    barrel_mask = pd.Series([False] * len(bb), index=bb.index)
    if 'launch_speed_angle' in bb.columns:
        barrel_mask = bb['launch_speed_angle'] == 6

    metrics = {
        'avg_ev':       round(float(bb['launch_speed'].mean()), 1),
        'max_ev':       round(float(bb['launch_speed'].max()), 1),
        'barrel_pct':   round(float(barrel_mask.mean() * 100), 1),
        'hard_hit_pct': round(float(hard_hit_mask.mean() * 100), 1),
        'avg_la':       round(float(bb['launch_angle'].mean()), 1),
        'sample_size':  len(bb),
    }
    if 'estimated_ba_using_speedangle' in df.columns:
        val = df['estimated_ba_using_speedangle'].mean()
        if pd.notna(val):
            metrics['xba']  = round(float(val), 3)
    if 'estimated_woba_using_speedangle' in df.columns:
        val = df['estimated_woba_using_speedangle'].mean()
        if pd.notna(val):
            metrics['xwoba'] = round(float(val), 3)
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
