"""
engine.py — Scoring Engine V5.5
==================================

All six formula improvements applied:

1. XB Score  — BB penalty reduced (0.3), K lightened (1.0)
               Power/selective hitters shouldn't be penalised for walks on XB targets.
2. Single Score — XB/HR penalty weights flipped: HR now penalises more (-0.8)
               than XB (-0.5). A pure HR swing profile is the furthest from a singles
               contact profile.
3. hist_bonus zero-hit trigger — raised from PA≥3 → PA≥8.
               Three PA is too small a sample to meaningfully penalise a batter.
4. pitcher_max_mult — raised to 0.08 in config.py.
               Pitcher is one of the two biggest variables — 5% was too conservative.
5. RC (run creation) weight — reduced across scores (0.5→0.2 Hit/Single, kept
               moderate for XB/HR where park environment is more directly relevant).
               RC is a park/environment metric already baked into p_* probabilities.
               Over-weighting it double-counts park advantage.
6. Single Score Statcast xBA — reduced from +3 → +1.5.
               xBA is driven by all batted ball events including barrels, making it
               a poor signal for the singles-specific contact profile.

Architecture (unchanged from V5.4):
  STAGE 1: BallPark Pal raw signal → normalize_0_100
  STAGE 2: Statcast quality-of-contact overlay (post-normalization, ±10 pts max)
"""

import pandas as pd
import numpy as np
from config import CONFIG
from helpers import normalize_0_100

_GC_COLS = ['gc_hr4', 'gc_hits20', 'gc_k20', 'gc_walks8', 'gc_runs10', 'gc_qs']


def _sc_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return pd.to_numeric(df[col], errors='coerce')


def _has_statcast(df: pd.DataFrame) -> bool:
    return any(col in df.columns and df[col].notna().any()
               for col in ['Barrel%', 'HH%', 'AvgEV', 'xBA', 'xSLG'])


# ─────────────────────────────────────────────────────────────────────────────
# STATCAST OVERLAY
# ─────────────────────────────────────────────────────────────────────────────

def _adj(series: pd.Series, avg: float, spread: float,
         pts: float, negate: bool = False) -> pd.Series:
    """Linear deviation from league avg, clipped to ±pts. NaN → 0 (neutral)."""
    raw = (series - avg) / spread * pts
    if negate:
        raw = -raw
    return raw.clip(-abs(pts), abs(pts)).fillna(0.0)


