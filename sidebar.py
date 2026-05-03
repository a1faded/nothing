"""
sidebar.py — Sidebar filters, filter application, lineup status panel

V2: Added "Confirmed lineups only" toggle.
    When ON, app.py filters the df to only show batters present in
    today's confirmed batting orders. Prevents betting on sitting players.
"""

import streamlit as st
import pandas as pd
from config import CONFIG


def build_filters(df: pd.DataFrame, container=None, key_prefix: str = "sidebar", show_title: bool = True) -> dict:
    """
    Build the predictor filter controls in any Streamlit container.

    This used to be sidebar-only.  The app now renders these controls in the
    main page so mobile users are not forced to open Streamlit's sidebar.
    The same function still supports st.sidebar for future desktop-only uses.
    """
    ui = container or st.sidebar

    if show_title:
        ui.markdown("### 🏟️ A1PICKS Filters")
        ui.markdown("---")

    filters = {}

    # ── Target ────────────────────────────────────────────────────────────────
    ui.markdown("#### 🎯 Betting Target")
    target_map = {
        "🎯 Hit Score — Any Base Hit":          "hit",
        "1️⃣ Single Score — Single Only":       "single",
        "🔥 XB Score — Double / Triple":        "xb",
        "💣 HR Score — Home Run":               "hr",
        "🔴 H+R+RBI Score — Hits+Runs+RBIs":   "hrr",
    }
    label = ui.selectbox(
        "Choose Your Betting Target",
        list(target_map.keys()),
        key=f"{key_prefix}_target",
    )
    filters['target'] = target_map[label]
    score_col_map = {'hit':'Hit_Score','single':'Single_Score',
                     'xb':'XB_Score','hr':'HR_Score','hrr':'HRR_Score'}
    filters['score_col']      = score_col_map[filters['target']]
    filters['score_col_base'] = filters['score_col']

    # ── Park / GC toggles ─────────────────────────────────────────────────────
    c1, c2 = ui.columns(2)
    with c1:
        st.markdown("#### 🏟️ Park")
        filters['use_park'] = st.toggle(
            "Include Park Factors", value=True,
            key=f"{key_prefix}_use_park",
            help="ON = blends park-adjusted + base probabilities.\nOFF = pure player vs pitcher."
        )
    with c2:
        st.markdown("#### 🌦️ Conditions")
        filters['use_gc'] = st.toggle(
            "Game Conditions", value=True,
            key=f"{key_prefix}_use_gc",
            help="ON → Full game-environment ceiling (±40% Hit/XB, ±35% HR).\nOFF → 30% of full weight."
        )
    if filters['use_gc']:
        ui.markdown(
            '<small style="color:#64748b">Cond Δ column shows per-player impact</small>',
            unsafe_allow_html=True
        )

    # ── Lineup filters ────────────────────────────────────────────────────────
    ui.markdown("#### 📋 Lineup")
    l1, l2 = ui.columns(2)
    with l1:
        filters['starters_only'] = st.checkbox(
            "Starters only", value=False, key=f"{key_prefix}_starters_only"
        )
    with l2:
        filters['confirmed_only'] = st.toggle(
            "✅ Confirmed lineups only",
            value=False,
            key=f"{key_prefix}_confirmed_only",
            help="ON = hide players not yet in a confirmed batting order.\n"
                 "Lineups typically confirm 60-90 min before first pitch."
        )

    # ── Stat filters ──────────────────────────────────────────────────────────
    ui.markdown("#### 📊 Stat Filters")
    s1, s2 = ui.columns(2)
    with s1:
        filters['max_k'] = st.slider(
            "Max K Prob %", 10.0, 50.0, 35.0, 0.5, key=f"{key_prefix}_max_k"
        )
    with s2:
        filters['max_bb'] = st.slider(
            "Max BB Prob %", 2.0, 20.0, 15.0, 0.5, key=f"{key_prefix}_max_bb"
        )

    min_cfg = {
        'hit':   ("Min Hit Prob % (1B+XB+HR)", "total_hit_prob", 0.0, 50.0, 20.0),
        'single':("Min 1B Prob %",             "p_1b",           0.0, 30.0, 10.0),
        'xb':    ("Min XB Prob %",             "p_xb",           0.0, 12.0,  4.0),
        'hr':    ("Min HR Prob %",             "p_hr",           0.0,  8.0,  2.0),
        'hrr':   ("Min Hit Prob % (H+R+RBI)",  "total_hit_prob", 0.0, 50.0, 15.0),
    }
    pl, pc, mn, mx, dv = min_cfg[filters['target']]
    s3, s4 = ui.columns(2)
    with s3:
        filters['min_prob'] = st.slider(pl, mn, mx, dv, 0.5, key=f"{key_prefix}_min_prob")
        filters['min_prob_col'] = pc
    with s4:
        filters['min_vs'] = st.slider("Min vs Grade", -10, 10, -10, 1, key=f"{key_prefix}_min_vs")

    # ── Team filters ──────────────────────────────────────────────────────────
    ui.markdown("#### 🏟️ Team Filters")
    all_teams = sorted(df['Team'].dropna().unique().tolist()) if df is not None and 'Team' in df.columns else []
    t1, t2 = ui.columns(2)
    with t1:
        filters['include_teams'] = st.multiselect(
            "Include Only Teams", options=all_teams, key=f"{key_prefix}_include_teams"
        )
    with t2:
        filters['exclude_teams'] = st.multiselect(
            "Exclude Teams", options=all_teams, key=f"{key_prefix}_exclude_teams"
        )

    # ── Player exclusions ─────────────────────────────────────────────────────
    ui.markdown("#### 🚫 Player Exclusions")
    if 'excluded_players' not in st.session_state:
        st.session_state.excluded_players = []
    all_players = sorted(df['Batter'].dropna().unique().tolist()) if df is not None and 'Batter' in df.columns else []
    default_exclusions = [p for p in st.session_state.excluded_players if p in all_players]
    excl = ui.multiselect(
        "Players NOT Playing Today",
        options=all_players,
        default=default_exclusions,
        key=f"{key_prefix}_lineup_exclusions",
    )
    st.session_state.excluded_players = excl
    filters['excluded_players'] = excl
    def _clear_exclusions(widget_key: str):
        st.session_state.excluded_players = []
        st.session_state[widget_key] = []

    ui.button(
        "🔄 Clear All Exclusions",
        key=f"{key_prefix}_clear_exclusions",
        on_click=_clear_exclusions,
        args=(f"{key_prefix}_lineup_exclusions",),
    )

    # ── Display ───────────────────────────────────────────────────────────────
    ui.markdown("#### 🔢 Display")
    sort_options = {
        "Score (High→Low)":      (filters['score_col'], False),
        "Hit Prob % (High→Low)": ("total_hit_prob",    False),
        "1B Prob % (High→Low)":  ("p_1b",              False),
        "XB Prob % (High→Low)":  ("p_xb",              False),
        "HR Prob % (High→Low)":  ("p_hr",              False),
        "K Prob % (Low→High)":   ("p_k",               True),
        "BB Prob % (Low→High)":  ("p_bb",              True),
        "vs Grade (High→Low)":   ("vs Grade",          False),
        "Pitcher Grade (A+→D)":  ("pitch_grade",       True),
    }
    d1, d2, d3 = ui.columns(3)
    with d1:
        filters['sort_label'] = st.selectbox(
            "Sort By", list(sort_options.keys()), key=f"{key_prefix}_sort_label"
        )
    filters['sort_col'], filters['sort_asc'] = sort_options[filters['sort_label']]
    with d2:
        filters['result_count'] = st.selectbox(
            "Show Top N", [5,10,15,20,25,30,"All"], index=2, key=f"{key_prefix}_result_count"
        )
    with d3:
        filters['best_per_team'] = st.checkbox(
            "🏟️ Best per team", value=False, key=f"{key_prefix}_best_per_team"
        )

    return filters


