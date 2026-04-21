"""
app.py — A1PICKS MLB Hit Predictor V7
======================================
New in V7:
  - Auto cache invalidation when GitHub detects new Matchups.csv commit
  - Slate staleness warning banner
  - Confirmed lineup filter (sidebar toggle)
  - New signal data (order_map, form_map, handedness_map) fetched once,
    passed into compute_scores()
"""

import logging
import pandas as pd
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
                     render_player_deep_dive, render_staleness_warning)
from player_profile import player_profile_page
from parlay import parlay_page
from unders import under_page
from reference import info_page
from loader import (load_matchups, load_pitcher_data, load_game_conditions,
                    load_pitcher_qs, merge_pitcher_data, merge_game_conditions)
from engine import (compute_metrics, compute_scores, compute_game_condition_scores)
from helpers import should_auto_invalidate

inject_css()

LOGGER = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# DATA PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def _build_scored_df(raw_df, pitcher_df, game_cond, qs_df,
                     use_park=True, use_gc=True,
                     order_map=None, form_map=None, handedness_map=None):
    """
    Full scoring pipeline. New signal dicts are optional — all default to {}
    so the pipeline degrades gracefully when API data is unavailable.
    """
    df = compute_metrics(raw_df, use_park=use_park)
    df = merge_pitcher_data(df, pitcher_df)
    try:
        from savant import join_statcast_to_slate
        df = join_statcast_to_slate(df)
    except Exception:
        pass
    df = compute_scores(df,
                        order_map=order_map or {},
                        form_map=form_map or {},
                        handedness_map=handedness_map or {})
    df = merge_game_conditions(df, game_cond, qs_df)
    df = compute_game_condition_scores(df, use_gc=use_gc)
    return df


def _get_player_id_map(df) -> dict:
    try:
        from mlb_api import build_player_id_map
        return build_player_id_map(tuple(sorted(df['Batter'].unique().tolist())))
    except Exception:
        return {}


def _enrich_with_ids(df, player_id_map):
    if not player_id_map:
        return df
    try:
        from savant import enrich_slate_with_statcast
        return enrich_slate_with_statcast(df, player_id_map)
    except Exception:
        return df


def _enrich_with_prop_odds(df, player_id_map: dict) -> pd.DataFrame:
    """Fetch today's player prop odds from Tank01 and join to df by MLBAM ID."""
    try:
        from prop_odds import fetch_player_props, enrich_with_props
        props = fetch_player_props()
        return enrich_with_props(df, player_id_map, props)
    except Exception:
        return df


def _enrich_with_tank_stats(df, player_id_map: dict) -> pd.DataFrame:
    """
    Fetch BvP and splits data from Tank01 and join to df.

    Pitcher ID map is built directly from df['Pitcher'] using the Tank01
    player list — no schedule API dependency, works even when lineups
    are not yet confirmed. This fixes the "No history" issue.
    """
    try:
        from mlb_api import _lookup_player_mlbam
        from tank_stats import (build_bvp_map, build_splits_map,
                                 enrich_with_bvp, enrich_with_splits)

        # Build pitcher_id_map from df['Pitcher'] — always available from BallPark Pal
        # {batter_name: pitcher_mlbam} derived from the Pitcher column each row already has
        pitcher_id_map: dict[str, int] = {}
        if 'Pitcher' in df.columns and 'Batter' in df.columns:
            for _, row in df.iterrows():
                pitcher_name = str(row.get('_pitcher_full_name') or row.get('Pitcher', '') or '').strip()
                batter_name  = str(row.get('Batter',  '') or '').strip()
                if not pitcher_name or not batter_name:
                    continue
                pid = _lookup_player_mlbam(pitcher_name)
                if pid:
                    pitcher_id_map[batter_name] = pid
                    # Also map by last name for fallback
                    last = batter_name.split()[-1]
                    pitcher_id_map[last] = pid

        if not pitcher_id_map:
            return df

        bvp_map = build_bvp_map(df, player_id_map, pitcher_id_map)
        df      = enrich_with_bvp(df, player_id_map, bvp_map)
        batter_splits, pitcher_splits = build_splits_map(
            df, player_id_map, pitcher_id_map)
        df = enrich_with_splits(
            df, player_id_map, pitcher_id_map,
            batter_splits, pitcher_splits)
        return df
    except Exception:
        return df


