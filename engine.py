"""
engine.py — Scoring Engine V5.2
==================================
Scoring now incorporates Statcast quality-of-contact metrics as secondary signals.

Architecture:
  BallPark Pal probs  → PRIMARY signal (3,000 simulation projections)
  Statcast metrics    → VALIDATOR/TIEBREAKER (±8 pts max per score)

Statcast weight rationale:
  Conservative-moderate approach: BallPark Pal already bakes in park, weather,
  matchup context. Statcast validates whether the player's contact profile
  physically supports the projection. Max ±8 pts keeps it as a tiebreaker
  rather than an override.

Per-score Statcast logic:
  HR Score:     Barrel% primary (±8 pts) — barrels = HRs
  XB Score:     Barrel% (±5 pts) + HH% (±3 pts) — hard contact = XBH
  Hit Score:    HH% (±4 pts) + xBA vs projection (±2 pts tiebreaker)
  Single Score: Contact quality negative — high barrel REDUCES single score
                (those balls go for XBH/HR/outs, not singles). HH% mild positive.

FIX V5.2: Extracted _gc_signals() helper so compute_game_condition_scores and
           gc_adjusted_score share identical math — no more duplicated weights.
"""

import pandas as pd
import numpy as np
from config import CONFIG
from helpers import normalize_0_100

# ─────────────────────────────────────────────────────────────────────────────
# STATCAST BONUS HELPERS
# ─────────────────────────────────────────────────────────────────────────────

# League average benchmarks for bonus/penalty calculation
_BARREL_AVG  = 7.5   # league avg Barrel%
_HH_AVG      = 38.0  # league avg HardHit%
_MAX_SC_ADJ  = 8.0   # max raw Statcast adjustment before normalize

def _barrel_bonus(barrel_pct: pd.Series, scale: float = 1.0) -> pd.Series:
    """
    Raw bonus based on Barrel% vs league avg.
    scale=1.0 → max ~±8 pts.  scale=0.6 → max ~±5 pts.
    NaN barrel → 0.0 (neutral, no penalty for missing data).
    """
    b = pd.to_numeric(barrel_pct, errors='coerce')
    bonus = ((b - _BARREL_AVG) / 7.0 * _MAX_SC_ADJ * scale)
    return bonus.clip(-_MAX_SC_ADJ * scale, _MAX_SC_ADJ * scale).fillna(0.0)

def _hh_bonus(hh_pct: pd.Series, scale: float = 0.5) -> pd.Series:
    """
    Raw bonus based on HardHit% vs league avg.
    scale=0.5 → max ~±4 pts.
    """
    h = pd.to_numeric(hh_pct, errors='coerce')
    bonus = ((h - _HH_AVG) / 15.0 * _MAX_SC_ADJ * scale)
    return bonus.clip(-_MAX_SC_ADJ * scale, _MAX_SC_ADJ * scale).fillna(0.0)

def _has_statcast(df: pd.DataFrame) -> bool:
    """True if Statcast columns are present and have some non-null values."""
    return ('Barrel%' in df.columns and df['Barrel%'].notna().any()) or \
           ('HH%'     in df.columns and df['HH%'].notna().any())

# ─────────────────────────────────────────────────────────────────────────────
# GAME CONDITION SIGNAL HELPER  ← NEW (eliminates duplication)
# ─────────────────────────────────────────────────────────────────────────────

_GC_COLS = ['gc_hr4', 'gc_hits20', 'gc_k20', 'gc_walks8', 'gc_runs10', 'gc_qs']

