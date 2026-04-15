"""
engine.py — Scoring Engine V5.3
==================================

V5.3 architecture — clean two-stage scoring:

STAGE 1: BallPark Pal raw signal (PRIMARY)
  Weighted combo of simulation probabilities (p_1b, p_xb, p_hr, p_k, p_bb),
  vs Grade, Run Creation, historical bonus, pitcher multiplier.
  → normalize_0_100() → produces the ranking within today's slate.
  This is the simulation engine doing its job. Statcast does NOT mix in here.

STAGE 2: Statcast quality-of-contact overlay (SECONDARY, post-normalization)
  Applied AFTER normalization so the adjustment is in transparent point terms.
  Max ±10 pts total per score — meaningful tiebreaker, never overrides the sim.
  Missing Statcast data → 0 pts (neutral, no penalty).

Per-score Statcast logic (derived from the planning session):

  💣 HR Score:
    Barrel%  (+6 max) — primary, barrels = HRs
    xSLG     (+4 max) — power output correlation  [NEW]
    maxEV    (+3 max) — ceiling: can this bat generate HR power?  [NEW]
    HH%      (+2 max) — hard contact support
    AvgEV    (+1.5 max) — average contact quality  [NEW]

  🔥 XB Score:
    HH%      (+5 max) — primary, doubles/triples need hard contact not barrels
    xSLG     (+4 max) — extra-base power profile  [NEW]
    Barrel%  (+3 max) — barrels that don't clear the fence become doubles
    AvgEV    (+2.5 max) — consistent hard contact  [NEW]
    xBA      (+1.5 max) — contact quality  [NEW]

  🎯 Hit Score:
    xBA      (+6 max) — primary, literally expected batting average  [NEW]
    HH%      (+3 max) — hard contact falls in more often
    xwOBA    (+2 max) — overall contact value  [NEW]
    AvgEV    (+1.5 max) — average exit velocity  [NEW]

  1️⃣ Single Score:
    xBA      (+3 max) — positive: expected hits
    HH%      (+2 max) — mild positive: hard grounders/liners become singles
    Barrel%  (-4 max) — NEGATIVE: barrels go for XBH/HR or hard outs, not singles
    xSLG     (-3 max) — NEGATIVE: power profile means contact goes for extra bases  [NEW]
    maxEV    (-1.5 max) — mild NEGATIVE: power ceiling → contact too hard for singles  [NEW]

GC scores (Hit/Single/XB/HR with game-conditions ceiling) are derived from
the Statcast-adjusted scores, so they automatically inherit the overlay.
"""

import pandas as pd
import numpy as np
from config import CONFIG
from helpers import normalize_0_100

# ─────────────────────────────────────────────────────────────────────────────
# STATCAST COLUMN HELPERS
# ─────────────────────────────────────────────────────────────────────────────

_GC_COLS = ['gc_hr4', 'gc_hits20', 'gc_k20', 'gc_walks8', 'gc_runs10', 'gc_qs']


def _sc_series(df: pd.DataFrame, col: str) -> pd.Series:
    """Safe numeric extraction of a Statcast column. NaN when missing."""
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return pd.to_numeric(df[col], errors='coerce')


def _has_statcast(df: pd.DataFrame) -> bool:
    """True if at least one key Statcast column has non-null values."""
    check_cols = ['Barrel%', 'HH%', 'AvgEV', 'xBA', 'xSLG']
    return any(col in df.columns and df[col].notna().any() for col in check_cols)


# ─────────────────────────────────────────────────────────────────────────────
# STATCAST ADJUSTMENT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def _adj(series: pd.Series, avg: float, spread: float,
         pts: float, negate: bool = False) -> pd.Series:
    """
    Linear deviation adjustment relative to league average.

    Formula:  (value - avg) / spread * pts
    Clipped:  [-|pts|, +|pts|]
    NaN:      → 0.0 (neutral — no penalty for missing data)

    Args:
        series:  Statcast metric column
        avg:     league average benchmark
        spread:  normalisation range (roughly ±1 SD from avg)
        pts:     maximum contribution in score points (pre-clip)
        negate:  True → flip sign so above-average = penalty (Single Score power stats)
    """
    raw = (series - avg) / spread * pts
    if negate:
        raw = -raw
    return raw.clip(-abs(pts), abs(pts)).fillna(0.0)


