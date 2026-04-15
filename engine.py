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
    Batting order position signal. Only active when confirmed lineup available.
    Cleanup (3-5): bonus on HR/XB.  Leadoff (1-2): bonus on Hit/Single.
    """
    cfg    = CONFIG
    MAX    = cfg['order_max_adj']
    result = pd.Series(0.0, index=df.index)

    if not order_map:
        return result

    for idx, row in df.iterrows():
        batter   = row.get('Batter','')
        position = order_map.get(batter)
        if position is None:
            continue
        if score_type in ('HR','XB') and 3 <= position <= 5:
            result[idx] = cfg['order_cleanup_bonus']
        elif score_type in ('Hit','Single') and 1 <= position <= 2:
            result[idx] = cfg['order_leadoff_bonus']

    return result.clip(-MAX, MAX)


# ─────────────────────────────────────────────────────────────────────────────
# NEW SIGNAL 3 — ROLLING 7-DAY FORM
# ─────────────────────────────────────────────────────────────────────────────

def _compute_form_adj(df: pd.DataFrame, form_map: dict,
                      score_type: str) -> pd.Series:
    """
    Recent hitting form (H/G last 7 days) adjustment.
    Applied to Hit/Single only — recency matters most for contact props.
    Applied mildly to HR/XB (0.5×) as hot hitters do tend to stay hot.
    """
    cfg    = CONFIG
    MAX    = cfg['form_max_adj']
    HOT    = cfg['form_hot_threshold']
    COLD   = cfg['form_cold_threshold']
    result = pd.Series(0.0, index=df.index)

    if not form_map:
        return result

    # Multiplier per score type — form matters more for hit/single
    mult = {'Hit':1.0, 'Single':1.0, 'XB':0.5, 'HR':0.35}.get(score_type, 0.5)

    for idx, row in df.iterrows():
        batter = row.get('Batter','')
        info   = form_map.get(batter)
        if info is None:
            continue
        rate = info.get('hit_rate', 0)
        if info.get('games', 0) < 3:   # too few games to be meaningful
            continue
        if rate >= HOT:
            result[idx] = cfg['form_hot_bonus'] * mult
        elif rate <= COLD:
            result[idx] = cfg['form_cold_penalty'] * mult

    return result.clip(-MAX, MAX)


# ─────────────────────────────────────────────────────────────────────────────
# NEW SIGNAL 4 — PLATOON / PITCHER HANDEDNESS
# ─────────────────────────────────────────────────────────────────────────────

# Typical batter handedness by full name — used when we can't look up.
# Engine will skip platoon if pitcher handedness is unknown.

def _compute_platoon_adj(df: pd.DataFrame,
                         handedness_map: dict) -> pd.Series:
    """
    Platoon advantage: opposite-hand batter vs pitcher = bonus.
    Same-hand = penalty.

    Batter hand is inferred from the 'Batter' column via a heuristic
    (most MLB batters are R; L and S batters require lookup, which we
    don't have in the current data). We use a conservative approach:
    only apply a penalty for same-hand, not a bonus for opposite.
    That way we don't reward unknown platoon situations.

    NOTE: Disable via CONFIG['use_platoon'] = False if BallPark Pal
    already incorporates handedness splits in their 3000-sim model.
    """
    cfg    = CONFIG
    if not cfg.get('use_platoon', True) or not handedness_map:
        return pd.Series(0.0, index=df.index)

    MAX    = cfg['platoon_max_adj']
    result = pd.Series(0.0, index=df.index)

    # Batter handedness — we don't have this in the slate data currently.
    # Rather than guessing, we apply a conservative neutral for unknown batters.
    # When batter handedness data becomes available (e.g. from mlb_api),
    # replace this dict with the actual lookup.
    # For now, this function is wired but conservative.
    batter_hand_map: dict = {}   # {batter_name: 'L'/'R'/'S'} — populate when available

    for idx, row in df.iterrows():
        pitcher_last = row.get('Pitcher','')
        p_hand       = handedness_map.get(pitcher_last)
        b_hand       = batter_hand_map.get(row.get('Batter',''))

        if not p_hand or not b_hand:
            continue   # unknown → neutral, no guess

        if b_hand == 'S':   # switch hitter — always has advantage
            result[idx] = cfg['platoon_bonus']
        elif b_hand != p_hand:   # opposite hand — platoon advantage
            result[idx] = cfg['platoon_bonus']
        else:                     # same hand — disadvantage
            result[idx] = cfg['platoon_penalty']

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

    return df


# ─────────────────────────────────────────────────────────────────────────────
# GC SCORES
# ─────────────────────────────────────────────────────────────────────────────

def compute_game_condition_scores(df: pd.DataFrame, use_gc: bool=True) -> pd.DataFrame:
    df = df.copy()
    has_gc = all(c in df.columns for c in _GC_COLS)
    if not has_gc:
        for sc in ['Hit_Score','Single_Score','XB_Score','HR_Score']:
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