def _gc_signals(df: pd.DataFrame, strength: float) -> tuple:
    """
    Compute (hit_combined, hr_combined) GC signals from the six gc_* columns.

    Both compute_game_condition_scores and gc_adjusted_score call this so
    the weights stay in one place. Returns two pd.Series aligned to df.index.
    """
    cfg    = CONFIG
    hits_a = cfg['gc_hits20_anchor']
    k_a    = cfg['gc_k20_anchor']
    runs_a = cfg['gc_runs10_anchor']
    walk_a = cfg['gc_walks8_anchor']
    hr4_a  = cfg['gc_hr4_anchor']
    qs_a   = cfg['gc_qs_anchor']

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
# METRIC COMPUTATION (unchanged from V5.0)
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

    df['vs_mod']    = pd.to_numeric(df['vs Grade'], errors='coerce').fillna(0).clip(-10, 10) / 10
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

    df['Starter'] = pd.to_numeric(df.get('Starter', 0), errors='coerce').fillna(0).astype(int)

    df['total_hit_prob'] = (df['p_1b'] + df['p_xb'] + df['p_hr']).clip(upper=100).round(1)

    xb_boost_park = pd.to_numeric(df['XB Boost'], errors='coerce').fillna(0) \
        if 'XB Boost' in df.columns else pd.Series(0.0, index=df.index)
    xb_boost_base = pd.to_numeric(df['XB Boost (no park)'], errors='coerce').fillna(0) \
        if 'XB Boost (no park)' in df.columns else pd.Series(0.0, index=df.index)
    df['xb_boost'] = (xb_boost_park + xb_boost_base) / 2 if use_park else xb_boost_base

    return df

