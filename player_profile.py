"""
player_profile.py — Player Profile Page
=========================================
Deep-dive view for a single batter on today's slate.

V3 fix: Season Statcast section now has a two-step lookup:
  Step 1 — read from slate df (already joined by join_statcast_to_slate)
  Step 2 — if still NaN, call get_player_season_statcast(mlbam_id) which
            uses the pre-cached MLBAM ID → stats leaderboard dict.
            This bypasses ALL name-matching and never fails due to
            accent/suffix/hyphen differences.
"""

import streamlit as st
import pandas as pd
import numpy as np
from config import CONFIG, LABEL_MAP, SCORE_CSS

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(val, fmt=".1f", fallback="—"):
    try:
        return format(float(val), fmt) if pd.notna(val) else fallback
    except Exception:
        return fallback


def _score_bar(score: float, color: str) -> str:
    pct = max(0.0, min(100.0, float(score)))
    return (
        f'<div style="display:flex;align-items:center;gap:.5rem;margin:.2rem 0">'
        f'  <div style="flex:1;background:#1e2d3d;border-radius:4px;height:10px;">'
        f'    <div style="width:{pct}%;background:{color};height:10px;border-radius:4px"></div>'
        f'  </div>'
        f'  <span style="font-size:.8rem;font-family:monospace;color:#e2e8f0;min-width:2.5rem">'
        f'    {pct:.1f}</span>'
        f'</div>'
    )


def _metric_row(label: str, value: str, delta: str = "", good: bool | None = None) -> str:
    delta_color = (
        "color:#4ade80" if good is True  else
        "color:#f87171" if good is False else
        "color:#94a3b8"
    )
    delta_html = (
        f'<span style="font-size:.72rem;{delta_color};margin-left:.4rem">{delta}</span>'
        if delta else ""
    )
    return (
        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'padding:.35rem 0;border-bottom:1px solid #1e2d3d;">'
        f'  <span style="font-size:.8rem;color:#94a3b8">{label}</span>'
        f'  <span style="font-size:.85rem;color:#e2e8f0;font-weight:600">{value}{delta_html}</span>'
        f'</div>'
    )

# ─────────────────────────────────────────────────────────────────────────────
# MAIN PAGE
# ─────────────────────────────────────────────────────────────────────────────

