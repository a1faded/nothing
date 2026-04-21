"""
engine.py — Scoring Engine V5.5 → V7
======================================
Four new post-normalization signals added on top of V5.5:

  1. xBA Luck (Hit Score only)
     xBA - fg_AVG delta. Positive gap = contact quality exceeds results =
     regression candidate upward. ±2 pts max.

  2. Batting Order Position
     Position 3-5 (cleanup): +1.5 pts HR/XB — more fastballs, protected by lineup.
     Position 1-2 (leadoff):  +1.0 pts Hit/Single — OBP profile, see more pitches.
     Only active when confirmed lineup data is available. ±2 pts max.

  3. Rolling 7-Day Form (Hit/Single only)
     Hit rate (H/G) last 7 days vs league average (~0.9).
     Hot (>1.2 H/G): +2.5 pts.  Cold (<0.5 H/G): -2.5 pts.
     Capped to avoid over-weighting small samples. ±2.5 pts max.

  4. Pitcher Handedness / Platoon
     Opposite-hand batter vs pitcher = natural platoon advantage.
     Same-hand = disadvantage. ±2 pts max.
     Controlled by CONFIG['use_platoon'] — set False if BallPark Pal
     already models handedness splits in their simulations.

All signals are applied post-normalization on the 0-100 score.
BallPark Pal remains the primary ranking engine.
"""

import pandas as pd
import numpy as np
from config import CONFIG
from helpers import normalize_0_100

_GC_COLS = ['gc_hr4','gc_hits20','gc_k20','gc_walks8','gc_runs10','gc_qs']


def _sc_series(df, col):
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return pd.to_numeric(df[col], errors='coerce')


def _has_statcast(df):
    return any(col in df.columns and df[col].notna().any()
               for col in ['Barrel%','HH%','AvgEV','xBA','xSLG'])


# ─────────────────────────────────────────────────────────────────────────────
# STATCAST OVERLAY  (unchanged from V5.5)
# ─────────────────────────────────────────────────────────────────────────────

def _adj(series, avg, spread, pts, negate=False):
    raw = (series - avg) / spread * pts
    if negate:
        raw = -raw
    return raw.clip(-abs(pts), abs(pts)).fillna(0.0)


