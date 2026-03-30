"""
scoring/engine.py — Scoring Engine
====================================
compute_metrics, compute_scores, compute_game_condition_scores
All pure DataFrame → DataFrame transforms. No Streamlit calls here.
"""

import pandas as pd
import numpy as np
from config import CONFIG
from utils.helpers import normalize_0_100


# ─────────────────────────────────────────────────────────────────────────────
# METRIC COMPUTATION
# ─────────────────────────────────────────────────────────────────────────────

def compute_metrics(df: pd.DataFrame, use_park: bool) -> pd.DataFrame:
    df = df.copy()
    for s in ['HR', 'XB', '1B', 'BB', 'K']:
        pk = f'{s} Prob'
        pb = f'{s} Prob (no park)'
        df[f'p_{s.lower()}_park'] = pd.to_numeric(df[pk], errors='coerce').fillna(0)
        df[f'p_{s.lower()}_base'] = pd.to_numeric(df[pb], errors='coerce').fillna(0)
        df[f'p_{s.lower()}'] = (
            (df[f'p_{s.lower()}_park'] + df[f'p_{s.lower()}_base']) / 2
            if use_park else df[f'p_{s.lower()}_base']
        )

    df['vs_mod']     = pd.to_numeric(df['vs Grade'], errors='coerce').fillna(0).clip(-10, 10) / 10
    df['vs_contrib'] = df['vs_mod'] * 2.0

    rc_col = 'RC' if use_park else 'RC (no park)'
    if rc_col not in df.columns:
        rc_col = 'RC'
    df['rc_norm'] = pd.to_numeric(df[rc_col], errors='coerce').fillna(0)
    rc_min, rc_max = df['rc_norm'].min(), df['rc_norm'].max()
    df['rc_contrib'] = (
        ((df['rc_norm'] - rc_min) / (rc_max - rc_min) * 2 - 1)
        if rc_max > rc_min else pd.Series(0.0, index=df.index)
    )

    df['PA']  = pd.to_numeric(df['PA'],  errors='coerce').fillna(0)
    df['H']   = pd.to_numeric(df['H'],   errors='coerce').fillna(0)
    df['AVG'] = pd.to_numeric(df['AVG'], errors='coerce').fillna(0)

    # Historical matchup adjustment
    zero_hit_penalty = np.where(
        (df['PA'] >= 3) & (df['H'] == 0),
        -np.clip(df['PA'] / 10.0 * 5.0, 1.5, 5.0),
        0.0
    )
    pos_bonus = np.where(
        (df['PA'] >= CONFIG['hist_min_pa']) & (df['H'] > 0),
        (df['AVG'] * CONFIG['hist_bonus_max']).round(3),
        0.0
    )
    df['hist_bonus'] = (zero_hit_penalty + pos_bonus).round(3)
    df['Starter']        = pd.to_numeric(df.get('Starter', 0), errors='coerce').fillna(0).astype(int)
    df['total_hit_prob'] = (df['p_1b'] + df['p_xb'] + df['p_hr']).clip(upper=100).round(1)

    xb_boost_park = pd.to_numeric(df['XB Boost'],           errors='coerce').fillna(0) \
                    if 'XB Boost' in df.columns else pd.Series(0.0, index=df.index)
    xb_boost_base = pd.to_numeric(df['XB Boost (no park)'], errors='coerce').fillna(0) \
                    if 'XB Boost (no park)' in df.columns else pd.Series(0.0, index=df.index)
    df['xb_boost'] = (xb_boost_park + xb_boost_base) / 2 if use_park else xb_boost_base

    return df


# ─────────────────────────────────────────────────────────────────────────────
# SCORES
# ─────────────────────────────────────────────────────────────────────────────

