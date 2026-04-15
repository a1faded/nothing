"""
player_profile.py — Player Profile Page V2
============================================
Added "📊 Splits & Signals" section showing all four new V7 signals:
  1. Lineup Position   — batting order slot with context
  2. Platoon Analysis  — pitcher handedness vs batter, advantage/disadvantage
  3. xBA Luck Signal   — contact quality vs actual results gap
  4. 7-Day Form        — rolling hit rate with hot/cold classification

Season Statcast lookup uses two-tier approach (name join → ID fallback).
Rolling 30-day Statcast via pybaseball statcast_batter().
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
        return format(float(val), fmt) if pd.notna(val) and val != 0 else fallback
    except Exception:
        return fallback


def _score_bar(score: float, color: str) -> str:
    pct = max(0.0, min(100.0, float(score)))
    return (
        f'<div style="display:flex;align-items:center;gap:.5rem;margin:.2rem 0">'
        f'  <div style="flex:1;background:#1e2d3d;border-radius:4px;height:10px;">'
        f'    <div style="width:{pct}%;background:{color};height:10px;'
        f'         border-radius:4px;transition:width .3s"></div>'
        f'  </div>'
        f'  <span style="font-size:.8rem;font-family:monospace;color:#e2e8f0;'
        f'    min-width:2.5rem">{pct:.1f}</span>'
        f'</div>'
    )


def _metric_row(label: str, value: str, delta: str = "",
                good: bool | None = None, value_color: str = "") -> str:
    delta_color = (
        "color:#4ade80" if good is True  else
        "color:#f87171" if good is False else
        "color:#94a3b8"
    )
    delta_html = (
        f'<span style="font-size:.72rem;{delta_color};margin-left:.4rem">{delta}</span>'
        if delta else ""
    )
    val_style = f"color:{value_color}" if value_color else "color:#e2e8f0"
    return (
        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'padding:.35rem 0;border-bottom:1px solid #1e2d3d;">'
        f'  <span style="font-size:.8rem;color:#94a3b8">{label}</span>'
        f'  <span style="font-size:.85rem;{val_style};font-weight:600">{value}{delta_html}</span>'
        f'</div>'
    )


def _card(title: str, rows_html: str, icon: str = "") -> str:
    return (
        f'<div style="background:#0f1923;border:1px solid #1e2d3d;'
        f'border-radius:10px;padding:.85rem 1rem;margin-bottom:.6rem">'
        f'<div style="font-size:.72rem;font-weight:700;color:#64748b;'
        f'text-transform:uppercase;letter-spacing:.08em;margin-bottom:.5rem">'
        f'{icon} {title}</div>'
        f'{rows_html}</div>'
    )


def _signal_badge(label: str, color: str, bg: str) -> str:
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:20px;'
        f'background:{bg};color:{color};font-size:.72rem;font-weight:700;'
        f'font-family:\'JetBrains Mono\',monospace;margin:.15rem .1rem">{label}</span>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PAGE
# ─────────────────────────────────────────────────────────────────────────────

def player_profile_page(df: pd.DataFrame, player_id_map: dict, filters: dict,
                         order_map:      dict | None = None,
                         form_map:       dict | None = None,
                         handedness_map: dict | None = None):
    """
    order_map, form_map, handedness_map — passed from app.py.
    All default to {} so page works even when API data is unavailable.
    """
    order_map      = order_map      or {}
    form_map       = form_map       or {}
    handedness_map = handedness_map or {}

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
    team      = row.get('Team',        '—')
    pitcher   = row.get('Pitcher',     '—')
    game      = row.get('Game',        '—')
    vs_grade  = row.get('vs Grade',    '—')
    pitch_grd = row.get('pitch_grade', 'B')
    player_id = player_id_map.get(selected)

    # ── Header ────────────────────────────────────────────────────────────────
    # Batting order slot in header if confirmed
    slot_html = ""
    order_pos = order_map.get(selected) or (
        int(row['_order_pos']) if '_order_pos' in row.index and pd.notna(row.get('_order_pos')) else None
    )
    if order_pos:
        slot_ctx  = {1:"Leadoff",2:"#2 Hitter",3:"#3 Hitter",
                     4:"Cleanup",5:"#5 Hitter"}.get(order_pos, f"#{order_pos} Hitter")
        slot_clr  = "#4ade80" if order_pos in (3,4,5) else \
                    "#60a5fa" if order_pos in (1,2)   else "#94a3b8"
        slot_html = (
            f' &nbsp;·&nbsp; <span style="color:{slot_clr};font-weight:700">'
            f'#{order_pos} — {slot_ctx}</span>'
        )

    # Form badge in header
    form_info  = form_map.get(selected)
    form_html  = ""
    if form_info and form_info.get('games', 0) >= 3:
        rate   = form_info.get('hit_rate', 0)
        cfg    = CONFIG
        if rate >= cfg['form_hot_threshold']:
            form_html = ' &nbsp;<span style="background:#052e16;color:#4ade80;padding:2px 8px;border-radius:20px;font-size:.72rem;font-weight:700">🔥 HOT STREAK</span>'
        elif rate <= cfg['form_cold_threshold']:
            form_html = ' &nbsp;<span style="background:#1c0000;color:#f87171;padding:2px 8px;border-radius:20px;font-size:.72rem;font-weight:700">❄️ COLD STREAK</span>'

    st.markdown(f"""
    <div style="background:#0f1923;border:1px solid #1e2d3d;border-radius:10px;
                padding:1.2rem 1.5rem;margin-bottom:1rem;">
      <div style="font-size:1.6rem;font-weight:800;color:#e2e8f0;
                  display:flex;align-items:center;gap:.6rem">
        {selected}{form_html}
      </div>
      <div style="font-size:.9rem;color:#64748b;margin-top:.25rem">
        {team} &nbsp;·&nbsp; {game}{slot_html}
      </div>
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

    # ── Three-column layout ───────────────────────────────────────────────────
    col_left, col_mid, col_right = st.columns([1.1, 1, 1])

    # ── LEFT: Matchup Breakdown ───────────────────────────────────────────────
    with col_left:
        st.markdown("#### Matchup Breakdown")

        def _s(col, default=0.0):
            try:    return float(row.get(col, default) or default)
            except: return default

        LG    = CONFIG
        k_lg  = LG['league_k_avg']  - _s('p_k')
        hr_lg = _s('p_hr')          - LG['league_hr_avg']
        bb_lg = LG['league_bb_avg'] - _s('p_bb')

        matchup_items = [
            ("Hit Prob",   f"{_s('total_hit_prob'):.1f}%", "", None),
            ("1B Prob",    f"{_s('p_1b'):.1f}%",           "", None),
            ("XB Prob",    f"{_s('p_xb'):.1f}%",           "", None),
            ("HR Prob",    f"{_s('p_hr'):.1f}%",           f"vs lg: {hr_lg:+.2f}%", hr_lg >= 0),
            ("K Prob",     f"{_s('p_k'):.1f}%",            f"vs lg: {k_lg:+.1f}%",  k_lg  >= 0),
            ("BB Prob",    f"{_s('p_bb'):.1f}%",           f"vs lg: {bb_lg:+.1f}%", bb_lg >= 0),
            ("vs Grade",   str(vs_grade), "", None),
            ("P. Grade",   str(pitch_grd),"", None),
            ("Hit8 (SP)",  f"{_s('hit8_prob'):.1f}%",  "", None),
            ("HR2 (SP)",   f"{_s('hr2_prob'):.1f}%",   "", None),
            ("Walk3 (SP)", f"{_s('walk3_prob'):.1f}%", "", None),
        ]

        html = '<div style="background:#0f1923;border:1px solid #1e2d3d;border-radius:8px;padding:.8rem 1rem;">'
        for label, value, delta, good in matchup_items:
            html += _metric_row(label, value, delta, good)
        html += "</div>"
        st.markdown(html, unsafe_allow_html=True)

        # Historical vs this pitcher
        pa = _s('PA'); h = _s('H'); avg = _s('AVG')
        if pa >= 1:
            st.markdown("**History vs this pitcher type**")
            st.markdown(
                '<div style="background:#0f1923;border:1px solid #1e2d3d;'
                'border-radius:8px;padding:.8rem 1rem;">'
                + _metric_row("PA",  str(int(pa)))
                + _metric_row("H",   str(int(h)))
                + _metric_row("AVG", f"{avg:.3f}", good=(avg >= LG['league_avg']))
                + '</div>',
                unsafe_allow_html=True
            )

    # ── MIDDLE: Splits & Signals ──────────────────────────────────────────────
    with col_mid:
        st.markdown("#### Splits & Signals")

        # ── 1. Lineup Position ─────────────────────────────────────────────────
        pos_html = ""
        if order_pos:
            slot_ctx   = {1:"Leadoff — OBP profile, max PAs",
                          2:"#2 — Table setter, high contact",
                          3:"#3 — Best hitter, premium spot",
                          4:"Cleanup — Maximum RBI opportunity",
                          5:"#5 — Secondary power slot"}.get(
                          order_pos, f"#{order_pos} — Mid/lower order")
            slot_bonus = "Positive signal for HR/XB" if order_pos in (3,4,5) else \
                         "Positive signal for Hit/Single" if order_pos in (1,2) else \
                         "Neutral for scoring"
            pos_color  = "#4ade80" if order_pos in (3,4,5) else \
                         "#60a5fa" if order_pos in (1,2)   else "#94a3b8"
            pos_html   = (
                _metric_row("Lineup Slot",   f"#{order_pos}", "", None, value_color=pos_color)
                + _metric_row("Slot Context", slot_ctx, "", None)
                + _metric_row("Scoring Impact", slot_bonus, "", None)
            )
        else:
            pos_html = _metric_row("Lineup Slot", "⏳ Not confirmed yet", "", None)

        st.markdown(_card("Lineup Position", pos_html, "📋"), unsafe_allow_html=True)

        # ── 2. Platoon Analysis ────────────────────────────────────────────────
        p_hand = (
            handedness_map.get(pitcher.split()[-1]) if pitcher else None
        ) or row.get('_pitcher_hand')

        platoon_html = ""
        if p_hand:
            # We don't yet have batter hand in slate data — show pitcher hand
            # and explain what to look for
            hand_label = "Left-handed" if p_hand == "L" else "Right-handed"
            hand_note  = (
                "LHP → typically harder for RHBs, easier for LHBs" if p_hand == "L"
                else "RHP → typically harder for LHBs, easier for RHBs"
            )
            platoon_html = (
                _metric_row("Pitcher Throws", hand_label,
                            "", None, value_color="#60a5fa")
                + _metric_row("Platoon Note", hand_note, "", None)
            )
            # Switch hitter note
            platoon_html += _metric_row(
                "Switch Hitters", "Always have advantage vs any hand", "", True
            )
        else:
            platoon_html = _metric_row("Pitcher Handedness", "⏳ Loading…", "", None)

        st.markdown(_card("Platoon Analysis", platoon_html, "🤜"), unsafe_allow_html=True)

        # ── 3. xBA Luck Signal ────────────────────────────────────────────────
        xba_val = row.get('xBA')
        fg_avg  = row.get('fg_AVG')
        luck_html = ""

        if pd.notna(xba_val) and pd.notna(fg_avg) and float(fg_avg or 0) > 0:
            xba_f  = float(xba_val)
            avg_f  = float(fg_avg)
            gap    = xba_f - avg_f
            cfg    = CONFIG
            luck_pts = gap * cfg['luck_weight']
            luck_pts = max(-cfg['luck_max_adj'], min(cfg['luck_max_adj'], luck_pts))

            if gap > 0.015:
                luck_label  = "Underperforming contact"
                luck_interp = "Results below expected — regression candidate upward"
                luck_good   = True
                luck_color  = "#4ade80"
            elif gap < -0.015:
                luck_label  = "Overperforming contact"
                luck_interp = "Results above expected — may come down"
                luck_good   = False
                luck_color  = "#f87171"
            else:
                luck_label  = "Performing as expected"
                luck_interp = "xBA and AVG well-aligned"
                luck_good   = None
                luck_color  = "#94a3b8"

            luck_html = (
                _metric_row("xBA",         f"{xba_f:.3f}",   "", None)
                + _metric_row("Season AVG", f"{avg_f:.3f}",   "", None)
                + _metric_row("Gap (xBA−AVG)", f"{gap:+.3f}",
                              "", luck_good, value_color=luck_color)
                + _metric_row("Assessment", luck_label, "", luck_good)
                + _metric_row("Hit Score Adj",
                              f"{luck_pts:+.1f} pts", "", luck_good)
            )
            luck_html += (
                f'<div style="font-size:.7rem;color:#64748b;padding:.3rem 0">'
                f'{luck_interp}</div>'
            )
        else:
            luck_html = _metric_row("xBA Luck", "xBA or fg_AVG unavailable", "", None)

        st.markdown(_card("xBA Luck Signal", luck_html, "📈"), unsafe_allow_html=True)

    # ── RIGHT: Statcast + Form ────────────────────────────────────────────────
    with col_right:
        st.markdown("#### Statcast Quality of Contact")

        # Season Statcast — Step 1: from slate df, Step 2: ID-based fallback
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

        if not has_season and player_id:
            try:
                from savant import get_player_season_statcast
                sd = get_player_season_statcast(int(player_id))
                if sd:
                    sc_barrel = sd.get('Barrel%', sc_barrel)
                    sc_hh     = sd.get('HH%',     sc_hh)
                    sc_avgev  = sd.get('AvgEV',   sc_avgev)
                    sc_maxev  = sd.get('maxEV',   sc_maxev)
                    sc_xba    = sd.get('xBA',     sc_xba)
                    sc_xslg   = sd.get('xSLG',    sc_xslg)
                    has_season = any(pd.notna(v) and v != 0
                                     for v in [sc_barrel, sc_hh, sc_avgev, sc_xba])
            except Exception:
                pass

        if has_season:
            LG_B, LG_HH = 7.5, 38.0
            b_val = float(sc_barrel) if pd.notna(sc_barrel) else None
            h_val = float(sc_hh)     if pd.notna(sc_hh)     else None

            season_items = [
                ("Barrel%",  f"{b_val:.1f}%"  if b_val else "—",
                 f"lg {LG_B}%",  b_val >= LG_B  if b_val else None),
                ("HardHit%", f"{h_val:.1f}%"  if h_val else "—",
                 f"lg {LG_HH}%", h_val >= LG_HH if h_val else None),
                ("Avg EV",   f"{_fmt(sc_avgev,'.1f')} mph" if pd.notna(sc_avgev) else "—", "", None),
                ("Max EV",   f"{_fmt(sc_maxev,'.1f')} mph" if pd.notna(sc_maxev) else "—", "", None),
                ("xBA",      _fmt(sc_xba,  '.3f') if pd.notna(sc_xba)  else "—", "", None),
                ("xSLG",     _fmt(sc_xslg, '.3f') if pd.notna(sc_xslg) else "—", "", None),
                ("OBP",      _fmt(sc_obp,  '.3f') if pd.notna(sc_obp)  else "—", "", None),
                ("SLG",      _fmt(sc_slg,  '.3f') if pd.notna(sc_slg)  else "—", "", None),
            ]
            st.markdown("**Season (FanGraphs / Savant)**")
            html2 = '<div style="background:#0f1923;border:1px solid #1e2d3d;border-radius:8px;padding:.8rem 1rem;">'
            for label, value, delta, good in season_items:
                html2 += _metric_row(label, value, delta, good)
            html2 += '</div>'
            st.markdown(html2, unsafe_allow_html=True)
        else:
            if player_id:
                st.info("Season Statcast not yet available — fewer than 5 batted-ball events this season.")
            else:
                st.warning("Player ID not resolved — cannot look up Statcast data.")

        # ── 4. Rolling 7-Day Form ─────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 7-Day Rolling Form")

        if form_info and form_info.get('games', 0) >= 1:
            cfg    = CONFIG
            rate   = form_info.get('hit_rate', 0)
            hits   = form_info.get('hits', 0)
            games  = form_info.get('games', 0)
            HOT, COLD = cfg['form_hot_threshold'], cfg['form_cold_threshold']

            if rate >= HOT:
                form_status = "🔥 HOT STREAK"
                form_color  = "#4ade80"
                form_bg     = "#052e16"
                form_note   = f"+{cfg['form_hot_bonus']:.1f} pts on Hit/Single scores"
            elif rate <= COLD:
                form_status = "❄️ COLD STREAK"
                form_color  = "#f87171"
                form_bg     = "#1c0000"
                form_note   = f"{cfg['form_cold_penalty']:.1f} pts on Hit/Single scores"
            else:
                form_status = "〰️ NEUTRAL"
                form_color  = "#94a3b8"
                form_bg     = "#1e2d3d"
                form_note   = "No form adjustment applied"

            bar_pct = min(100, int(rate / 2.0 * 100))   # visual: 2.0 H/G = 100%

            st.markdown(f"""
            <div style="background:#0f1923;border:1px solid #1e2d3d;
                        border-radius:10px;padding:.9rem 1rem;margin-bottom:.5rem">
              <div style="display:flex;justify-content:space-between;align-items:center;
                          margin-bottom:.5rem">
                <span style="font-size:.72rem;color:#64748b;text-transform:uppercase;
                             letter-spacing:.06em;font-weight:700">7-Day Form</span>
                <span style="background:{form_bg};color:{form_color};padding:2px 10px;
                             border-radius:20px;font-size:.72rem;font-weight:700;
                             font-family:'JetBrains Mono',monospace">{form_status}</span>
              </div>
              <div style="display:flex;justify-content:space-between;margin-bottom:.4rem">
                <span style="font-size:.82rem;color:#94a3b8">{hits} H in {games} G</span>
                <span style="font-family:'JetBrains Mono',monospace;font-size:.9rem;
                             color:{form_color};font-weight:700">{rate:.2f} H/G</span>
              </div>
              <div style="background:#1e2d3d;border-radius:4px;height:8px">
                <div style="width:{bar_pct}%;background:{form_color};height:8px;
                            border-radius:4px"></div>
              </div>
              <div style="font-size:.68rem;color:#64748b;margin-top:.4rem">
                Threshold — Hot: &gt;{HOT} H/G · Cold: &lt;{COLD} H/G · 
                League avg: ~0.90 H/G
              </div>
              <div style="font-size:.72rem;color:{form_color};margin-top:.25rem;
                          font-weight:600">{form_note}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("7-day form data unavailable for this player.")

        # Rolling pitch-level Statcast (30 days)
        st.markdown("**Rolling 30-Day (Statcast)**")
        if player_id:
            days_back = st.slider("Days back", 7, 60, 30, key="profile_days")
            try:
                from savant import get_batter_quality_metrics
                with st.spinner("Fetching pitch data…"):
                    m = get_batter_quality_metrics(int(player_id), days_back=days_back)
                if m:
                    rolling_items = [
                        ("Sample",    f"{m.get('sample_size','—')} BIP",    "var(--muted)"),
                        ("Avg EV",    f"{m.get('avg_ev','—')} mph",
                         "var(--hit)" if m.get('avg_ev',0) >= 90 else "var(--text)"),
                        ("Max EV",    f"{m.get('max_ev','—')} mph",
                         "var(--hit)" if m.get('max_ev',0) >= 105 else "var(--text)"),
                        ("Barrel%",   f"{m.get('barrel_pct','—')}%",
                         "var(--hit)" if m.get('barrel_pct',0) >= 8 else "var(--text)"),
                        ("Hard Hit%", f"{m.get('hard_hit_pct','—')}%",
                         "var(--hit)" if m.get('hard_hit_pct',0) >= 40 else "var(--text)"),
                        ("Avg LA",    f"{m.get('avg_la','—')}°",   "var(--text)"),
                        ("xBA",       f"{m.get('xba','—')}",       "var(--text)"),
                        ("xwOBA",     f"{m.get('xwoba','—')}",     "var(--text)"),
                    ]
                    rows_html = "".join(
                        f'<div style="display:flex;justify-content:space-between;'
                        f'padding:.2rem 0;border-bottom:1px solid #1e2d3d;">'
                        f'<span style="font-size:.69rem;color:#94a3b8">{label}</span>'
                        f'<span style="font-family:\'JetBrains Mono\',monospace;'
                        f'font-size:.72rem;color:{color};font-weight:600">{val}</span>'
                        f'</div>'
                        for label, val, color in rolling_items
                    )
                    st.markdown(
                        f'<div style="background:#0f1923;border:1px solid #1e2d3d;'
                        f'border-radius:8px;padding:.8rem 1rem">{rows_html}</div>',
                        unsafe_allow_html=True
                    )
                else:
                    st.info(f"No pitch-level data in last {days_back} days.")
            except Exception as e:
                st.warning(f"Could not load pitch-level data: {e}")
        else:
            st.info("MLBAM ID not found — rolling data unavailable.")

    # ── Game Environment ──────────────────────────────────────────────────────
    gc_cols = ['gc_hr4','gc_hits20','gc_k20','gc_walks8','gc_runs10','gc_qs']
    if all(c in row.index for c in gc_cols):
        st.markdown("---")
        st.markdown("#### 🌦️ Game Environment")
        gc_c1, gc_c2, gc_c3, gc_c4, gc_c5, gc_c6 = st.columns(6)
        pairs = [
            (gc_c1,"4+ HR %",    float(row['gc_hr4']),    CONFIG['gc_hr4_anchor'],    True),
            (gc_c2,"20+ Hits %", float(row['gc_hits20']), CONFIG['gc_hits20_anchor'], True),
            (gc_c3,"10+ Runs %", float(row['gc_runs10']), CONFIG['gc_runs10_anchor'], True),
            (gc_c4,"20+ Ks %",   float(row['gc_k20']),    CONFIG['gc_k20_anchor'],    False),
            (gc_c5,"8+ Walks %", float(row['gc_walks8']), CONFIG['gc_walks8_anchor'], False),
            (gc_c6,"SP QS %",    float(row['gc_qs']),     CONFIG['gc_qs_anchor'],     False),
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
                    f'<div style="font-size:.65rem;color:#475569">med {anchor:.1f}%</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