def build_predictor_control_panel(df: pd.DataFrame) -> dict:
    """Primary predictor controls shown in the main page for mobile usability."""
    st.markdown(
        '<div class="mobile-control-intro">📱 <b>Controls & Filters</b> — primary controls are here so the app is usable on phones without opening the Streamlit sidebar.</div>',
        unsafe_allow_html=True,
    )
    with st.expander("⚙️ Open / close predictor controls", expanded=True):
        return build_filters(df, container=st, key_prefix="main_filters", show_title=False)

def render_lineup_status_sidebar():
    try:
        from mlb_api import get_lineup_status_map
        status_map = get_lineup_status_map()
        if not status_map:
            return
        confirmed = sum(1 for v in status_map.values() if '✅' in v['status'])
        total     = len(status_map)
        st.sidebar.markdown("### 📋 Lineup Status")
        st.sidebar.markdown(
            f'<div style="font-size:.75rem;color:#64748b;margin-bottom:.3rem">'
            f'{confirmed}/{total} games confirmed</div>',
            unsafe_allow_html=True
        )
        for matchup, info in status_map.items():
            icon = '✅' if '✅' in info['status'] else '⏳'
            st.sidebar.markdown(
                f'<div style="font-size:.72rem;padding:.2rem 0;'
                f'border-bottom:1px solid #1e2d3d;color:#e2e8f0">'
                f'{icon} <b>{matchup}</b><br>'
                f'<span style="color:#64748b;font-size:.65rem">'
                f'SP: {info["away_sp"]} / {info["home_sp"]}</span>'
                f'</div>',
                unsafe_allow_html=True
            )
    except Exception:
        pass


