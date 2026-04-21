"""
unders.py — Under Targets Page
================================
Flips the predictor logic: instead of finding who WILL get hits/XBs/HRs,
finds players unlikely to accumulate bases — useful for total bases unders,
extra base hit unders, and no-hit props.

Architecture mirrors the main Predictor page:
  - Same sidebar filters (starters, confirmed lineups, team, exclusions)
  - Same df (already scored by engine.py)
  - New compute_under_scores() adds Under_Score columns
  - New rendering logic inverts the table (low is good)

Three under target types:
  XB Under   — player unlikely to get an extra base hit (double/triple)
  TB Under   — player unlikely to accumulate total bases (line at 1.5 or 2.0)
  Hit Under  — player unlikely to get any base hit (0.5 line, highest variance)

Disqualification logic:
  Each target has offsetting categories that can STILL produce bases even
  when the primary category is low. Any player exceeding the disqualification
  threshold in an offsetting category is flagged ⚠️ and ranked lower.
  Users can override with the "Show disqualified" toggle.

Under_Score computation (per type):
  XB Under:  (100 - XB_Score)*0.5 + (100 - HR_Score)*0.35
             + (100 - Hit_Score)*0.15 + K_bonus + pitcher_bonus
  TB Under:  (100 - Hit_Score)*0.45 + (100 - XB_Score)*0.35
             + (100 - HR_Score)*0.20 + K_bonus + pitcher_bonus
  Hit Under: (100 - Hit_Score)*0.70 + K_bonus*1.5 + pitcher_bonus
             (K% matters more here — strikeout = guaranteed no hit)

Higher Under_Score = better under candidate.
"""

import streamlit as st
import pandas as pd
import numpy as np
from config import CONFIG
from helpers import grade_pill, style_grade_cell


# ─────────────────────────────────────────────────────────────────────────────
# UNDER SCORE COMPUTATION
# ─────────────────────────────────────────────────────────────────────────────

