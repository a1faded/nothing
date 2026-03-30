"""
ui/sidebar.py — Sidebar filters and filter application
"""

import streamlit as st
import pandas as pd
from config import CONFIG


def build_filters(df: pd.DataFrame) -> dict:
    st.sidebar.title("🏟️ A1PICKS Filters")
    st.sidebar.markdown("---")
    filters = {}

    st.sidebar.markdown("### 🎯 Betting Target")
    target_map = {
        "🎯 Hit Score  — Any Base Hit":          "hit",
        "1️⃣ Single Score — Single Specifically":  "single",
        "🔥 XB Score  — Double / Triple":         "xb",
        "💣 HR Score  — Home Run":                "hr",
    }
    label = st.sidebar.selectbox("Choose Your Betting Target", list(target_map.keys()))
    filters['target']    = target_map[label]
    score_col_map        = {'hit':'Hit_Score','single':'Single_Score','xb':'XB_Score','hr':'HR_Score'}
    filters['score_col'] = score_col_map[filters['target']]
    filters['score_col_base'] = filters['score_col']

    st.sidebar.markdown("### 🏟️ Park Adjustment")
    filters['use_park'] = st.sidebar.toggle(
        "Include Park Factors", value=True,
        help="ON = blends park-adjusted + base probabilities.\nOFF = pure player vs pitcher only."
    )

    st.sidebar.markdown("### 🌦️ Game Conditions")
    filters['use_gc'] = st.sidebar.toggle(
        "🌦️ Game Conditions (Full Weight)", value=True,
        help=(
            "ON → Full game-environment ceiling applied (±40% Hit/Single/XB, ±35% HR).\n"
            "OFF → 30% of full weight applied (not zero)."
        )
    )
    if filters['use_gc']:
        st.sidebar.markdown(
            '<small style="color:#64748b">Cond Δ column shows per-player impact</small>',
            unsafe_allow_html=True
        )

    st.sidebar.markdown("### ⚾ Pitcher Filter")
    filters['starters_only'] = st.sidebar.checkbox("Starters only", value=False)

    st.sidebar.markdown("### 📊 Stat Filters")
    filters['max_k']  = st.sidebar.slider("Max K Prob %",  10.0, 50.0, 35.0, 0.5)
    filters['max_bb'] = st.sidebar.slider("Max BB Prob %",  2.0, 20.0, 15.0, 0.5)

    min_cfg = {
        'hit':    ("Min Hit Prob % (1B+XB+HR)", "total_hit_prob", 0.0, 50.0, 20.0),
        'single': ("Min 1B Prob %",              "p_1b",           0.0, 30.0, 10.0),
        'xb':     ("Min XB Prob %",              "p_xb",           0.0, 12.0,  4.0),
        'hr':     ("Min HR Prob %",              "p_hr",           0.0,  8.0,  2.0),
    }
    pl, pc, mn, mx, dv = min_cfg[filters['target']]
    filters['min_prob']     = st.sidebar.slider(pl, mn, mx, dv, 0.5)
    filters['min_prob_col'] = pc
    filters['min_vs']       = st.sidebar.slider("Min vs Grade", -10, 10, -10, 1)

    st.sidebar.markdown("### 🏟️ Team Filters")
    all_teams = sorted(df['Team'].unique().tolist()) if df is not None else []
    filters['include_teams'] = st.sidebar.multiselect("Include Only Teams", options=all_teams)
    filters['exclude_teams'] = st.sidebar.multiselect("Exclude Teams",       options=all_teams)

    st.sidebar.markdown("### 🚫 Lineup Status")
    if 'excluded_players' not in st.session_state:
        st.session_state.excluded_players = []
    all_players = sorted(df['Batter'].unique().tolist()) if df is not None else []
    excl = st.sidebar.multiselect(
        "Players NOT Playing Today",
        options=all_players,
        default=st.session_state.excluded_players,
        key="lineup_exclusions"
    )
    st.session_state.excluded_players = excl
    filters['excluded_players'] = excl
    if st.sidebar.button("🔄 Clear All Exclusions"):
        st.session_state.excluded_players = []
        st.rerun()

    st.sidebar.markdown("### 🔢 Display")
    sort_options = {
        "Score (High→Low)":         (filters['score_col'], False),
        "Hit Prob % (High→Low)":    ("total_hit_prob",     False),
        "1B Prob % (High→Low)":     ("p_1b",               False),
        "XB Prob % (High→Low)":     ("p_xb",               False),
        "HR Prob % (High→Low)":     ("p_hr",               False),
        "K Prob % (Low→High)":      ("p_k",                True),
        "BB Prob % (Low→High)":     ("p_bb",               True),
        "vs Grade (High→Low)":      ("vs Grade",           False),
        "Pitcher Grade (A+→D)":     ("pitch_grade",        True),
    }
    filters['sort_label'] = st.sidebar.selectbox("Sort By", list(sort_options.keys()))
    filters['sort_col'], filters['sort_asc'] = sort_options[filters['sort_label']]
    filters['result_count'] = st.sidebar.selectbox("Show Top N", [5,10,15,20,25,30,"All"], index=2)
    filters['best_per_team'] = st.sidebar.checkbox("🏟️ Best player per team only", value=False)
    return filters


def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()

    if filters.get('starters_only'):
        out = out[out['Starter'] == 1]

    excl = filters.get('excluded_players', [])
    if excl:
        n = len(out)
        out = out[~out['Batter'].isin(excl)]
        if n - len(out):
            st.info(f"🚫 Excluded {n - len(out)} player(s) from lineups")

    if filters.get('include_teams'):
        out = out[out['Team'].isin(filters['include_teams'])]
    if filters.get('exclude_teams'):
        n = len(out)
        out = out[~out['Team'].isin(filters['exclude_teams'])]
        if n - len(out):
            st.info(f"🚫 Excluded players from {', '.join(filters['exclude_teams'])}")

    out = out[out['p_k']  <= filters['max_k']]
    out = out[out['p_bb'] <= filters['max_bb']]

    mc = filters.get('min_prob_col', 'total_hit_prob')
    if mc in out.columns:
        out = out[out[mc] >= filters['min_prob']]

    if filters['min_vs'] > -10:
        out = out[pd.to_numeric(out['vs Grade'], errors='coerce').fillna(-10) >= filters['min_vs']]

    sc     = filters['score_col']
    sc_eff = sc if sc in out.columns else filters.get('score_col_base', sc)

    if filters.get('best_per_team') and not out.empty:
        out = out.loc[out.groupby('Team')[sc_eff].idxmax()].copy()
        st.info(f"🏟️ Best player from each of {len(out)} teams")

    sc_s = filters['sort_col']
    if sc_s not in out.columns:
        sc_s = sc_s.replace('_gc', '') if sc_s.endswith('_gc') else sc_s
    if sc_s in out.columns:
        out[sc_s] = pd.to_numeric(out[sc_s], errors='coerce')
        out = out.sort_values(sc_s, ascending=filters['sort_asc'], na_position='last')

    n = filters['result_count']
    if n != "All":
        out = out.head(int(n))
    return out


def get_slate_df(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """Full slate with player exclusions only — for persistent summary sections."""
    if df is None or df.empty:
        return df
    out = df.copy()
    excl = filters.get('excluded_players', [])
    if excl:
        out = out[~out['Batter'].isin(excl)]
    return out