def _merge_signal_metadata(df, order_map: dict, form_map: dict,
                            handedness_map: dict) -> pd.DataFrame:
    """
    Attach signal data as display columns so renders.py / player_profile.py
    can surface them without re-fetching.

    Columns added:
      _order_pos    int 1-9 batting slot  (NaN = unconfirmed)
      _form_rate    float H/G last 7 days (NaN = missing)
      _form_label   '🔥 HOT' / '❄️ COLD' / None
      _pitcher_hand 'L' / 'R' / None
    """
    from config import CONFIG as _cfg
    HOT  = _cfg['form_hot_threshold']
    COLD = _cfg['form_cold_threshold']
    df   = df.copy()

    if order_map:
        df['_order_pos'] = df['Batter'].map(order_map)

    if form_map:
        def _label(name):
            info = form_map.get(name)
            if not info or info.get('games', 0) < 3:
                return None
            rate = info.get('hit_rate', 0)
            if rate >= HOT:  return '🔥 HOT'
            if rate <= COLD: return '❄️ COLD'
            return None

        df['_form_rate']  = df['Batter'].apply(
            lambda n: form_map.get(n, {}).get('hit_rate'))
        df['_form_label'] = df['Batter'].apply(_label)

    if handedness_map:
        df['_pitcher_hand'] = df.apply(
            lambda r: handedness_map.get(r.get('_pitcher_full_name'))
            or handedness_map.get(r.get('_pitcher_key'))
            or handedness_map.get(r.get('Pitcher')), axis=1)
    else:
        df['_pitcher_hand'] = None

    # Fallback: if _pitcher_hand is still missing for any row, look up directly
    # from df['Pitcher'] using _lookup_pitcher_hand (statsapi call, cached).
    # This fires when handedness_map didn't cover this pitcher because they
    # weren't listed as a probable pitcher in the schedule yet.
    missing_hand = df['_pitcher_hand'].isna()
    if missing_hand.any():
        try:
            from mlb_api import _lookup_pitcher_hand as _lph
            unique_pitchers = df.loc[missing_hand, ['Pitcher','_pitcher_full_name']].drop_duplicates()
            hand_cache = {}
            for pitcher in unique_pitchers:
                if pitcher and pitcher not in hand_cache:
                    hand = _lph(pitcher)
                    if hand:
                        hand_cache[pitcher] = hand
            if hand_cache:
                df['_pitcher_hand'] = df.apply(
                    lambda r: (hand_cache.get(r['Pitcher'])
                               if pd.isna(r['_pitcher_hand']) else r['_pitcher_hand']),
                    axis=1
                )
        except Exception:
            pass

    return df


def _fetch_signal_data() -> tuple[dict, dict, dict, dict]:
    """
    Fetch signal dicts independently so one API failure doesn't wipe out all three.
    Returns (order_map, form_map, handedness_map, status_map).
    """
    order_map, form_map, handedness_map = {}, {}, {}
    status_map = {
        'batting_order': 'unavailable',
        'recent_form': 'unavailable',
        'pitcher_handedness': 'unavailable',
    }
    try:
        from mlb_api import get_batting_order_map
        order_map = get_batting_order_map() or {}
        status_map['batting_order'] = 'loaded' if order_map else 'empty'
    except Exception as exc:
        LOGGER.warning('batting_order signal unavailable: %s', exc)

    try:
        from mlb_api import get_recent_batting_form
        form_map = get_recent_batting_form(days=7) or {}
        status_map['recent_form'] = 'loaded' if form_map else 'empty'
    except Exception as exc:
        LOGGER.warning('recent_form signal unavailable: %s', exc)

    try:
        from mlb_api import get_pitcher_handedness_map
        handedness_map = get_pitcher_handedness_map() or {}
        status_map['pitcher_handedness'] = 'loaded' if handedness_map else 'empty'
    except Exception as exc:
        LOGGER.warning('pitcher_handedness signal unavailable: %s', exc)

    return order_map, form_map, handedness_map, status_map


def _build_source_status(raw_df, pitcher_df, game_cond, qs_df, signal_status: dict, df: pd.DataFrame | None = None) -> dict:
    status = {
        'matchups_csv': 'loaded' if raw_df is not None and not raw_df.empty else 'missing',
        'pitcher_context': 'loaded' if pitcher_df is not None and not pitcher_df.empty else 'missing',
        'game_conditions': 'loaded' if game_cond is not None and not game_cond.empty else 'missing',
        'quality_starts': 'loaded' if qs_df is not None and not qs_df.empty else 'missing',
    }
    status.update(signal_status or {})
    if df is not None:
        status['statcast'] = 'loaded' if any(c in df.columns and df[c].notna().any() for c in ['Barrel%', 'HH%', 'xBA']) else 'empty'
        status['bvp_splits'] = 'loaded' if any(c in df.columns and df[c].notna().any() for c in ['bvp_ab', 'split_avg', 'pitcher_split_avg']) else 'empty'
        status['prop_odds'] = 'loaded' if any(c in df.columns and df[c].notna().any() for c in ['prop_tb_under_pct', 'prop_hr_pct']) else 'empty'
    return status


# ─────────────────────────────────────────────────────────────────────────────
# PREDICTOR PAGE
# ─────────────────────────────────────────────────────────────────────────────

