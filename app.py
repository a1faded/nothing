"""
app.py — A1PICKS MLB Hit Predictor  V5.0
==========================================
Entry point. Thin as possible — just wires modules together.

Module map:
  config.py           → all constants, mappings, CONFIG dict
  data/loader.py      → BallPark Pal CSV loading (current primary source)
  data/mlb_api.py     → MLB Stats API (player stats, lineups, game logs)
  data/savant.py      → Baseball Savant / pybaseball (Statcast metrics)
  scoring/engine.py   → metric computation + all four scores + GC scores
  ui/styles.py        → CSS injection
  ui/sidebar.py       → build_filters, apply_filters, get_slate_df
  ui/renders.py       → all render_* functions (header, table, cards, charts)
  ui/parlay.py        → parlay builder
  ui/reference.py     → reference manual page
  utils/helpers.py    → normalize_0_100, grade_pill, freshness badge, etc.
"""

import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime

# ── Page config must be first Streamlit call ──────────────────────────────────
st.set_page_config(
    page_title="A1PICKS MLB Hit Predictor",
    layout="wide",
    page_icon="⚾",
)

# ── Module imports ─────────────────────────────────────────────────────────────
from ui.styles   import inject_css
from ui.sidebar  import build_filters, apply_filters, get_slate_df
from ui.renders  import (
    render_header,
    render_stat_bar,
    render_score_summary_cards,
    render_pitcher_landscape,
    render_park_notice,
    render_game_conditions_panel,
    render_results_table,
    render_best_per_target,
    render_visualizations,
)
from ui.parlay    import parlay_page
from ui.reference import info_page

from data.loader  import (
    load_matchups,
    load_pitcher_data,
    load_game_conditions,
    load_pitcher_qs,
    merge_pitcher_data,
    merge_game_conditions,
)
from scoring.engine import (
    compute_metrics,
    compute_scores,
    compute_game_condition_scores,
)

# ── Inject CSS ─────────────────────────────────────────────────────────────────
inject_css()


# ─────────────────────────────────────────────────────────────────────────────
# PREDICTOR PAGE
# ─────────────────────────────────────────────────────────────────────────────

def main_page():
    render_header()

    with st.spinner("⚾ Loading today's matchups…"):
        raw_df     = load_matchups()
        pitcher_df = load_pitcher_data()
        game_cond  = load_game_conditions()
        qs_df      = load_pitcher_qs()

    if raw_df is None:
        st.error("❌ Could not load Matchups data. Check connection or try again.")
        return

    filters = build_filters(raw_df)
    df      = compute_metrics(raw_df, use_park=filters['use_park'])
    df      = merge_pitcher_data(df, pitcher_df)
    df      = compute_scores(df)
    df      = merge_game_conditions(df, game_cond, qs_df)
    df      = compute_game_condition_scores(df, use_gc=filters.get('use_gc', True))

    # When GC toggle ON, upgrade the active score column to its _gc variant
    if filters.get('use_gc', False):
        gc_col = filters['score_col'] + '_gc'
        if gc_col in df.columns:
            filters['score_col'] = gc_col
            if filters.get('sort_col') == filters.get('score_col_base'):
                filters['sort_col'] = gc_col

    slate_df    = get_slate_df(df, filters)
    filtered_df = apply_filters(df, filters)

    render_stat_bar(df)
    render_pitcher_landscape(pitcher_df, df)
    render_park_notice(slate_df, filters)
    render_game_conditions_panel(slate_df, filters, game_cond, qs_df)
    render_score_summary_cards(slate_df, filters)

    target_labels = {
        'Hit_Score':       '🎯 Any Base Hit',
        'Single_Score':    '1️⃣ Single',
        'XB_Score':        '🔥 Extra Base Hit',
        'HR_Score':        '💣 Home Run',
        'Hit_Score_gc':    '🎯 Any Base Hit ⛅',
        'Single_Score_gc': '1️⃣ Single ⛅',
        'XB_Score_gc':     '🔥 Extra Base Hit ⛅',
        'HR_Score_gc':     '💣 Home Run ⛅',
    }
    display_sc = filters['score_col_base']
    st.markdown(f"""
<div class="result-head">
  <span class="rh-label">{target_labels.get(filters['score_col'], target_labels.get(display_sc, 'Hit'))} Candidates</span>
  <span class="rh-count">{len(filtered_df)} results</span>
</div>
""", unsafe_allow_html=True)

    render_results_table(filtered_df, filters)
    render_best_per_target(slate_df, filters)

    if not filtered_df.empty:
        render_visualizations(df, filtered_df, filters['score_col_base'])

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()
    with c2:
        if not filtered_df.empty:
            st.download_button(
                "💾 Export CSV",
                filtered_df.to_csv(index=False),
                f"a1picks_mlb_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv"
            )


# ─────────────────────────────────────────────────────────────────────────────
# NAVIGATION
# ─────────────────────────────────────────────────────────────────────────────

def main():
    st.sidebar.markdown("---")
    if st.sidebar.checkbox("🎵 Music"):
        audio_url = (
            "https://github.com/a1faded/a1picks-hits-bot/raw/refs/heads/main/"
            "Take%20Me%20Out%20to%20the%20Ballgame%20-%20Nancy%20Bea%20-%20Dodger%20Stadium%20Organ.mp3"
        )
        components.html(
            f'<audio controls autoplay loop style="width:100%;">'
            f'<source src="{audio_url}" type="audio/mpeg"></audio>',
            height=55
        )

    page = st.sidebar.radio(
        "Navigate",
        ["⚾ Predictor", "⚡ Parlay Builder", "📚 Reference Manual"],
        index=0
    )

    if page == "⚾ Predictor":
        main_page()

    elif page == "⚡ Parlay Builder":
        raw_df = load_matchups()
        if raw_df is not None:
            pitcher_df = load_pitcher_data()
            game_cond  = load_game_conditions()
            qs_df      = load_pitcher_qs()
            df = compute_metrics(raw_df, use_park=True)
            df = merge_pitcher_data(df, pitcher_df)
            df = compute_scores(df)
            df = merge_game_conditions(df, game_cond, qs_df)
            df = compute_game_condition_scores(df, use_gc=True)
            excl = st.session_state.get('excluded_players', [])
            if excl:
                df = df[~df['Batter'].isin(excl)]
            parlay_page(df)
        else:
            st.error("❌ Could not load data for Parlay Builder.")

    else:
        info_page()

    st.sidebar.markdown("---")
    st.sidebar.caption("V5.0 · Multi-module · MLB Stats API ready · BallPark Pal + Savant")


if __name__ == "__main__":
    main()