def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()

    if filters.get('starters_only'):
        out = out[out['Starter'] == 1]

    excl = filters.get('excluded_players', [])
    if excl:
        n   = len(out)
        out = out[~out['Batter'].isin(excl)]
        if n - len(out):
            st.info(f"🚫 Excluded {n - len(out)} player(s) from lineups")

    if filters.get('include_teams'):
        out = out[out['Team'].isin(filters['include_teams'])]
    if filters.get('exclude_teams'):
        n   = len(out)
        out = out[~out['Team'].isin(filters['exclude_teams'])]
        if n - len(out):
            st.info(f"🚫 Excluded players from {', '.join(filters['exclude_teams'])}")

    out = out[out['p_k']  <= filters['max_k']]
    out = out[out['p_bb'] <= filters['max_bb']]

    mc = filters.get('min_prob_col', 'total_hit_prob')
    if mc in out.columns:
        out = out[out[mc] >= filters['min_prob']]

    if filters['min_vs'] > -10:
        out = out[pd.to_numeric(out['vs Grade'],errors='coerce').fillna(-10) >= filters['min_vs']]

    sc     = filters['score_col']
    sc_eff = sc if sc in out.columns else filters.get('score_col_base', sc)

    if filters.get('best_per_team') and not out.empty:
        out = out.loc[out.groupby('Team')[sc_eff].idxmax()].copy()
        st.info(f"🏟️ Best player from each of {len(out)} teams")

    sc_s = filters['sort_col']
    if sc_s not in out.columns:
        sc_s = sc_s.replace('_gc','') if sc_s.endswith('_gc') else sc_s
    if sc_s in out.columns:
        out[sc_s] = pd.to_numeric(out[sc_s], errors='coerce')

        # ── Profile-prioritized sort ───────────────────────────────────────────
        # For Single and XB targets: profile-eligible players always rank above
        # profile-mismatched ones, even if their raw score is lower.
        # Mismatched players are still shown (visible but ranked below eligibles).
        #
        # Single: mismatched = XB_Score > Single_Score OR HR_Score > Single_Score
        # XB:     mismatched = HR_Score > XB_Score
        # Hit/HR: no profile ranking — sort purely by score
        sc_base_for_sort = filters.get('score_col_base', sc_s.replace('_gc',''))
        is_profile_target = sc_base_for_sort in ('Single_Score', 'XB_Score')
        if is_profile_target and not out.empty:
            if sc_base_for_sort == 'Single_Score':
                mismatch = pd.Series(False, index=out.index)
                if 'XB_Score' in out.columns:
                    mismatch |= (out['XB_Score'] > out['Single_Score'])
                if 'HR_Score' in out.columns:
                    mismatch |= (out['HR_Score'] > out['Single_Score'])
            else:   # XB_Score
                mismatch = pd.Series(False, index=out.index)
                if 'HR_Score' in out.columns:
                    mismatch |= (out['HR_Score'] > out['XB_Score'])

            out['_profile_rank'] = mismatch.astype(int)   # 0=eligible, 1=mismatch
            out = out.sort_values(
                ['_profile_rank', sc_s],
                ascending=[True, filters['sort_asc']],
                na_position='last'
            ).drop(columns=['_profile_rank'])
        else:
            out = out.sort_values(sc_s, ascending=filters['sort_asc'], na_position='last')

    n = filters['result_count']
    if n != "All":
        out = out.head(int(n))
    return out


def get_slate_df(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """
    Slate df used by Today's Best and Best Per Target sections.

    Applies ALL global filters so these sections always reflect the user's
    active filter state — not just exclusions.

    Global filters (applied here AND in apply_filters):
      excluded_players  — manually excluded players
      starters_only     — only lineup starters (Starter == 1)
      include_teams     — only show selected teams
      exclude_teams     — hide selected teams

    Stat filters (only in apply_filters, NOT here):
      max_k, max_bb, min_prob, min_vs, result_count, best_per_team
      These are "narrow" filters for the results table, not for the best-player cards.

    Note: confirmed_only is applied to df in app.py BEFORE this is called,
    so slate_df automatically inherits it.
    """
    if df is None or df.empty:
        return df

    out = df.copy()

    # Exclusions
    excl = filters.get('excluded_players', [])
    if excl:
        out = out[~out['Batter'].isin(excl)]

    # Starters only — most important: Today's Best should only show starting players
    if filters.get('starters_only') and 'Starter' in out.columns:
        out = out[out['Starter'] == 1]

    # Team filters
    if filters.get('include_teams'):
        out = out[out['Team'].isin(filters['include_teams'])]
    if filters.get('exclude_teams'):
        out = out[~out['Team'].isin(filters['exclude_teams'])]

    return out