def compute_scores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    vc = df['vs_contrib']
    rc = df['rc_contrib']
    hb = df['hist_bonus']

    hit_mult    = (df['pitch_hit_mult']  + df['pitch_walk_pen']).clip(0.90, 1.10)
    xb_mult     = ((df['pitch_hit_mult'] + df['pitch_hr_mult']) / 2 + df['pitch_walk_pen']).clip(0.90, 1.10)
    hr_mult     = (df['pitch_hr_mult']   + df['pitch_walk_pen']).clip(0.90, 1.10)
    single_mult = (df['pitch_hit_mult']  + df['pitch_walk_pen']).clip(0.90, 1.10)

    hit_raw    = (df['p_1b']*3.0 + df['p_xb']*2.0 + df['p_hr']*1.0 - df['p_k']*2.5 - df['p_bb']*1.0 + vc*1.0 + rc*0.5 + hb) * hit_mult
    df['Hit_Score'] = normalize_0_100(hit_raw)

    single_raw = (df['p_1b']*5.0 - df['p_k']*2.5 - df['p_bb']*1.0 - df['p_xb']*0.8 - df['p_hr']*0.5 + vc*0.8 + rc*0.4 + hb) * single_mult
    df['Single_Score'] = normalize_0_100(single_raw)

    xb_raw     = (df['p_xb']*5.0 + df['p_hr']*0.8 - df['p_k']*1.5 - df['p_bb']*1.0 + vc*1.2 + rc*0.6 + hb) * xb_mult
    df['XB_Score'] = normalize_0_100(xb_raw)

    hr_raw     = (df['p_hr']*6.0 + df['p_xb']*0.8 - df['p_k']*0.8 - df['p_bb']*1.0 + df['xb_boost']*0.03 + vc*0.5 + rc*0.5 + hb) * hr_mult
    df['HR_Score'] = normalize_0_100(hr_raw)

    # Base (no-park) versions for Park Δ
    df['Hit_Score_base']    = normalize_0_100((df['p_1b_base']*3.0 + df['p_xb_base']*2.0 + df['p_hr_base']*1.0 - df['p_k_base']*2.5 - df['p_bb_base']*1.0 + vc*1.0 + rc*0.5 + hb) * hit_mult)
    df['Single_Score_base'] = normalize_0_100((df['p_1b_base']*5.0 - df['p_k_base']*2.5 - df['p_bb_base']*1.0 - df['p_xb_base']*0.8 - df['p_hr_base']*0.5 + vc*0.8 + rc*0.4 + hb) * single_mult)
    df['XB_Score_base']     = normalize_0_100((df['p_xb_base']*5.0 + df['p_hr_base']*0.8 - df['p_k_base']*1.5 - df['p_bb_base']*1.0 + vc*1.2 + rc*0.6 + hb) * xb_mult)
    df['HR_Score_base']     = normalize_0_100((df['p_hr_base']*6.0 + df['p_xb_base']*0.8 - df['p_k_base']*0.8 - df['p_bb_base']*1.0 + df['xb_boost']*0.03 + vc*0.5 + rc*0.5 + hb) * hr_mult)

    return df


# ─────────────────────────────────────────────────────────────────────────────
# GAME CONDITION SCORES
# ─────────────────────────────────────────────────────────────────────────────

def compute_game_condition_scores(df: pd.DataFrame, use_gc: bool = True) -> pd.DataFrame:
    df = df.copy()
    gc_cols = ['gc_hr4', 'gc_hits20', 'gc_k20', 'gc_walks8', 'gc_runs10', 'gc_qs']
    has_gc  = all(c in df.columns for c in gc_cols)

    if not has_gc:
        for sc in ['Hit_Score', 'Single_Score', 'XB_Score', 'HR_Score']:
            df[sc + '_gc'] = df[sc]
        return df

    strength = 1.0 if use_gc else CONFIG['gc_reduced_strength']

    hits_a = CONFIG['gc_hits20_anchor']
    k_a    = CONFIG['gc_k20_anchor']
    runs_a = CONFIG['gc_runs10_anchor']
    walk_a = CONFIG['gc_walks8_anchor']
    hr4_a  = CONFIG['gc_hr4_anchor']
    qs_a   = CONFIG['gc_qs_anchor']

    # Hit / Single / XB ceiling signals
    hits_sig = (df['gc_hits20'] - hits_a) / 15.0 * 1.8
    k_sig    = -(df['gc_k20']   - k_a)   / 20.0 * 1.5
    runs_sig = (df['gc_runs10'] - runs_a) / 20.0 * 1.0
    walk_sig = -(df['gc_walks8']- walk_a) / 15.0 * 0.8
    qs_sig   = -(df['gc_qs']    - qs_a)  / 20.0 * 1.0

    hit_combined     = (hits_sig + k_sig + runs_sig + walk_sig + qs_sig) * strength
    HIT_MAX          = CONFIG['gc_hit_max_range']
    hit_ceiling_mult = (1.0 + hit_combined.clip(-HIT_MAX, HIT_MAX))

    df['Hit_Score_gc']    = normalize_0_100(df['Hit_Score']    * hit_ceiling_mult)
    df['Single_Score_gc'] = normalize_0_100(df['Single_Score'] * hit_ceiling_mult)
    df['XB_Score_gc']     = normalize_0_100(df['XB_Score']     * hit_ceiling_mult)

    # HR ceiling signals
    hr4_sig   = (df['gc_hr4']    - hr4_a) / 15.0 * 1.8
    hr_k_sig  = -(df['gc_k20']  - k_a)   / 20.0 * 1.2
    hr_r_sig  = (df['gc_runs10']- runs_a) / 20.0 * 0.8
    hr_w_sig  = -(df['gc_walks8']-walk_a) / 15.0 * 0.8
    hr_qs_sig = -(df['gc_qs']   - qs_a)  / 20.0 * 0.8

    hr_combined     = (hr4_sig + hr_k_sig + hr_r_sig + hr_w_sig + hr_qs_sig) * strength
    HR_MAX          = CONFIG['gc_hr_max_range']
    hr_ceiling_mult = (1.0 + hr_combined.clip(-HR_MAX, HR_MAX))

    df['HR_Score_gc'] = normalize_0_100(df['HR_Score'] * hr_ceiling_mult)

    return df


