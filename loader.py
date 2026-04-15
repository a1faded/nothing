"""
data/loader.py — BallPark Pal CSV loading
==========================================
All data fetching from GitHub-hosted CSVs.
When BallPark Pal API is ready, swap these functions out here only.

FIX V5.2: Pitcher matching now handles last-name collisions correctly.
  - load_pitcher_data() no longer blindly drop_duplicates on last_name.
    Instead it tags rows whose last name appears more than once as ambiguous.
  - merge_pitcher_data() returns neutral multipliers for ambiguous names
    rather than silently applying the wrong pitcher's stats.
"""

import streamlit as st
import pandas as pd
import numpy as np
import requests
from io import StringIO
from config import CONFIG, PARK_TO_TEAM, NICK_TO_ABBR

# ─────────────────────────────────────────────────────────────────────────────
# BASE FETCHER
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=CONFIG['cache_ttl'])
def _fetch_csv(url: str, label: str):
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return pd.read_csv(StringIO(r.text))
    except Exception as e:
        st.warning(f"⚠️ Could not load {label}: {e}")
        return None

# ─────────────────────────────────────────────────────────────────────────────
# MATCHUPS
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=CONFIG['cache_ttl'])
def load_matchups():
    df = _fetch_csv(CONFIG['matchups_url'], "Matchups")
    if df is None:
        return None

    required = [
        'Game', 'Team', 'Batter', 'Pitcher',
        'HR Prob', 'XB Prob', '1B Prob', 'BB Prob', 'K Prob',
        'HR Prob (no park)', 'XB Prob (no park)', '1B Prob (no park)',
        'BB Prob (no park)', 'K Prob (no park)', 'RC', 'vs Grade'
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error(f"❌ Matchups CSV missing columns: {missing}")
        return None

    for col in ['Team', 'Batter', 'Pitcher', 'Game']:
        df[col] = df[col].astype(str).str.strip()
    return df

# ─────────────────────────────────────────────────────────────────────────────
# PITCHER DATA
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=CONFIG['cache_ttl'])
def load_pitcher_data():
    hits_df  = _fetch_csv(CONFIG['pitcher_hits_url'],  "Pitcher Hits")
    hrs_df   = _fetch_csv(CONFIG['pitcher_hrs_url'],   "Pitcher HRs")
    walks_df = _fetch_csv(CONFIG['pitcher_walks_url'], "Pitcher Walks")

    if hits_df is None and hrs_df is None and walks_df is None:
        return None

    def clean(df, col_name):
        if df is None:
            return pd.DataFrame(columns=['last_name', 'full_name', 'team', 'park', col_name])
        d = df.copy()
        d.columns = [c.strip() for c in d.columns]
        d['prob_val'] = pd.to_numeric(
            d['Prob'].astype(str).str.replace('%', '', regex=False).str.strip(),
            errors='coerce'
        ).fillna(0)
        d['last_name'] = d['Name'].astype(str).str.split().str[-1]
        d['full_name'] = d['Name'].astype(str).str.strip()
        d['team']      = d['Team'].astype(str).str.strip()
        d['park']      = d['Park'].astype(str).str.strip() if 'Park' in d.columns else ''
        return d[['last_name', 'full_name', 'team', 'park', 'prob_val']].rename(
            columns={'prob_val': col_name})

    hits_c  = clean(hits_df,  'hit8_prob')
    hrs_c   = clean(hrs_df,   'hr2_prob')
    walks_c = clean(walks_df, 'walk3_prob')

    merged = hits_c.merge(hrs_c,   on=['last_name', 'full_name', 'team', 'park'], how='outer')
    merged = merged.merge(walks_c, on=['last_name', 'full_name', 'team', 'park'], how='outer')

    merged['hit8_prob']  = merged['hit8_prob'].fillna(CONFIG['pitcher_hit_neutral'])
    merged['hr2_prob']   = merged['hr2_prob'].fillna(CONFIG['pitcher_hr_neutral'])
    merged['walk3_prob'] = merged['walk3_prob'].fillna(CONFIG['pitcher_walk_neutral'])

    M = CONFIG['pitcher_max_mult']
    merged['pitch_hit_mult']  = (1.0 + np.clip(
        (merged['hit8_prob']  - CONFIG['pitcher_hit_neutral'])  / 4.0  * M, -M, M)).round(4)
    merged['pitch_hr_mult']   = (1.0 + np.clip(
        (merged['hr2_prob']   - CONFIG['pitcher_hr_neutral'])   / 8.0  * M, -M, M)).round(4)
    merged['pitch_walk_pen']  = (0.0 - np.clip(
        (merged['walk3_prob'] - CONFIG['pitcher_walk_neutral']) / 10.0 * (M * 0.5),
        -(M * 0.5), (M * 0.5))).round(4)

    composite = merged['pitch_hit_mult'] + merged['pitch_walk_pen']
    merged['pitch_grade'] = np.select(
        [composite >= 1.04, composite >= 1.01, composite >= 0.98, composite >= 0.95],
        ['A+', 'A', 'B', 'C'], default='D'
    )

    # ── FIX: tag ambiguous last names instead of silently dropping one ────────
    name_counts = merged['last_name'].value_counts()
    merged['_ambiguous'] = merged['last_name'].map(name_counts) > 1

    # Drop full-name exact duplicates (same pitcher listed twice), but keep
    # rows where two *different* pitchers share a last name.
    merged = merged.drop_duplicates(subset='full_name').reset_index(drop=True)

    return merged