def compute_under_scores(df: pd.DataFrame,
                         form_map: dict | None = None,
                         use_gc:   bool = True) -> pd.DataFrame:
    """
    Full 8+1 layer under score computation. Vectorized throughout.

    Signal architecture:
      Layer 1 — Primary offensive scores, GC-adjusted when use_gc=True (Fix 1)
      Layer 2 — K% and BB% (non-contact plate appearance outcomes)
      Layer 3 — Pitcher grade
      Layer 4 — Historical matchup AVG/PA (BallPark Pal)
      Layer 5 — Recent XB rate (7-day 2B+3B/G from pybaseball)
      Layer 6 — Recent hit rate (7-day H/G — cold hitter signal for Hit Under)
      Layer 7 — Statcast contact quality (Barrel%, HH%, AvgEV, xSLG, xBA, xwOBA)
      Layer 8 — vs Grade + park factor (matchup context)
      Layer 9 — Game conditions suppression (Fix 2) — pitcher/game environment today

    Fix 1: When use_gc=True, use Hit_Score_gc/XB_Score_gc/HR_Score_gc as the
           primary Layer 1 inputs. These already encode park, weather, and game
           environment from compute_game_condition_scores(). Falls back to base
           scores if GC variants not in df.

    Fix 2: Layer 9 adds a direct gc_suppression bonus from today's GC data:
           low gc_hits20 + low gc_runs10 + high gc_k20 + high gc_qs = pitcher day.
           For XB/HR unders: also factors in low gc_hr4.
           Applied to all four under types, ±6 pts max.

    All Statcast signals neutral (0.0) when NaN. All form signals neutral when
    player not in map or <3 games. Hist signal neutral when PA < under_hist_min_pa.
    """
    df       = df.copy()
    cfg      = CONFIG
    form_map = form_map or {}

    for col in ['Hit_Score','Single_Score','XB_Score','HR_Score']:
        if col not in df.columns:
            df[col] = 50.0

    # ── FIX 1: Use GC-adjusted scores as Layer 1 primary ─────────────────────
    # GC scores incorporate park, weather, game total, and pitcher environment.
    # Inverting GC scores gives a more accurate "how bad is this matchup today"
    # signal than inverting base scores. Falls back gracefully when not available.
    def _gc_or_base(gc_col: str, base_col: str) -> pd.Series:
        if use_gc and gc_col in df.columns:
            return pd.to_numeric(df[gc_col], errors='coerce').fillna(
                pd.to_numeric(df[base_col], errors='coerce').fillna(50.0)
            ).clip(0, 100)
        return df[base_col].clip(0, 100)

    hit    = _gc_or_base('Hit_Score_gc',    'Hit_Score')
    xb     = _gc_or_base('XB_Score_gc',     'XB_Score')
    hr     = _gc_or_base('HR_Score_gc',     'HR_Score')
    # Single stays as base — no GC variant changes its meaning for unders
    single = df['Single_Score'].clip(0, 100)

    # ── Raw probability columns ───────────────────────────────────────────────
    k  = pd.to_numeric(df.get('p_k',  0), errors='coerce').fillna(0)
    bb = pd.to_numeric(df.get('p_bb', 0), errors='coerce').fillna(0)

    # ─────────────────────────────────────────────────────────────────────────
    # LAYER 2 — K% and BB% bonuses
    # ─────────────────────────────────────────────────────────────────────────
    k_bonus = ((k - cfg['league_k_avg']) * cfg['under_k_weight']).clip(lower=0)

    bb_xb   = ((bb - cfg['league_bb_avg']) * cfg['under_bb_weight_xb']  ).clip(lower=0)
    bb_tb15 = ((bb - cfg['league_bb_avg']) * cfg['under_bb_weight_tb15']).clip(lower=0)
    bb_tb05 = ((bb - cfg['league_bb_avg']) * cfg['under_bb_weight_tb05']).clip(lower=0)
    bb_hit  = ((bb - cfg['league_bb_avg']) * cfg['under_bb_weight_hit'] ).clip(lower=0)

    # ─────────────────────────────────────────────────────────────────────────
    # LAYER 3 — Pitcher grade bonus
    # ─────────────────────────────────────────────────────────────────────────
    def _pgbonus(grade):
        return (cfg['under_pitcher_bonus'] if grade == 'A+' else
                cfg['under_pitcher_a']     if grade == 'A'  else 0.0)

    p_bonus = df['pitch_grade'].apply(_pgbonus) \
              if 'pitch_grade' in df.columns \
              else pd.Series(0.0, index=df.index)

    # ─────────────────────────────────────────────────────────────────────────
    # LAYER 4 — Historical matchup AVG/PA
    # ─────────────────────────────────────────────────────────────────────────
    hist_min_pa = cfg['under_hist_min_pa']
    hist_weight = cfg['under_hist_weight']
    hist_max    = cfg['under_hist_max_adj']
    league_avg  = cfg['league_avg']

    pa_col  = pd.to_numeric(df.get('PA',  0), errors='coerce').fillna(0)
    avg_col = pd.to_numeric(df.get('AVG', 0), errors='coerce').fillna(0)

    hist_raw  = (league_avg - avg_col) * hist_weight
    hist_base = hist_raw.where(pa_col >= hist_min_pa, 0.0).clip(-hist_max, hist_max)

    hist_xb   = hist_base * 0.6
    hist_tb15 = hist_base * 0.8
    hist_tb05 = hist_base * 1.0
    hist_hit  = hist_base * 1.2

    # ─────────────────────────────────────────────────────────────────────────
    # LAYER 5 — Recent XB rate (7-day 2B+3B/G)
    # ─────────────────────────────────────────────────────────────────────────
    xb_rate_lg  = cfg['under_xb_rate_lg_avg']
    xb_rate_w   = cfg['under_xb_rate_weight']
    xb_rate_max = cfg['under_xb_rate_max_adj']

    def _xb_rate_sig(batter: str) -> float:
        info = form_map.get(batter, {})
        if not info or info.get('games', 0) < 3:
            return 0.0
        rate = info.get('xb_rate', xb_rate_lg)
        return float(np.clip((xb_rate_lg - rate) * xb_rate_w,
                             -xb_rate_max, xb_rate_max))

    xb_rate_adj = df['Batter'].apply(_xb_rate_sig)

    # ─────────────────────────────────────────────────────────────────────────
    # LAYER 6 — Recent hit rate (7-day H/G)
    # ─────────────────────────────────────────────────────────────────────────
    hit_rate_lg  = cfg['under_hit_rate_lg_avg']
    hit_rate_w   = cfg['under_hit_rate_weight']
    hit_rate_max = cfg['under_hit_rate_max_adj']

    def _hit_rate_sig(batter: str) -> float:
        info = form_map.get(batter, {})
        if not info or info.get('games', 0) < 3:
            return 0.0
        rate = info.get('hit_rate', hit_rate_lg)
        return float(np.clip((hit_rate_lg - rate) * hit_rate_w,
                             -hit_rate_max, hit_rate_max))

    hit_rate_adj = df['Batter'].apply(_hit_rate_sig)

    # ─────────────────────────────────────────────────────────────────────────
    # LAYER 7 — Statcast contact quality
    # ─────────────────────────────────────────────────────────────────────────
    def _sc(col: str, lg_val: float) -> pd.Series:
        if col not in df.columns:
            return pd.Series(lg_val, index=df.index)
        return pd.to_numeric(df[col], errors='coerce').fillna(lg_val)

    barrel = _sc('Barrel%', cfg['league_barrel_pct'])
    hh     = _sc('HH%',     cfg['league_hh_pct'])
    avgev  = _sc('AvgEV',   cfg['league_avgev'])
    xslg   = _sc('xSLG',    cfg['league_xslg'])
    xba    = _sc('xBA',     cfg['league_xba'])
    xwoba  = _sc('xwOBA',   cfg['league_xwoba'])

    barrel_adj = ((cfg['league_barrel_pct'] - barrel) * cfg['under_barrel_weight']
                  ).clip(-cfg['under_barrel_max'], cfg['under_barrel_max'])
    hh_adj     = ((cfg['league_hh_pct'] - hh) * cfg['under_hh_weight']
                  ).clip(-cfg['under_hh_max'], cfg['under_hh_max'])
    avgev_adj  = ((cfg['league_avgev'] - avgev) * cfg['under_avgev_weight']
                  ).clip(-cfg['under_avgev_max'], cfg['under_avgev_max'])
    xslg_adj   = ((cfg['league_xslg'] - xslg) * cfg['under_xslg_weight']
                  ).clip(-cfg['under_xslg_max'], cfg['under_xslg_max'])
    xba_adj    = ((cfg['league_xba']   - xba)   * cfg['under_xba_weight']
                  ).clip(-cfg['under_xba_max'], cfg['under_xba_max'])
    xwoba_adj  = ((cfg['league_xwoba'] - xwoba) * cfg['under_xwoba_weight']
                  ).clip(-cfg['under_xwoba_max'], cfg['under_xwoba_max'])

    # ─────────────────────────────────────────────────────────────────────────
    # LAYER 8 — vs Grade + park XB factor
    # ─────────────────────────────────────────────────────────────────────────
    vs_grade   = pd.to_numeric(df.get('vs Grade', 0), errors='coerce').fillna(0)
    vsgrade_adj = ((-vs_grade).clip(lower=0) * cfg['under_vsgrade_weight']
                   ).clip(0, cfg['under_vsgrade_max'])

    xb_boost  = pd.to_numeric(df.get('xb_boost', 0), errors='coerce').fillna(0)
    parkxb_pen = (xb_boost * cfg['under_parkxb_weight']
                  ).clip(0, cfg['under_parkxb_max'])

    # ─────────────────────────────────────────────────────────────────────────
    # LAYER 9 — FIX 2: Game conditions suppression signal
    # ─────────────────────────────────────────────────────────────────────────
    # Computes a per-row GC suppression bonus based on today's game environment.
    # Positive = pitcher-friendly conditions = good for unders.
    # Negative = hitter-friendly conditions = bad for unders.
    # Only fires when GC columns are present; gracefully returns 0 otherwise.
    gc_max = cfg['under_gc_max']

    _GC_COLS = ['gc_hits20','gc_runs10','gc_k20','gc_qs','gc_hr4']
    has_gc_data = use_gc and all(c in df.columns for c in _GC_COLS)

    if has_gc_data:
        gc_hits = pd.to_numeric(df['gc_hits20'], errors='coerce').fillna(cfg['gc_hits20_anchor'])
        gc_runs = pd.to_numeric(df['gc_runs10'], errors='coerce').fillna(cfg['gc_runs10_anchor'])
        gc_k    = pd.to_numeric(df['gc_k20'],    errors='coerce').fillna(cfg['gc_k20_anchor'])
        gc_qs   = pd.to_numeric(df['gc_qs'],     errors='coerce').fillna(cfg['gc_qs_anchor'])
        gc_hr4  = pd.to_numeric(df['gc_hr4'],    errors='coerce').fillna(cfg['gc_hr4_anchor'])

        hits_sig = (cfg['gc_hits20_anchor'] - gc_hits) * cfg['under_gc_hits_weight']
        runs_sig = (cfg['gc_runs10_anchor'] - gc_runs) * cfg['under_gc_runs_weight']
        k_sig    = (gc_k  - cfg['gc_k20_anchor']) * cfg['under_gc_k_weight']
        qs_sig   = (gc_qs - cfg['gc_qs_anchor'])  * cfg['under_gc_qs_weight']
        hr_sig   = (cfg['gc_hr4_anchor'] - gc_hr4) * cfg['under_gc_hr_weight']

        gc_general    = (hits_sig + runs_sig + k_sig + qs_sig).clip(-gc_max, gc_max)
        gc_power_supp = (hits_sig + runs_sig + k_sig + qs_sig + hr_sig).clip(-gc_max, gc_max)
    else:
        gc_general    = pd.Series(0.0, index=df.index)
        gc_power_supp = pd.Series(0.0, index=df.index)

    # ─────────────────────────────────────────────────────────────────────────
    # LAYER 10 — Batting order position
    # ─────────────────────────────────────────────────────────────────────────
    # Late-order batters (8-9) get fewer quality at-bats, face fresh pitchers
    # more often, and are typically weaker offensive players.
    # → Small bonus for under targets (they're less likely to accumulate bases).
    # Cleanup hitters (3-5) see the most pitches with runners on, pitchers work
    # carefully, more walks — neutral to slight penalty for under targets.
    # Applied uniformly to all under types, small cap (±2 pts max).
    order_adj = pd.Series(0.0, index=df.index)
    if '_order_pos' in df.columns:
        pos = pd.to_numeric(df['_order_pos'], errors='coerce')
        # Slots 8-9: typically weakest bats → under bonus
        order_adj = order_adj.where(~(pos.isin([8, 9])), order_adj + 1.5)
        # Slots 1-2: table-setters, high OBP, walk-prone → mild under bonus
        order_adj = order_adj.where(~(pos.isin([1, 2])), order_adj + 0.5)
        # Slots 3-5: cleanup, most dangerous offensive spots → slight under penalty
        order_adj = order_adj.where(~(pos.isin([3, 4, 5])), order_adj - 1.0)
        order_adj = order_adj.clip(-2.0, 2.0)

    # ─────────────────────────────────────────────────────────────────────────
    # LAYER 11 — Platoon split
    # ─────────────────────────────────────────────────────────────────────────
    # Same-hand matchups (RHB vs RHP or LHB vs LHP) suppress batting averages
    # historically. Opposite hand = platoon advantage = batter sees ball better.
    # For unders: same-hand = bonus (batter disadvantaged = fewer hits/XBs).
    # Only fires when both pitcher hand and batter hand are known.
    # Batter hand data wires in when MLB roster lookup activates.
    # Conservative: pitcher hand is known (from mlb_api), batter hand not yet
    # programmatically fetched — so we apply a mild pitcher-hand-only signal:
    # LHP facing the lineup = generally favorable for under (LHPs suppress AVG
    # across the slate because most batters are RHH and see fewer LHPs).
    platoon_adj = pd.Series(0.0, index=df.index)
    if '_pitcher_hand' in df.columns:
        # LHP bonus: league-wide RHH AVG vs LHP is ~.010 below vs RHP
        lhp_mask     = df['_pitcher_hand'] == 'L'
        platoon_adj  = platoon_adj.where(~lhp_mask, platoon_adj + 0.8)
        platoon_adj  = platoon_adj.clip(-1.5, 1.5)

    # ─────────────────────────────────────────────────────────────────────────
    # FINAL SCORES — all 9 layers
    # ─────────────────────────────────────────────────────────────────────────

    # ── XB Under ─────────────────────────────────────────────────────────────
    df['Under_XB_Score'] = (
        (100 - xb)  * 0.42      # L1
      + (100 - hr)  * 0.22      # L1
      + (100 - hit) * 0.08      # L1
      + k_bonus + bb_xb         # L2
      + p_bonus                  # L3
      + hist_xb                  # L4
      + xb_rate_adj              # L5
      + barrel_adj               # L7
      + hh_adj                   # L7
      + avgev_adj                # L7
      + xslg_adj                 # L7
      + vsgrade_adj              # L8
      - parkxb_pen               # L8
      + gc_power_supp            # L9
      + order_adj                # L10
      + platoon_adj              # L11
    ).clip(0, 100).round(1)

    # ── TB Under 1.5 ─────────────────────────────────────────────────────────
    single_profile_bonus = ((single - xb) * 0.15).clip(lower=0, upper=5)
    df['Under_TB15_Score'] = (
        (100 - xb)  * 0.45      # L1
      + (100 - hr)  * 0.28      # L1
      + single_profile_bonus
      + k_bonus + bb_tb15       # L2
      + p_bonus                  # L3
      + hist_tb15                # L4
      + xb_rate_adj * 0.7       # L5
      + xslg_adj * 0.8          # L7
      + barrel_adj * 0.5        # L7
      + vsgrade_adj              # L8
      - parkxb_pen * 0.5        # L8
      + gc_power_supp * 0.8     # L9
      + order_adj                # L10
      + platoon_adj              # L11
    ).clip(0, 100).round(1)

    # ── TB Under 0.5 ─────────────────────────────────────────────────────────
    df['Under_TB05_Score'] = (
        (100 - hit) * 0.40      # L1
      + (100 - xb)  * 0.28      # L1
      + (100 - hr)  * 0.22      # L1
      + k_bonus * 1.2 + bb_tb05 # L2
      + p_bonus                  # L3
      + hist_tb05                # L4
      + hit_rate_adj             # L6
      + xba_adj   * 0.7         # L7
      + xwoba_adj * 0.5         # L7
      + vsgrade_adj              # L8
      + gc_general               # L9
      + order_adj                # L10
      + platoon_adj              # L11
    ).clip(0, 100).round(1)

    # ── Hit Under ─────────────────────────────────────────────────────────────
    df['Under_Hit_Score'] = (
        (100 - hit) * 0.45      # L1
      + k_bonus * 1.8 + bb_hit  # L2
      + p_bonus                  # L3
      + hist_hit                 # L4
      + hit_rate_adj * 1.2      # L6
      + xba_adj                  # L7
      + xwoba_adj * 0.7         # L7
      + vsgrade_adj * 1.2       # L8
      + gc_general * 1.1        # L9
      + order_adj                # L10
      + platoon_adj              # L11
    ).clip(0, 100).round(1)

    # ── Disqualification flags ─────────────────────────────────────────────────
    df['_disq_xb']   = (hr  > cfg['under_xb_disq_hr']) | \
                       (hit > cfg['under_xb_disq_hit'])
    df['_disq_tb15'] = (xb  > cfg['under_xb_disq_hr']) | \
                       (hr  > cfg['under_xb_disq_hr'])
    df['_disq_tb05'] = (hit > cfg['under_tb_disq_any']) | \
                       (xb  > cfg['under_tb_disq_any']) | \
                       (hr  > cfg['under_tb_disq_any'])
    df['_disq_hit']  = hit > cfg['under_hit_disq_hit']

    return df


