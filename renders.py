"""
renders.py — All render_* functions for the main predictor page

UI/UX improvements V2:
  - Animated pulse dot on fresh data badge in header
  - Score tier labels (Elite / Strong / Good / Moderate) on cards
  - Better section dividers and visual hierarchy
  - Confidence badge on Best Per Target cards
  - Statcast indicator badge on results header when data present
  - .map() replaces deprecated .applymap() (pandas 3.0)
  - width='stretch' replaces use_container_width (Streamlit 1.45+)
"""

import streamlit as st
import pandas as pd
import altair as alt
from config import CONFIG
from helpers import grade_pill, style_grade_cell, data_freshness_badge


# ─────────────────────────────────────────────────────────────────────────────
# STALENESS WARNING
# ─────────────────────────────────────────────────────────────────────────────

def render_staleness_warning():
    """
    Show a loud warning banner when the loaded slate is from a previous day.
    Reads st.session_state['slate_stale'] set by loader.load_matchups().
    """
    if not st.session_state.get('slate_stale', False):
        return

    slate_date = st.session_state.get('slate_date', 'unknown date')
    st.markdown(f"""
    <div style="background:#1c0000;border:2px solid #ef4444;border-radius:10px;
                padding:.85rem 1.2rem;margin:.5rem 0;display:flex;align-items:center;gap:.8rem;">
      <span style="font-size:1.4rem">⚠️</span>
      <div>
        <div style="font-weight:700;color:#f87171;font-size:.9rem">
          Stale Data Detected — Slate from {slate_date}
        </div>
        <div style="color:#fca5a5;font-size:.78rem;margin-top:.2rem">
          Today's Matchups.csv has not been uploaded yet. All scores reflect yesterday's
          slate. Do not place bets until today's data is loaded.
        </div>
      </div>
      <div style="margin-left:auto;font-size:.72rem;color:#f87171">
        Hit 🔄 Refresh when today's file is ready
      </div>
    </div>
    """, unsafe_allow_html=True)


def _score_tier(score: float) -> tuple[str, str]:
    """Return (label, css_color) for a 0-100 score."""
    if score >= 75: return "ELITE",    "#4ade80"
    if score >= 60: return "STRONG",   "#a3e635"
    if score >= 45: return "GOOD",     "#fbbf24"
    if score >= 30: return "MODERATE", "#fb923c"
    return             "WEAK",     "#f87171"


def _eligible_for_target(df: pd.DataFrame, sc: str) -> pd.DataFrame:
    """
    Hard profile filter — removes players whose score is higher in a
    more powerful category than the target category.

    Single:  exclude if XB_Score > Single_Score or HR_Score > Single_Score
    XB:      exclude if HR_Score > XB_Score
    Hit/HR:  no exclusions

    Falls back to the full df if filtering leaves it empty.
    """
    sc_base = sc.replace('_gc', '')

    if sc_base == 'Single_Score':
        mask = pd.Series(True, index=df.index)
        if 'XB_Score' in df.columns:
            mask &= ~(df['XB_Score'] > df['Single_Score'])
        if 'HR_Score' in df.columns:
            mask &= ~(df['HR_Score'] > df['Single_Score'])
        filtered = df[mask]
        return filtered if not filtered.empty else df

    if sc_base == 'XB_Score':
        mask = pd.Series(True, index=df.index)
        if 'HR_Score' in df.columns:
            mask &= ~(df['HR_Score'] > df['XB_Score'])
        filtered = df[mask]
        return filtered if not filtered.empty else df

    return df


def _profile_badge(row: pd.Series, target_sc: str) -> str:
    """
    Returns an HTML warning badge when the player's contact profile is a
    mismatch for the target bet type.

    Single: warn when XB_Score or HR_Score significantly exceeds Single_Score
    XB:     warn when HR_Score significantly exceeds XB_Score
    Hit/HR: no warning
    """
    if target_sc not in ('Single_Score', 'XB_Score'):
        return ""

    try:
        single = float(row.get('Single_Score', 0) or 0)
        xb     = float(row.get('XB_Score',     0) or 0)
        hr     = float(row.get('HR_Score',      0) or 0)
    except (ValueError, TypeError):
        return ""

    badge = ""

    if target_sc == 'Single_Score':
        xb_gap = xb - single
        hr_gap = hr - single
        if xb_gap >= 12:
            badge = (
                '<span style="background:#1c1400;color:#f59e0b;padding:1px 7px;'
                'border-radius:20px;font-size:.62rem;font-weight:700;margin-left:.3rem;'
                'font-family:\'JetBrains Mono\',monospace">⚡ XB PROFILE</span>'
            )
        elif xb_gap >= 7:
            badge = (
                '<span style="background:#1c1000;color:#fb923c;padding:1px 7px;'
                'border-radius:20px;font-size:.62rem;font-weight:700;margin-left:.3rem;'
                'font-family:\'JetBrains Mono\',monospace">⚡ XB LEAN</span>'
            )
        elif hr_gap >= 15:
            badge = (
                '<span style="background:#1c0000;color:#f87171;padding:1px 7px;'
                'border-radius:20px;font-size:.62rem;font-weight:700;margin-left:.3rem;'
                'font-family:\'JetBrains Mono\',monospace">💣 POWER PROFILE</span>'
            )

    elif target_sc == 'XB_Score':
        hr_gap = hr - xb
        if hr_gap >= 12:
            badge = (
                '<span style="background:#1c0000;color:#f87171;padding:1px 7px;'
                'border-radius:20px;font-size:.62rem;font-weight:700;margin-left:.3rem;'
                'font-family:\'JetBrains Mono\',monospace">💣 HR PROFILE</span>'
            )

    return badge


# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────