# ─────────────────────────────────────────────────────────────────────────────
# SCORES (V5.1 — Statcast integrated)
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

    # ── Statcast bonuses (0 when data unavailable — no penalty for missing) ──
    has_sc = _has_statcast(df)
    if has_sc:
        barrel_col = df['Barrel%'] if 'Barrel%' in df.columns else pd.Series(np.nan, index=df.index)
        hh_col     = df['HH%']     if 'HH%'     in df.columns else pd.Series(np.nan, index=df.index)

        # HR: Barrel% is primary (scale=1.0 → ±8 pts), HH% mild support (±2 pts)
        sc_hr     = _barrel_bonus(barrel_col, scale=1.0) + _hh_bonus(hh_col, scale=0.25)
        # XB: Barrel% (±5 pts) + HH% (±3 pts)
        sc_xb     = _barrel_bonus(barrel_col, scale=0.6) + _hh_bonus(hh_col, scale=0.35)
        # Hit: HH% (±4 pts) — hard contact = hits, barrel less relevant for getting on base
        sc_hit    = _hh_bonus(hh_col, scale=0.5)
        # Single: contact hitters have LOW barrel (high barrel = XBH/HR/hard outs)
        sc_single = _hh_bonus(hh_col, scale=0.2) - _barrel_bonus(barrel_col, scale=0.2)
    else:
        sc_hr = sc_xb = sc_hit = sc_single = pd.Series(0.0, index=df.index)

    # ── 🎯 Hit Score ──────────────────────────────────────────────────────────
    hit_raw = (
        df['p_1b']*3.0 + df['p_xb']*2.0 + df['p_hr']*1.0
        - df['p_k']*2.5 - df['p_bb']*1.0
        + vc*1.0 + rc*0.5 + hb + sc_hit
    ) * hit_mult
    df['Hit_Score'] = normalize_0_100(hit_raw)

    # ── 1️⃣ Single Score ────────────────────────────────────────────────────────
    single_raw = (
        df['p_1b']*5.0 - df['p_k']*2.5 - df['p_bb']*1.0
        - df['p_xb']*0.8 - df['p_hr']*0.5
        + vc*0.8 + rc*0.4 + hb + sc_single
    ) * single_mult
    df['Single_Score'] = normalize_0_100(single_raw)

    # ── 🔥 XB Score ────────────────────────────────────────────────────────────
    xb_raw = (
        df['p_xb']*5.0 + df['p_hr']*0.8
        - df['p_k']*1.5 - df['p_bb']*1.0
        + vc*1.2 + rc*0.6 + hb + sc_xb
    ) * xb_mult
    df['XB_Score'] = normalize_0_100(xb_raw)

    # ── 💣 HR Score ────────────────────────────────────────────────────────────
    hr_raw = (
        df['p_hr']*6.0 + df['p_xb']*0.8
        - df['p_k']*0.8 - df['p_bb']*1.0
        + df['xb_boost']*0.03
        + vc*0.5 + rc*0.5 + hb + sc_hr
    ) * hr_mult
    df['HR_Score'] = normalize_0_100(hr_raw)

    # ── Base (no-park) versions for Park Δ ───────────────────────────────────
    df['Hit_Score_base']    = normalize_0_100(
        (df['p_1b_base']*3.0 + df['p_xb_base']*2.0 + df['p_hr_base']*1.0
         - df['p_k_base']*2.5 - df['p_bb_base']*1.0
         + vc*1.0 + rc*0.5 + hb + sc_hit) * hit_mult)

    df['Single_Score_base'] = normalize_0_100(
        (df['p_1b_base']*5.0 - df['p_k_base']*2.5 - df['p_bb_base']*1.0
         - df['p_xb_base']*0.8 - df['p_hr_base']*0.5
         + vc*0.8 + rc*0.4 + hb + sc_single) * single_mult)

    df['XB_Score_base']     = normalize_0_100(
        (df['p_xb_base']*5.0 + df['p_hr_base']*0.8
         - df['p_k_base']*1.5 - df['p_bb_base']*1.0
         + vc*1.2 + rc*0.6 + hb + sc_xb) * xb_mult)

    df['HR_Score_base']     = normalize_0_100(
        (df['p_hr_base']*6.0 + df['p_xb_base']*0.8
         - df['p_k_base']*0.8 - df['p_bb_base']*1.0
         + df['xb_boost']*0.03
         + vc*0.5 + rc*0.5 + hb + sc_hr) * hr_mult)

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

    # ── shared signal computation ─────────────────────────────────────────────
    hit_combined, hr_combined = _gc_signals(df, strength)

    hit_ceiling_mult = (1.0 + hit_combined.clip(
        -CONFIG['gc_hit_max_range'], CONFIG['gc_hit_max_range']))
    hr_ceiling_mult  = (1.0 + hr_combined.clip(
        -CONFIG['gc_hr_max_range'],  CONFIG['gc_hr_max_range']))

    df['Hit_Score_gc']    = normalize_0_100(df['Hit_Score']    * hit_ceiling_mult)
    df['Single_Score_gc'] = normalize_0_100(df['Single_Score'] * hit_ceiling_mult)
    df['XB_Score_gc']     = normalize_0_100(df['XB_Score']     * hit_ceiling_mult)
    df['HR_Score_gc']     = normalize_0_100(df['HR_Score']     * hr_ceiling_mult)

    return df


def gc_adjusted_score(pool: pd.DataFrame, sc: str, use_gc: bool = True) -> pd.Series:
    """
    GC-adjusted score for parlay builder.

    Calls _gc_signals() — same math as compute_game_condition_scores,
    no duplicated weights.
    """
    base_sc = sc.replace('_gc', '')
    gc_col  = base_sc + '_gc'

    # Fast path — already computed
    if gc_col in pool.columns:
        return pool[gc_col]

    if base_sc not in pool.columns:
        return pd.Series(50.0, index=pool.index)

    if not all(c in pool.columns for c in _GC_COLS):
        return pool[base_sc]

    strength = 1.0 if use_gc else CONFIG['gc_reduced_strength']
    hit_combined, hr_combined = _gc_signals(pool, strength)

    if base_sc == 'HR_Score':
        combined = hr_combined
        MAX      = CONFIG['gc_hr_max_range']
    else:
        combined = hit_combined
        MAX      = CONFIG['gc_hit_max_range']

    raw = pool[base_sc] * (1.0 + combined.clip(-MAX, MAX))
    mn, mx = raw.min(), raw.max()
    if mx == mn:
        return pd.Series(50.0, index=pool.index)
    return ((raw - mn) / (mx - mn) * 100).round(1)