# ─────────────────────────────────────────────────────────────────────────────
# UNDER TIER LABEL (inverted — lower offensive scores = better)
# ─────────────────────────────────────────────────────────────────────────────

def _under_tier(score: float) -> tuple[str, str]:
    """Return (label, color) for an Under_Score. Higher = better under."""
    if score >= 75: return "ELITE",    "#4ade80"
    if score >= 60: return "STRONG",   "#a3e635"
    if score >= 45: return "GOOD",     "#fbbf24"
    if score >= 30: return "MODERATE", "#fb923c"
    return             "RISKY",    "#f87171"


# ─────────────────────────────────────────────────────────────────────────────
# DISQUALIFICATION REASON STRING
# ─────────────────────────────────────────────────────────────────────────────

def _disq_reason(row: pd.Series, target: str) -> str:
    cfg = CONFIG
    reasons = []
    if target == 'xb':
        hr  = float(row.get('HR_Score',  0) or 0)
        hit = float(row.get('Hit_Score', 0) or 0)
        if hr  > cfg['under_xb_disq_hr']:
            reasons.append(f"HR={hr:.0f} (can still go yard)")
        if hit > cfg['under_xb_disq_hit']:
            reasons.append(f"Hit={hit:.0f} (high contact vol)")
    elif target == 'tb15':
        xb = float(row.get('XB_Score', 0) or 0)
        hr = float(row.get('HR_Score', 0) or 0)
        if xb > cfg['under_xb_disq_hr']:
            reasons.append(f"XB={xb:.0f} (likely extra bases)")
        if hr > cfg['under_xb_disq_hr']:
            reasons.append(f"HR={hr:.0f} (4 bases = loses 1.5)")
    elif target == 'tb05':
        for sc, lbl in [('Hit_Score','Hit'),('XB_Score','XB'),('HR_Score','HR')]:
            val = float(row.get(sc, 0) or 0)
            if val > cfg['under_tb_disq_any']:
                reasons.append(f"{lbl}={val:.0f}")
    elif target == 'hit':
        hit = float(row.get('Hit_Score', 0) or 0)
        if hit > cfg['under_hit_disq_hit']:
            reasons.append(f"Hit={hit:.0f}")
    return ", ".join(reasons)