def render_header():
    badge = data_freshness_badge()
    # Add animated pulse to green badge
    badge_html = badge.replace(
        'sbadge-green">',
        'sbadge-green"><span class="pulse-dot"></span>'
    )
    st.markdown(f"""
    <div class="app-header">
      <div>
        <img src="https://github.com/a1faded/a1picks-hits-bot/blob/main/a1sports.png?raw=true"
             style="height:40px;width:auto;filter:drop-shadow(0 0 8px rgba(59,130,246,.4))" />
      </div>
      <div class="title-wrap">
        <h1>A1PICKS MLB Hit Predictor</h1>
        <p>BallPark Pal simulations &nbsp;·&nbsp; MLB Stats API &nbsp;·&nbsp; Statcast &nbsp;·&nbsp; V5.5</p>
      </div>
      <div class="meta">{badge_html}</div>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# STAT BAR
# ─────────────────────────────────────────────────────────────────────────────

def render_stat_bar(df: pd.DataFrame):
    if df is None or df.empty:
        return

    avg_hp = df['total_hit_prob'].mean()
    avg_hr = df['p_hr'].mean() if 'p_hr' in df.columns else 0
    has_sc = any(c in df.columns and df[c].notna().any() for c in ['Barrel%', 'HH%', 'xBA'])

    lineup_badge = ""
    try:
        from mlb_api import get_lineup_status_map
        smap      = get_lineup_status_map()
        confirmed = sum(1 for v in smap.values() if '✅' in v['status'])
        total     = len(smap)
        color     = "var(--hit)" if confirmed == total else "var(--xb)"
        lineup_badge = (
            f'<div class="stat-item">'
            f'<span class="val" style="color:{color}">{confirmed}/{total}</span>'
            f'<span class="lbl">Lineups ✅</span></div>'
        )
    except Exception:
        pass

    sc_badge = (
        '<div class="stat-item">'
        '<span class="val" style="color:var(--accent);font-size:.85rem">⚡</span>'
        '<span class="lbl">Statcast ON</span></div>'
    ) if has_sc else ""

    # ── Game Conditions quick indicators ─────────────────────────────────────
    # Show slate-level GC environment as color-coded pills in the stat bar.
    # Average across all games so the user sees the overall day's environment.
    gc_badge = ""
    _GC_NEEDED = ['gc_hits20','gc_k20','gc_hr4']
    if all(c in df.columns for c in _GC_NEEDED):
        from config import CONFIG as _cfg
        avg_hits20 = df['gc_hits20'].mean()
        avg_k20    = df['gc_k20'].mean()
        avg_hr4    = df['gc_hr4'].mean()

        # Hits: above median = hitter day (green for overs, no color for unders)
        hits_color = "var(--hit)" if avg_hits20 > _cfg['gc_hits20_anchor'] else "var(--muted)"
        # K%: above median = pitcher day
        k_color    = "var(--xb)"  if avg_k20    > _cfg['gc_k20_anchor']    else "var(--muted)"
        # HR: above median = power day
        hr_color   = "var(--hr)"  if avg_hr4    > _cfg['gc_hr4_anchor']    else "var(--muted)"

        gc_badge = (
            f'<div class="stat-item">'
            f'<span class="val" style="font-size:.72rem;color:{hits_color}">'
            f'{avg_hits20:.0f}%</span>'
            f'<span class="lbl">Hit Env</span></div>'
            f'<div class="stat-item">'
            f'<span class="val" style="font-size:.72rem;color:{k_color}">'
            f'{avg_k20:.0f}%</span>'
            f'<span class="lbl">K Env</span></div>'
            f'<div class="stat-item">'
            f'<span class="val" style="font-size:.72rem;color:{hr_color}">'
            f'{avg_hr4:.0f}%</span>'
            f'<span class="lbl">HR Env</span></div>'
        )

    st.markdown(f"""
    <div class="stat-bar">
      <div class="stat-item">
        <span class="val">{len(df)}</span>
        <span class="lbl">Matchups</span>
      </div>
      <div class="stat-item">
        <span class="val">{df['Batter'].nunique()}</span>
        <span class="lbl">Batters</span>
      </div>
      <div class="stat-item">
        <span class="val">{df['Team'].nunique()}</span>
        <span class="lbl">Teams</span>
      </div>
      <div class="stat-item">
        <span class="val" style="color:var(--hit)">{avg_hp:.1f}%</span>
        <span class="lbl">Avg Hit Prob</span>
      </div>
      <div class="stat-item">
        <span class="val" style="color:var(--hr)">{avg_hr:.2f}%</span>
        <span class="lbl">Avg HR Prob</span>
      </div>
      {gc_badge}{lineup_badge}{sc_badge}
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# SCORE SUMMARY CARDS
# ─────────────────────────────────────────────────────────────────────────────

def render_score_summary_cards(slate_df: pd.DataFrame, filters: dict):
    if slate_df.empty:
        return

    st.markdown('<div class="section-head">🏆 Today\'s Best — Full Slate</div>',
                unsafe_allow_html=True)

    defs = [
        ('Hit_Score',    'scard-hit',    '🎯', 'HIT',    'Any Base Hit'),
        ('Single_Score', 'scard-single', '1️⃣', 'SINGLE', 'Single Specifically'),
        ('XB_Score',     'scard-xb',     '🔥', 'XB',     'Double / Triple'),
        ('HR_Score',     'scard-hr',     '💣', 'HR',     'Home Run'),
    ]

    use_gc     = filters.get('use_gc', False)
    cards_html = '<div class="score-grid">'

    for sc, css, icon, short, desc in defs:
        if sc not in slate_df.columns:
            continue
        rank_sc   = (sc + '_gc') if (use_gc and sc + '_gc' in slate_df.columns) else sc
        eligible  = _eligible_for_target(slate_df, sc)
        row       = eligible.loc[eligible[rank_sc].idxmax()]
        disp_val  = float(row[rank_sc])
        base_col = sc + '_base'
        gc_str   = " ⛅" if use_gc and rank_sc != sc else ""

        park_str = ""
        if filters['use_park'] and base_col in slate_df.columns and row.get(base_col, 0) != 0:
            delta    = row[sc] - row[base_col]
            pct      = delta / row[base_col] * 100
            park_str = f" · <span style='color:{'var(--pos)' if delta>=0 else 'var(--neg)'}'>{'+' if delta>=0 else ''}{pct:.0f}% park</span>"

        tier_lbl, tier_color = _score_tier(disp_val)
        profile_badge = _profile_badge(row, sc)

        cards_html += f"""
        <div class="scard {css}">
          <div class="sc-type"><span>{icon} {short}</span>{gc_str} — {desc}</div>
          <div class="sc-name">{row['Batter']}{profile_badge}</div>
          <div class="sc-meta">{row['Team']} vs {row['Pitcher']}{park_str}</div>
          <div class="sc-score">{disp_val:.1f}</div>
          <div style="margin-top:.35rem">
            <span style="font-size:.62rem;padding:1px 6px;border-radius:20px;
              background:{tier_color}22;color:{tier_color};font-weight:700;
              font-family:'JetBrains Mono',monospace;letter-spacing:.04em">{tier_lbl}</span>
          </div>
        </div>"""

    cards_html += '</div>'
    st.markdown(cards_html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# PITCHER LANDSCAPE
# ─────────────────────────────────────────────────────────────────────────────

def render_pitcher_landscape(pitcher_df, df: pd.DataFrame):
    with st.expander("⚾ Pitcher Landscape", expanded=False):
        if pitcher_df is None or pitcher_df.empty:
            st.markdown('<div class="notice notice-info">ℹ️ Pitcher CSV data unavailable.</div>',
                        unsafe_allow_html=True)
            return

        today_pitchers = df['Pitcher'].unique()
        pm             = pitcher_df.set_index('last_name')
        rows_html      = ""

        for p in sorted(today_pitchers):
            if p in pm.index:
                r       = pm.loc[p]
                grade_h = grade_pill(str(r['pitch_grade']))
                name, team = r['full_name'], r['team']
                hit_val    = f"{r['hit8_prob']:.1f}%"
                hr_val     = f"{r['hr2_prob']:.1f}%"
                wk_val     = f"{r['walk3_prob']:.1f}%"
                hm_val     = f"{r['pitch_hit_mult']:.3f}×"
                hrm_val    = f"{r['pitch_hr_mult']:.3f}×"
            else:
                grade_h = grade_pill('B')
                name, team = p, "—"
                hit_val = f"{CONFIG['pitcher_hit_neutral']:.1f}% *"
                hr_val  = f"{CONFIG['pitcher_hr_neutral']:.1f}% *"
                wk_val  = f"{CONFIG['pitcher_walk_neutral']:.1f}% *"
                hm_val  = hrm_val = "1.000×"

            rows_html += f"""<tr>
              <td style="color:var(--text)">{name}</td>
              <td style="color:var(--muted)">{team}</td>
              <td>{grade_h}</td>
              <td style="color:var(--hit)">{hit_val}</td>
              <td style="color:var(--hr)">{hr_val}</td>
              <td style="color:var(--xb)">{wk_val}</td>
              <td style="color:var(--muted)">{hm_val}</td>
              <td style="color:var(--muted)">{hrm_val}</td>
            </tr>"""

        st.markdown(f"""
        <div class="pt-wrap"><table class="pt-table"><thead><tr>
          <th>Pitcher</th><th>Team</th><th>Grade</th>
          <th>Hit 8+</th><th>HR 2+</th><th>Walk 3+</th>
          <th>Hit Mult</th><th>HR Mult</th>
        </tr></thead><tbody>{rows_html}</tbody></table></div>
        <div class="notice notice-pitcher" style="margin-top:.5rem">
          📊 <b>Hit 8+</b> drives Hit/Single/XB multiplier · <b>HR 2+</b> drives HR multiplier ·
          <b>Walk 3+</b> mild penalty all scores · Max effect ±8%
        </div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# PARK NOTICE
# ─────────────────────────────────────────────────────────────────────────────

def render_park_notice(slate_df: pd.DataFrame, filters: dict):
    sc_base  = filters.get('score_col_base', filters['score_col'].replace('_gc', ''))
    use_gc   = filters.get('use_gc', False)
    sc       = (sc_base + '_gc') if (use_gc and sc_base + '_gc' in slate_df.columns) else sc_base
    base_sc  = sc_base + '_base'

    if not filters['use_park']:
        st.markdown('<div class="notice notice-park">🏟️ <b>Park OFF</b> — pure player vs pitcher.</div>',
                    unsafe_allow_html=True)
        return

    if base_sc not in slate_df.columns or slate_df.empty:
        return

    ab, bl = slate_df[base_sc].mean(), slate_df[sc].mean()
    delta   = bl - ab
    pct     = (delta / ab * 100) if ab != 0 else 0
    dir_    = "boosted" if delta >= 0 else "reduced"
    col_    = "var(--pos)" if delta >= 0 else "var(--neg)"

    st.markdown(
        f'<div class="notice notice-park">🏟️ <b>Park ON</b> — '
        f'<span style="color:{col_};font-weight:700">{dir_} ~{abs(pct):.1f}%</span> avg · '
        f'Park Δ column shows per-player impact</div>',
        unsafe_allow_html=True
    )


# ─────────────────────────────────────────────────────────────────────────────
# GAME CONDITIONS PANEL
# ─────────────────────────────────────────────────────────────────────────────

def render_game_conditions_panel(slate_df: pd.DataFrame, filters: dict,
                                  game_cond, pitcher_qs):
    use_gc  = filters.get('use_gc', False)
    sc_base = filters.get('score_col_base', filters['score_col'].replace('_gc', ''))
    sc      = (sc_base + '_gc') if (use_gc and sc_base + '_gc' in slate_df.columns) else sc_base

    if not use_gc:
        return

    gc_cols = ['gc_hr4', 'gc_hits20', 'gc_k20', 'gc_walks8', 'gc_runs10', 'gc_qs']
    if slate_df.empty or not all(c in slate_df.columns for c in gc_cols):
        st.markdown(
            '<div class="notice notice-warn">🌦️ <b>Game Conditions ON</b> — '
            'No game condition CSVs found. Scores unaffected.</div>',
            unsafe_allow_html=True)
        return

    gc_sc_col = sc + '_gc'
    if gc_sc_col not in slate_df.columns:
        return

    game_rows = []
    for game in sorted(slate_df['Game'].unique()):
        gdf = slate_df[slate_df['Game'] == game]
        if gdf.empty:
            continue
        row      = gdf.iloc[0]
        avg_base = gdf[sc].mean()
        avg_gc   = gdf[gc_sc_col].mean()
        game_rows.append({
            'Game':         game,
            '4+ HR %':     f"{row['gc_hr4']:.1f}%",
            '20+ Hits %':  f"{row['gc_hits20']:.1f}%",
            '20+ Ks %':    f"{row['gc_k20']:.1f}%",
            '8+ Walks %':  f"{row['gc_walks8']:.1f}%",
            '10+ Runs %':  f"{row['gc_runs10']:.1f}%",
            'QS %':         f"{row['gc_qs']:.1f}%",
            'Cond Δ (avg)': avg_gc - avg_base,
        })

    if not game_rows:
        return

    sc_lbl = {'Hit_Score':'Hit','Single_Score':'Single',
               'XB_Score':'XB','HR_Score':'HR'}.get(sc, 'Score')

    with st.expander(f"🌦️ Game Conditions — {sc_lbl} Score Impact", expanded=True):
        gdf_disp = pd.DataFrame(game_rows)
        styled   = gdf_disp.style.format({'Cond Δ (avg)': '{:+.1f}'})
        styled   = styled.background_gradient(subset=['Cond Δ (avg)'],
                                              cmap='RdYlGn', vmin=-8, vmax=8)
        st.dataframe(styled, width='stretch', hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# RESULTS TABLE
# ─────────────────────────────────────────────────────────────────────────────

def render_results_table(filtered_df: pd.DataFrame, filters: dict):
    if filtered_df.empty:
        st.warning("⚠️ No players match your filters — try relaxing the thresholds.")
        return

    use_gc   = filters.get('use_gc', False)
    use_park = filters['use_park']
    sc_base  = filters.get('score_col_base', filters['score_col'].replace('_gc', ''))
    sc_gc    = sc_base + '_gc'
    base_sc  = sc_base + '_base'
    sc       = sc_gc if (use_gc and sc_gc in filtered_df.columns) else sc_base

    disp = filtered_df.copy()
    disp['K% ↓Lg']  = (CONFIG['league_k_avg']  - disp['p_k']).round(1)
    disp['BB% ↓Lg'] = (CONFIG['league_bb_avg'] - disp['p_bb']).round(1)
    disp['HR% ↑Lg'] = (disp['p_hr'] - CONFIG['league_hr_avg']).round(2)
    disp['Hit%']    = disp['total_hit_prob'].round(1)
    disp['PA']      = disp['PA'].astype(int)
    disp['AVG']     = disp['AVG'].round(3)
    disp['vs Grade']= pd.to_numeric(disp['vs Grade'], errors='coerce').round(0).astype(int)
    disp['Park Δ']  = (
        (disp[sc_base] - disp[base_sc]).round(1)
        if (use_park and base_sc in disp.columns) else 0.0
    )
    disp['Cond Δ'] = (
        (disp[sc_gc] - disp[sc_base]).round(1)
        if (use_gc and sc_gc in disp.columns) else 0.0
    )

    # ── New signal columns ─────────────────────────────────────────────────────
    has_order = '_order_pos' in disp.columns and disp['_order_pos'].notna().any()
    has_form  = '_form_label' in disp.columns

    if has_order:
        disp['Pos'] = disp['_order_pos'].apply(
            lambda x: f"#{int(x)}" if pd.notna(x) else "—"
        )
    if has_form:
        disp['Form'] = disp['_form_label'].fillna('—')

    lbl          = {'Hit_Score':'🎯 Hit','Single_Score':'1️⃣ Single',
                    'XB_Score':'🔥 XB','HR_Score':'💣 HR'}
    active       = lbl.get(sc_base, 'Score')
    active_label = (active + ' ⛅') if (use_gc and sc_gc in filtered_df.columns) else active

    cols = {'Batter':'Batter','Team':'Team','Pitcher':'Pitcher',
            'pitch_grade':'P.Grd', sc: active_label}

    # Profile mismatch column — immediately after score for visibility
    if 'Profile' in disp.columns:
        cols['Profile'] = 'Profile'

    # Inject Pos immediately after Batter/Team when available
    if has_order and 'Pos' in disp.columns:
        cols['Pos'] = 'Pos'

    if use_park and base_sc in disp.columns:
        cols[base_sc]  = 'Base'
        cols['Park Δ'] = 'Park Δ'
    if use_gc and sc_gc in disp.columns:
        cols['Cond Δ'] = 'Cond Δ'

    for sc2, lb2 in lbl.items():
        if sc2 != sc_base and sc2 != sc_gc and sc2 in disp.columns:
            cols[sc2] = lb2

    cols.update({'Hit%':'Hit%','p_1b':'1B%','p_xb':'XB%','p_hr':'HR%',
                 'p_k':'K%','p_bb':'BB%','K% ↓Lg':'K% ↓Lg',
                 'BB% ↓Lg':'BB% ↓Lg','HR% ↑Lg':'HR% ↑Lg',
                 'vs Grade':'vsPit','PA':'PA','AVG':'AVG'})

    # Form near the end (before Statcast)
    if has_form and 'Form' in disp.columns:
        cols['Form'] = 'Form'

    # ── Profile mismatch column ────────────────────────────────────────────────
    # Plain-text label that renders cleanly in st.dataframe()
    # Shows for Single and XB targets — blank for Hit and HR
    sc_base_for_profile = filters.get('score_col_base',
                                      filters['score_col'].replace('_gc',''))
    if sc_base_for_profile in ('Single_Score', 'XB_Score'):
        def _profile_label(row):
            try:
                xb  = float(row.get('XB_Score',  0) or 0)
                hr  = float(row.get('HR_Score',   0) or 0)
                si  = float(row.get('Single_Score',0) or 0)
                if sc_base_for_profile == 'Single_Score':
                    if xb - si >= 12:  return "⚡ XB Profile"
                    if xb - si >=  7:  return "⚡ XB Lean"
                    if hr - si >= 15:  return "💣 Power"
                    return "✅ Clean"
                else:  # XB_Score
                    if hr - xb >= 12:  return "💣 HR Profile"
                    return "✅ Clean"
            except Exception:
                return ""
        disp['Profile'] = disp.apply(_profile_label, axis=1)

    # ── Prop odds columns ──────────────────────────────────────────────────────
    # TB line + under odds on every target (quick reference for any under prop)
    # HR odds only when the active target is HR (over side context)
    has_props = 'prop_tb_line' in disp.columns and disp['prop_tb_line'].astype(bool).any()
    if has_props:
        cols['prop_tb_line']       = 'TB Line'
        cols['prop_tb_under_odds'] = 'TB Under'
        cols['prop_tb_over_odds']  = 'TB Over'
        if sc_base == 'HR_Score':
            cols['prop_hr_odds'] = 'HR Odds'

    statcast_cols = {'Barrel%':'Barrel%','HH%':'HH%','xBA':'xBA',
                     'xSLG':'xSLG','AvgEV':'AvgEV','maxEV':'maxEV'}
    has_statcast  = any(c in disp.columns and disp[c].notna().any() for c in statcast_cols)
    if has_statcast:
        for raw, label in statcast_cols.items():
            if raw in disp.columns:
                cols[raw] = label

    existing = [c for c in cols if c in disp.columns]
    out_df   = disp[existing].rename(columns=cols)

    # ── Add Tier column (ELITE/STRONG/GOOD/MODERATE/WEAK) ─────────────────────
    # Placed immediately after the score column so users get a text label
    # alongside the number — no mental calibration needed.
    tier_map = lambda s: (
        "🟢 ELITE"    if s >= 75 else
        "🟡 STRONG"   if s >= 60 else
        "🟠 GOOD"     if s >= 45 else
        "🔴 MODERATE" if s >= 30 else
        "⚫ WEAK"
    )
    if active_label in out_df.columns:
        tier_vals = out_df[active_label].apply(
            lambda x: tier_map(float(x)) if pd.notna(x) else "—"
        )
        insert_at = out_df.columns.get_loc(active_label) + 1
        out_df    = out_df.copy()       # decouple before mutation
        out_df.insert(insert_at, 'Tier', tier_vals)

    # Text-only columns that must never receive a numeric format string
    _text_cols = {'Tier', 'Profile', 'Form', 'Pos', 'Market Edge',
                  'TB Line', 'TB Under', 'TB Over', 'HR Odds', 'P.Grd',
                  'Batter', 'Team', 'Pitcher'}

    fmt = {}
    for cn in out_df.columns:
        if cn in _text_cols:
            continue                    # skip — no format for string columns
        if cn in ['Hit%','1B%','XB%','HR%','K%','BB%','Barrel%','HH%']:
            fmt[cn] = "{:.1f}%"
        elif cn in ['K% ↓Lg','BB% ↓Lg']:
            fmt[cn] = "{:+.1f}%"
        elif cn == 'HR% ↑Lg':
            fmt[cn] = "{:+.2f}%"
        elif cn in ['Park Δ','Cond Δ']:
            fmt[cn] = "{:+.1f}"
        elif cn in ['AVG','xBA','xSLG']:
            fmt[cn] = "{:.3f}"
        elif cn in ['AvgEV','maxEV']:
            fmt[cn] = "{:.1f}"
        elif any(e in cn for e in ['🎯','1️⃣','🔥','💣','Base']) and 'Prob' not in cn:
            fmt[cn] = "{:.1f}"

    styled = out_df.style.format(fmt, na_rep="—")

    for sn, cm in {'🎯 Hit':'Greens','1️⃣ Single':'GnBu',
                   '🔥 XB':'YlOrBr','💣 HR':'YlOrRd'}.items():
        tc = sn + ' ⛅' if (sn + ' ⛅') in out_df.columns else sn
        if tc in out_df.columns:
            try:
                styled = styled.background_gradient(subset=[tc], cmap=cm, vmin=0, vmax=100)
            except Exception:
                pass

    for cn, cm, v0, v1 in [
        ('Park Δ','RdYlGn',-10,10), ('Cond Δ','RdYlGn',-8,8),
        ('K% ↓Lg','RdYlGn',-8,12), ('HR% ↑Lg','RdYlGn',-2,3),
        ('vsPit','RdYlGn',-10,10),
        ('Barrel%','Greens',0,20),  ('HH%','Greens',20,60),
        ('AvgEV','Greens',85,100),
    ]:
        if cn in out_df.columns:
            try:
                styled = styled.background_gradient(subset=[cn], cmap=cm, vmin=v0, vmax=v1)
            except Exception:
                pass

    if 'P.Grd' in out_df.columns:
        styled = styled.map(style_grade_cell, subset=['P.Grd'])

    # ── Column config — widths, tooltips, number formatting ───────────────────
    col_cfg: dict = {}
    try:
        import streamlit as _st
        CC = _st.column_config

        col_cfg['Batter'] = CC.TextColumn("Batter", width="medium")
        col_cfg['Team']   = CC.TextColumn("Team",   width="small")
        col_cfg['Tier']   = CC.TextColumn(
            "Tier", width="small",
            help="ELITE ≥75 · STRONG ≥60 · GOOD ≥45 · MODERATE ≥30 · WEAK <30"
        )
        if 'Profile' in out_df.columns:
            col_cfg['Profile'] = CC.TextColumn(
                "Profile", width="small",
                help="Contact profile fit for this prop. ✅ Clean = ideal. "
                     "⚡ XB/💣 Power = player's contact tends toward extra bases."
            )
        for score_lbl in ['🎯 Hit','1️⃣ Single','🔥 XB','💣 HR',
                           '🎯 Hit ⛅','1️⃣ Single ⛅','🔥 XB ⛅','💣 HR ⛅']:
            if score_lbl in out_df.columns:
                col_cfg[score_lbl] = CC.NumberColumn(
                    score_lbl, format="%.1f",
                    min_value=0, max_value=100,
                    help="Score 0–100. Higher = stronger candidate for this prop."
                )
        for odds_col in ['TB Under','TB Over','HR Odds']:
            if odds_col in out_df.columns:
                col_cfg[odds_col] = CC.TextColumn(
                    odds_col, width="small",
                    help="American odds from Tank01 market data. e.g. -190 means you bet $190 to win $100."
                )
        if 'TB Line' in out_df.columns:
            col_cfg['TB Line'] = CC.TextColumn(
                "TB Line", width="small",
                help="Total Bases line set by the sportsbook (0.5 or 1.5)."
            )
        if 'Market Edge' in out_df.columns:
            col_cfg['Market Edge'] = CC.TextColumn(
                "Market Edge", width="small",
                help="⚡ EDGE = model favours under more than market. "
                     "✅ CONFIRMED = both agree. 🔄 CONTRARIAN = market more bullish on under than model."
            )
    except Exception:
        col_cfg = {}

    st.dataframe(styled, use_container_width=True, column_config=col_cfg or None,
                 hide_index=False)

    LG        = CONFIG
    park_note = (
        "<b>Park Δ</b> = park impact per player."
        if use_park else "Park OFF — pure player vs pitcher."
    )
    gc_note = " · <b>Cond Δ ⛅</b> = game conditions shift" if use_gc else ""
    sc_note = " · <b>Barrel%/HH%/AvgEV</b> = Statcast season" if has_statcast else ""

    st.markdown(f"""
    <div class="legend-compact">
      <span class="hit-c">🎯 Hit</span> 1B×3 · K pen heavy &nbsp;
      <span class="sl-c">1️⃣ Single</span> 1B×5 · XB/HR penalised &nbsp;
      <span class="xb-c">🔥 XB</span> XB×5 · mod K &nbsp;
      <span class="hr-c">💣 HR</span> HR×6 · K near-neutral · BB neutral<br>
      <b>K% ↓Lg</b> vs league {LG['league_k_avg']}% ·
      <b>BB% ↓Lg</b> vs league {LG['league_bb_avg']}% ·
      <b>HR% ↑Lg</b> vs league {LG['league_hr_avg']}% ·
      <b>PA/AVG</b> vs this pitcher ·
      {park_note}{gc_note}{sc_note}
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# PLAYER DEEP DIVE
# ─────────────────────────────────────────────────────────────────────────────

def render_player_deep_dive(filtered_df: pd.DataFrame, player_id_map: dict):
    if filtered_df.empty:
        return

    with st.expander("🔬 Player Deep Dive — Game Log & Statcast", expanded=False):
        st.markdown(
            '<div class="notice notice-info">Select any player from the filtered list '
            'to see their last 10 games + rolling quality-of-contact metrics.</div>',
            unsafe_allow_html=True
        )
        players    = sorted(filtered_df['Batter'].unique().tolist())
        sel_player = st.selectbox("Select Player", players, key="deep_dive_player")
        pid        = player_id_map.get(sel_player)

        col1, col2 = st.columns([3, 2])

        with col1:
            st.markdown(f"**📅 {sel_player} — Last 10 Games**")
            if pid:
                from mlb_api import get_player_game_log
                log_df = get_player_game_log(pid, last_n=10)
                if not log_df.empty:
                    def _style_hits(val):
                        return 'color:#10b981;font-weight:700' if val > 0 else ''
                    styled_log = (
                        log_df.style
                        .map(_style_hits, subset=['H'])
                        .format({'AVG': '{}'})
                    )
                    st.dataframe(styled_log, width='stretch', hide_index=True)

                    if 'H' in log_df.columns and 'AB' in log_df.columns:
                        played   = len(log_df[log_df['AB'] > 0])
                        hit_games= len(log_df[log_df['H'] > 0])
                        total_h  = log_df['H'].sum()
                        total_hr = log_df['HR'].sum()
                        rate     = hit_games / played if played else 0
                        color    = ("var(--hit)" if rate >= 0.6 else
                                    "var(--xb)"  if rate >= 0.4 else "var(--hr)")
                        tier, tc = _score_tier(rate * 100)
                        st.markdown(
                            f'<div style="font-size:.78rem;color:var(--muted);margin-top:.4rem">'
                            f'Last {played} G: <span style="color:{color};font-weight:700">'
                            f'{hit_games} hits in {played} games</span> · '
                            f'{total_h} H · {total_hr} HR &nbsp;'
                            f'<span style="background:{tc}22;color:{tc};padding:1px 6px;'
                            f'border-radius:20px;font-size:.65rem;font-weight:700">{tier}</span>'
                            f'</div>',
                            unsafe_allow_html=True
                        )
                else:
                    st.info("No game log data available yet for this season.")
            else:
                st.info("⏳ Player ID not resolved — game log unavailable.")

        with col2:
            st.markdown(f"**⚡ Statcast — Last 30 Days**")
            if pid:
                try:
                    from savant import get_batter_quality_metrics
                    metrics = get_batter_quality_metrics(pid, days_back=30)
                    if metrics:
                        metric_rows = [
                            ("Sample",    f"{metrics.get('sample_size','—')} BIP",  "var(--muted)"),
                            ("Avg EV",    f"{metrics.get('avg_ev','—')} mph",
                             "var(--hit)" if metrics.get('avg_ev',0) >= 90 else "var(--text)"),
                            ("Max EV",    f"{metrics.get('max_ev','—')} mph",
                             "var(--hit)" if metrics.get('max_ev',0) >= 105 else "var(--text)"),
                            ("Barrel%",   f"{metrics.get('barrel_pct','—')}%",
                             "var(--hit)" if metrics.get('barrel_pct',0) >= 8 else "var(--text)"),
                            ("Hard Hit%", f"{metrics.get('hard_hit_pct','—')}%",
                             "var(--hit)" if metrics.get('hard_hit_pct',0) >= 40 else "var(--text)"),
                            ("Avg LA",    f"{metrics.get('avg_la','—')}°",    "var(--text)"),
                            ("xBA",       f"{metrics.get('xba','—')}",        "var(--text)"),
                            ("xwOBA",     f"{metrics.get('xwoba','—')}",      "var(--text)"),
                        ]
                        rows_html = "".join(
                            f'<div class="pcard-row">'
                            f'<span class="pk">{label}</span>'
                            f'<span class="pv" style="color:{color}">{val}</span>'
                            f'</div>'
                            for label, val, color in metric_rows
                        )
                        st.markdown(
                            f'<div class="pcard" style="margin-top:0">{rows_html}</div>',
                            unsafe_allow_html=True
                        )
                    else:
                        st.info(f"No Statcast data in last 30 days.")
                except Exception:
                    st.info("Statcast unavailable.")
            else:
                st.info("⏳ Player ID not resolved.")


# ─────────────────────────────────────────────────────────────────────────────
# BEST PER TARGET
# ─────────────────────────────────────────────────────────────────────────────

def render_best_per_target(slate_df: pd.DataFrame, filters: dict):
    if len(slate_df) < 3:
        return

    with st.expander("🔍 Best Per Target — Full Slate", expanded=True):
        st.markdown(
            '<div class="notice notice-info">ℹ️ Full slate (exclusions only). '
            'Not affected by target/stat filters.</div>',
            unsafe_allow_html=True
        )

        defs = [
            ('Hit_Score',    'pcard-hit',    '🎯', 'HIT',    'Any Base Hit'),
            ('Single_Score', 'pcard-single', '1️⃣', 'SINGLE', 'Single'),
            ('XB_Score',     'pcard-xb',     '🔥', 'XB',     'Double / Triple'),
            ('HR_Score',     'pcard-hr',     '💣', 'HR',     'Home Run'),
        ]

        use_gc     = filters.get('use_gc', False)
        cards_html = '<div class="pcard-grid">'
        LG         = CONFIG

        for sc, css, icon, short, desc in defs:
            if sc not in slate_df.columns:
                continue
            rank_sc  = (sc + '_gc') if (use_gc and sc + '_gc' in slate_df.columns) else sc
            eligible = _eligible_for_target(slate_df, sc)
            row      = eligible.loc[eligible[rank_sc].idxmax()]
            disp_val = float(row[rank_sc])
            base_col = sc + '_base'

            tier_lbl, tier_color = _score_tier(disp_val)
            profile_badge = _profile_badge(row, sc)

            park_row = ""
            if filters['use_park'] and base_col in slate_df.columns \
                    and row.get(base_col, 0) != 0:
                delta    = row[sc] - row[base_col]
                pct      = delta / row[base_col] * 100
                col_     = "var(--pos)" if delta >= 0 else "var(--neg)"
                park_row = (
                    f'<div class="pcard-row"><span class="pk">Park Δ</span>'
                    f'<span class="pv" style="color:{col_}">'
                    f'{("+" if delta>=0 else "")}{pct:.1f}%</span></div>'
                )

            k_lg  = LG['league_k_avg']  - row['p_k']
            bb_lg = LG['league_bb_avg'] - row['p_bb']
            hr_lg = row['p_hr']         - LG['league_hr_avg']
            k_cls  = "pos-val" if k_lg  >= 0 else "neg-val"
            bb_cls = "pos-val" if bb_lg >= 0 else "neg-val"
            hr_cls = "pos-val" if hr_lg >= 0 else "neg-val"
            gph    = grade_pill(str(row.get('pitch_grade', 'B')))

            hist_row = ""
            if row['PA'] >= LG['hist_min_pa']:
                hist_row = (
                    f'<div class="pcard-row"><span class="pk">Hist PA</span>'
                    f'<span class="pv">{int(row["PA"])} PA · {row["AVG"]:.3f}</span></div>'
                )

            sc_row = ""
            if 'Barrel%' in slate_df.columns and pd.notna(row.get('Barrel%')):
                sc_row = (
                    f'<div class="pcard-row"><span class="pk">Barrel%</span>'
                    f'<span class="pv" style="color:var(--hit)">'
                    f'{row["Barrel%"]:.1f}%</span></div>'
                )

            # Batting order slot
            order_row = ""
            if '_order_pos' in slate_df.columns and pd.notna(row.get('_order_pos')):
                try:
                    slot = int(float(row['_order_pos']))   # float() first handles "4.0" strings
                except (ValueError, TypeError):
                    slot = None
                if slot:
                    slot_ctx   = {1:"Leadoff",2:"#2 Hitter",3:"#3 Hitter",
                                  4:"Cleanup",5:"#5 Hitter"}.get(slot, f"#{slot} Hitter")
                    slot_color = "var(--hit)" if slot in (3,4,5) else \
                                 "var(--accent)" if slot in (1,2) else "var(--muted)"
                    order_row  = (
                        f'<div class="pcard-row"><span class="pk">Lineup Slot</span>'
                        f'<span class="pv" style="color:{slot_color}">#{slot} — {slot_ctx}</span></div>'
                    )

            # Rolling form badge
            form_row = ""
            if '_form_label' in slate_df.columns and pd.notna(row.get('_form_label')):
                flabel = row['_form_label']
                frate  = row.get('_form_rate')
                fcolor = "var(--hit)" if '🔥' in str(flabel) else "var(--hr)"
                frate_str = f" ({frate:.2f} H/G)" if pd.notna(frate) else ""
                form_row = (
                    f'<div class="pcard-row"><span class="pk">7-Day Form</span>'
                    f'<span class="pv" style="color:{fcolor}">'
                    f'{flabel}{frate_str}</span></div>'
                )

            # Profile gap explanation row — shows the gap that triggered the badge
            profile_row = ""
            if sc == 'Single_Score':
                xb_val  = float(row.get('XB_Score', 0) or 0)
                hr_val  = float(row.get('HR_Score',  0) or 0)
                xb_gap  = xb_val - disp_val
                hr_gap  = hr_val - disp_val
                if xb_gap >= 7:
                    profile_row = (
                        f'<div class="pcard-row"><span class="pk">XB vs Single gap</span>'
                        f'<span class="pv" style="color:#f59e0b">'
                        f'XB={xb_val:.1f} (+{xb_gap:.1f})</span></div>'
                    )
                elif hr_gap >= 12:
                    profile_row = (
                        f'<div class="pcard-row"><span class="pk">HR vs Single gap</span>'
                        f'<span class="pv" style="color:#ef4444">'
                        f'HR={hr_val:.1f} (+{hr_gap:.1f})</span></div>'
                    )
            elif sc == 'XB_Score':
                hr_val = float(row.get('HR_Score', 0) or 0)
                hr_gap = hr_val - disp_val
                if hr_gap >= 12:
                    profile_row = (
                        f'<div class="pcard-row"><span class="pk">HR vs XB gap</span>'
                        f'<span class="pv" style="color:#ef4444">'
                        f'HR={hr_val:.1f} (+{hr_gap:.1f})</span></div>'
                    )

            cards_html += f"""
            <div class="pcard {css}">
              <div class="pcard-header">
                <div>
                  <div class="pcard-name">{row['Batter']}{profile_badge}</div>
                  <div class="pcard-team">{row['Team']} · {icon} {desc}</div>
                </div>
                <div style="text-align:right">
                  <div class="pcard-score">{disp_val:.1f}</div>
                  <div style="font-size:.6rem;padding:1px 5px;border-radius:20px;
                    background:{tier_color}22;color:{tier_color};font-weight:700;
                    margin-top:.2rem;font-family:'JetBrains Mono',monospace">{tier_lbl}</div>
                </div>
              </div>
              <div class="pcard-row"><span class="pk">Pitcher</span>
                <span class="pv">{row['Pitcher']} {gph}</span></div>
              <div class="pcard-row"><span class="pk">Hit Prob</span>
                <span class="pv">{row['total_hit_prob']:.1f}%</span></div>
              <div class="pcard-row"><span class="pk">1B / XB / HR</span>
                <span class="pv">{row['p_1b']:.1f} / {row['p_xb']:.1f} / {row['p_hr']:.1f}%</span></div>
              <div class="pcard-row"><span class="pk">K%</span>
                <span class="pv {k_cls}">{row['p_k']:.1f}% ({k_lg:+.1f} vs lg)</span></div>
              <div class="pcard-row"><span class="pk">BB%</span>
                <span class="pv {bb_cls}">{row['p_bb']:.1f}% ({bb_lg:+.1f} vs lg)</span></div>
              <div class="pcard-row"><span class="pk">HR vs Lg</span>
                <span class="pv {hr_cls}">{hr_lg:+.2f}%</span></div>
              <div class="pcard-row"><span class="pk">vs Grade</span>
                <span class="pv">{int(row['vs Grade'])}</span></div>
              {profile_row}{order_row}{form_row}{sc_row}{park_row}{hist_row}
            </div>"""

        cards_html += '</div>'
        st.markdown(cards_html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# VISUALIZATIONS
# ─────────────────────────────────────────────────────────────────────────────

def render_visualizations(df: pd.DataFrame, filtered_df: pd.DataFrame, score_col: str):
    with st.expander("📈 Charts & Team Summary", expanded=False):
        axis_cfg  = alt.Axis(gridColor='#1e2d3d', domainColor='#1e2d3d',
                             labelColor='#64748b', titleColor='#64748b', labelFontSize=9)
        title_cfg = lambda t: alt.TitleParams(t, color='#94a3b8', fontSize=11)

        c1, c2 = st.columns(2)
        with c1:
            ch = alt.Chart(df).mark_bar(
                color='#3b82f6', opacity=0.8, cornerRadiusTopLeft=3, cornerRadiusTopRight=3
            ).encode(
                alt.X(f'{score_col}:Q', bin=alt.Bin(maxbins=15), title='Score', axis=axis_cfg),
                alt.Y('count()', title='Players', axis=axis_cfg),
                tooltip=['count()']
            ).properties(title=title_cfg(f'{score_col} Distribution'), width=300, height=200)
            st.altair_chart(ch.configure_view(strokeWidth=0), use_container_width=True)

        with c2:
            if not filtered_df.empty:
                ch2 = alt.Chart(filtered_df).mark_circle(size=80, opacity=0.85).encode(
                    alt.X('total_hit_prob:Q', title='Hit Prob %', axis=axis_cfg),
                    alt.Y('p_k:Q',            title='K Prob %',   axis=axis_cfg),
                    alt.Color(f'{score_col}:Q', scale=alt.Scale(scheme='viridis'), legend=None),
                    alt.Size('p_hr:Q', legend=None),
                    tooltip=['Batter','Team',
                             alt.Tooltip(score_col, format='.1f'),
                             'total_hit_prob','p_k','p_hr','pitch_grade']
                ).properties(title=title_cfg('Hit Prob vs K Risk'), width=300, height=200)
                st.altair_chart(ch2.configure_view(strokeWidth=0), use_container_width=True)

        if not filtered_df.empty and len(filtered_df) <= 30:
            st.markdown("**Individual Score Breakdowns**")
            score_defs = [
                ('Hit_Score',    '#10b981', '🎯 Hit Score'),
                ('Single_Score', '#06b6d4', '1️⃣ Single Score'),
                ('XB_Score',     '#f59e0b', '🔥 XB Score'),
                ('HR_Score',     '#ef4444', '💣 HR Score'),
            ]
            r1c1, r1c2 = st.columns(2)
            r2c1, r2c2 = st.columns(2)
            for i, (sc, colour, label) in enumerate(score_defs):
                if sc not in filtered_df.columns:
                    continue
                chart_df = filtered_df[['Batter', sc]].sort_values(sc, ascending=False)
                ch_s = alt.Chart(chart_df).mark_bar(
                    color=colour, opacity=0.85, cornerRadiusTopLeft=2, cornerRadiusTopRight=2
                ).encode(
                    alt.X('Batter:N', sort='-y',
                          axis=alt.Axis(labelAngle=-45, labelFontSize=8,
                                        labelColor='#64748b', domainColor='#1e2d3d')),
                    alt.Y(f'{sc}:Q', scale=alt.Scale(domain=[0, 100]),
                          axis=alt.Axis(labelFontSize=8, labelColor='#64748b',
                                        domainColor='#1e2d3d', gridColor='#1e2d3d',
                                        title='Score')),
                    tooltip=['Batter', alt.Tooltip(f'{sc}:Q', format='.1f', title='Score')]
                ).properties(title=title_cfg(label), width=250, height=180)
                with [r1c1, r1c2, r2c1, r2c2][i]:
                    st.altair_chart(ch_s.configure_view(strokeWidth=0), use_container_width=True)

        if not filtered_df.empty:
            ts = filtered_df.groupby('Team').agg(
                Players    =('Batter',        'count'),
                AvgHitProb =('total_hit_prob', 'mean'),
                AvgHit     =('Hit_Score',       'mean'),
                AvgXB      =('XB_Score',        'mean'),
                AvgHR      =('HR_Score',        'mean'),
            ).round(1).sort_values('AvgHitProb', ascending=False).reset_index()
            ts.columns = ['Team','Players','Avg Hit%','🎯 Hit','🔥 XB','💣 HR']
            st.markdown("**Team Summary**")
            st.dataframe(ts, width='stretch', hide_index=True)