# ─────────────────────────────────────────────────────────────────────────────
# GC ADJUSTED SCORE (used by parlay builder)
# ─────────────────────────────────────────────────────────────────────────────

def gc_adjusted_score(pool: pd.DataFrame, sc: str, use_gc: bool = True) -> pd.Series:
    """
    Return game-conditions-adjusted score Series for a given score column.
    Uses same ceiling architecture as compute_game_condition_scores.
    If pool already has *_gc columns, returns those directly.
    """
    base_sc = sc.replace('_gc', '')
    gc_col  = base_sc + '_gc'

    if gc_col in pool.columns:
        return pool[gc_col]

    if base_sc not in pool.columns:
        return pd.Series(50.0, index=pool.index)

    gc_cols = ['gc_hr4', 'gc_hits20', 'gc_k20', 'gc_walks8', 'gc_runs10', 'gc_qs']
    if not all(c in pool.columns for c in gc_cols):
        return pool[base_sc]

    strength = 1.0 if use_gc else CONFIG['gc_reduced_strength']
    hits_a   = CONFIG['gc_hits20_anchor']
    k_a      = CONFIG['gc_k20_anchor']
    runs_a   = CONFIG['gc_runs10_anchor']
    walk_a   = CONFIG['gc_walks8_anchor']
    hr4_a    = CONFIG['gc_hr4_anchor']
    qs_a     = CONFIG['gc_qs_anchor']

    if base_sc == 'HR_Score':
        hr4_sig  = (pool['gc_hr4']    - hr4_a) / 15.0 * 1.8
        k_sig    = -(pool['gc_k20']   - k_a)   / 20.0 * 1.2
        runs_sig = (pool['gc_runs10'] - runs_a) / 20.0 * 0.8
        walk_sig = -(pool['gc_walks8']- walk_a) / 15.0 * 0.8
        qs_sig   = -(pool['gc_qs']    - qs_a)  / 20.0 * 0.8
        combined = (hr4_sig + k_sig + runs_sig + walk_sig + qs_sig) * strength
        MAX      = CONFIG['gc_hr_max_range']
    else:
        hits_sig = (pool['gc_hits20'] - hits_a) / 15.0 * 1.8
        k_sig    = -(pool['gc_k20']   - k_a)   / 20.0 * 1.5
        runs_sig = (pool['gc_runs10'] - runs_a) / 20.0 * 1.0
        walk_sig = -(pool['gc_walks8']- walk_a) / 15.0 * 0.8
        qs_sig   = -(pool['gc_qs']    - qs_a)  / 20.0 * 1.0
        combined = (hits_sig + k_sig + runs_sig + walk_sig + qs_sig) * strength
        MAX      = CONFIG['gc_hit_max_range']

    ceiling_mult = (1.0 + combined.clip(-MAX, MAX))
    raw  = pool[base_sc] * ceiling_mult
    mn, mx = raw.min(), raw.max()
    if mx == mn:
        return pd.Series(50.0, index=pool.index)
    return ((raw - mn) / (mx - mn) * 100).round(1)