# ─────────────────────────────────────────────────────────────────────────────
# UNDER SIDEBAR FILTERS
# ─────────────────────────────────────────────────────────────────────────────

def build_under_filters(df: pd.DataFrame) -> dict:
    """
    Sidebar filters for the Under Targets page.
    Mirrors the main Predictor filters — same lineup/team/exclusion controls,
    different target selector (XB / TB / Hit under).
    """
    st.sidebar.title("🔻 Under Target Filters")
    st.sidebar.markdown("---")
    filters = {}

    # ── Under type ────────────────────────────────────────────────────────────
    st.sidebar.markdown("### 🎯 Under Type")
    under_map = {
        "🔻 XB Under — No Extra Bases (doubles/triples)":  "xb",
        "📊 TB Under 1.5 — Under 1.5 Total Bases":         "tb15",
        "📉 TB Under 0.5 — No Bases At All":               "tb05",
        "❌ Hit Under — No Hit (0.5 line)":                 "hit",
    }
    u_label            = st.sidebar.selectbox("Choose Under Target", list(under_map.keys()))
    filters['under']   = under_map[u_label]
    filters['under_label'] = u_label

    score_col_map = {
        'xb':   'Under_XB_Score',
        'tb15': 'Under_TB15_Score',
        'tb05': 'Under_TB05_Score',
        'hit':  'Under_Hit_Score',
    }
    disq_col_map = {
        'xb':   '_disq_xb',
        'tb15': '_disq_tb15',
        'tb05': '_disq_tb05',
        'hit':  '_disq_hit',
    }
    filters['under_score_col'] = score_col_map[filters['under']]
    filters['under_disq_col']  = disq_col_map[filters['under']]

    # ── Show disqualified players ─────────────────────────────────────────────
    filters['show_disq'] = st.sidebar.toggle(
        "Show disqualified players",
        value=False,
        help="Disqualified = player has an offsetting score high enough to still "
             "accumulate bases through another route. ON = show with ⚠️ warning."
    )

    # ── Park / GC ─────────────────────────────────────────────────────────────
    st.sidebar.markdown("### 🏟️ Park Adjustment")
    filters['use_park'] = st.sidebar.toggle("Include Park Factors", value=True)
    st.sidebar.markdown("### 🌦️ Game Conditions")
    filters['use_gc'] = st.sidebar.toggle("🌦️ Game Conditions Weight", value=True)

    # ── Lineup ────────────────────────────────────────────────────────────────
    st.sidebar.markdown("### 📋 Lineup")
    filters['starters_only']  = st.sidebar.checkbox("Starters only", value=False)
    filters['confirmed_only'] = st.sidebar.toggle(
        "✅ Confirmed lineups only", value=False,
        help="Only show batters in a confirmed batting order."
    )

    # ── Stat filters (inverted for unders) ────────────────────────────────────
    st.sidebar.markdown("### 📊 Filters")
    filters['min_k'] = st.sidebar.slider(
        "Min K Prob % (higher = better under)", 0.0, 50.0, 15.0, 0.5,
        help="Focus on batters facing high strikeout matchups"
    )
    filters['min_bb'] = st.sidebar.slider(
        "Min BB Prob % (higher = more walks = better under)", 0.0, 20.0, 0.0, 0.5,
        help="Walks = 0 bases/hits. High walk rate is one of the strongest under signals."
    )
    filters['max_hit_prob'] = st.sidebar.slider(
        "Max Hit Prob % (lower = better under)", 0.0, 50.0, 35.0, 0.5,
        help="Exclude players with high overall hit probability"
    )
    filters['max_vs'] = st.sidebar.slider(
        "Max vs Grade (lower = weaker matchup)", -10, 10, 5, 1,
        help="Target batters in unfavorable pitcher matchups"
    )

    # ── Team filters ──────────────────────────────────────────────────────────
    st.sidebar.markdown("### 🏟️ Team Filters")
    all_teams = sorted(df['Team'].unique().tolist()) if df is not None else []
    filters['include_teams'] = st.sidebar.multiselect("Include Only Teams", options=all_teams)
    filters['exclude_teams'] = st.sidebar.multiselect("Exclude Teams",       options=all_teams)

    # ── Exclusions ────────────────────────────────────────────────────────────
    st.sidebar.markdown("### 🚫 Player Exclusions")
    if 'excluded_players' not in st.session_state:
        st.session_state.excluded_players = []
    all_players = sorted(df['Batter'].unique().tolist()) if df is not None else []
    excl = st.sidebar.multiselect(
        "Players NOT Playing Today",
        options=all_players,
        default=st.session_state.excluded_players,
        key="under_exclusions",
    )
    st.session_state.excluded_players = excl
    filters['excluded_players'] = excl

    # ── Display ───────────────────────────────────────────────────────────────
    st.sidebar.markdown("### 🔢 Display")
    filters['result_count'] = st.sidebar.selectbox("Show Top N", [5,10,15,20,25,30,"All"], index=2)

    return filters


