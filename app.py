"""
app.py — A1PICKS MLB Hit Predictor  V5.1
==========================================
Entry point. Navigation: Predictor | Player Profile | Parlay Builder | Reference
"""

import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime

st.set_page_config(
    page_title="A1PICKS MLB Hit Predictor",
    layout="wide",
    page_icon="⚾",
)

from styles         import inject_css
from sidebar        import (build_filters, apply_filters, get_slate_df,
                             render_lineup_status_sidebar)
from renders        import (render_header, render_stat_bar, render_score_summary_cards,
                             render_pitcher_landscape, render_park_notice,
                             render_game_conditions_panel, render_results_table,
                             render_best_per_target, render_visualizations)
from player_profile import player_profile_page
from parlay         import parlay_page
from reference      import info_page

from loader  import (load_matchups, load_pitcher_data, load_game_conditions,
                      load_pitcher_qs, merge_pitcher_data, merge_game_conditions)
from engine  import (compute_metrics, compute_scores, compute_game_condition_scores)

inject_css()


def _load_and_score(use_park=True, use_gc=True):
    """Shared data pipeline used by both Predictor and Parlay pages."""
    raw_df     = load_matchups()
    if raw_df is None:
        return None, None, None, None
    pitcher_df = load_pitcher_data()
    game_cond  = load_game_conditions()
    qs_df      = load_pitcher_qs()
    df = compute_metrics(raw_df, use_park=use_park)
    df = merge_pitcher_data(df, pitcher_df)

    # Join Statcast BEFORE scoring so scores can use Barrel%/HH%
    try:
        from savant import join_statcast_to_slate
        df = join_statcast_to_slate(df)
    except Exception:
        pass

    df = compute_scores(df)
    df = merge_game_conditions(df, game_cond, qs_df)
    df = compute_game_condition_scores(df, use_gc=use_gc)
    return df, pitcher_df, game_cond, qs_df


def _get_player_id_map(df):
    try:
        from mlb_api import build_player_id_map
        batter_names = tuple(sorted(df['Batter'].unique().tolist()))
        return build_player_id_map(batter_names)
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# PREDICTOR PAGE
# ─────────────────────────────────────────────────────────────────────────────

def main_page():
    render_header()

    with st.spinner("⚾ Loading today's matchups…"):
        filters    = {}   # Need raw_df first for filters
        raw_df     = load_matchups()
        pitcher_df = load_pitcher_data()
        game_cond  = load_game_conditions()
        qs_df      = load_pitcher_qs()

    if raw_df is None:
        st.error("❌ Could not load Matchups data.")
        return

    filters = build_filters(raw_df)

    df = compute_metrics(raw_df, use_park=filters['use_park'])
    df = merge_pitcher_data(df, pitcher_df)

    # Statcast join BEFORE scoring
    try:
        from savant import join_statcast_to_slate
        df = join_statcast_to_slate(df)
    except Exception:
        pass

    df = compute_scores(df)
    df = merge_game_conditions(df, game_cond, qs_df)
    df = compute_game_condition_scores(df, use_gc=filters.get('use_gc', True))

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
  <span class="rh-label">
    {target_labels.get(filters['score_col'], target_labels.get(display_sc,'Hit'))} Candidates
  </span>
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
        ["⚾ Predictor", "👤 Player Profile", "⚡ Parlay Builder", "📚 Reference Manual"],
        index=0
    )

    if page == "⚾ Predictor":
        main_page()

    elif page == "👤 Player Profile":
        with st.spinner("Loading slate data…"):
            raw_df = load_matchups()
        if raw_df is None:
            st.error("❌ Could not load Matchups data.")
        else:
            pitcher_df  = load_pitcher_data()
            game_cond   = load_game_conditions()
            qs_df       = load_pitcher_qs()
            df = compute_metrics(raw_df, use_park=True)
            df = merge_pitcher_data(df, pitcher_df)
            try:
                from savant import join_statcast_to_slate
                df = join_statcast_to_slate(df)
            except Exception:
                pass
            df = compute_scores(df)
            df = merge_game_conditions(df, game_cond, qs_df)
            df = compute_game_condition_scores(df, use_gc=True)

            # Build filters just for GC context (don't render sidebar filters here)
            filters = {
                'use_gc': True, 'use_park': True,
                'score_col': 'Hit_Score', 'score_col_base': 'Hit_Score',
            }
            player_id_map = _get_player_id_map(df)
            player_profile_page(df, player_id_map, filters)

    elif page == "⚡ Parlay Builder":
        raw_df = load_matchups()
        if raw_df is not None:
            pitcher_df = load_pitcher_data()
            game_cond  = load_game_conditions()
            qs_df      = load_pitcher_qs()
            df = compute_metrics(raw_df, use_park=True)
            df = merge_pitcher_data(df, pitcher_df)
            try:
                from savant import join_statcast_to_slate
                df = join_statcast_to_slate(df)
            except Exception:
                pass
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

    render_lineup_status_sidebar()

    st.sidebar.markdown("---")
    st.sidebar.caption("V5.1 · BallPark Pal + MLB Stats API + Statcast")


if __name__ == "__main__":
    main()