def merge_pitcher_data(df: pd.DataFrame, pitcher_df) -> pd.DataFrame:
    """
    Join pitcher multipliers onto the slate DataFrame.

    Ambiguous last names (two different pitchers share the same last name)
    → neutral multipliers rather than silently using the wrong pitcher's data.
    """
    neutral = {
        'pitch_hit_mult':  1.0,
        'pitch_hr_mult':   1.0,
        'pitch_walk_pen':  0.0,
        'pitch_grade':     'B',
        'hit8_prob':       CONFIG['pitcher_hit_neutral'],
        'hr2_prob':        CONFIG['pitcher_hr_neutral'],
        'walk3_prob':      CONFIG['pitcher_walk_neutral'],
    }

    if pitcher_df is None or pitcher_df.empty:
        for col, val in neutral.items():
            df[col] = val
        return df

    # Build lookup dicts — one entry per last_name only when unambiguous
    unambiguous = pitcher_df[~pitcher_df['_ambiguous']]
    pm = unambiguous.set_index('last_name')

    # Set of ambiguous last names so we can return neutral for them
    ambiguous_names = set(pitcher_df.loc[pitcher_df['_ambiguous'], 'last_name'])

    def _g(pitcher_last, col, default):
        if pitcher_last in ambiguous_names:
            return default   # two pitchers with same last name — can't tell which
        return pm.at[pitcher_last, col] if pitcher_last in pm.index else default

    df['pitch_hit_mult']  = df['Pitcher'].apply(lambda p: _g(p, 'pitch_hit_mult',  neutral['pitch_hit_mult']))
    df['pitch_hr_mult']   = df['Pitcher'].apply(lambda p: _g(p, 'pitch_hr_mult',   neutral['pitch_hr_mult']))
    df['pitch_walk_pen']  = df['Pitcher'].apply(lambda p: _g(p, 'pitch_walk_pen',  neutral['pitch_walk_pen']))
    df['pitch_grade']     = df['Pitcher'].apply(lambda p: _g(p, 'pitch_grade',     neutral['pitch_grade']))
    df['hit8_prob']       = df['Pitcher'].apply(lambda p: _g(p, 'hit8_prob',       neutral['hit8_prob']))
    df['hr2_prob']        = df['Pitcher'].apply(lambda p: _g(p, 'hr2_prob',        neutral['hr2_prob']))
    df['walk3_prob']      = df['Pitcher'].apply(lambda p: _g(p, 'walk3_prob',      neutral['walk3_prob']))

    return df

# ─────────────────────────────────────────────────────────────────────────────
# GAME CONDITIONS
# ─────────────────────────────────────────────────────────────────────────────

