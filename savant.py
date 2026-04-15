"""
savant.py — Baseball Savant / Statcast Integration V3
======================================================
V3 key change: ID-BASED lookup replaces fragile name matching.

Problem with V2: joining season Statcast data by last-name + first-initial
fails silently for any name mismatch (accents, suffixes Jr./Sr., hyphens,
nick-names, etc.). BallPark Pal names don't always match FanGraphs names.

V3 solution — two-tier approach:
  Tier 1 (pipeline, name-based): join_statcast_to_slate()
    → keeps existing name join as a best-effort first pass
  Tier 2 (post-pipeline, ID-based): enrich_slate_with_statcast(df, player_id_map)
    → fills gaps using MLBAM IDs from mlb_api.build_player_id_map()
    → calls pre-fetched leaderboard dicts (single API call per season, cached)
  Tier 3 (player profile, ID-based): get_player_season_statcast(mlbam_id)
    → instant dict lookup from the same cached leaderboard
    → used as fallback when slate columns are still NaN for a specific player

Per-player rolling data (Player Profile deep dive):
  get_batter_statcast(player_id, days_back)       → pitch-level DataFrame
  get_batter_quality_metrics(player_id, days_back) → summarised metrics dict
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, timedelta

try:
    from pybaseball import (
        batting_stats,
        statcast_batter,
        statcast_batter_exitvelo_barrels,
        statcast_batter_expected_stats,
        playerid_lookup,
    )
    from pybaseball import cache as pb_cache
    pb_cache.enable()
    _PB_AVAILABLE = True
except ImportError:
    _PB_AVAILABLE = False


def _pb_ok() -> bool:
    return _PB_AVAILABLE

_SC_COLS = ['Barrel%', 'HH%', 'AvgEV', 'maxEV', 'xBA', 'xSLG', 'xwOBA']

# ─────────────────────────────────────────────────────────────────────────────
# TIER 2/3 — SAVANT LEADERBOARD CACHE  (MLBAM ID → stats dict)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=7200)
def _get_savant_leaderboard(season: int) -> dict:
    """
    Fetch both Savant leaderboards and index by MLBAM player_id.

    statcast_batter_exitvelo_barrels() → Barrel%, HH%(EV95%), AvgEV, maxEV
    statcast_batter_expected_stats()   → xBA, xSLG, xwOBA

    Returns: {mlbam_id (int): {stat_name: value, ...}}

    Cached 2 hours — single call covers all players on the slate.
    minBBE/minPA=5 to capture early-season players with limited games.
    """
    if not _PB_AVAILABLE:
        return {}

    result: dict[int, dict] = {}

    # ── Exit velo / barrels ────────────────────────────────────────────────
    try:
        ev_df = statcast_batter_exitvelo_barrels(season, minBBE=5)
        if ev_df is not None and not ev_df.empty:
            ev_df.columns = [c.lower() for c in ev_df.columns]

            # Column name map (Savant sometimes changes these)
            col_aliases = {
                'avg_hit_speed':  'AvgEV',
                'max_hit_speed':  'maxEV',
                'brl_percent':    'Barrel%',
                'ev95percent':    'HH%',
                # older column names
                'avg_exit_velocity': 'AvgEV',
                'max_exit_velocity': 'maxEV',
                'barrel_batted_rate':'Barrel%',
            }

            for _, row in ev_df.iterrows():
                pid_raw = row.get('player_id')
                if not pid_raw or not str(pid_raw).isdigit():
                    continue
                pid = int(pid_raw)
                result.setdefault(pid, {})
                for src, dst in col_aliases.items():
                    if src in row and pd.notna(row[src]) and row[src] != 0:
                        result[pid][dst] = float(row[src])
    except Exception:
        pass

    # ── Expected stats ────────────────────────────────────────────────────
    try:
        xs_df = statcast_batter_expected_stats(season, minPA=5)
        if xs_df is not None and not xs_df.empty:
            xs_df.columns = [c.lower() for c in xs_df.columns]

            xstat_aliases = {
                'est_ba':   'xBA',
                'xba':      'xBA',
                'est_slg':  'xSLG',
                'xslg':     'xSLG',
                'est_woba': 'xwOBA',
                'xwoba':    'xwOBA',
            }

            for _, row in xs_df.iterrows():
                pid_raw = row.get('player_id')
                if not pid_raw or not str(pid_raw).isdigit():
                    continue
                pid = int(pid_raw)
                result.setdefault(pid, {})
                for src, dst in xstat_aliases.items():
                    if src in row and pd.notna(row[src]) and dst not in result[pid]:
                        val = float(row[src])
                        if val != 0:
                            result[pid][dst] = val
    except Exception:
        pass

    return result


def get_player_season_statcast(mlbam_id: int, season: int | None = None) -> dict:
    """
    Instant lookup of season Statcast stats for one player by MLBAM ID.

    Uses the pre-cached leaderboard — no additional API call.
    Returns: {'Barrel%': 12.5, 'HH%': 46.3, 'AvgEV': 91.2, 'xBA': 0.289, ...}
    Returns {} if player not found or pybaseball unavailable.

    Used by player_profile.py as fallback when slate join returns NaN.
    """
    if not mlbam_id:
        return {}
    if season is None:
        season = date.today().year
    leaderboard = _get_savant_leaderboard(season)
    return leaderboard.get(int(mlbam_id), {})


def enrich_slate_with_statcast(df: pd.DataFrame, player_id_map: dict) -> pd.DataFrame:
    """
    Fill Statcast columns in the slate df using MLBAM ID lookup.

    Called AFTER join_statcast_to_slate() (name-based) as a second pass.
    For any player where Barrel%/HH%/etc. is still NaN, looks up by MLBAM ID
    from the pre-cached leaderboard dict.

    This is why ID-based lookup is critical:
      BallPark Pal: "Ronald Acuña Jr."  ← accent + suffix
      FanGraphs:    "Ronald Acuna Jr."  ← no accent
      → name join silently fails, player gets no Statcast data

    With this function, the MLBAM ID bridge means name format never matters.

    Args:
        df:            scored slate DataFrame (output of _build_scored_df)
        player_id_map: {batter_name: mlbam_id} from mlb_api.build_player_id_map()
    Returns:
        df with Statcast columns filled where previously NaN
    """
    if not player_id_map or df.empty:
        return df

    season      = date.today().year
    leaderboard = _get_savant_leaderboard(season)
    if not leaderboard:
        return df

    df = df.copy()

    # Ensure Statcast columns exist
    for col in _SC_COLS:
        if col not in df.columns:
            df[col] = np.nan

    for idx, row in df.iterrows():
        batter  = row.get('Batter', '')
        mlbam   = player_id_map.get(batter)
        if not mlbam:
            continue

        stats = leaderboard.get(int(mlbam), {})
        if not stats:
            continue

        for col, val in stats.items():
            if col in df.columns and (pd.isna(df.at[idx, col]) or df.at[idx, col] == 0):
                df.at[idx, col] = val

    return df

# ─────────────────────────────────────────────────────────────────────────────
# TIER 1 — NAME-BASED SEASON JOIN  (first-pass, kept for speed)
# ─────────────────────────────────────────────────────────────────────────────

def _norm_col(col: str) -> str:
    return col.lower().replace(' ', '').replace('%', 'pct').replace('/', '_')


_FG_LOOKUP: dict[str, str] = {
    'name':            'fg_name',
    'barrel%':         'Barrel%', 'barrelpct':      'Barrel%',
    'hardhit%':        'HH%',     'hardhitpct':     'HH%',
    'avgexitvelocity': 'AvgEV',   'maxev':           'maxEV',
    'xba':             'xBA',     'xslg':            'xSLG',
    'xwoba':           'xwOBA',
    'obp':             'OBP',     'slg':             'SLG',
    'ops':             'OPS',     'avg':             'fg_AVG',
    'hr':              'fg_HR',
    'k%':    'fg_Kpct', 'kpct':  'fg_Kpct',
    'bb%':   'fg_BBpct','bbpct': 'fg_BBpct',
}


@st.cache_data(ttl=7200)
def get_season_statcast_df(season: int | None = None) -> pd.DataFrame:
    """
    FanGraphs batting_stats() for name-based join.
    Falls back to prior season if < 50 qualified hitters (early-season gap).
    """
    if not _PB_AVAILABLE:
        return pd.DataFrame()
    if season is None:
        season = date.today().year
    try:
        df = batting_stats(season, season, qual=10)
        if df is None or len(df) < 50:
            df = batting_stats(season - 1, season - 1, qual=100)
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.rename(columns={c: _norm_col(c) for c in df.columns})

        keep = {}
        for norm_name, canon in _FG_LOOKUP.items():
            if norm_name in df.columns and canon not in keep.values():
                keep[norm_name] = canon

        available = {k: v for k, v in keep.items() if k in df.columns}
        if 'name' not in available:
            return pd.DataFrame()

        out = df[list(available.keys())].rename(columns=available).copy()
        out['_last']       = out['fg_name'].astype(str).str.split().str[-1].str.lower()
        out['_first_init'] = out['fg_name'].astype(str).str[0].str.lower()

        for col in _SC_COLS:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors='coerce').replace(0.0, np.nan)

        return out.reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


def join_statcast_to_slate(slate_df: pd.DataFrame) -> pd.DataFrame:
    """
    Tier 1: name-based join.  Gaps filled later by enrich_slate_with_statcast().
    FIX V5.2: disambiguation uses ['Batter','Game'] not df.index.name.
    """
    savant_df = get_season_statcast_df()
    if savant_df.empty or slate_df.empty:
        return slate_df

    df = slate_df.copy()
    df['_last']       = df['Batter'].astype(str).str.split().str[-1].str.lower()
    df['_first_init'] = df['Batter'].astype(str).str[0].str.lower()

    sv_merge = savant_df.drop(columns=['fg_name'], errors='ignore')

    merged = df.merge(sv_merge, on='_last', how='left', suffixes=('', '_sv'))

    dup_mask = merged.duplicated(subset=['Batter', 'Game'], keep=False)
    if dup_mask.any():
        init_sv = '_first_init_sv' if '_first_init_sv' in merged.columns else '_first_init'
        keep_mask = (
            ~dup_mask
            | (merged['_first_init'] == merged[init_sv])
        )
        merged = merged[keep_mask]

    merged = merged.drop_duplicates(subset=['Batter', 'Game']).reset_index(drop=True)
    drop_cols = [c for c in merged.columns if c.startswith('_')]
    merged.drop(columns=drop_cols, inplace=True, errors='ignore')

    for col in _SC_COLS:
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors='coerce').replace(0.0, np.nan)

    return merged

# ─────────────────────────────────────────────────────────────────────────────
# PER-PLAYER ROLLING DATA  (Player Profile deep dive)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_batter_statcast(player_id: int, days_back: int = 30) -> pd.DataFrame:
    """Pitch-level Statcast for a single batter. player_id = MLBAM ID."""
    if not _PB_AVAILABLE:
        return pd.DataFrame()
    try:
        end_dt   = date.today().strftime('%Y-%m-%d')
        start_dt = (date.today() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        df       = statcast_batter(start_dt, end_dt, player_id)
        return df if df is not None and not df.empty else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def get_batter_quality_metrics(player_id: int, days_back: int = 30) -> dict:
    """
    Summarise rolling quality-of-contact for one batter (last N days).
    Uses pitch-level statcast_batter() data.
    """
    df = get_batter_statcast(player_id, days_back)
    if df.empty:
        return {}

    bb = df[df['launch_speed'].notna()].copy()
    if bb.empty:
        return {}

    hard_hit_mask = bb['launch_speed'] >= 95
    barrel_mask   = pd.Series(False, index=bb.index)
    if 'launch_speed_angle' in bb.columns:
        barrel_mask = bb['launch_speed_angle'] == 6

    metrics: dict = {
        'avg_ev':       round(float(bb['launch_speed'].mean()), 1),
        'max_ev':       round(float(bb['launch_speed'].max()),  1),
        'barrel_pct':   round(float(barrel_mask.mean() * 100),  1),
        'hard_hit_pct': round(float(hard_hit_mask.mean() * 100),1),
        'avg_la':       round(float(bb['launch_angle'].mean()),  1),
        'sample_size':  len(bb),
    }

    if 'estimated_ba_using_speedangle' in df.columns:
        val = df['estimated_ba_using_speedangle'].mean()
        if pd.notna(val) and val > 0:
            metrics['xba'] = round(float(val), 3)

    if 'estimated_woba_using_speedangle' in df.columns:
        val = df['estimated_woba_using_speedangle'].mean()
        if pd.notna(val) and val > 0:
            metrics['xwoba'] = round(float(val), 3)

    return metrics


@st.cache_data(ttl=86400)
def get_savant_player_id(last_name: str, first_name: str) -> int | None:
    """Look up MLBAM ID via pybaseball playerid_lookup (single player)."""
    if not _PB_AVAILABLE:
        return None
    try:
        result = playerid_lookup(last_name, first_name)
        if not result.empty and 'key_mlbam' in result.columns:
            mlbam = result.iloc[0]['key_mlbam']
            if pd.notna(mlbam):
                return int(mlbam)
    except Exception:
        pass
    return None
