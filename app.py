"""
app.py — A1PICKS MLB Hit Predictor V5.2
==========================================
Entry point. Navigation: Predictor | Player Profile | Parlay Builder | Reference

Changes V5.2:
  - _build_scored_df() eliminates 3× copy-pasted pipeline
  - render_player_deep_dive() now called in main_page() with player_id_map
  - player_id_map built once per page load (3600s cache in mlb_api)
"""

import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime

st.set_page_config(
    page_title="A1PICKS MLB Hit Predictor",
    layout="wide",
    page_icon="⚾",
)

from styles import inject_css
from sidebar import (build_filters, apply_filters, get_slate_df,
                     render_lineup_status_sidebar)
from renders import (render_header, render_stat_bar, render_score_summary_cards,
                     render_pitcher_landscape, render_park_notice,
                     render_game_conditions_panel, render_results_table,
                     render_best_per_target, render_visualizations,
                     render_player_deep_dive)
from player_profile import player_profile_page
from parlay import parlay_page
from reference import info_page
from loader import (load_matchups, load_pitcher_data, load_game_conditions,
                    load_pitcher_qs, merge_pitcher_data, merge_game_conditions)
from engine import (compute_metrics, compute_scores, compute_game_condition_scores)

inject_css()

# ─────────────────────────────────────────────────────────────────────────────
# SHARED DATA PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def _build_scored_df(raw_df, pitcher_df, game_cond, qs_df,
                     use_park: bool = True, use_gc: bool = True):
    """
    Single authoritative scoring pipeline used by all three pages.
    The four loader calls are individually @st.cache_data cached — only
    the pandas computation reruns when use_park / use_gc change.
    """
    df = compute_metrics(raw_df, use_park=use_park)
    df = merge_pitcher_data(df, pitcher_df)
    try:
        from savant import join_statcast_to_slate
        df = join_statcast_to_slate(df)
    except Exception:
        pass
    df = compute_scores(df)
    df = merge_game_conditions(df, game_cond, qs_df)
    df = compute_game_condition_scores(df, use_gc=use_gc)
    return df


def _get_player_id_map(df) -> dict:
    """Build batter → MLBAM ID map. Cached for 1h inside mlb_api."""
    try:
        from mlb_api import build_player_id_map
        names = tuple(sorted(df['Batter'].unique().tolist()))
        return build_player_id_map(names)
    except Exception:
        return {}

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
            st.error("❌ Could not load Matchups data.")
            return

        filters = build_filters(raw_df)

        df = _build_scored_df(
            raw_df, pitcher_df, game_cond, qs_df,
            use_park=filters['use_park'],
            use_gc=filters.get('use_gc', True),
        )

    # Promote GC score column when game conditions are active
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

    # ── Player Deep Dive panel (game log + rolling Statcast) ─────────────────
    if not filtered_df.empty:
        player_id_map = _get_player_id_map(df)
        render_player_deep_dive(filtered_df, player_id_map)

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

    # Load all four CSVs once — each is individually @st.cache_data cached
    raw_df     = load_matchups()
    pitcher_df = load_pitcher_data()
    game_cond  = load_game_conditions()
    qs_df      = load_pitcher_qs()

    if page == "⚾ Predictor":
        main_page()

    elif page == "👤 Player Profile":
        if raw_df is None:
            st.error("❌ Could not load Matchups data.")
        else:
            with st.spinner("Loading slate data…"):
                df = _build_scored_df(raw_df, pitcher_df, game_cond, qs_df,
                                      use_park=True, use_gc=True)
            filters = {
                'use_gc': True, 'use_park': True,
                'score_col': 'Hit_Score', 'score_col_base': 'Hit_Score',
            }
            player_id_map = _get_player_id_map(df)
            player_profile_page(df, player_id_map, filters)

    elif page == "⚡ Parlay Builder":
        if raw_df is None:
            st.error("❌ Could not load data for Parlay Builder.")
        else:
            df   = _build_scored_df(raw_df, pitcher_df, game_cond, qs_df,
                                    use_park=True, use_gc=True)
            excl = st.session_state.get('excluded_players', [])
            if excl:
                df = df[~df['Batter'].isin(excl)]
            parlay_page(df)

    else:
        info_page()

    render_lineup_status_sidebar()
    st.sidebar.markdown("---")
    st.sidebar.caption("V5.2 · BallPark Pal + MLB Stats API + Statcast")


if __name__ == "__main__":
    main()