def _clean_prob_col(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace('%', '', regex=False).str.strip(),
        errors='coerce'
    ).fillna(0)


@st.cache_data(ttl=CONFIG['cache_ttl'])
def load_game_conditions():
    files = {
        'hr4_prob':   CONFIG['game_4hr_url'],
        'hits20_prob':CONFIG['game_20hits_url'],
        'k20_prob':   CONFIG['game_20k_url'],
        'walks8_prob':CONFIG['game_8walks_url'],
        'runs10_prob':CONFIG['game_10runs_url'],
    }

    frames = {}
    for col_name, url in files.items():
        df = _fetch_csv(url, col_name)
        if df is not None and 'Park' in df.columns and 'Prob' in df.columns:
            df = df.copy()
            df['home_team'] = df['Park'].astype(str).str.strip().map(PARK_TO_TEAM)
            df[col_name]    = _clean_prob_col(df['Prob'])
            frames[col_name] = df[['home_team', col_name]].dropna(subset=['home_team'])

    if not frames:
        return None

    merged = None
    for col_name, frame in frames.items():
        merged = frame if merged is None else merged.merge(frame, on='home_team', how='outer')

    defaults = {
        'hr4_prob':   CONFIG['gc_hr4_anchor'],
        'hits20_prob':CONFIG['gc_hits20_anchor'],
        'k20_prob':   CONFIG['gc_k20_anchor'],
        'walks8_prob':CONFIG['gc_walks8_anchor'],
        'runs10_prob':CONFIG['gc_runs10_anchor'],
    }
    for col, default in defaults.items():
        if col in merged.columns:
            merged[col] = merged[col].fillna(default)
        else:
            merged[col] = default

    return merged.reset_index(drop=True)


@st.cache_data(ttl=CONFIG['cache_ttl'])
def load_pitcher_qs():
    df = _fetch_csv(CONFIG['pitcher_qs_url'], "Pitcher QS")
    if df is None:
        return None
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    if 'Prob' not in df.columns or 'Name' not in df.columns:
        return None
    df['qs_prob']   = _clean_prob_col(df['Prob'])
    df['last_name'] = df['Name'].astype(str).str.split().str[-1]
    df['home_team'] = df['Park'].astype(str).str.strip() if 'Park' in df.columns else ''
    return df[['last_name', 'home_team', 'qs_prob']].reset_index(drop=True)


def merge_game_conditions(df: pd.DataFrame, game_cond, pitcher_qs) -> pd.DataFrame:
    df = df.copy()
    df['_home_nick'] = df['Game'].astype(str).str.split(' @ ').str[-1].str.strip()
    df['_home_abbr'] = df['_home_nick'].map(NICK_TO_ABBR).fillna('')

    defaults = {
        'gc_hr4':    CONFIG['gc_hr4_anchor'],
        'gc_hits20': CONFIG['gc_hits20_anchor'],
        'gc_k20':    CONFIG['gc_k20_anchor'],
        'gc_walks8': CONFIG['gc_walks8_anchor'],
        'gc_runs10': CONFIG['gc_runs10_anchor'],
    }
    for col, default in defaults.items():
        df[col] = default

    if game_cond is not None and not game_cond.empty:
        gmap = game_cond.set_index('home_team')
        col_map = {
            'hr4_prob':   'gc_hr4',
            'hits20_prob':'gc_hits20',
            'k20_prob':   'gc_k20',
            'walks8_prob':'gc_walks8',
            'runs10_prob':'gc_runs10',
        }
        for src_col, dst_col in col_map.items():
            if src_col in gmap.columns:
                df[dst_col] = df['_home_abbr'].map(gmap[src_col]).fillna(defaults[dst_col])

    df['gc_qs'] = CONFIG['gc_qs_anchor']
    if pitcher_qs is not None and not pitcher_qs.empty:
        qs_map    = pitcher_qs.set_index('last_name')['qs_prob']
        df['gc_qs'] = df['Pitcher'].map(qs_map).fillna(CONFIG['gc_qs_anchor'])

    df.drop(columns=['_home_nick', '_home_abbr'], inplace=True, errors='ignore')
    return df