# ─────────────────────────────────────────────────────────────────────────────
# APPLY UNDER FILTERS
# ─────────────────────────────────────────────────────────────────────────────

def apply_under_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """Filter and sort the df for under candidates."""
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    # Standard exclusions
    excl = filters.get('excluded_players', [])
    if excl:
        out = out[~out['Batter'].isin(excl)]

    if filters.get('starters_only') and 'Starter' in out.columns:
        out = out[out['Starter'] == 1]

    if filters.get('include_teams'):
        out = out[out['Team'].isin(filters['include_teams'])]
    if filters.get('exclude_teams'):
        out = out[~out['Team'].isin(filters['exclude_teams'])]

    # Under-specific stat filters
    if 'p_k' in out.columns:
        out = out[pd.to_numeric(out['p_k'], errors='coerce').fillna(0) >= filters['min_k']]
    if 'p_bb' in out.columns and filters.get('min_bb', 0) > 0:
        out = out[pd.to_numeric(out['p_bb'], errors='coerce').fillna(0) >= filters['min_bb']]
    if 'total_hit_prob' in out.columns:
        out = out[pd.to_numeric(out['total_hit_prob'], errors='coerce').fillna(100)
                  <= filters['max_hit_prob']]
    if 'vs Grade' in out.columns:
        out = out[pd.to_numeric(out['vs Grade'], errors='coerce').fillna(10)
                  <= filters['max_vs']]

    # Disqualification filter
    disq_col = filters['under_disq_col']
    if not filters.get('show_disq') and disq_col in out.columns:
        out = out[~out[disq_col]]

    # ── Profile-prioritized sort for under targets ────────────────────────────
    # When show_disq=True, disqualified players are visible but always ranked
    # below non-disqualified players — regardless of their Under_Score.
    # This ensures users see the cleanest candidates first.
    sc  = filters['under_score_col']
    disq_col = filters['under_disq_col']
    if sc in out.columns:
        if filters.get('show_disq') and disq_col in out.columns:
            out['_disq_rank'] = out[disq_col].astype(int)   # 0=clean, 1=disqualified
            out = out.sort_values(
                ['_disq_rank', sc],
                ascending=[True, False],
                na_position='last'
            ).drop(columns=['_disq_rank'])
        else:
            out = out.sort_values(sc, ascending=False, na_position='last')

    n = filters['result_count']
    if n != "All":
        out = out.head(int(n))

    return out


# ─────────────────────────────────────────────────────────────────────────────
# RENDER BEST UNDERS (top cards, like Today's Best)
# ─────────────────────────────────────────────────────────────────────────────

