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

def compute_under_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds three Under_Score columns to the slate df.
    Called once per page load — fast, vectorized.

    Columns added:
      Under_XB_Score   — how good a candidate for XB under
      Under_TB_Score   — how good a candidate for total bases under
      Under_Hit_Score  — how good a candidate for no-hit prop
      _disq_xb         — True if disqualified for XB under
      _disq_tb         — True if disqualified for TB under
      _disq_hit        — True if disqualified for Hit under
    """
    df  = df.copy()
    cfg = CONFIG

    # Safety: ensure score columns exist
    for col in ['Hit_Score','Single_Score','XB_Score','HR_Score']:
        if col not in df.columns:
            df[col] = 50.0

    hit = df['Hit_Score'].clip(0, 100)
    xb  = df['XB_Score'].clip(0, 100)
    hr  = df['HR_Score'].clip(0, 100)
    k   = pd.to_numeric(df.get('p_k', 0), errors='coerce').fillna(0)

    # K% bonus: how much above league average (more Ks = better under)
    k_bonus  = ((k - cfg['league_k_avg']) * cfg['under_k_weight']).clip(lower=0)

    # Pitcher grade bonus — good pitcher suppresses all contact
    def _pgbonus(grade):
        return (cfg['under_pitcher_bonus'] if grade == 'A+' else
                cfg['under_pitcher_a']     if grade == 'A'  else 0.0)

    if 'pitch_grade' in df.columns:
        p_bonus = df['pitch_grade'].apply(_pgbonus)
    else:
        p_bonus = pd.Series(0.0, index=df.index)

    # ── XB Under Score ────────────────────────────────────────────────────────
    # Primary: low XB_Score. Secondary: HR must also be low (HR is also multi-base).
    # Hit_Score plays a smaller role — singles don't cash an XB over.
    df['Under_XB_Score'] = (
        (100 - xb)  * 0.50
      + (100 - hr)  * 0.35
      + (100 - hit) * 0.15
      + k_bonus + p_bonus
    ).clip(0, 100).round(1)

    # ── TB Under Score ────────────────────────────────────────────────────────
    # Total bases — ALL routes to accumulating bases matter.
    # A player can go 1-for-3 with a single and still cash TB1.5 under,
    # so Hit_Score carries more weight here than for XB under.
    df['Under_TB_Score'] = (
        (100 - hit) * 0.45
      + (100 - xb)  * 0.35
      + (100 - hr)  * 0.20
      + k_bonus + p_bonus
    ).clip(0, 100).round(1)

    # ── Hit Under Score ───────────────────────────────────────────────────────
    # Hardest to cash — any hit type kills it. Hit_Score is overwhelmingly primary.
    # K% is even more important here since a strikeout = guaranteed 0 hits.
    df['Under_Hit_Score'] = (
        (100 - hit) * 0.70
      + k_bonus * 1.5
      + p_bonus
    ).clip(0, 100).round(1)

    # ── Disqualification flags ─────────────────────────────────────────────────
    df['_disq_xb']  = (hr  > cfg['under_xb_disq_hr'])   | \
                      (hit > cfg['under_xb_disq_hit'])
    df['_disq_tb']  = (hit > cfg['under_tb_disq_any'])   | \
                      (xb  > cfg['under_tb_disq_any'])   | \
                      (hr  > cfg['under_tb_disq_any'])
    df['_disq_hit'] = hit > cfg['under_hit_disq_hit']

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
    elif target == 'tb':
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
        "🔻 XB Under — Extra Bases":      "xb",
        "📊 TB Under — Total Bases":      "tb",
        "❌ Hit Under — No Hit (0.5 line)":"hit",
    }
    u_label            = st.sidebar.selectbox("Choose Under Target", list(under_map.keys()))
    filters['under']   = under_map[u_label]
    filters['under_label'] = u_label

    score_col_map = {'xb': 'Under_XB_Score', 'tb': 'Under_TB_Score', 'hit': 'Under_Hit_Score'}
    disq_col_map  = {'xb': '_disq_xb',        'tb': '_disq_tb',       'hit': '_disq_hit'}
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

    # Sort by Under_Score descending (higher = better under candidate)
    sc = filters['under_score_col']
    if sc in out.columns:
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
        'Under_XB_Score':  '🔻 XB Under',
        'Under_TB_Score':  '📊 TB Under',
        'Under_Hit_Score': '❌ Hit Under',
    }

    col_order = ['Batter','Team','Pitcher','pitch_grade','Disq',
                 sc,
                 'Hit_Score','XB_Score','HR_Score',
                 'p_k','p_bb','total_hit_prob','p_1b','p_xb','p_hr',
                 'vs Grade']

    existing = [c for c in col_order if c in disp.columns]
    rename   = {
        sc:            label_map.get(sc, 'Under Score'),
        'pitch_grade': 'P.Grd',
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
    }

    out_df = disp[existing].rename(columns=rename)

    fmt = {}
    for cn in out_df.columns:
        if cn in ['K%','BB%','Hit%','1B%','XB%','HR%']:
            fmt[cn] = "{:.1f}%"
        elif cn in ['🎯 Hit','🔥 XB','💣 HR', label_map.get(sc,'')]:
            fmt[cn] = "{:.1f}"
        elif cn == 'vsPit':
            fmt[cn] = "{:.0f}"

    styled = out_df.style.format(fmt, na_rep="—")

    # Under_Score: purple gradient (high = good under)
    under_label = label_map.get(sc, 'Under Score')
    if under_label in out_df.columns:
        try:
            styled = styled.background_gradient(
                subset=[under_label], cmap='RdYlGn', vmin=20, vmax=80
            )
        except Exception:
            pass

    # Offensive scores: Red gradient (low = good for under)
    for col, cmap in [('🎯 Hit','RdYlGn_r'),('🔥 XB','RdYlGn_r'),('💣 HR','RdYlGn_r')]:
        if col in out_df.columns:
            try:
                styled = styled.background_gradient(subset=[col], cmap=cmap, vmin=0, vmax=100)
            except Exception:
                pass

    # K%: Green gradient (high K = good for under)
    if 'K%' in out_df.columns:
        try:
            styled = styled.background_gradient(subset=['K%'], cmap='Greens', vmin=10, vmax=40)
        except Exception:
            pass

    if 'P.Grd' in out_df.columns:
        styled = styled.map(style_grade_cell, subset=['P.Grd'])

    st.dataframe(styled, width='stretch')

    # Legend
    disq_note = {
        'xb':  f"Disqualified if HR_Score>{cfg['under_xb_disq_hr']:.0f} or Hit_Score>{cfg['under_xb_disq_hit']:.0f}",
        'tb':  f"Disqualified if ANY of Hit/XB/HR_Score>{cfg['under_tb_disq_any']:.0f}",
        'hit': f"Disqualified if Hit_Score>{cfg['under_hit_disq_hit']:.0f}",
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

    # Compute under scores
    df = compute_under_scores(df)

    # Build under-specific sidebar filters
    filters = build_under_filters(df)

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