def main_page():
    render_header()

    # ── Staleness warning ─────────────────────────────────────────────────────
    render_staleness_warning()

    with st.spinner("⚾ Loading today's matchups…"):
        raw_df     = load_matchups()
        pitcher_df = load_pitcher_data()
        game_cond  = load_game_conditions()
        qs_df      = load_pitcher_qs()

        if raw_df is None:
            st.error("❌ Could not load Matchups data.")
            return

        filters = build_filters(raw_df)

        # Fetch signal data (batting order, form, handedness)
        order_map, form_map, handedness_map, signal_status = _fetch_signal_data()

        df = _build_scored_df(
            raw_df, pitcher_df, game_cond, qs_df,
            use_park=filters['use_park'],
            use_gc=filters.get('use_gc', True),
            order_map=order_map,
            form_map=form_map,
            handedness_map=handedness_map,
        )

        player_id_map = _get_player_id_map(df)
        df = _enrich_with_ids(df, player_id_map)
        df = _merge_signal_metadata(df, order_map, form_map, handedness_map)
        df = _enrich_with_tank_stats(df, player_id_map)   # BvP + splits
        df = _enrich_with_prop_odds(df, player_id_map)    # Tank01 odds join
        st.session_state['source_status'] = _build_source_status(raw_df, pitcher_df, game_cond, qs_df, signal_status, df)

    # ── Apply confirmed lineup filter if toggled ──────────────────────────────
    # Uses get_confirmed_game_abbrs() which derives confirmation from
    # get_lineup_status_map() — the same function that powers the ✅ sidebar.
    # Matches on (away_abbr, home_abbr) game pairs instead of player names,
    # so it works regardless of name format differences between BallPark Pal
    # and the MLB Stats API.
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
                    away_nick = parts[0].strip()
                    home_nick = parts[1].strip()
                    away_abbr = NICK_TO_ABBR.get(away_nick)
                    home_abbr = NICK_TO_ABBR.get(home_nick)
                    return bool(away_abbr and home_abbr and
                                (away_abbr, home_abbr) in confirmed_abbrs)
                pre_count = len(df)
                df = df[df['Game'].apply(_game_confirmed)]
                hidden = pre_count - len(df)
                confirmed_game_count = len(confirmed_abbrs)
                st.info(
                    f"📋 {confirmed_game_count} games with confirmed lineups · "
                    f"showing {len(df)} batters ({hidden} from unconfirmed games hidden)"
                )
            else:
                st.warning("⏳ No lineups confirmed yet — filter has no effect yet")
        except Exception as e:
            st.warning(f"Confirmed filter unavailable: {e}")

    if filters.get('use_gc', False):
        gc_col = filters['score_col'] + '_gc'
        if gc_col in df.columns:
            filters['score_col'] = gc_col
        if filters.get('sort_col') == filters.get('score_col_base'):
            filters['sort_col'] = gc_col

    slate_df    = get_slate_df(df, filters)
    filtered_df = apply_filters(df, filters)

    render_stat_bar(df)
    from renders import render_source_status_panel
    render_source_status_panel(st.session_state.get("source_status", {}))
    render_pitcher_landscape(pitcher_df, df)
    render_park_notice(slate_df, filters)
    render_game_conditions_panel(slate_df, filters, game_cond, qs_df)
    render_score_summary_cards(slate_df, filters)

    target_labels = {
        'Hit_Score':'🎯 Any Base Hit','Single_Score':'1️⃣ Single',
        'XB_Score':'🔥 Extra Base Hit','HR_Score':'💣 Home Run',
        'Hit_Score_gc':'🎯 Any Base Hit ⛅','Single_Score_gc':'1️⃣ Single ⛅',
        'XB_Score_gc':'🔥 Extra Base Hit ⛅','HR_Score_gc':'💣 Home Run ⛅',
    }
    display_sc = filters['score_col_base']
    st.markdown(f"""
    <div class="result-head">
      <span class="rh-label">
        {target_labels.get(filters['score_col'], target_labels.get(display_sc,'Hit'))} Candidates
      </span>
      <span class="rh-count">{len(filtered_df)} results</span>
    </div>""", unsafe_allow_html=True)

    render_results_table(filtered_df, filters)
    render_best_per_target(slate_df, filters)

    if not filtered_df.empty:
        render_player_deep_dive(filtered_df, player_id_map)
        render_visualizations(df, filtered_df, filters['score_col_base'])

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()
    with c2:
        if not filtered_df.empty:
            from renders import _build_export_xlsx
            try:
                xlsx_bytes = _build_export_xlsx(filtered_df, filters)
                st.download_button(
                    "📊 Export Excel",
                    xlsx_bytes,
                    f"a1picks_mlb_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    help="Color-coded Excel spreadsheet with score tiers, BvP highlights, and auto-filter",
                )
            except Exception:
                from renders import _build_export_df
                export_df = _build_export_df(filtered_df, filters)
                st.download_button(
                    "💾 Export CSV",
                    export_df.to_csv(index=False),
                    f"a1picks_mlb_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                )


# ─────────────────────────────────────────────────────────────────────────────
# NAVIGATION
# ─────────────────────────────────────────────────────────────────────────────

def main():
    # Auto-invalidation runs on every page load
    if should_auto_invalidate():
        st.rerun()

    st.sidebar.markdown("---")
    if st.sidebar.checkbox("🎵 Music"):
        audio_url = (
            "https://github.com/a1faded/a1picks-hits-bot/raw/refs/heads/main/"
            "Take%20Me%20Out%20to%20the%20Ballgame%20-%20Nancy%20Bea%20-%20Dodger%20Stadium%20Organ.mp3"
        )
        components.html(
            f'<audio controls autoplay loop style="width:100%;">'
            f'<source src="{audio_url}" type="audio/mpeg"></audio>',
            height=55,
        )

    page = st.sidebar.radio(
        "Navigate",
        ["⚾ Predictor","👤 Player Profile","🔻 Under Targets","⚡ Parlay Builder","📚 Reference Manual"],
        index=0,
    )

    raw_df     = load_matchups()
    pitcher_df = load_pitcher_data()
    game_cond  = load_game_conditions()
    qs_df      = load_pitcher_qs()

    if page == "⚾ Predictor":
        main_page()

    elif page == "👤 Player Profile":
        render_staleness_warning()
        if raw_df is None:
            st.error("❌ Could not load Matchups data.")
        else:
            with st.spinner("Loading slate data…"):
                order_map, form_map, handedness_map, signal_status = _fetch_signal_data()
                df = _build_scored_df(raw_df, pitcher_df, game_cond, qs_df,
                                      use_park=True, use_gc=True,
                                      order_map=order_map, form_map=form_map,
                                      handedness_map=handedness_map)
                player_id_map = _get_player_id_map(df)
                df = _enrich_with_ids(df, player_id_map)
                df = _merge_signal_metadata(df, order_map, form_map, handedness_map)
                df = _enrich_with_tank_stats(df, player_id_map)   # BvP + splits
                df = _enrich_with_prop_odds(df, player_id_map)    # Tank01 odds join
                st.session_state['source_status'] = _build_source_status(raw_df, pitcher_df, game_cond, qs_df, signal_status, df)
            filters = {'use_gc':True,'use_park':True,
                       'score_col':'Hit_Score','score_col_base':'Hit_Score'}
            player_profile_page(df, player_id_map, filters,
                                order_map=order_map,
                                form_map=form_map,
                                handedness_map=handedness_map)

    elif page == "🔻 Under Targets":
        render_staleness_warning()
        if raw_df is None:
            st.error("❌ Could not load Matchups data.")
        else:
            with st.spinner("Loading slate data…"):
                order_map, form_map, handedness_map, signal_status = _fetch_signal_data()
                df = _build_scored_df(raw_df, pitcher_df, game_cond, qs_df,
                                      use_park=True, use_gc=True,
                                      order_map=order_map, form_map=form_map,
                                      handedness_map=handedness_map)
                player_id_map = _get_player_id_map(df)
                df = _enrich_with_ids(df, player_id_map)
                df = _merge_signal_metadata(df, order_map, form_map, handedness_map)
                df = _enrich_with_tank_stats(df, player_id_map)   # BvP + splits
                df = _enrich_with_prop_odds(df, player_id_map)    # Tank01 odds join
                st.session_state['source_status'] = _build_source_status(raw_df, pitcher_df, game_cond, qs_df, signal_status, df)
            under_page(df, filters_base={})

    elif page == "⚡ Parlay Builder":
        if raw_df is None:
            st.error("❌ Could not load data for Parlay Builder.")
        else:
            order_map, form_map, handedness_map, signal_status = _fetch_signal_data()
            df = _build_scored_df(raw_df, pitcher_df, game_cond, qs_df,
                                  use_park=True, use_gc=True,
                                  order_map=order_map, form_map=form_map,
                                  handedness_map=handedness_map)
            st.session_state['source_status'] = _build_source_status(raw_df, pitcher_df, game_cond, qs_df, signal_status, df)
            excl = st.session_state.get('excluded_players', [])
            if excl:
                df = df[~df['Batter'].isin(excl)]
            parlay_page(df)

    else:
        info_page()

    render_lineup_status_sidebar()
    st.sidebar.markdown("---")
    st.sidebar.caption("V7 · BallPark Pal + MLB Stats API + Statcast")


if __name__ == "__main__":
    main()