def _compute_statcast_adj(df: pd.DataFrame, score_type: str) -> pd.Series:
    """
    Build the post-normalization Statcast adjustment for one score type.

    Returns a pd.Series in range [-sc_max_total_adj, +sc_max_total_adj].
    Values are in score points, applied directly to the 0-100 normalized score.

    League average benchmarks come from CONFIG so they can be tuned in one place.
    """
    cfg = CONFIG
    MAX = cfg['sc_max_total_adj']   # ±10 pts total

    # Pull all columns once
    barrel = _sc_series(df, 'Barrel%')
    hh     = _sc_series(df, 'HH%')
    avgev  = _sc_series(df, 'AvgEV')
    maxev  = _sc_series(df, 'maxEV')
    xslg   = _sc_series(df, 'xSLG')
    xba    = _sc_series(df, 'xBA')
    xwoba  = _sc_series(df, 'xwOBA')

    # Benchmarks
    B_AVG  = cfg['league_barrel_pct']   # 7.5
    HH_AVG = cfg['league_hh_pct']       # 38.0
    EV_AVG = cfg['league_avgev']        # 88.5
    MX_AVG = cfg['league_maxev']        # 108.0
    SL_AVG = cfg['league_xslg']         # 0.400
    BA_AVG = cfg['league_xba']          # 0.248
    WO_AVG = cfg['league_xwoba']        # 0.320

    # ── 💣 HR Score ─────────────────────────────────────────────────────────
    if score_type == 'HR':
        total = (
            _adj(barrel, B_AVG,  7.5,  6.0)   # primary — barrels drive HRs
          + _adj(xslg,   SL_AVG, 0.150, 4.0)  # xSLG — power output
          + _adj(maxev,  MX_AVG, 7.0,  3.0)   # maxEV — ceiling, can he hit it 400ft?
          + _adj(hh,     HH_AVG, 12.0, 2.0)   # HH% — hard contact support
          + _adj(avgev,  EV_AVG, 5.5,  1.5)   # AvgEV — avg contact quality
        )

    # ── 🔥 XB Score ─────────────────────────────────────────────────────────
    elif score_type == 'XB':
        total = (
            _adj(hh,     HH_AVG, 12.0, 5.0)   # primary — hard contact, not needing barrel
          + _adj(xslg,   SL_AVG, 0.120, 4.0)  # xSLG — extra-base power profile
          + _adj(barrel, B_AVG,  7.5,  3.0)   # barrel — often a double vs fence
          + _adj(avgev,  EV_AVG, 5.5,  2.5)   # AvgEV — consistent hard contact
          + _adj(xba,    BA_AVG, 0.062, 1.5)  # xBA — contact quality
        )

    # ── 🎯 Hit Score ─────────────────────────────────────────────────────────
    elif score_type == 'Hit':
        total = (
            _adj(xba,   BA_AVG, 0.062, 6.0)   # primary — literally expected batting avg
          + _adj(hh,    HH_AVG, 12.0, 3.0)    # HH% — hard contact falls in more
          + _adj(xwoba, WO_AVG, 0.080, 2.0)   # xwOBA — overall contact value
          + _adj(avgev, EV_AVG, 5.5,  1.5)    # AvgEV — exit velocity quality
        )

    # ── 1️⃣ Single Score ─────────────────────────────────────────────────────
    elif score_type == 'Single':
        total = (
            _adj(xba,    BA_AVG, 0.062, 3.0)          # positive — expected hits are hits
          + _adj(hh,     HH_AVG, 12.0,  2.0)          # mild positive — hard liners/grounders
          + _adj(barrel, B_AVG,  7.5,   4.0, negate=True)  # NEGATIVE — barrels → XBH not singles
          + _adj(xslg,   SL_AVG, 0.150, 3.0, negate=True)  # NEGATIVE — power profile = extra bases
          + _adj(maxev,  MX_AVG, 7.0,   1.5, negate=True)  # mild NEGATIVE — power ceiling
        )

    else:
        return pd.Series(0.0, index=df.index)

    return total.clip(-MAX, MAX).fillna(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# GAME CONDITION SIGNAL HELPER  (shared by compute and gc_adjusted_score)
# ─────────────────────────────────────────────────────────────────────────────

def _gc_signals(df: pd.DataFrame, strength: float) -> tuple:
    """
    Compute (hit_combined, hr_combined) GC signals.
    Both compute_game_condition_scores and gc_adjusted_score call this so
    the weights are in one place.
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
# STAGE 1 — METRIC COMPUTATION  (unchanged from V5.0)
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
# STAGE 2 — SCORES  (BallPark Pal primary → normalize → Statcast overlay)
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

    # ── STAGE 1: BallPark Pal raw scores (no Statcast — clean separation) ────
    # These formulas are the BallPark Pal simulation signal only.
    # Statcast is applied afterward as a transparent post-normalization overlay.

    # 🎯 Hit Score
    hit_raw = (
        df['p_1b']*3.0 + df['p_xb']*2.0 + df['p_hr']*1.0
        - df['p_k']*2.5 - df['p_bb']*1.0
        + vc*1.0 + rc*0.5 + hb
    ) * hit_mult
    df['Hit_Score'] = normalize_0_100(hit_raw)

    # 1️⃣ Single Score
    single_raw = (
        df['p_1b']*5.0 - df['p_k']*2.5 - df['p_bb']*1.0
        - df['p_xb']*0.8 - df['p_hr']*0.5
        + vc*0.8 + rc*0.4 + hb
    ) * single_mult
    df['Single_Score'] = normalize_0_100(single_raw)

    # 🔥 XB Score
    xb_raw = (
        df['p_xb']*5.0 + df['p_hr']*0.8
        - df['p_k']*1.5 - df['p_bb']*1.0
        + vc*1.2 + rc*0.6 + hb
    ) * xb_mult
    df['XB_Score'] = normalize_0_100(xb_raw)

    # 💣 HR Score
    # K%:  near-neutral (-0.15). Power swingers K a lot — high K ≠ bad HR target.
    #      Tiny residual penalty acknowledges contact still matters at the floor.
    # BB%: neutral (0). p_bb includes intentional walks (IBB). IBB = pitcher avoided
    #      the matchup entirely — no pitch thrown = no HR opportunity. The unintentional
    #      walk (positive signal) and IBB (negative signal) cancel out → 0 is honest.
    hr_raw = (
        df['p_hr']*6.0 + df['p_xb']*0.8
        - df['p_k']*0.15
        + df['xb_boost']*0.03
        + vc*0.5 + rc*0.5 + hb
    ) * hr_mult
    df['HR_Score'] = normalize_0_100(hr_raw)

    # ── Base (no-park) versions for Park Δ display ────────────────────────────
    df['Hit_Score_base'] = normalize_0_100(
        (df['p_1b_base']*3.0 + df['p_xb_base']*2.0 + df['p_hr_base']*1.0
         - df['p_k_base']*2.5 - df['p_bb_base']*1.0
         + vc*1.0 + rc*0.5 + hb) * hit_mult)

    df['Single_Score_base'] = normalize_0_100(
        (df['p_1b_base']*5.0 - df['p_k_base']*2.5 - df['p_bb_base']*1.0
         - df['p_xb_base']*0.8 - df['p_hr_base']*0.5
         + vc*0.8 + rc*0.4 + hb) * single_mult)

    df['XB_Score_base'] = normalize_0_100(
        (df['p_xb_base']*5.0 + df['p_hr_base']*0.8
         - df['p_k_base']*1.5 - df['p_bb_base']*1.0
         + vc*1.2 + rc*0.6 + hb) * xb_mult)

    df['HR_Score_base'] = normalize_0_100(
        (df['p_hr_base']*6.0 + df['p_xb_base']*0.8
         - df['p_k_base']*0.15
         + df['xb_boost']*0.03
         + vc*0.5 + rc*0.5 + hb) * hr_mult)

    # ── STAGE 2: Statcast post-normalization overlay ──────────────────────────
    # Applied to both the main score and base score so Park Δ is unaffected.
    # If Statcast data is unavailable for a player → 0 pts (neutral, no penalty).
    # Total capped at ±10 pts — BallPark Pal rankings stay intact.

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

    hit_ceiling_mult = 1.0 + hit_combined.clip(-CONFIG['gc_hit_max_range'],
                                                CONFIG['gc_hit_max_range'])
    hr_ceiling_mult  = 1.0 + hr_combined.clip(-CONFIG['gc_hr_max_range'],
                                               CONFIG['gc_hr_max_range'])

    # GC scores derive from the Statcast-adjusted main scores,
    # so they automatically inherit the Statcast overlay.
    df['Hit_Score_gc']    = normalize_0_100(df['Hit_Score']    * hit_ceiling_mult)
    df['Single_Score_gc'] = normalize_0_100(df['Single_Score'] * hit_ceiling_mult)
    df['XB_Score_gc']     = normalize_0_100(df['XB_Score']     * hit_ceiling_mult)
    df['HR_Score_gc']     = normalize_0_100(df['HR_Score']     * hr_ceiling_mult)

    return df


def gc_adjusted_score(pool: pd.DataFrame, sc: str, use_gc: bool = True) -> pd.Series:
    """GC-adjusted score for parlay builder. Uses _gc_signals — no duplicated weights."""
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