def player_profile_page(df: pd.DataFrame, player_id_map: dict, filters: dict):
    st.title("👤 Player Profile")

    if df is None or df.empty:
        st.error("❌ No slate data loaded.")
        return

    all_batters = sorted(df['Batter'].unique().tolist())
    if not all_batters:
        st.warning("No batters found in today's slate.")
        return

    selected = st.selectbox("Select a player", all_batters, key="profile_player_select")
    if not selected:
        return

    player_rows = df[df['Batter'] == selected]
    if player_rows.empty:
        st.warning(f"No slate data for {selected}.")
        return

    row       = player_rows.iloc[0]
    team      = row.get('Team', '—')
    pitcher   = row.get('Pitcher', '—')
    game      = row.get('Game', '—')
    vs_grade  = row.get('vs Grade', '—')
    pitch_grd = row.get('pitch_grade', 'B')

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div style="background:#0f1923;border:1px solid #1e2d3d;border-radius:10px;
                padding:1.2rem 1.5rem;margin-bottom:1rem;">
      <div style="font-size:1.6rem;font-weight:800;color:#e2e8f0">{selected}</div>
      <div style="font-size:.9rem;color:#64748b;margin-top:.25rem">{team} &nbsp;·&nbsp; {game}</div>
      <div style="font-size:.85rem;color:#94a3b8;margin-top:.4rem">
        vs <b style="color:#e2e8f0">{pitcher}</b>
        &nbsp;·&nbsp; vs Grade: <b style="color:#e2e8f0">{vs_grade}</b>
        &nbsp;·&nbsp; Pitcher Grade: <b style="color:#e2e8f0">{pitch_grd}</b>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Score Cards ───────────────────────────────────────────────────────────
    score_targets = [
        ('Hit_Score',    '🎯 Hit',    'var(--hit)'),
        ('Single_Score', '1️⃣ Single', 'var(--single)'),
        ('XB_Score',     '🔥 XB',     'var(--xb)'),
        ('HR_Score',     '💣 HR',     'var(--hr)'),
    ]
    use_gc = filters.get('use_gc', True)

    st.markdown("#### Today's Scores")
    cols = st.columns(4)
    for i, (sc, label, color) in enumerate(score_targets):
        gc_sc   = sc + '_gc'
        display = gc_sc if (use_gc and gc_sc in df.columns) else sc
        score   = float(row.get(display, 0) or 0)
        with cols[i]:
            st.markdown(
                f'<div style="background:#0f1923;border:1px solid #1e2d3d;'
                f'border-radius:8px;padding:.8rem .9rem;text-align:center">'
                f'<div style="font-size:.75rem;color:#64748b;margin-bottom:.4rem">{label}</div>'
                f'<div style="font-size:1.6rem;font-weight:800;color:{color}">{score:.1f}</div>'
                f'{_score_bar(score, color)}'
                f'</div>',
                unsafe_allow_html=True
            )

    st.markdown("---")
    left, right = st.columns(2)

    # ── Matchup Breakdown ────────────────────────────────────────────────────
    with left:
        st.markdown("#### Matchup Breakdown")

        def _s(col, default=0.0):
            try:    return float(row.get(col, default) or default)
            except: return default

        LG      = CONFIG
        k_lg    = LG['league_k_avg']  - _s('p_k')
        hr_lg   = _s('p_hr')          - LG['league_hr_avg']
        bb_lg   = LG['league_bb_avg'] - _s('p_bb')

        items = [
            ("Hit Prob (1B+XB+HR)", f"{_s('total_hit_prob'):.1f}%",  "", None),
            ("1B Prob",             f"{_s('p_1b'):.1f}%",             "", None),
            ("XB Prob",             f"{_s('p_xb'):.1f}%",             "", None),
            ("HR Prob",             f"{_s('p_hr'):.1f}%",             f"vs lg: {hr_lg:+.2f}%", hr_lg >= 0),
            ("K Prob",              f"{_s('p_k'):.1f}%",              f"vs lg: {k_lg:+.1f}%",  k_lg  >= 0),
            ("BB Prob",             f"{_s('p_bb'):.1f}%",             f"vs lg: {bb_lg:+.1f}%", bb_lg >= 0),
            ("vs Grade",            str(vs_grade),                    "", None),
            ("Pitcher Grade",       str(pitch_grd),                   "", None),
            ("Hit8 Prob (SP)",      f"{_s('hit8_prob'):.1f}%",        "", None),
            ("HR2 Prob (SP)",       f"{_s('hr2_prob'):.1f}%",         "", None),
            ("Walk3 Prob (SP)",     f"{_s('walk3_prob'):.1f}%",       "", None),
        ]

        html = '<div style="background:#0f1923;border:1px solid #1e2d3d;border-radius:8px;padding:.8rem 1rem;">'
        for label, value, delta, good in items:
            html += _metric_row(label, value, delta, good)
        html += "</div>"
        st.markdown(html, unsafe_allow_html=True)

        pa  = _s('PA')
        h   = _s('H')
        avg = _s('AVG')
        if pa >= 1:
            st.markdown("**Batter History (vs this pitcher type)**")
            st.markdown(
                '<div style="background:#0f1923;border:1px solid #1e2d3d;'
                'border-radius:8px;padding:.8rem 1rem;">'
                + _metric_row("PA",  str(int(pa)))
                + _metric_row("H",   str(int(h)))
                + _metric_row("AVG", f"{avg:.3f}", good=(avg >= LG['league_avg']))
                + '</div>',
                unsafe_allow_html=True
            )

    # ── Season Statcast ───────────────────────────────────────────────────────
    with right:
        st.markdown("#### Statcast Quality of Contact")

        player_id = player_id_map.get(selected)

        # Step 1 — read from slate df (populated by join_statcast_to_slate)
        sc_barrel = row.get('Barrel%')
        sc_hh     = row.get('HH%')
        sc_avgev  = row.get('AvgEV')
        sc_maxev  = row.get('maxEV')
        sc_xba    = row.get('xBA')
        sc_xslg   = row.get('xSLG')
        sc_obp    = row.get('OBP')
        sc_slg    = row.get('SLG')

        has_season = any(pd.notna(v) and v != 0
                         for v in [sc_barrel, sc_hh, sc_avgev, sc_xba])

        # Step 2 — ID-based fallback when name join returned NaN
        # This fires for any player where BallPark Pal name ≠ FanGraphs name
        # (accents, Jr./Sr. suffix, hyphens, nicknames, etc.)
        if not has_season and player_id:
            try:
                from savant import get_player_season_statcast
                season_data = get_player_season_statcast(int(player_id))
                if season_data:
                    sc_barrel = season_data.get('Barrel%', sc_barrel)
                    sc_hh     = season_data.get('HH%',     sc_hh)
                    sc_avgev  = season_data.get('AvgEV',   sc_avgev)
                    sc_maxev  = season_data.get('maxEV',   sc_maxev)
                    sc_xba    = season_data.get('xBA',     sc_xba)
                    sc_xslg   = season_data.get('xSLG',    sc_xslg)
                    has_season = any(pd.notna(v) and v != 0
                                     for v in [sc_barrel, sc_hh, sc_avgev, sc_xba])
            except Exception:
                pass

        if has_season:
            LG_BARREL = 7.5
            LG_HH     = 38.0
            b_val = float(sc_barrel) if pd.notna(sc_barrel) else None
            h_val = float(sc_hh)     if pd.notna(sc_hh)     else None

            season_items = [
                ("Barrel%",
                 f"{b_val:.1f}%" if b_val is not None else "—",
                 f"lg avg {LG_BARREL}%",
                 b_val >= LG_BARREL if b_val is not None else None),
                ("HardHit%",
                 f"{h_val:.1f}%" if h_val is not None else "—",
                 f"lg avg {LG_HH}%",
                 h_val >= LG_HH if h_val is not None else None),
                ("Avg EV",
                 f"{_fmt(sc_avgev, '.1f')} mph" if pd.notna(sc_avgev) else "—",
                 "", None),
                ("Max EV",
                 f"{_fmt(sc_maxev, '.1f')} mph" if pd.notna(sc_maxev) else "—",
                 "", None),
                ("xBA",  _fmt(sc_xba,  '.3f') if pd.notna(sc_xba)  else "—", "", None),
                ("xSLG", _fmt(sc_xslg, '.3f') if pd.notna(sc_xslg) else "—", "", None),
                ("OBP",  _fmt(sc_obp,  '.3f') if pd.notna(sc_obp)  else "—", "", None),
                ("SLG",  _fmt(sc_slg,  '.3f') if pd.notna(sc_slg)  else "—", "", None),
            ]

            st.markdown("**Season (Statcast / FanGraphs)**")
            html2 = '<div style="background:#0f1923;border:1px solid #1e2d3d;border-radius:8px;padding:.8rem 1rem;">'
            for label, value, delta, good in season_items:
                html2 += _metric_row(label, value, delta, good)
            html2 += '</div>'
            st.markdown(html2, unsafe_allow_html=True)
        else:
            if player_id:
                st.info(
                    "Season Statcast data not yet available for this player — "
                    "likely fewer than 5 batted-ball events so far this season."
                )
            else:
                st.warning(
                    "Player ID not resolved — cannot look up Statcast data. "
                    "Check that MLB-StatsAPI is installed and the player name matches the MLB roster."
                )

        # Rolling 30-day pitch-level
        st.markdown("**Rolling 30-Day (Statcast)**")
        if player_id:
            days_back = st.slider("Days back", 7, 60, 30, key="profile_days")
            try:
                from savant import get_batter_quality_metrics
                with st.spinner("Fetching pitch data…"):
                    m = get_batter_quality_metrics(int(player_id), days_back=days_back)

                if m:
                    rolling_items = [
                        ("Sample (BIP)",  str(m.get('sample_size', '—')),           "", None),
                        ("Avg EV",        f"{m.get('avg_ev','—')} mph",              "", None),
                        ("Max EV",        f"{m.get('max_ev','—')} mph",              "", None),
                        ("Barrel%",       f"{m.get('barrel_pct','—')}%",             "", None),
                        ("HardHit%",      f"{m.get('hard_hit_pct','—')}%",           "", None),
                        ("Avg LA",        f"{m.get('avg_la','—')}°",                 "", None),
                        ("xBA",           _fmt(m.get('xba'), '.3f'),                 "", None),
                        ("xwOBA",         _fmt(m.get('xwoba'), '.3f'),               "", None),
                    ]
                    html3 = '<div style="background:#0f1923;border:1px solid #1e2d3d;border-radius:8px;padding:.8rem 1rem;">'
                    for label, value, delta, good in rolling_items:
                        html3 += _metric_row(label, value, delta, good)
                    html3 += '</div>'
                    st.markdown(html3, unsafe_allow_html=True)
                else:
                    st.info(f"No pitch-level data in last {days_back} days.")

            except Exception as e:
                st.warning(f"Could not load pitch-level data: {e}")
        else:
            st.info("MLBAM ID not found — rolling data unavailable.")

    # ── Game Environment ──────────────────────────────────────────────────────
    gc_cols = ['gc_hr4', 'gc_hits20', 'gc_k20', 'gc_walks8', 'gc_runs10', 'gc_qs']
    if all(c in row.index for c in gc_cols):
        st.markdown("---")
        st.markdown("#### 🌦️ Game Environment")
        gc_c1, gc_c2, gc_c3, gc_c4, gc_c5, gc_c6 = st.columns(6)
        pairs = [
            (gc_c1, "4+ HR %",    float(row['gc_hr4']),    CONFIG['gc_hr4_anchor'],    True),
            (gc_c2, "20+ Hits %", float(row['gc_hits20']), CONFIG['gc_hits20_anchor'], True),
            (gc_c3, "10+ Runs %", float(row['gc_runs10']), CONFIG['gc_runs10_anchor'], True),
            (gc_c4, "20+ Ks %",   float(row['gc_k20']),    CONFIG['gc_k20_anchor'],    False),
            (gc_c5, "8+ Walks %", float(row['gc_walks8']), CONFIG['gc_walks8_anchor'], False),
            (gc_c6, "SP QS %",    float(row['gc_qs']),     CONFIG['gc_qs_anchor'],     False),
        ]
        for col, label, val, anchor, higher_is_good in pairs:
            good  = val > anchor if higher_is_good else val < anchor
            icon  = "✅" if good else "⚠️"
            color = "#4ade80" if good else "#f87171"
            with col:
                st.markdown(
                    f'<div style="background:#0f1923;border:1px solid #1e2d3d;'
                    f'border-radius:8px;padding:.6rem;text-align:center">'
                    f'<div style="font-size:.7rem;color:#64748b">{label}</div>'
                    f'<div style="font-size:1.1rem;font-weight:700;color:{color}">'
                    f'{icon} {val:.1f}%</div>'
                    f'<div style="font-size:.65rem;color:#475569">median {anchor:.1f}%</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