def _render_under_top_cards(df: pd.DataFrame, filters: dict):
    """Show top 3 under candidates across the full (exclusion-filtered) slate."""
    if df.empty:
        return

    sc      = filters['under_score_col']
    disq_col= filters['under_disq_col']
    target  = filters['under']

    # Only clean (non-disqualified) players for top cards
    clean = df[~df[disq_col]] if disq_col in df.columns else df
    if clean.empty:
        clean = df  # fallback

    clean = clean.sort_values(sc, ascending=False)

    icons = {'xb': '🔻', 'tb': '📊', 'hit': '❌'}
    icon  = icons.get(target, '🔻')

    cards_html = '<div class="score-grid">'
    for i, (_, row) in enumerate(clean.head(3).iterrows()):
        score     = float(row.get(sc, 0) or 0)
        tier, tc  = _under_tier(score)
        hit_val   = float(row.get('Hit_Score',0) or 0)
        xb_val    = float(row.get('XB_Score', 0) or 0)
        hr_val    = float(row.get('HR_Score', 0) or 0)
        k_val     = float(row.get('p_k',      0) or 0)
        gph       = grade_pill(str(row.get('pitch_grade','B')))

        cards_html += f"""
        <div class="scard scard-hr" style="border-color:#8b5cf6">
          <div class="sc-type" style="color:#8b5cf6">
            <span>{icon} UNDER #{i+1}</span> — {filters['under_label'].split('—')[0].strip()}
          </div>
          <div class="sc-name">{row['Batter']}</div>
          <div class="sc-meta" style="font-size:.7rem">
            {row.get('Team','?')} vs {row.get('Pitcher','?')} {gph}
          </div>
          <div class="sc-score" style="color:#8b5cf6">{score:.1f}</div>
          <div style="margin-top:.4rem">
            <span style="font-size:.62rem;padding:1px 6px;border-radius:20px;
              background:{tc}22;color:{tc};font-weight:700;
              font-family:'JetBrains Mono',monospace">{tier}</span>
          </div>
          <div style="font-size:.68rem;color:#64748b;margin-top:.3rem;line-height:1.5">
            Hit={hit_val:.0f} · XB={xb_val:.0f} · HR={hr_val:.0f} · K%={k_val:.1f}%
          </div>
        </div>"""

    cards_html += '</div>'
    st.markdown(cards_html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# RENDER UNDER TABLE
# ─────────────────────────────────────────────────────────────────────────────

def _render_under_table(filtered_df: pd.DataFrame, filters: dict):
    if filtered_df.empty:
        st.warning("⚠️ No players match your filters. Try relaxing thresholds.")
        return

    target  = filters['under']
    sc      = filters['under_score_col']
    disq_col= filters['under_disq_col']
    cfg     = CONFIG

    disp = filtered_df.copy()

    # Compute is-disqualified for display (may include them with warning)
    disp['Disq'] = disp[disq_col].map({True: '⚠️', False: '✅'}) \
                   if disq_col in disp.columns else '✅'

    # Rename Under_Score for display
    label_map = {
        'Under_XB_Score':   '🔻 XB Under',
        'Under_TB15_Score': '📊 TB Under 1.5',
        'Under_TB05_Score': '📉 TB Under 0.5',
        'Under_Hit_Score':  '❌ Hit Under',
    }

    col_order = ['Batter','Team','Pitcher','pitch_grade','Disq',
                 sc,
                 'prop_tb_line','prop_tb_under_odds','prop_tb_over_odds',
                 'prop_hr_odds',
                 'Hit_Score','XB_Score','HR_Score',
                 'p_k','p_bb','total_hit_prob','p_1b','p_xb','p_hr',
                 'vs Grade',
                 'PA','H','AVG']    # historical matchup data — always last

    rename   = {
        sc:            label_map.get(sc, 'Under Score'),
        'pitch_grade': 'P.Grd ↑',    # ↑ = higher grade = better for under
        'p_k':         'K%',
        'p_bb':        'BB%',
        'total_hit_prob':'Hit%',
        'p_1b':        '1B%',
        'p_xb':        'XB%',
        'p_hr':        'HR%',
        'vs Grade':    'vsPit',
        'Hit_Score':   '🎯 Hit',
        'XB_Score':    '🔥 XB',
        'HR_Score':    '💣 HR',
        'Disq':        'Status',
        'prop_tb_line':       'TB Line',
        'prop_tb_under_odds': 'TB Under',
        'prop_tb_over_odds':  'TB Over',
        'prop_hr_odds':       'HR Odds',
        'PA':          'Hist PA',
        'H':           'Hist H',
        'AVG':         'Hist AVG',
    }

    # Add market edge badge column when prop data available
    has_props = 'prop_tb_under_odds' in disp.columns and \
                disp['prop_tb_under_odds'].astype(bool).any()
    if has_props:
        try:
            from prop_odds import edge_label
            under_score_col = sc
            disp['Market Edge'] = disp.apply(
                lambda r: edge_label(
                    float(r.get(under_score_col, 0) or 0),
                    float(r.get('prop_tb_under_pct', 0) or 0)
                ), axis=1
            )
            col_order_extra = ['Market Edge']
        except Exception:
            col_order_extra = []
    else:
        col_order_extra = []

    existing = [c for c in col_order if c in disp.columns] + \
               [c for c in col_order_extra if c in disp.columns]
    out_df   = disp[existing].rename(columns=rename)

    # ── Under Tier column — insert BEFORE styler is created ───────────────────
    # Must happen before out_df.style.format() — mutating after styler creation
    # causes pandas to crash with a format error on the new string column.
    under_label = label_map.get(sc, 'Under Score')
    if under_label in out_df.columns:
        u_tier = lambda s: (
            "🟢 ELITE"    if s >= 75 else
            "🟡 STRONG"   if s >= 60 else
            "🟠 GOOD"     if s >= 45 else
            "🔴 MODERATE" if s >= 30 else "⚫ WEAK"
        )
        tier_vals = out_df[under_label].apply(
            lambda x: u_tier(float(x)) if pd.notna(x) else "—"
        )
        insert_at = out_df.columns.get_loc(under_label) + 1
        out_df    = out_df.copy()          # decouple from disp before insert
        out_df.insert(insert_at, 'Tier', tier_vals)

    _text_cols = {'Tier', 'Status', 'Market Edge', 'TB Line', 'TB Under',
                  'TB Over', 'HR Odds', 'P.Grd', 'P.Grd ↑', 'Batter', 'Team', 'Pitcher'}

    fmt = {}
    for cn in out_df.columns:
        if cn in _text_cols:
            continue
        if cn in ['K%','BB%','Hit%','1B%','XB%','HR%']:
            fmt[cn] = "{:.1f}%"
        elif cn in ['🎯 Hit','🔥 XB','💣 HR', under_label]:
            fmt[cn] = "{:.1f}"
        elif cn == 'vsPit':
            fmt[cn] = "{:.0f}"
        elif cn == 'Hist AVG':
            fmt[cn] = "{:.3f}"
        elif cn == 'Hist PA':
            fmt[cn] = "{:.0f}"

    styled = out_df.style.format(fmt, na_rep="—")

    # Under_Score gradient
    if under_label in out_df.columns:
        try:
            styled = styled.background_gradient(
                subset=[under_label], cmap='RdYlGn', vmin=20, vmax=80
            )
        except Exception:
            pass

    # Offensive scores: reversed gradient (low = good for under)
    for col, cmap in [('🎯 Hit','RdYlGn_r'),('🔥 XB','RdYlGn_r'),('💣 HR','RdYlGn_r')]:
        if col in out_df.columns:
            try:
                styled = styled.background_gradient(subset=[col], cmap=cmap, vmin=0, vmax=100)
            except Exception:
                pass

    if 'K%' in out_df.columns:
        try:
            styled = styled.background_gradient(subset=['K%'], cmap='Greens', vmin=10, vmax=40)
        except Exception:
            pass

    if 'BB%' in out_df.columns:
        try:
            styled = styled.background_gradient(subset=['BB%'], cmap='Greens', vmin=5, vmax=20)
        except Exception:
            pass

    if 'P.Grd' in out_df.columns:
        styled = styled.map(style_grade_cell, subset=['P.Grd'])

    # Hist AVG: reversed gradient — lower AVG = better under candidate (greener)
    if 'Hist AVG' in out_df.columns:
        try:
            styled = styled.background_gradient(
                subset=['Hist AVG'], cmap='RdYlGn_r', vmin=0.100, vmax=0.400
            )
        except Exception:
            pass

    # ── Column config ─────────────────────────────────────────────────────────
    col_cfg: dict = {}
    try:
        import streamlit as _st
        CC = _st.column_config
        col_cfg['Batter'] = CC.TextColumn("Batter", width="medium")
        col_cfg['Team']   = CC.TextColumn("Team",   width="small")
        col_cfg['Status'] = CC.TextColumn("Status", width="small",
                                          help="✅ = clean candidate · ⚠️ = disqualified (offsetting high score)")
        col_cfg['Tier']   = CC.TextColumn("Tier", width="small",
                                          help="Under Score tier: ELITE ≥75 · STRONG ≥60 · GOOD ≥45")
        if 'P.Grd ↑' in out_df.columns or 'P.Grd' in out_df.columns:
            pgrd_col = 'P.Grd ↑' if 'P.Grd ↑' in out_df.columns else 'P.Grd'
            col_cfg[pgrd_col] = CC.TextColumn(
                pgrd_col, width="small",
                help="Pitcher grade. A+/A = GOOD for unders (elite pitchers suppress hits). "
                     "D/C = BAD for unders (weak pitchers give up bases freely)."
            )
        if under_label in out_df.columns:
            col_cfg[under_label] = CC.NumberColumn(
                under_label, format="%.1f", min_value=0, max_value=100,
                help="Under Score 0–100. Higher = stronger under candidate."
            )
        if 'Market Edge' in out_df.columns:
            col_cfg['Market Edge'] = CC.TextColumn(
                "Market Edge", width="small",
                help="⚡ EDGE = model likes under more than market. ✅ CONFIRMED = both agree."
            )
        for odds_col in ['TB Under','TB Over','HR Odds']:
            if odds_col in out_df.columns:
                col_cfg[odds_col] = CC.TextColumn(odds_col, width="small")
        if 'TB Line' in out_df.columns:
            col_cfg['TB Line'] = CC.TextColumn("TB Line", width="small",
                                               help="Sportsbook line: 0.5 or 1.5 total bases")
        if 'Hist PA' in out_df.columns:
            col_cfg['Hist PA'] = CC.NumberColumn(
                "Hist PA", format="%d", min_value=0,
                help="Plate appearances vs this pitcher type (BallPark Pal). "
                     "≥5 PA = signal is meaningful. <5 = small sample."
            )
        if 'Hist H' in out_df.columns:
            col_cfg['Hist H'] = CC.NumberColumn(
                "Hist H", format="%d", min_value=0,
                help="Hits in those plate appearances vs this pitcher type."
            )
        if 'Hist AVG' in out_df.columns:
            col_cfg['Hist AVG'] = CC.NumberColumn(
                "Hist AVG", format="%.3f",
                help="Batting average vs this pitcher type. "
                     "Below .245 (league avg) = historically struggles here = under signal."
            )
    except Exception:
        col_cfg = {}

    st.dataframe(styled, use_container_width=True,
                 column_config=col_cfg or None, hide_index=False)

    # Legend
    disq_note = {
        'xb':   f"Disqualified if HR_Score>{cfg['under_xb_disq_hr']:.0f} or Hit_Score>{cfg['under_xb_disq_hit']:.0f}",
        'tb15': f"Disqualified if XB_Score>{cfg['under_xb_disq_hr']:.0f} or HR_Score>{cfg['under_xb_disq_hr']:.0f} — singles are FINE for this line",
        'tb05': f"Disqualified if ANY of Hit/XB/HR_Score>{cfg['under_tb_disq_any']:.0f}",
        'hit':  f"Disqualified if Hit_Score>{cfg['under_hit_disq_hit']:.0f}",
    }.get(target, "")

    st.markdown(
        f'<div style="background:#0f1923;border:1px solid #1e2d3d;border-radius:8px;'
        f'padding:.6rem 1rem;font-size:.74rem;color:#64748b;margin-top:.4rem;line-height:1.7">'
        f'<b style="color:#94a3b8">Under Score</b> = weighted sum of (100 - offensive scores) '
        f'+ K% bonus + pitcher grade bonus. Higher = better under candidate.<br>'
        f'<b style="color:#94a3b8">⚠️ Disqualified:</b> {disq_note} — these players can still '
        f'accumulate bases through an offsetting route. Toggle "Show disqualified" to include.<br>'
        f'<b style="color:#94a3b8">Usage:</b> Cross-reference with sportsbook line. '
        f'Low offensive scores + strong pitcher + high K% = high-confidence under candidate.'
        f'</div>',
        unsafe_allow_html=True
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PAGE
# ─────────────────────────────────────────────────────────────────────────────

def under_page(df: pd.DataFrame, filters_base: dict):
    """
    Under Targets page.

    df          — already scored slate df (from app._build_scored_df)
    filters_base — base filters from the main sidebar (exclusions etc.
                   that persist across all pages via session_state)
    """
    st.title("🔻 Under Targets")
    st.markdown(
        '<div style="background:#0f1923;border:1px solid #3730a3;border-radius:8px;'
        'padding:.65rem 1rem;margin-bottom:.75rem;font-size:.82rem;color:#a5b4fc">'
        '📖 <b>How to use:</b> Find players unlikely to accumulate bases for a specific prop type. '
        'High Under Score = strong candidate. Always verify the sportsbook line before betting — '
        'an XB Under with score 78 means nothing if the book has it at -300 already. '
        'Disqualified (⚠️) players have a high score in an offsetting category that can still '
        'produce bases through a different route.</div>',
        unsafe_allow_html=True
    )

    if df is None or df.empty:
        st.error("❌ No slate data loaded.")
        return

    # Build sidebar filters FIRST — use_gc must be known before scoring
    filters = build_under_filters(df)

    # Now compute under scores with the correct use_gc from filters
    try:
        from mlb_api import get_recent_batting_form as _get_form
        _form = _get_form(days=7)
    except Exception:
        _form = {}
    df = compute_under_scores(df, form_map=_form,
                              use_gc=filters.get('use_gc', True))

    # Apply confirmed lineup filter (same logic as main page)
    if filters.get('confirmed_only'):
        try:
            from mlb_api import get_confirmed_game_abbrs
            from config import NICK_TO_ABBR
            confirmed_abbrs = get_confirmed_game_abbrs()
            if confirmed_abbrs:
                def _game_confirmed(game_str: str) -> bool:
                    parts = str(game_str).split(' @ ')
                    if len(parts) != 2:
                        return False
                    away_abbr = NICK_TO_ABBR.get(parts[0].strip())
                    home_abbr = NICK_TO_ABBR.get(parts[1].strip())
                    return bool(away_abbr and home_abbr and
                                (away_abbr, home_abbr) in confirmed_abbrs)
                pre = len(df)
                df  = df[df['Game'].apply(_game_confirmed)]
                if len(df) < pre:
                    st.info(f"📋 {len(confirmed_abbrs)} confirmed games · "
                            f"{len(df)} batters shown")
        except Exception:
            pass

    if df.empty:
        st.warning("No players available after applying lineup filter.")
        return

    # Staleness warning
    if st.session_state.get('slate_stale'):
        slate_date = st.session_state.get('slate_date', 'unknown')
        st.markdown(
            f'<div style="background:#1c0000;border:2px solid #ef4444;border-radius:8px;'
            f'padding:.7rem 1rem;margin:.4rem 0;color:#f87171;font-size:.82rem">'
            f'⚠️ <b>Stale Data ({slate_date})</b> — today\'s slate not yet uploaded.</div>',
            unsafe_allow_html=True
        )

    # Full slate for top cards (only exclusions applied)
    slate_excl = df[~df['Batter'].isin(filters.get('excluded_players', []))]
    if filters.get('starters_only') and 'Starter' in slate_excl.columns:
        slate_excl = slate_excl[slate_excl['Starter'] == 1]
    if filters.get('include_teams'):
        slate_excl = slate_excl[slate_excl['Team'].isin(filters['include_teams'])]
    if filters.get('exclude_teams'):
        slate_excl = slate_excl[~slate_excl['Team'].isin(filters['exclude_teams'])]

    # Top cards
    st.markdown(
        '<div style="font-size:.68rem;text-transform:uppercase;letter-spacing:.1em;'
        'color:#5a7090;font-weight:700;margin:.8rem 0 .4rem;display:flex;align-items:center;gap:.5rem">'
        '🏆 BEST UNDER CANDIDATES — FULL SLATE'
        '<span style="flex:1;height:1px;background:linear-gradient(90deg,#1e2d3d,transparent);margin-left:.5rem"></span>'
        '</div>',
        unsafe_allow_html=True
    )
    _render_under_top_cards(slate_excl, filters)

    # ── Game Conditions Panel ─────────────────────────────────────────────────
    # Show today's game-level environment so users can see whether GC data
    # supports or conflicts with their under target.
    # Inverted from main predictor: LOW hits/runs/HR = ✅ for unders.
    # HIGH K% / QS% = ✅ for unders.
    _GC_DISPLAY = ['gc_hits20','gc_runs10','gc_k20','gc_qs','gc_hr4']
    if all(c in slate_excl.columns for c in _GC_DISPLAY):
        with st.expander("🌦️ Game Conditions — Under Context", expanded=False):
            st.markdown(
                '<div style="font-size:.74rem;color:#64748b;margin-bottom:.5rem">'
                '✅ = favors unders &nbsp;·&nbsp; ⚠️ = favors overs &nbsp;·&nbsp; '
                'Anchors: Hits 18.6% · Runs 28.4% · Ks 23.3% · QS 21.5% · HR 12.2%'
                '</div>',
                unsafe_allow_html=True
            )
            # Build one row per unique game
            game_rows = (slate_excl[['Game'] + _GC_DISPLAY]
                         .drop_duplicates(subset='Game')
                         .sort_values('Game'))
            cfg = CONFIG
            display_rows = []
            for _, row in game_rows.iterrows():
                def _flag_under(val, anchor, lower_good: bool) -> str:
                    """✅ when favorable for unders, ⚠️ when harmful."""
                    return "✅" if (val < anchor if lower_good else val > anchor) else "⚠️"
                display_rows.append({
                    'Game':       row['Game'],
                    '20+Hits %':  f"{_flag_under(row['gc_hits20'], cfg['gc_hits20_anchor'], True)}"
                                  f" {row['gc_hits20']:.1f}%",
                    '10+Runs %':  f"{_flag_under(row['gc_runs10'], cfg['gc_runs10_anchor'], True)}"
                                  f" {row['gc_runs10']:.1f}%",
                    '20+Ks %':    f"{_flag_under(row['gc_k20'],    cfg['gc_k20_anchor'],    False)}"
                                  f" {row['gc_k20']:.1f}%",
                    'SP QS %':    f"{_flag_under(row['gc_qs'],     cfg['gc_qs_anchor'],     False)}"
                                  f" {row['gc_qs']:.1f}%",
                    '4+HR %':     f"{_flag_under(row['gc_hr4'],    cfg['gc_hr4_anchor'],    True)}"
                                  f" {row['gc_hr4']:.1f}%",
                })
            if display_rows:
                st.dataframe(
                    pd.DataFrame(display_rows),
                    use_container_width=True, hide_index=True
                )

    # ── TB line auto-suggest from prop odds ────────────────────────────────────
    # If prop data is available, check whether the book's line matches the
    # user's selected under type — and surface a note if it doesn't.
    if 'prop_tb_line' in slate_excl.columns:
        lines_available = slate_excl['prop_tb_line'].dropna()
        lines_available = lines_available[lines_available.astype(bool)]
        if not lines_available.empty:
            line_counts = lines_available.value_counts()
            top_line    = line_counts.index[0]
            target      = filters['under']
            # Suggest switching if the dominant book line doesn't match selection
            if top_line == '0.5' and target == 'tb15':
                st.info(
                    "📊 **Book tip:** Most players today have TB lines at **0.5**. "
                    "Consider switching to **TB Under 0.5** for this slate."
                )
            elif top_line == '1.5' and target == 'tb05':
                st.info(
                    "📊 **Book tip:** Most players today have TB lines at **1.5**. "
                    "Consider switching to **TB Under 1.5** which matches the available market."
                )

    # Results table
    st.markdown("---")
    filtered_df = apply_under_filters(df, filters)

    target_lbl = filters['under_label'].split('—')[0].strip()
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:.6rem;margin:.5rem 0 .35rem">'
        f'<span style="font-size:.9rem;font-weight:700;color:#e2e8f0">'
        f'{target_lbl} Candidates</span>'
        f'<span style="background:#131c2e;border:1px solid #2a3f57;border-radius:20px;'
        f'padding:.15rem .6rem;font-family:\'JetBrains Mono\',monospace;font-size:.72rem;'
        f'color:#5a7090">{len(filtered_df)} results</span>'
        f'</div>',
        unsafe_allow_html=True
    )

    _render_under_table(filtered_df, filters)

    # Export
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔄 Refresh Data", key="under_refresh"):
            st.cache_data.clear()
            st.rerun()
    with c2:
        if not filtered_df.empty:
            from datetime import datetime
            export_cols = [c for c in filtered_df.columns
                           if not c.startswith('_') and c not in
                           ['pitch_hit_mult','pitch_hr_mult','pitch_walk_pen',
                            'rc_norm','rc_contrib','vs_mod','vs_contrib',
                            'xb_boost','hist_bonus']]
            st.download_button(
                "💾 Export CSV",
                filtered_df[export_cols].to_csv(index=False),
                f"a1picks_unders_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                key="under_export"
            )
