"""
savant.py — Baseball Savant / Statcast Integration V2
======================================================
Multi-source season-level Statcast fetch with robust fallbacks.

Source hierarchy (all from pybaseball):
  1. batting_stats(season, qual)          → FanGraphs: Barrel%, HH%, AvgEV, maxEV,
                                            xBA, xSLG, OBP, SLG, K%, BB%
  2. statcast_batter_exitvelo_barrels()   → Baseball Savant: Barrel%, HH%, AvgEV,
                                            maxEV (direct from Statcast leaderboard)
  3. statcast_batter_expected_stats()     → Baseball Savant: xBA, xSLG, xwOBA
                                            (expected stats leaderboard)

Source 1 is tried first. If it returns < 50 players OR is missing key Statcast
columns, sources 2 & 3 are fetched and merged in to fill gaps.

Per-player rolling data (for Player Profile):
  statcast_batter(start_dt, end_dt, player_id) → pitch-level DataFrame
  → summarised by get_batter_quality_metrics()

Join strategy (slate merge):
  - All sources join on last name + first initial to avoid full-name mismatches
  - Zero Barrel%/HH% after join → treated as NaN (not real zeros)

FIX V5.2:
  - join_statcast_to_slate disambiguation fixed (subset=['Batter','Game'])
  - Multi-source fetch fills gaps early in season when qual=10 returns
    insufficient Statcast coverage
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

# ─────────────────────────────────────────────────────────────────────────────
# COLUMN NORMALISATION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _norm_col(col: str) -> str:
    """Lower-case, strip spaces, % → pct, / → _"""
    return col.lower().replace(' ', '').replace('%', 'pct').replace('/', '_')


# FanGraphs batting_stats output → our canonical labels
_FG_LOOKUP: dict[str, str] = {
    'name':              'fg_name',
    # Statcast quality-of-contact
    'barrel%':           'Barrel%',
    'barrelpct':         'Barrel%',
    'hardhit%':          'HH%',
    'hardhitpct':        'HH%',
    'avgexitvelocity':   'AvgEV',
    'maxev':             'maxEV',
    # Expected stats
    'xba':               'xBA',
    'xslg':              'xSLG',
    'xwoba':             'xwOBA',
    # Traditional
    'obp':               'OBP',
    'slg':               'SLG',
    'ops':               'OPS',
    'avg':               'fg_AVG',
    'hr':                'fg_HR',
    'k%':                'fg_Kpct',
    'kpct':              'fg_Kpct',
    'bb%':               'fg_BBpct',
    'bbpct':             'fg_BBpct',
}

# Baseball Savant exitvelo/barrels leaderboard → canonical labels
_EV_LOOKUP: dict[str, str] = {
    'last_name':         '_sv_last',
    'first_name':        '_sv_first',
    'player_id':         '_sv_mlbam',   # MLBAM ID from Savant — gold!
    'avg_hit_speed':     'AvgEV',
    'max_hit_speed':     'maxEV',
    'brl_percent':       'Barrel%',
    'ev95percent':       'HH%',         # hard-hit: EV ≥ 95 mph %
    'brl_pa':            'Barrel_PA',
}

# Baseball Savant expected stats leaderboard → canonical labels
_ES_LOOKUP: dict[str, str] = {
    'last_name':         '_sv_last',
    'first_name':        '_sv_first',
    'player_id':         '_sv_mlbam',
    'est_ba':            'xBA',
    'est_slg':           'xSLG',
    'est_woba':          'xwOBA',
    'xba':               'xBA',
    'xslg':              'xSLG',
    'xwoba':             'xwOBA',
}

_SC_COLS = ['Barrel%', 'HH%', 'AvgEV', 'maxEV', 'xBA', 'xSLG', 'xwOBA']

# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 1 — FanGraphs batting_stats
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=7200)
def _fetch_fg_stats(season: int) -> pd.DataFrame:
    """
    Pull FanGraphs batting stats. Tries current season first, falls back to
    prior season when < 50 qualified hitters returned (early-season gaps).
    """
    if not _pb_ok():
        return pd.DataFrame()
    try:
        df = batting_stats(season, season, qual=10)
        if df is None or len(df) < 50:
            prior = batting_stats(season - 1, season - 1, qual=100)
            if prior is not None and not prior.empty:
                df = prior

        if df is None or df.empty:
            return pd.DataFrame()

        # Normalise column names
        df = df.rename(columns={c: _norm_col(c) for c in df.columns})

        # Map to canonical labels
        keep = {}
        for norm_name, canon in _FG_LOOKUP.items():
            if norm_name in df.columns and canon not in keep.values():
                keep[norm_name] = canon

        available = {k: v for k, v in keep.items() if k in df.columns}
        if 'name' not in available:
            return pd.DataFrame()

        out = df[list(available.keys())].rename(columns=available).copy()
        out = _add_join_keys(out, name_col='fg_name')
        out = _zero_to_nan(out)
        return out.reset_index(drop=True)

    except Exception:
        return pd.DataFrame()

# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 2 — Baseball Savant exit velo / barrels leaderboard
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=7200)
def _fetch_savant_ev(season: int) -> pd.DataFrame:
    """
    statcast_batter_exitvelo_barrels(year) → direct from Baseball Savant.
    Returns Barrel%, HH%(EV95%), AvgEV, maxEV with MLBAM IDs.
    """
    if not _pb_ok():
        return pd.DataFrame()
    try:
        df = statcast_batter_exitvelo_barrels(season, minBBE=10)
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.rename(columns={c: c.lower() for c in df.columns})

        # Map columns
        keep = {}
        for raw, canon in _EV_LOOKUP.items():
            if raw in df.columns:
                keep[raw] = canon

        if '_sv_last' not in keep.values():
            return pd.DataFrame()

        out = df[list(keep.keys())].rename(columns=keep).copy()

        # Build join keys from split name fields
        out['_last'] = out['_sv_last'].astype(str).str.strip().str.lower()
        if '_sv_first' in out.columns:
            out['_first_init'] = out['_sv_first'].astype(str).str[0].str.lower()

        out = _zero_to_nan(out)
        return out.drop(columns=['_sv_last', '_sv_first'], errors='ignore').reset_index(drop=True)

    except Exception:
        return pd.DataFrame()

# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 3 — Baseball Savant expected stats leaderboard
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=7200)
def _fetch_savant_xstats(season: int) -> pd.DataFrame:
    """
    statcast_batter_expected_stats(year) → xBA, xSLG, xwOBA with MLBAM IDs.
    """
    if not _pb_ok():
        return pd.DataFrame()
    try:
        df = statcast_batter_expected_stats(season, minPA=10)
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.rename(columns={c: c.lower() for c in df.columns})

        keep = {}
        for raw, canon in _ES_LOOKUP.items():
            if raw in df.columns and canon not in keep.values():
                keep[raw] = canon

        if '_sv_last' not in keep.values():
            return pd.DataFrame()

        out = df[list(keep.keys())].rename(columns=keep).copy()
        out['_last'] = out['_sv_last'].astype(str).str.strip().str.lower()
        if '_sv_first' in out.columns:
            out['_first_init'] = out['_sv_first'].astype(str).str[0].str.lower()

        out = _zero_to_nan(out)
        return out.drop(columns=['_sv_last', '_sv_first'], errors='ignore').reset_index(drop=True)

    except Exception:
        return pd.DataFrame()

# ─────────────────────────────────────────────────────────────────────────────
# MERGE SOURCES → SINGLE STATCAST DF
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=7200)
def get_season_statcast_df(season: int | None = None) -> pd.DataFrame:
    """
    Pull and merge all three Statcast sources into one DataFrame per player.

    Source 1 (FanGraphs batting_stats) is primary.
    Sources 2 & 3 (Savant leaderboards) fill in where Source 1 is null.

    Returns one row per unique (last, first_init) pair with columns:
      _last, _first_init, [_sv_mlbam], Barrel%, HH%, AvgEV, maxEV,
      xBA, xSLG, xwOBA, OBP, SLG, OPS, fg_AVG, fg_HR, fg_Kpct, fg_BBpct
    """
    if season is None:
        season = date.today().year

    fg  = _fetch_fg_stats(season)
    ev  = _fetch_savant_ev(season)
    xs  = _fetch_savant_xstats(season)

    if fg.empty and ev.empty and xs.empty:
        return pd.DataFrame()

    # Start with FanGraphs (has most columns)
    base = fg.copy() if not fg.empty else pd.DataFrame()

    # Merge Savant EV data — fill missing Barrel%/HH%/EV columns
    if not ev.empty and not base.empty:
        base = _fill_from_source(base, ev, fill_cols=['Barrel%', 'HH%', 'AvgEV', 'maxEV'])
    elif not ev.empty:
        base = ev.copy()

    # Merge Savant expected stats — fill missing xBA/xSLG/xwOBA
    if not xs.empty and not base.empty:
        base = _fill_from_source(base, xs, fill_cols=['xBA', 'xSLG', 'xwOBA'])
    elif not xs.empty and base.empty:
        base = xs.copy()

    if base.empty:
        return pd.DataFrame()

    # Ensure join keys exist
    if '_last' not in base.columns or '_first_init' not in base.columns:
        return pd.DataFrame()

    base = _zero_to_nan(base)
    return base.reset_index(drop=True)


def _fill_from_source(base: pd.DataFrame, source: pd.DataFrame,
                      fill_cols: list[str]) -> pd.DataFrame:
    """
    For each column in fill_cols, where base has NaN, pull from source
    matched on (_last, _first_init).
    """
    fill_cols_present = [c for c in fill_cols if c in source.columns]
    if not fill_cols_present:
        return base

    src = source[['_last', '_first_init'] + fill_cols_present].copy()

    # Dedup source on join keys
    src = src.drop_duplicates(subset=['_last', '_first_init'])

    merged = base.merge(
        src, on=['_last', '_first_init'], how='left', suffixes=('', '_src')
    )

    for col in fill_cols_present:
        src_col = col + '_src'
        if src_col in merged.columns:
            # Fill NaN in base column from source column
            if col in merged.columns:
                merged[col] = merged[col].fillna(merged[src_col])
            else:
                merged[col] = merged[src_col]
            merged.drop(columns=[src_col], inplace=True)

    return merged


def _add_join_keys(df: pd.DataFrame, name_col: str) -> pd.DataFrame:
    """Add _last and _first_init join keys from a full name column."""
    df['_last']       = df[name_col].astype(str).str.split().str[-1].str.lower()
    df['_first_init'] = df[name_col].astype(str).str[0].str.lower()
    return df


def _zero_to_nan(df: pd.DataFrame) -> pd.DataFrame:
    """Replace 0.0 → NaN for Statcast columns (zero = failed join, not reality)."""
    for col in _SC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').replace(0.0, np.nan)
    return df

# ─────────────────────────────────────────────────────────────────────────────
# SLATE JOIN
# ─────────────────────────────────────────────────────────────────────────────

def join_statcast_to_slate(slate_df: pd.DataFrame) -> pd.DataFrame:
    """
    Left-join season Statcast metrics onto today's slate DataFrame.

    Matching strategy:
      1. Merge on last name (_last).
      2. Where a batter has multiple Statcast matches (same last name),
         keep only the row where Statcast first initial matches batter initial.
      3. Final dedup on (Batter, Game) — one row per matchup slot.

    FIX V5.2: Uses ['Batter', 'Game'] as duplicate key (previously broken).
    """
    savant_df = get_season_statcast_df()
    if savant_df.empty or slate_df.empty:
        return slate_df

    df = slate_df.copy()
    df['_last']       = df['Batter'].astype(str).str.split().str[-1].str.lower()
    df['_first_init'] = df['Batter'].astype(str).str[0].str.lower()

    # Drop name column from Statcast side before merge (already have it in slate)
    sv_drop = ['fg_name'] + [c for c in savant_df.columns if c.startswith('_sv')]
    sv_merge = savant_df.drop(columns=sv_drop, errors='ignore')

    # Left merge on last name
    merged = df.merge(
        sv_merge,
        on='_last', how='left', suffixes=('', '_sv')
    )

    # Fix disambiguation: when last name matched multiple Statcast rows,
    # keep only the row where first initials match.
    dup_mask = merged.duplicated(subset=['Batter', 'Game'], keep=False)
    if dup_mask.any():
        init_sv = '_first_init_sv' if '_first_init_sv' in merged.columns else '_first_init'
        keep_mask = (
            ~dup_mask                                          # unique rows: always keep
            | (merged['_first_init'] == merged[init_sv])      # dups: keep initial match
        )
        merged = merged[keep_mask]

    # Final safety dedup
    merged = merged.drop_duplicates(subset=['Batter', 'Game']).reset_index(drop=True)

    # Drop all helper columns
    drop_cols = [c for c in merged.columns if c.startswith('_')]
    merged.drop(columns=drop_cols, inplace=True, errors='ignore')

    # Zero-to-NaN cleanup
    merged = _zero_to_nan(merged)

    return merged

# ─────────────────────────────────────────────────────────────────────────────
# PER-PLAYER PITCH-LEVEL DATA (Player Profile / Deep Dive)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_batter_statcast(player_id: int, days_back: int = 30) -> pd.DataFrame:
    """
    Pitch-level Statcast for a single batter over last N days.
    player_id = MLBAM ID (from mlb_api.build_player_id_map).
    """
    if not _pb_ok():
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
    Summarise rolling quality-of-contact metrics for a single batter.

    Uses pitch-level statcast_batter() data. Requires MLBAM player_id.

    Returns dict with keys:
      avg_ev, max_ev, barrel_pct, hard_hit_pct, avg_la,
      xba, xwoba, sample_size
    """
    df = get_batter_statcast(player_id, days_back)
    if df.empty:
        return {}

    # Filter to batted-ball events (have launch speed)
    bb = df[df['launch_speed'].notna()].copy()
    if bb.empty:
        return {}

    # Hard hit: exit velo ≥ 95 mph (Statcast definition)
    hard_hit_mask = bb['launch_speed'] >= 95

    # Barrel: launch_speed_angle == 6 in Statcast coding
    barrel_mask = pd.Series(False, index=bb.index)
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
        if pd.notna(val):
            metrics['xba'] = round(float(val), 3)

    if 'estimated_woba_using_speedangle' in df.columns:
        val = df['estimated_woba_using_speedangle'].mean()
        if pd.notna(val):
            metrics['xwoba'] = round(float(val), 3)

    return metrics


@st.cache_data(ttl=86400)
def get_savant_player_id(last_name: str, first_name: str) -> int | None:
    """
    Look up MLBAM ID via pybaseball playerid_lookup.
    Returns key_mlbam or None. Prefer mlb_api.build_player_id_map for batch lookups.
    """
    if not _pb_ok():
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