def _compute_statcast_adj(df: pd.DataFrame, score_type: str) -> pd.Series:
    cfg    = CONFIG
    MAX    = cfg['sc_max_total_adj']
    barrel = _sc_series(df, 'Barrel%')
    hh     = _sc_series(df, 'HH%')
    avgev  = _sc_series(df, 'AvgEV')
    maxev  = _sc_series(df, 'maxEV')
    xslg   = _sc_series(df, 'xSLG')
    xba    = _sc_series(df, 'xBA')
    xwoba  = _sc_series(df, 'xwOBA')
    B, HH, EV, MX = cfg['league_barrel_pct'], cfg['league_hh_pct'], cfg['league_avgev'], cfg['league_maxev']
    SL, BA, WO    = cfg['league_xslg'], cfg['league_xba'], cfg['league_xwoba']

    if score_type == 'HR':
        total = (
            _adj(barrel, B,  7.5,  6.0)
          + _adj(xslg,   SL, 0.15, 4.0)
          + _adj(maxev,  MX, 7.0,  3.0)
          + _adj(hh,     HH, 12.0, 2.0)
          + _adj(avgev,  EV, 5.5,  1.5)
        )
    elif score_type == 'XB':
        total = (
            _adj(hh,     HH, 12.0, 5.0)
          + _adj(xslg,   SL, 0.12, 4.0)
          + _adj(barrel, B,  7.5,  3.0)
          + _adj(avgev,  EV, 5.5,  2.5)
          + _adj(xba,    BA, 0.062,1.5)
        )
    elif score_type == 'Hit':
        total = (
            _adj(xba,   BA, 0.062, 6.0)
          + _adj(hh,    HH, 12.0,  3.0)
          + _adj(xwoba, WO, 0.080, 2.0)
          + _adj(avgev, EV, 5.5,   1.5)
        )
    elif score_type == 'Single':
        total = (
            _adj(xba,    BA, 0.062, 1.5)           # FIX 6: reduced from 3.0→1.5
          + _adj(hh,     HH, 12.0,  2.0)
          + _adj(barrel, B,  7.5,   4.0, negate=True)
          + _adj(xslg,   SL, 0.150, 3.0, negate=True)
          + _adj(maxev,  MX, 7.0,   1.5, negate=True)
        )
    else:
        return pd.Series(0.0, index=df.index)

    return total.clip(-MAX, MAX).fillna(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# GC SIGNAL HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _gc_signals(df: pd.DataFrame, strength: float) -> tuple:
    cfg    = CONFIG
    hits_a = cfg['gc_hits20_anchor'];  k_a    = cfg['gc_k20_anchor']
    runs_a = cfg['gc_runs10_anchor'];  walk_a = cfg['gc_walks8_anchor']
    hr4_a  = cfg['gc_hr4_anchor'];     qs_a   = cfg['gc_qs_anchor']

    hit_combined = (
        (df['gc_hits20'] - hits_a) / 15.0 * 1.8
      - (df['gc_k20']   - k_a   ) / 20.0 * 1.5
      + (df['gc_runs10']- runs_a ) / 20.0 * 1.0
      - (df['gc_walks8']- walk_a ) / 15.0 * 0.8
      - (df['gc_qs']    - qs_a   ) / 20.0 * 1.0
    ) * strength

    hr_combined = (
        (df['gc_hr4']   - hr4_a  ) / 15.0 * 1.8
      - (df['gc_k20']   - k_a   ) / 20.0 * 1.2
      + (df['gc_runs10']- runs_a ) / 20.0 * 0.8
      - (df['gc_walks8']- walk_a ) / 15.0 * 0.8
      - (df['gc_qs']    - qs_a   ) / 20.0 * 0.8
    ) * strength

    return hit_combined, hr_combined


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1 — METRICS
# ─────────────────────────────────────────────────────────────────────────────

def compute_metrics(df: pd.DataFrame, use_park: bool) -> pd.DataFrame:
    df = df.copy()

    for s in ['HR', 'XB', '1B', 'BB', 'K']:
        pk = f'{s} Prob';  pb = f'{s} Prob (no park)'
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

    zero_hit_penalty = np.where(
        (df['PA'] >= 8) & (df['H'] == 0),   # FIX 3: raised from 3 → 8 PA
        -np.clip(df['PA'] / 10.0 * 5.0, 1.5, 5.0),
        0.0
    )
    pos_bonus = np.where(
        (df['PA'] >= CONFIG['hist_min_pa']) & (df['H'] > 0),
        (df['AVG'] * CONFIG['hist_bonus_max']).round(3),
        0.0
    )
    df['hist_bonus'] = (zero_hit_penalty + pos_bonus).round(3)

    df['Starter'] = pd.to_numeric(df.get('Starter', 0), errors='coerce').fillna(0).astype(int)
    df['total_hit_prob'] = (df['p_1b'] + df['p_xb'] + df['p_hr']).clip(upper=100).round(1)

    xb_boost_park = pd.to_numeric(df['XB Boost'], errors='coerce').fillna(0) \
        if 'XB Boost' in df.columns else pd.Series(0.0, index=df.index)
    xb_boost_base = pd.to_numeric(df['XB Boost (no park)'], errors='coerce').fillna(0) \
        if 'XB Boost (no park)' in df.columns else pd.Series(0.0, index=df.index)
    df['xb_boost'] = (xb_boost_park + xb_boost_base) / 2 if use_park else xb_boost_base

    return df


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2 — SCORES
# ─────────────────────────────────────────────────────────────────────────────

def compute_scores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    vc = df['vs_contrib']
    rc = df['rc_contrib']
    hb = df['hist_bonus']

    hit_mult    = (df['pitch_hit_mult'] + df['pitch_walk_pen']).clip(0.90, 1.10)
    xb_mult     = ((df['pitch_hit_mult'] + df['pitch_hr_mult']) / 2 + df['pitch_walk_pen']).clip(0.90, 1.10)
    hr_mult     = (df['pitch_hr_mult']  + df['pitch_walk_pen']).clip(0.90, 1.10)
    single_mult = (df['pitch_hit_mult'] + df['pitch_walk_pen']).clip(0.90, 1.10)

    # ── 🎯 Hit Score ──────────────────────────────────────────────────────────
    # rc weight: 0.5 → 0.2 (FIX 5: RC double-counts park already in p_* probs)
    hit_raw = (
        df['p_1b']*3.0 + df['p_xb']*2.0 + df['p_hr']*1.0
        - df['p_k']*2.5 - df['p_bb']*1.0
        + vc*1.0 + rc*0.2 + hb
    ) * hit_mult
    df['Hit_Score'] = normalize_0_100(hit_raw)

    # ── 1️⃣ Single Score ────────────────────────────────────────────────────────
    # FIX 2: flipped XB/HR penalty weights. HR penalty (-0.8) > XB penalty (-0.5)
    #        because an HR swing profile is more opposite to a singles profile.
    # FIX 5: rc weight 0.4 → 0.2
    single_raw = (
        df['p_1b']*5.0 - df['p_k']*2.5 - df['p_bb']*1.0
        - df['p_xb']*0.5 - df['p_hr']*0.8    # FIX 2: flipped from (0.8, 0.5)
        + vc*0.8 + rc*0.2 + hb
    ) * single_mult
    df['Single_Score'] = normalize_0_100(single_raw)

    # ── 🔥 XB Score ────────────────────────────────────────────────────────────
    # FIX 1: BB reduced 1.0→0.3, K reduced 1.5→1.0
    #        Power/selective hitters walk a lot — IBB included → near neutral.
    #        K still penalised (contact required for doubles/triples) but lightened.
    # FIX 5: rc weight 0.6 → 0.4 (keep moderate — park matters more for XBH)
    xb_raw = (
        df['p_xb']*5.0 + df['p_hr']*0.8
        - df['p_k']*1.0 - df['p_bb']*0.3     # FIX 1
        + vc*1.2 + rc*0.4 + hb
    ) * xb_mult
    df['XB_Score'] = normalize_0_100(xb_raw)

    # ── 💣 HR Score ────────────────────────────────────────────────────────────
    # K near-neutral (0.15): power swingers K a lot — high K ≠ bad HR target.
    # BB removed (0): p_bb includes IBB (pitcher avoids matchup) — signals cancel.
    # FIX 5: rc weight 0.5 → 0.35 (park still relevant for HR, modest reduction)
    hr_raw = (
        df['p_hr']*6.0 + df['p_xb']*0.8
        - df['p_k']*0.15
        + df['xb_boost']*0.03
        + vc*0.5 + rc*0.35 + hb
    ) * hr_mult
    df['HR_Score'] = normalize_0_100(hr_raw)

    # ── Base (no-park) versions ────────────────────────────────────────────────
    df['Hit_Score_base'] = normalize_0_100(
        (df['p_1b_base']*3.0 + df['p_xb_base']*2.0 + df['p_hr_base']*1.0
         - df['p_k_base']*2.5 - df['p_bb_base']*1.0
         + vc*1.0 + rc*0.2 + hb) * hit_mult)

    df['Single_Score_base'] = normalize_0_100(
        (df['p_1b_base']*5.0 - df['p_k_base']*2.5 - df['p_bb_base']*1.0
         - df['p_xb_base']*0.5 - df['p_hr_base']*0.8
         + vc*0.8 + rc*0.2 + hb) * single_mult)

    df['XB_Score_base'] = normalize_0_100(
        (df['p_xb_base']*5.0 + df['p_hr_base']*0.8
         - df['p_k_base']*1.0 - df['p_bb_base']*0.3
         + vc*1.2 + rc*0.4 + hb) * xb_mult)

    df['HR_Score_base'] = normalize_0_100(
        (df['p_hr_base']*6.0 + df['p_xb_base']*0.8
         - df['p_k_base']*0.15
         + df['xb_boost']*0.03
         + vc*0.5 + rc*0.35 + hb) * hr_mult)

    # ── Statcast post-normalization overlay ────────────────────────────────────
    if _has_statcast(df):
        for score_type, score_col, base_col in [
            ('HR',     'HR_Score',     'HR_Score_base'),
            ('XB',     'XB_Score',     'XB_Score_base'),
            ('Hit',    'Hit_Score',    'Hit_Score_base'),
            ('Single', 'Single_Score', 'Single_Score_base'),
        ]:
            adj = _compute_statcast_adj(df, score_type)
            df[score_col] = (df[score_col] + adj).clip(0, 100).round(1)
            df[base_col]  = (df[base_col]  + adj).clip(0, 100).round(1)

    return df


# ─────────────────────────────────────────────────────────────────────────────
# GAME CONDITION SCORES
# ─────────────────────────────────────────────────────────────────────────────

def compute_game_condition_scores(df: pd.DataFrame, use_gc: bool = True) -> pd.DataFrame:
    df = df.copy()
    has_gc = all(c in df.columns for c in _GC_COLS)
    if not has_gc:
        for sc in ['Hit_Score', 'Single_Score', 'XB_Score', 'HR_Score']:
            df[sc + '_gc'] = df[sc]
        return df

    strength = 1.0 if use_gc else CONFIG['gc_reduced_strength']
    hit_combined, hr_combined = _gc_signals(df, strength)

    hit_mult = 1.0 + hit_combined.clip(-CONFIG['gc_hit_max_range'], CONFIG['gc_hit_max_range'])
    hr_mult  = 1.0 + hr_combined.clip(-CONFIG['gc_hr_max_range'],  CONFIG['gc_hr_max_range'])

    df['Hit_Score_gc']    = normalize_0_100(df['Hit_Score']    * hit_mult)
    df['Single_Score_gc'] = normalize_0_100(df['Single_Score'] * hit_mult)
    df['XB_Score_gc']     = normalize_0_100(df['XB_Score']     * hit_mult)
    df['HR_Score_gc']     = normalize_0_100(df['HR_Score']     * hr_mult)
    return df


def gc_adjusted_score(pool: pd.DataFrame, sc: str, use_gc: bool = True) -> pd.Series:
    base_sc = sc.replace('_gc', '')
    gc_col  = base_sc + '_gc'
    if gc_col in pool.columns:
        return pool[gc_col]
    if base_sc not in pool.columns:
        return pd.Series(50.0, index=pool.index)
    if not all(c in pool.columns for c in _GC_COLS):
        return pool[base_sc]

    strength = 1.0 if use_gc else CONFIG['gc_reduced_strength']
    hit_combined, hr_combined = _gc_signals(pool, strength)
    combined = hr_combined if base_sc == 'HR_Score' else hit_combined
    MAX      = CONFIG['gc_hr_max_range'] if base_sc == 'HR_Score' else CONFIG['gc_hit_max_range']
    raw      = pool[base_sc] * (1.0 + combined.clip(-MAX, MAX))
    mn, mx   = raw.min(), raw.max()
    if mx == mn:
        return pd.Series(50.0, index=pool.index)
    return ((raw - mn) / (mx - mn) * 100).round(1)