def _compute_statcast_adj(df, score_type):
    cfg = CONFIG
    MAX = cfg['sc_max_total_adj']
    barrel = _sc_series(df,'Barrel%'); hh    = _sc_series(df,'HH%')
    avgev  = _sc_series(df,'AvgEV');   maxev = _sc_series(df,'maxEV')
    xslg   = _sc_series(df,'xSLG');    xba   = _sc_series(df,'xBA')
    xwoba  = _sc_series(df,'xwOBA')
    B,HH,EV,MX = cfg['league_barrel_pct'],cfg['league_hh_pct'],cfg['league_avgev'],cfg['league_maxev']
    SL,BA,WO   = cfg['league_xslg'],cfg['league_xba'],cfg['league_xwoba']

    if score_type == 'HR':
        total = (_adj(barrel,B,7.5,6.0)+_adj(xslg,SL,0.15,4.0)
                +_adj(maxev,MX,7.0,3.0)+_adj(hh,HH,12.0,2.0)+_adj(avgev,EV,5.5,1.5))
    elif score_type == 'XB':
        total = (_adj(hh,HH,12.0,5.0)+_adj(xslg,SL,0.12,4.0)
                +_adj(barrel,B,7.5,3.0)+_adj(avgev,EV,5.5,2.5)+_adj(xba,BA,0.062,1.5))
    elif score_type == 'Hit':
        total = (_adj(xba,BA,0.062,6.0)+_adj(hh,HH,12.0,3.0)
                +_adj(xwoba,WO,0.080,2.0)+_adj(avgev,EV,5.5,1.5))
    elif score_type == 'Single':
        total = (_adj(xba,BA,0.062,1.5)+_adj(hh,HH,12.0,2.0)
                +_adj(barrel,B,7.5,4.0,negate=True)
                +_adj(xslg,SL,0.150,3.0,negate=True)
                +_adj(maxev,MX,7.0,1.5,negate=True))
    else:
        return pd.Series(0.0, index=df.index)
    return total.clip(-MAX, MAX).fillna(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# NEW SIGNAL 1 — xBA LUCK  (Hit Score)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_xba_luck_adj(df: pd.DataFrame) -> pd.Series:
    """
    (xBA - fg_AVG) * weight, capped at ±luck_max_adj pts.
    Positive = underperforming contact quality = regression candidate upward.
    Applied only when both xBA and fg_AVG are present.
    """
    cfg   = CONFIG
    xba   = _sc_series(df, 'xBA')
    fg_avg= _sc_series(df, 'fg_AVG')

    has_both = xba.notna() & fg_avg.notna() & (fg_avg > 0)
    luck = pd.Series(0.0, index=df.index)
    luck[has_both] = (xba[has_both] - fg_avg[has_both]) * cfg['luck_weight']
    return luck.clip(-cfg['luck_max_adj'], cfg['luck_max_adj']).fillna(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# NEW SIGNAL 2 — BATTING ORDER POSITION
# ─────────────────────────────────────────────────────────────────────────────

def _compute_order_adj(df: pd.DataFrame, order_map: dict,
                       score_type: str) -> pd.Series:
    """
    Batting order position signal — vectorized via map() not iterrows().
    Cleanup (3-5): bonus on HR/XB.  Leadoff (1-2): bonus on Hit/Single.
    """
    cfg    = CONFIG
    MAX    = cfg['order_max_adj']
    result = pd.Series(0.0, index=df.index)

    if not order_map:
        return result

    positions = df['Batter'].map(order_map)   # Series of int or NaN

    if score_type in ('HR', 'XB'):
        result = positions.apply(
            lambda p: cfg['order_cleanup_bonus'] if pd.notna(p) and 3 <= int(p) <= 5 else 0.0
        )
    elif score_type in ('Hit', 'Single'):
        result = positions.apply(
            lambda p: cfg['order_leadoff_bonus'] if pd.notna(p) and 1 <= int(p) <= 2 else 0.0
        )

    return result.clip(-MAX, MAX)


# ─────────────────────────────────────────────────────────────────────────────
# NEW SIGNAL 3 — ROLLING 7-DAY FORM
# ─────────────────────────────────────────────────────────────────────────────

def _compute_form_adj(df: pd.DataFrame, form_map: dict,
                      score_type: str) -> pd.Series:
    """
    Recent hitting form (H/G last 7 days) — vectorized via map().
    Applied to all scores; weight varies by score type.
    """
    cfg    = CONFIG
    MAX    = cfg['form_max_adj']
    HOT    = cfg['form_hot_threshold']
    COLD   = cfg['form_cold_threshold']
    result = pd.Series(0.0, index=df.index)

    if not form_map:
        return result

    mult = {'Hit':1.0, 'Single':1.0, 'XB':0.5, 'HR':0.35}.get(score_type, 0.5)

    def _form_pts(name):
        info = form_map.get(name)
        if not info or info.get('games', 0) < 3:
            return 0.0
        rate = info.get('hit_rate', 0)
        if rate >= HOT:  return cfg['form_hot_bonus']   * mult
        if rate <= COLD: return cfg['form_cold_penalty'] * mult
        return 0.0

    result = df['Batter'].apply(_form_pts)
    return result.clip(-MAX, MAX)


# ─────────────────────────────────────────────────────────────────────────────
# NEW SIGNAL 4 — PLATOON / PITCHER HANDEDNESS
# ─────────────────────────────────────────────────────────────────────────────

# Typical batter handedness by full name — used when we can't look up.
# Engine will skip platoon if pitcher handedness is unknown.

def _compute_platoon_adj(df: pd.DataFrame,
                         handedness_map: dict) -> pd.Series:
    """
    Platoon advantage — vectorized via apply().
    Conservative: only fires when BOTH pitcher and batter handedness are known.
    batter_hand_map is empty until batter-side lookup is added to mlb_api.
    """
    cfg    = CONFIG
    if not cfg.get('use_platoon', True) or not handedness_map:
        return pd.Series(0.0, index=df.index)

    MAX              = cfg['platoon_max_adj']
    batter_hand_map  : dict = {}   # {batter_name: 'L'/'R'/'S'} — wire when available

    def _platoon_pts(row):
        p_hand = handedness_map.get(row.get('Pitcher',''))
        b_hand = batter_hand_map.get(row.get('Batter',''))
        if not p_hand or not b_hand:
            return 0.0
        if b_hand == 'S':
            return cfg['platoon_bonus']
        if b_hand != p_hand:
            return cfg['platoon_bonus']
        return cfg['platoon_penalty']

    result = df.apply(_platoon_pts, axis=1)
    return result.clip(-MAX, MAX)


# ─────────────────────────────────────────────────────────────────────────────
# GC SIGNALS
# ─────────────────────────────────────────────────────────────────────────────

def _gc_signals(df, strength):
    cfg    = CONFIG
    hits_a = cfg['gc_hits20_anchor']; k_a    = cfg['gc_k20_anchor']
    runs_a = cfg['gc_runs10_anchor']; walk_a = cfg['gc_walks8_anchor']
    hr4_a  = cfg['gc_hr4_anchor'];    qs_a   = cfg['gc_qs_anchor']

    hit_combined = (
        (df['gc_hits20']-hits_a)/15.0*1.8 - (df['gc_k20']-k_a)/20.0*1.5
       +(df['gc_runs10']-runs_a)/20.0*1.0 - (df['gc_walks8']-walk_a)/15.0*0.8
       -(df['gc_qs']-qs_a)/20.0*1.0
    ) * strength

    hr_combined = (
        (df['gc_hr4']-hr4_a)/15.0*1.8   - (df['gc_k20']-k_a)/20.0*1.2
       +(df['gc_runs10']-runs_a)/20.0*0.8 - (df['gc_walks8']-walk_a)/15.0*0.8
       -(df['gc_qs']-qs_a)/20.0*0.8
    ) * strength

    return hit_combined, hr_combined


# ─────────────────────────────────────────────────────────────────────────────
# METRIC COMPUTATION  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def compute_metrics(df: pd.DataFrame, use_park: bool) -> pd.DataFrame:
    df = df.copy()
    for s in ['HR','XB','1B','BB','K']:
        pk = f'{s} Prob'; pb = f'{s} Prob (no park)'
        df[f'p_{s.lower()}_park'] = pd.to_numeric(df[pk], errors='coerce').fillna(0)
        df[f'p_{s.lower()}_base'] = pd.to_numeric(df[pb], errors='coerce').fillna(0)
        df[f'p_{s.lower()}'] = (
            (df[f'p_{s.lower()}_park']+df[f'p_{s.lower()}_base'])/2
            if use_park else df[f'p_{s.lower()}_base']
        )
    df['vs_mod']     = pd.to_numeric(df['vs Grade'],errors='coerce').fillna(0).clip(-10,10)/10
    df['vs_contrib'] = df['vs_mod']*2.0

    rc_col = 'RC' if use_park else 'RC (no park)'
    if rc_col not in df.columns: rc_col = 'RC'
    df['rc_norm'] = pd.to_numeric(df[rc_col],errors='coerce').fillna(0)
    rc_min,rc_max = df['rc_norm'].min(), df['rc_norm'].max()
    df['rc_contrib'] = (
        ((df['rc_norm']-rc_min)/(rc_max-rc_min)*2-1)
        if rc_max>rc_min else pd.Series(0.0,index=df.index)
    )

    df['PA']  = pd.to_numeric(df['PA'],  errors='coerce').fillna(0)
    df['H']   = pd.to_numeric(df['H'],   errors='coerce').fillna(0)
    df['AVG'] = pd.to_numeric(df['AVG'], errors='coerce').fillna(0)

    zero_hit_penalty = np.where(
        (df['PA']>=8)&(df['H']==0),
        -np.clip(df['PA']/10.0*5.0, 1.5, 5.0), 0.0
    )
    pos_bonus = np.where(
        (df['PA']>=CONFIG['hist_min_pa'])&(df['H']>0),
        (df['AVG']*CONFIG['hist_bonus_max']).round(3), 0.0
    )
    df['hist_bonus'] = (zero_hit_penalty+pos_bonus).round(3)
    df['Starter']    = pd.to_numeric(df.get('Starter',0),errors='coerce').fillna(0).astype(int)
    df['total_hit_prob'] = (df['p_1b']+df['p_xb']+df['p_hr']).clip(upper=100).round(1)

    xb_boost_park = pd.to_numeric(df['XB Boost'],errors='coerce').fillna(0) \
        if 'XB Boost' in df.columns else pd.Series(0.0,index=df.index)
    xb_boost_base = pd.to_numeric(df['XB Boost (no park)'],errors='coerce').fillna(0) \
        if 'XB Boost (no park)' in df.columns else pd.Series(0.0,index=df.index)
    df['xb_boost'] = (xb_boost_park+xb_boost_base)/2 if use_park else xb_boost_base
    return df


# ─────────────────────────────────────────────────────────────────────────────
# SCORES  (Stage 1: BallPark Pal → Stage 2: Statcast → Stage 3: new signals)
# ─────────────────────────────────────────────────────────────────────────────

def compute_scores(df: pd.DataFrame,
                   order_map:      dict | None = None,
                   form_map:       dict | None = None,
                   handedness_map: dict | None = None) -> pd.DataFrame:
    """
    order_map:      {batter_name: batting_order_position}  from mlb_api
    form_map:       {batter_name: {hit_rate, hits, games}} from mlb_api
    handedness_map: {pitcher_last_name: 'L'/'R'}           from mlb_api
    All three default to {} (neutral) when not supplied.
    """
    order_map      = order_map      or {}
    form_map       = form_map       or {}
    handedness_map = handedness_map or {}

    df = df.copy()
    vc = df['vs_contrib']; rc = df['rc_contrib']; hb = df['hist_bonus']

    hit_mult    = (df['pitch_hit_mult']+df['pitch_walk_pen']).clip(0.90,1.10)
    xb_mult     = ((df['pitch_hit_mult']+df['pitch_hr_mult'])/2+df['pitch_walk_pen']).clip(0.90,1.10)
    hr_mult     = (df['pitch_hr_mult'] +df['pitch_walk_pen']).clip(0.90,1.10)
    single_mult = (df['pitch_hit_mult']+df['pitch_walk_pen']).clip(0.90,1.10)

    # ── Stage 1: BallPark Pal raw (no Statcast) ───────────────────────────────
    hit_raw = (df['p_1b']*3.0+df['p_xb']*2.0+df['p_hr']*1.0
               -df['p_k']*2.5-df['p_bb']*1.0+vc*1.0+rc*0.2+hb)*hit_mult
    df['Hit_Score'] = normalize_0_100(hit_raw)

    single_raw = (df['p_1b']*5.0-df['p_k']*2.5-df['p_bb']*1.0
                  -df['p_xb']*0.5-df['p_hr']*0.8+vc*0.8+rc*0.2+hb)*single_mult
    df['Single_Score'] = normalize_0_100(single_raw)

    xb_raw = (df['p_xb']*5.0+df['p_hr']*0.8
              -df['p_k']*1.0-df['p_bb']*0.3+vc*1.2+rc*0.4+hb)*xb_mult
    df['XB_Score'] = normalize_0_100(xb_raw)

    hr_raw = (df['p_hr']*6.0+df['p_xb']*0.8-df['p_k']*0.15
              +df['xb_boost']*0.03+vc*0.5+rc*0.35+hb)*hr_mult
    df['HR_Score'] = normalize_0_100(hr_raw)

    # Base (no-park) versions
    df['Hit_Score_base']    = normalize_0_100(
        (df['p_1b_base']*3.0+df['p_xb_base']*2.0+df['p_hr_base']*1.0
         -df['p_k_base']*2.5-df['p_bb_base']*1.0+vc*1.0+rc*0.2+hb)*hit_mult)
    df['Single_Score_base'] = normalize_0_100(
        (df['p_1b_base']*5.0-df['p_k_base']*2.5-df['p_bb_base']*1.0
         -df['p_xb_base']*0.5-df['p_hr_base']*0.8+vc*0.8+rc*0.2+hb)*single_mult)
    df['XB_Score_base']     = normalize_0_100(
        (df['p_xb_base']*5.0+df['p_hr_base']*0.8
         -df['p_k_base']*1.0-df['p_bb_base']*0.3+vc*1.2+rc*0.4+hb)*xb_mult)
    df['HR_Score_base']     = normalize_0_100(
        (df['p_hr_base']*6.0+df['p_xb_base']*0.8-df['p_k_base']*0.15
         +df['xb_boost']*0.03+vc*0.5+rc*0.35+hb)*hr_mult)

    # ── Stage 2: Statcast overlay ─────────────────────────────────────────────
    if _has_statcast(df):
        for st_, sc_, bc_ in [('HR','HR_Score','HR_Score_base'),
                               ('XB','XB_Score','XB_Score_base'),
                               ('Hit','Hit_Score','Hit_Score_base'),
                               ('Single','Single_Score','Single_Score_base')]:
            adj = _compute_statcast_adj(df, st_)
            df[sc_] = (df[sc_]+adj).clip(0,100).round(1)
            df[bc_] = (df[bc_]+adj).clip(0,100).round(1)

    # ── Stage 3: New signals (post-normalization, all capped small) ───────────

    # 1. xBA luck — Hit Score only
    luck_adj = _compute_xba_luck_adj(df)
    df['Hit_Score']      = (df['Hit_Score']     + luck_adj).clip(0,100).round(1)
    df['Hit_Score_base'] = (df['Hit_Score_base'] + luck_adj).clip(0,100).round(1)

    # 2. Batting order position
    platoon_adj = _compute_platoon_adj(df, handedness_map)
    for st_, cols_ in [
        ('HR',     ['HR_Score',    'HR_Score_base']),
        ('XB',     ['XB_Score',    'XB_Score_base']),
        ('Hit',    ['Hit_Score',   'Hit_Score_base']),
        ('Single', ['Single_Score','Single_Score_base']),
    ]:
        order_adj = _compute_order_adj(df, order_map, st_)
        for col in cols_:
            df[col] = (df[col] + order_adj).clip(0,100).round(1)

        # 3. Rolling form — on all scores with varying weight (built into _compute_form_adj)
        form_adj = _compute_form_adj(df, form_map, st_)
        for col in cols_:
            df[col] = (df[col] + form_adj).clip(0,100).round(1)

        # 4. Platoon — applied uniformly (conservative — only fires when both hands known)
        for col in cols_:
            df[col] = (df[col] + platoon_adj).clip(0,100).round(1)

    # ── Stage 4: Cross-score profile correction ───────────────────────────────
    XB_GAP_THRESHOLD = 5.0
    XB_RATE          = 0.60
    XB_MAX           = 12.0
    HR_GAP_THRESHOLD = 10.0
    HR_RATE          = 0.40
    HR_MAX           = 7.0

    if 'XB_Score' in df.columns and 'Single_Score' in df.columns:
        xb_gap  = (df['XB_Score'] - df['Single_Score'] - XB_GAP_THRESHOLD).clip(lower=0)
        xb_pen  = (xb_gap * XB_RATE).clip(upper=XB_MAX)
        df['Single_Score']      = (df['Single_Score']      - xb_pen).clip(0, 100).round(1)
        df['Single_Score_base'] = (df['Single_Score_base'] - xb_pen).clip(0, 100).round(1)

    if 'HR_Score' in df.columns and 'Single_Score' in df.columns:
        hr_gap  = (df['HR_Score'] - df['Single_Score'] - HR_GAP_THRESHOLD).clip(lower=0)
        hr_pen  = (hr_gap * HR_RATE).clip(upper=HR_MAX)
        df['Single_Score']      = (df['Single_Score']      - hr_pen).clip(0, 100).round(1)
        df['Single_Score_base'] = (df['Single_Score_base'] - hr_pen).clip(0, 100).round(1)

    # ── Stage 5: HRR Score (Hits + Runs + RBIs composite) ────────────────────
    # Prop: Player totals hits + runs scored + RBIs ≥ 2.
    # Batting order is the dominant signal — cleanup/leadoff produce 80%+ of events.
    # BvP OPS is the best historical predictor when enough AB exist.
    cfg = CONFIG
    hit_s = df['Hit_Score'].clip(0, 100)
    hr_s  = df['HR_Score'].clip(0, 100)

    # Batting order bonus/penalty for run-production context
    order_hrr = pd.Series(0.0, index=df.index)
    if '_order_pos' in df.columns:
        pos = pd.to_numeric(df['_order_pos'], errors='coerce')
        # Slots 1-5: most R+RBI opportunities
        order_hrr = order_hrr.where(~pos.isin([1, 2, 3, 4, 5]),
                                     order_hrr + cfg['hrr_order_bonus'])
        # Slots 7-9: fewest at-bats, least RBI/run context
        order_hrr = order_hrr.where(~pos.isin([7, 8, 9]),
                                     order_hrr - cfg['hrr_order_penalty'])

    # GC run environment bonus
    gc_hrr = pd.Series(0.0, index=df.index)
    if all(c in df.columns for c in ['gc_runs10']):
        gc_runs = pd.to_numeric(df['gc_runs10'], errors='coerce').fillna(
            cfg['gc_runs10_anchor'])
        gc_hrr = ((gc_runs - cfg['gc_runs10_anchor']) * cfg['hrr_gc_weight']
                  ).clip(-cfg['hrr_gc_max'], cfg['hrr_gc_max'])

    # BvP OPS signal (only when bvp_conf is high enough)
    bvp_hrr = pd.Series(0.0, index=df.index)
    if 'bvp_ops' in df.columns and 'bvp_conf' in df.columns:
        bvp_ops  = pd.to_numeric(df['bvp_ops'],  errors='coerce').fillna(
            cfg['hrr_bvp_ops_lg'])
        bvp_conf = pd.to_numeric(df['bvp_conf'], errors='coerce').fillna(0.0)
        bvp_raw  = ((bvp_ops - cfg['hrr_bvp_ops_lg']) * cfg['hrr_bvp_weight']
                    ).clip(-cfg['hrr_bvp_max'], cfg['hrr_bvp_max'])
        bvp_hrr  = bvp_raw * bvp_conf   # scale by confidence (0 when AB < min)

    # BvP AVG overlay on Hit_Score (when BvP data available)
    if 'bvp_avg' in df.columns and 'bvp_conf' in df.columns:
        bvp_avg  = pd.to_numeric(df['bvp_avg'],  errors='coerce').fillna(
            cfg['league_avg'])
        bvp_conf = pd.to_numeric(df['bvp_conf'], errors='coerce').fillna(0.0)
        bvp_avg_adj = ((bvp_avg - cfg['league_avg']) * cfg['bvp_avg_weight']
                       ).clip(-cfg['bvp_avg_max'], cfg['bvp_avg_max'])
        bvp_avg_adj = bvp_avg_adj * bvp_conf
        df['Hit_Score']      = (df['Hit_Score']      + bvp_avg_adj).clip(0,100).round(1)
        df['Hit_Score_base'] = (df['Hit_Score_base'] + bvp_avg_adj).clip(0,100).round(1)

    # BvP HR bonus on HR_Score
    if 'bvp_hr' in df.columns and 'bvp_conf' in df.columns:
        bvp_hr   = pd.to_numeric(df['bvp_hr'],   errors='coerce').fillna(0)
        bvp_conf = pd.to_numeric(df['bvp_conf'], errors='coerce').fillna(0.0)
        bvp_hr_adj = (bvp_hr * cfg['bvp_hr_bonus']
                      ).clip(0, cfg['bvp_hr_bonus_max']) * bvp_conf
        df['HR_Score']      = (df['HR_Score']      + bvp_hr_adj).clip(0,100).round(1)
        df['HR_Score_base'] = (df['HR_Score_base'] + bvp_hr_adj).clip(0,100).round(1)

    # Compose HRR_Score
    hrr_raw = (
        hit_s * cfg['hrr_hit_weight']
      + order_hrr
      + hr_s  * cfg['hrr_hr_weight']
      + gc_hrr
      + bvp_hrr
    )
    df['HRR_Score']      = normalize_0_100(hrr_raw).round(1)
    df['HRR_Score_base'] = df['HRR_Score'].copy()   # park doesn't change HRR

    return df


# ─────────────────────────────────────────────────────────────────────────────
# GC SCORES
# ─────────────────────────────────────────────────────────────────────────────

def compute_game_condition_scores(df: pd.DataFrame, use_gc: bool=True) -> pd.DataFrame:
    df = df.copy()
    has_gc = all(c in df.columns for c in _GC_COLS)
    if not has_gc:
        for sc in ['Hit_Score','Single_Score','XB_Score','HR_Score','HRR_Score']:
            if sc in df.columns:
                df[sc+'_gc'] = df[sc]
        return df

    strength = 1.0 if use_gc else CONFIG['gc_reduced_strength']
    hit_comb, hr_comb = _gc_signals(df, strength)
    hit_mult = 1.0+hit_comb.clip(-CONFIG['gc_hit_max_range'],CONFIG['gc_hit_max_range'])
    hr_mult  = 1.0+hr_comb.clip(-CONFIG['gc_hr_max_range'], CONFIG['gc_hr_max_range'])

    df['Hit_Score_gc']    = normalize_0_100(df['Hit_Score']    * hit_mult)
    df['Single_Score_gc'] = normalize_0_100(df['Single_Score'] * hit_mult)
    df['XB_Score_gc']     = normalize_0_100(df['XB_Score']     * hit_mult)
    df['HR_Score_gc']     = normalize_0_100(df['HR_Score']      * hr_mult)
    # HRR uses a blend — run environment (hr_mult) dominates over contact (hit_mult)
    if 'HRR_Score' in df.columns:
        hrr_mult = 1.0 + (hit_comb * 0.4 + hr_comb * 0.6).clip(
            -CONFIG['gc_hr_max_range'], CONFIG['gc_hr_max_range'])
        df['HRR_Score_gc'] = normalize_0_100(df['HRR_Score'] * hrr_mult)

    # ── Hot park extra boost ──────────────────────────────────────────────────
    # When gc_hr4 > 2× league median (12.2%), a game environment is genuinely
    # elevated — the whole lineup benefits, not just one player.
    # Data shows: Reds (GABP), Angels, Rays, Braves all had 3+ HRs in same game.
    # We add a flat +1.5 pts to HR_Score_gc for every batter in that game.
    # This surfaces more players from hot-park games, not just the top-1 scorer.
    # Cap at +1.5 pts total — small enough to not override individual quality.
    if use_gc:
        hot_park_threshold = CONFIG['gc_hr4_anchor'] * 2.0   # 2× median = 24.4%
        hot_park_mask      = df['gc_hr4'] > hot_park_threshold
        if hot_park_mask.any():
            boost = CONFIG.get('hot_park_boost', 1.5)
            df.loc[hot_park_mask, 'HR_Score_gc'] = (
                (df.loc[hot_park_mask, 'HR_Score_gc'] + boost)
                .clip(0, 100).round(1)
            )

    return df


def gc_adjusted_score(pool, sc, use_gc=True):
    base_sc = sc.replace('_gc','')
    gc_col  = base_sc+'_gc'
    if gc_col in pool.columns:   return pool[gc_col]
    if base_sc not in pool.columns: return pd.Series(50.0, index=pool.index)
    if not all(c in pool.columns for c in _GC_COLS): return pool[base_sc]

    strength = 1.0 if use_gc else CONFIG['gc_reduced_strength']
    hc, hrc  = _gc_signals(pool, strength)
    combined = hrc if base_sc=='HR_Score' else hc
    MAX      = CONFIG['gc_hr_max_range'] if base_sc=='HR_Score' else CONFIG['gc_hit_max_range']
    raw      = pool[base_sc]*(1.0+combined.clip(-MAX,MAX))
    mn,mx    = raw.min(), raw.max()
    return pd.Series(50.0,index=pool.index) if mx==mn else ((raw-mn)/(mx-mn)*100).round(1)
