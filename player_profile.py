"""
player_profile.py — Player Profile Page V3
============================================
Layout: Header → Score Cards → 3-col (Matchup | Splits & Signals | Statcast + Form)
        → Game Log expander → Game Environment

Fixes V3:
  - xBA Luck: falls back to BallPark Pal AVG column when fg_AVG unavailable
  - Platoon: shows "Unavailable" cleanly instead of "Loading…" when no data
  - Game Log: full game-by-game table added as bottom section
  - Lineup slot: reads from _order_pos column (set in app._merge_signal_metadata)
"""

import streamlit as st
import pandas as pd
import numpy as np
from config import CONFIG

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(val, fmt=".1f", fallback="—"):
    try:
        return format(float(val), fmt) if pd.notna(val) and float(val) != 0 else fallback
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


def _row(label: str, value: str, delta: str = "",
         good: bool | None = None, vcol: str = "") -> str:
    dc = "color:#4ade80" if good is True else "color:#f87171" if good is False else "color:#94a3b8"
    dh = f'<span style="font-size:.72rem;{dc};margin-left:.4rem">{delta}</span>' if delta else ""
    vs = f"color:{vcol}" if vcol else "color:#e2e8f0"
    return (
        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'padding:.35rem 0;border-bottom:1px solid #1e2d3d;">'
        f'<span style="font-size:.8rem;color:#94a3b8">{label}</span>'
        f'<span style="font-size:.85rem;{vs};font-weight:600">{value}{dh}</span>'
        f'</div>'
    )


def _card(title: str, body: str, icon: str = "") -> str:
    return (
        f'<div style="background:#0f1923;border:1px solid #1e2d3d;border-radius:10px;'
        f'padding:.85rem 1rem;margin-bottom:.6rem">'
        f'<div style="font-size:.68rem;font-weight:700;color:#5a7090;text-transform:uppercase;'
        f'letter-spacing:.08em;margin-bottom:.5rem">{icon} {title}</div>'
        f'{body}</div>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def player_profile_page(df: pd.DataFrame, player_id_map: dict, filters: dict,
                         order_map:      dict | None = None,
                         form_map:       dict | None = None,
                         handedness_map: dict | None = None):

    order_map      = order_map      or {}
    form_map       = form_map       or {}
    handedness_map = handedness_map or {}

    st.title("👤 Player Profile")

    if df is None or df.empty:
        st.error("❌ No slate data loaded.")
        return

    all_batters = sorted(df['Batter'].unique().tolist())
    selected    = st.selectbox("Select a player", all_batters, key="profile_player_select")
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
    cfg       = CONFIG

    # ── Batting order slot ────────────────────────────────────────────────────
    # Try _order_pos column first (set in app._merge_signal_metadata),
    # then fall back to direct order_map lookup by last name or full name.
    order_pos = None
    raw_op    = row.get('_order_pos')
    if pd.notna(raw_op):
        order_pos = int(raw_op)
    else:
        order_pos = order_map.get(selected) or order_map.get(selected.split()[-1])
        if order_pos:
            order_pos = int(order_pos)

    # ── Form info ─────────────────────────────────────────────────────────────
    form_info = form_map.get(selected)
    HOT, COLD = cfg['form_hot_threshold'], cfg['form_cold_threshold']

    # ── Header ────────────────────────────────────────────────────────────────
    slot_html = ""
    if order_pos:
        slot_ctx  = {1:"Leadoff",2:"#2 Hitter",3:"#3 Hitter",
                     4:"Cleanup",5:"#5 Hitter"}.get(order_pos, f"#{order_pos} Hitter")
        slot_clr  = "#4ade80" if order_pos in (3,4,5) else \
                    "#60a5fa" if order_pos in (1,2)   else "#94a3b8"
        slot_html = (
            f' &nbsp;·&nbsp; <span style="color:{slot_clr};font-weight:700">'
            f'#{order_pos} — {slot_ctx}</span>'
        )

    form_html = ""
    if form_info and form_info.get('games', 0) >= 3:
        rate = form_info.get('hit_rate', 0)
        if rate >= HOT:
            form_html = (' &nbsp;<span style="background:#052e16;color:#4ade80;padding:2px 8px;'
                         'border-radius:20px;font-size:.72rem;font-weight:700">🔥 HOT</span>')
        elif rate <= COLD:
            form_html = (' &nbsp;<span style="background:#1c0000;color:#f87171;padding:2px 8px;'
                         'border-radius:20px;font-size:.72rem;font-weight:700">❄️ COLD</span>')

    confirmed_badge = (
        ' &nbsp;<span style="background:#052e16;color:#4ade80;padding:1px 7px;'
        'border-radius:20px;font-size:.68rem;font-weight:700">✅ CONFIRMED</span>'
        if order_pos else
        ' &nbsp;<span style="background:#1e2d3d;color:#64748b;padding:1px 7px;'
        'border-radius:20px;font-size:.68rem;font-weight:600">⏳ PENDING</span>'
    )

    st.markdown(f"""
    <div style="background:#0f1923;border:1px solid #1e2d3d;border-radius:10px;
                padding:1.2rem 1.5rem;margin-bottom:1rem;">
      <div style="font-size:1.6rem;font-weight:800;color:#e2e8f0;
                  display:flex;align-items:center;gap:.5rem;flex-wrap:wrap">
        {selected}{confirmed_badge}{form_html}
      </div>
      <div style="font-size:.9rem;color:#64748b;margin-top:.25rem">
        {team} &nbsp;·&nbsp; {game}{slot_html}
      </div>
      <div style="font-size:.85rem;color:#94a3b8;margin-top:.4rem">
        vs <b style="color:#e2e8f0">{pitcher}</b>
        &nbsp;·&nbsp; vs Grade: <b style="color:#e2e8f0">{vs_grade}</b>
        &nbsp;·&nbsp; P.Grade: <b style="color:#e2e8f0">{pitch_grd}</b>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Score Cards ───────────────────────────────────────────────────────────
    st.markdown("#### Today's Scores")
    use_gc = filters.get('use_gc', True)
    score_targets = [
        ('Hit_Score',    '🎯 Hit',    'var(--hit)'),
        ('Single_Score', '1️⃣ Single', 'var(--single)'),
        ('XB_Score',     '🔥 XB',     'var(--xb)'),
        ('HR_Score',     '💣 HR',     'var(--hr)'),
    ]
    sc_cols = st.columns(4)
    for i, (sc, label, color) in enumerate(score_targets):
        gc_sc   = sc + '_gc'
        display = gc_sc if (use_gc and gc_sc in df.columns) else sc
        score   = float(row.get(display, 0) or 0)
        with sc_cols[i]:
            st.markdown(
                f'<div style="background:#0f1923;border:1px solid #1e2d3d;'
                f'border-radius:8px;padding:.8rem .9rem;text-align:center">'
                f'<div style="font-size:.75rem;color:#64748b;margin-bottom:.4rem">{label}</div>'
                f'<div style="font-size:1.6rem;font-weight:800;color:{color}">{score:.1f}</div>'
                f'{_score_bar(score, color)}'
                f'</div>', unsafe_allow_html=True
            )

    st.markdown("---")

    # ── Three-column layout ───────────────────────────────────────────────────
    col_l, col_m, col_r = st.columns([1.05, 1, 1])

    # ── LEFT: Matchup ─────────────────────────────────────────────────────────
    with col_l:
        st.markdown("#### Matchup Breakdown")

        def _s(col, default=0.0):
            try:    return float(row.get(col, default) or default)
            except: return default

        k_lg  = cfg['league_k_avg']  - _s('p_k')
        hr_lg = _s('p_hr') - cfg['league_hr_avg']
        bb_lg = cfg['league_bb_avg'] - _s('p_bb')

        items = [
            ("Hit Prob",   f"{_s('total_hit_prob'):.1f}%", "", None),
            ("1B Prob",    f"{_s('p_1b'):.1f}%",           "", None),
            ("XB Prob",    f"{_s('p_xb'):.1f}%",           "", None),
            ("HR Prob",    f"{_s('p_hr'):.1f}%",  f"vs lg: {hr_lg:+.2f}%", hr_lg >= 0),
            ("K Prob",     f"{_s('p_k'):.1f}%",   f"vs lg: {k_lg:+.1f}%",  k_lg  >= 0),
            ("BB Prob",    f"{_s('p_bb'):.1f}%",  f"vs lg: {bb_lg:+.1f}%", bb_lg >= 0),
            ("vs Grade",   str(vs_grade), "", None),
            ("P. Grade",   str(pitch_grd), "", None),
            ("Hit8 (SP)",  f"{_s('hit8_prob'):.1f}%",  "", None),
            ("HR2 (SP)",   f"{_s('hr2_prob'):.1f}%",   "", None),
            ("Walk3 (SP)", f"{_s('walk3_prob'):.1f}%", "", None),
        ]

        html = '<div style="background:#0f1923;border:1px solid #1e2d3d;border-radius:8px;padding:.8rem 1rem">'
        for args in items:
            html += _row(*args)
        html += "</div>"
        st.markdown(html, unsafe_allow_html=True)

        pa = _s('PA'); h_val = _s('H'); avg = _s('AVG')
        if pa >= 1:
            st.markdown("**History vs pitcher type**")
            st.markdown(
                '<div style="background:#0f1923;border:1px solid #1e2d3d;'
                'border-radius:8px;padding:.8rem 1rem">'
                + _row("PA",  str(int(pa)))
                + _row("H",   str(int(h_val)))
                + _row("AVG", f"{avg:.3f}", good=(avg >= cfg['league_avg']))
                + '</div>', unsafe_allow_html=True
            )

    # ── MIDDLE: Splits & Signals ──────────────────────────────────────────────
    with col_m:
        st.markdown("#### Splits & Signals")

        # 1. Lineup Position
        if order_pos:
            slot_ctx  = {1:"Leadoff — most PAs, OBP focus",
                         2:"#2 — Table setter, high contact",
                         3:"#3 — Best hitter, premium spot",
                         4:"Cleanup — max RBI opportunity",
                         5:"#5 — Secondary power slot"}.get(
                         order_pos, f"#{order_pos} — Mid/lower order")
            scoring_note = (
                f"+{cfg['order_cleanup_bonus']:.1f} pts on HR/XB" if order_pos in (3,4,5)
                else f"+{cfg['order_leadoff_bonus']:.1f} pts on Hit/Single" if order_pos in (1,2)
                else "Neutral — no adjustment"
            )
            slot_clr   = "#4ade80" if order_pos in (3,4,5) else \
                         "#60a5fa" if order_pos in (1,2)   else "#94a3b8"
            pos_body   = (
                _row("Slot",           f"#{order_pos}", "", None, vcol=slot_clr)
                + _row("Context",      slot_ctx, "", None)
                + _row("Score Impact", scoring_note, "", order_pos in (1,2,3,4,5))
            )
        else:
            pos_body = _row("Lineup Slot", "⏳ Not confirmed yet", "", None)
        st.markdown(_card("Lineup Position", pos_body, "📋"), unsafe_allow_html=True)

        # 2. Platoon Analysis
        p_hand = (
            handedness_map.get(row.get('_pitcher_full_name')) if row.get('_pitcher_full_name') else None
        ) or handedness_map.get(row.get('_pitcher_key')) or (row.get('_pitcher_hand') or None)

        if p_hand:
            hand_label = "Left-handed (LHP)" if p_hand == "L" else "Right-handed (RHP)"
            hand_note  = (
                "LHP — RHB have natural platoon advantage" if p_hand == "L"
                else "RHP — LHB have natural platoon advantage"
            )
            plat_body = (
                _row("Pitcher Throws", hand_label, "", None, vcol="#60a5fa")
                + _row("Platoon Note", hand_note, "", None)
                + _row("Switch Hitters", "Always have advantage vs any hand", "", True)
            )
            note = '<div style="font-size:.68rem;color:#64748b;margin-top:.3rem">Batter hand data wires automatically when MLB roster lookup activates.</div>'
        else:
            plat_body = (
                _row("Pitcher Handedness", "Unavailable", "", None)
                + _row("Reason", "MLB API lookup in progress or pitcher not confirmed", "", None)
            )
            note = ""
        st.markdown(_card("Platoon Analysis", plat_body + note, "🤜"), unsafe_allow_html=True)

        # 3. Pitcher Rest & Workload
        rest_info = None
        if pitcher and pitcher != '—':
            try:
                from mlb_api import get_pitcher_rest_map as _grm
                _rm = _grm()
                rest_info = _rm.get(row.get('_pitcher_full_name')) or _rm.get(row.get('_pitcher_key')) or _rm.get(pitcher)
            except Exception:
                pass

        if rest_info:
            days  = rest_info.get('days_rest', 0)
            lip   = rest_info.get('last_ip',   0.0)
            rsig  = rest_info.get('rest_signal', 0.0)
            ldate = rest_info.get('last_date', '—')

            if days >= 5:
                rest_lbl, rest_col = "Well rested ✅", "#4ade80"
            elif days == 4:
                rest_lbl, rest_col = "Normal rest ✅", "#94a3b8"
            elif days == 3:
                rest_lbl, rest_col = "Short rest ⚠️", "#fbbf24"
            else:
                rest_lbl, rest_col = "Very short rest ❌", "#f87171"

            workload_note = (
                "Deep outing — arm well-conditioned" if lip >= 7.0 else
                "Short outing — arm state uncertain" if 0 < lip <= 3.0 else
                "Standard workload"
            )
            rest_body = (
                _row("Days Rest",      str(days),       rest_lbl, days >= 4, vcol=rest_col)
              + _row("Last Start",     ldate,            "",   None)
              + _row("Last Start IP",  f"{lip:.1f}",    workload_note, lip >= 5.0)
              + _row("Under Adj",      f"{rsig:+.1f} pts",
                     "added to all under scores", rsig >= 0)
            )
        else:
            rest_body = (
                _row("Rest Data", "Unavailable", "", None)
              + _row("Reason",    "Pitcher not confirmed or API unavailable", "", None)
            )
        st.markdown(_card("Pitcher Rest & Workload", rest_body, "💤"),
                    unsafe_allow_html=True)

        # 4. xBA Luck Signal
        xba_val = row.get('xBA')
        # FIX: fall back to BallPark Pal AVG when FanGraphs fg_AVG is missing
        fg_avg  = row.get('fg_AVG')
        avg_src = "fg_AVG"
        if (fg_avg is None or not pd.notna(fg_avg) or float(fg_avg or 0) == 0):
            fg_avg  = row.get('AVG')   # BallPark Pal season history vs pitcher type
            avg_src = "H/PA (vs pitcher)"

        xba_f   = float(xba_val) if pd.notna(xba_val) and float(xba_val or 0) > 0 else None
        avg_f   = float(fg_avg)  if pd.notna(fg_avg)  and float(fg_avg  or 0) > 0 else None

        if xba_f and avg_f:
            gap      = xba_f - avg_f
            luck_pts = max(-cfg['luck_max_adj'],
                           min(cfg['luck_max_adj'], gap * cfg['luck_weight']))
            if gap > 0.015:
                lbl, good, lcol = "Underperforming contact", True,  "#4ade80"
                interp = "Results below expected — regression candidate ↑"
            elif gap < -0.015:
                lbl, good, lcol = "Overperforming contact", False, "#f87171"
                interp = "Results above expected — may come down ↓"
            else:
                lbl, good, lcol = "Performing as expected", None, "#94a3b8"
                interp = "xBA and AVG well-aligned"

            luck_body = (
                _row("xBA",         f"{xba_f:.3f}")
                + _row(avg_src,     f"{avg_f:.3f}")
                + _row("Gap",       f"{gap:+.3f}", "", good, vcol=lcol)
                + _row("Assessment",lbl, "", good)
                + _row("Hit Score", f"{luck_pts:+.1f} pts", "", good)
            )
            luck_body += (
                f'<div style="font-size:.68rem;color:#64748b;padding:.3rem 0">{interp}</div>'
            )
        else:
            luck_body = (
                _row("xBA",     _fmt(xba_f, '.3f') if xba_f else "—")
                + _row("AVG",   _fmt(avg_f, '.3f') if avg_f else "—")
                + _row("Status","Insufficient data for luck calculation", "", None)
            )
        st.markdown(_card("xBA Luck Signal", luck_body, "📈"), unsafe_allow_html=True)

    # ── RIGHT: Statcast + Form ────────────────────────────────────────────────
    with col_r:
        st.markdown("#### Statcast Quality of Contact")

        sc_barrel = row.get('Barrel%')
        sc_hh     = row.get('HH%')
        sc_avgev  = row.get('AvgEV')
        sc_maxev  = row.get('maxEV')
        sc_xba    = row.get('xBA')
        sc_xslg   = row.get('xSLG')
        sc_obp    = row.get('OBP')
        sc_slg    = row.get('SLG')

        has_season = any(pd.notna(v) and float(v or 0) != 0
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
                    has_season = any(pd.notna(v) and float(v or 0) != 0
                                     for v in [sc_barrel, sc_hh, sc_avgev, sc_xba])
            except Exception:
                pass

        if has_season:
            LG_B, LG_HH = 7.5, 38.0
            b_val = float(sc_barrel) if pd.notna(sc_barrel) and sc_barrel else None
            h_val = float(sc_hh)     if pd.notna(sc_hh)     and sc_hh     else None
            season_items = [
                ("Barrel%",  f"{b_val:.1f}%" if b_val else "—",
                 f"lg {LG_B}%",   b_val >= LG_B  if b_val else None),
                ("HardHit%", f"{h_val:.1f}%" if h_val else "—",
                 f"lg {LG_HH}%",  h_val >= LG_HH if h_val else None),
                ("Avg EV",   f"{_fmt(sc_avgev,'.1f')} mph" if pd.notna(sc_avgev) else "—","",None),
                ("Max EV",   f"{_fmt(sc_maxev,'.1f')} mph" if pd.notna(sc_maxev) else "—","",None),
                ("xBA",      _fmt(sc_xba,  '.3f') if pd.notna(sc_xba)  else "—","",None),
                ("xSLG",     _fmt(sc_xslg, '.3f') if pd.notna(sc_xslg) else "—","",None),
                ("OBP",      _fmt(sc_obp,  '.3f') if pd.notna(sc_obp)  else "—","",None),
                ("SLG",      _fmt(sc_slg,  '.3f') if pd.notna(sc_slg)  else "—","",None),
            ]
            st.markdown("**Season (FanGraphs / Savant)**")
            html2 = '<div style="background:#0f1923;border:1px solid #1e2d3d;border-radius:8px;padding:.8rem 1rem">'
            for args in season_items:
                html2 += _row(*args)
            html2 += '</div>'
            st.markdown(html2, unsafe_allow_html=True)
        else:
            if player_id:
                st.info("Season Statcast unavailable — fewer than 5 batted-ball events this season.")
            else:
                st.warning("Player ID not resolved — cannot look up Statcast data.")

        # 7-Day Form
        st.markdown("---")
        st.markdown("**7-Day Rolling Form**")

        if form_info and form_info.get('games', 0) >= 1:
            rate   = form_info.get('hit_rate', 0)
            hits   = form_info.get('hits',  0)
            games  = form_info.get('games', 0)

            if rate >= HOT:
                status, fclr, fbg = "🔥 HOT", "#4ade80", "#052e16"
                fnote = f"+{cfg['form_hot_bonus']:.1f} pts on Hit/Single"
            elif rate <= COLD:
                status, fclr, fbg = "❄️ COLD", "#f87171", "#1c0000"
                fnote = f"{cfg['form_cold_penalty']:.1f} pts on Hit/Single"
            else:
                status, fclr, fbg = "〰️ NEUTRAL", "#94a3b8", "#1e2d3d"
                fnote = "No form adjustment"

            bar_pct = min(100, int(rate / 2.0 * 100))
            st.markdown(f"""
            <div style="background:#0f1923;border:1px solid #1e2d3d;
                        border-radius:10px;padding:.9rem 1rem;margin-bottom:.5rem">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.5rem">
                <span style="font-size:.7rem;color:#64748b;font-weight:700;
                             text-transform:uppercase;letter-spacing:.06em">7-Day Form</span>
                <span style="background:{fbg};color:{fclr};padding:2px 10px;border-radius:20px;
                             font-size:.7rem;font-weight:700;font-family:'JetBrains Mono',monospace">{status}</span>
              </div>
              <div style="display:flex;justify-content:space-between;margin-bottom:.4rem">
                <span style="font-size:.82rem;color:#94a3b8">{hits} H in {games} G</span>
                <span style="font-family:'JetBrains Mono',monospace;font-size:.9rem;
                             color:{fclr};font-weight:700">{rate:.2f} H/G</span>
              </div>
              <div style="background:#1e2d3d;border-radius:4px;height:8px">
                <div style="width:{bar_pct}%;background:{fclr};height:8px;border-radius:4px"></div>
              </div>
              <div style="font-size:.68rem;color:#64748b;margin-top:.4rem">
                Hot ≥{HOT} &nbsp;·&nbsp; Cold ≤{COLD} &nbsp;·&nbsp; Lg avg ~0.90 H/G
              </div>
              <div style="font-size:.72rem;color:{fclr};font-weight:600;margin-top:.2rem">{fnote}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("7-day form data unavailable.")

        # Rolling 30-day Statcast
        st.markdown("**Rolling 30-Day (Statcast)**")
        if player_id:
            days_back = st.slider("Days back", 7, 60, 30, key="profile_days")
            try:
                from savant import get_batter_quality_metrics
                with st.spinner("Fetching pitch data…"):
                    m = get_batter_quality_metrics(int(player_id), days_back=days_back)
                if m:
                    rolling_rows = [
                        ("Sample",    f"{m.get('sample_size','—')} BIP", "var(--muted)"),
                        ("Avg EV",    f"{m.get('avg_ev','—')} mph",
                         "var(--hit)" if m.get('avg_ev',0) >= 90  else "var(--text)"),
                        ("Max EV",    f"{m.get('max_ev','—')} mph",
                         "var(--hit)" if m.get('max_ev',0) >= 105 else "var(--text)"),
                        ("Barrel%",   f"{m.get('barrel_pct','—')}%",
                         "var(--hit)" if m.get('barrel_pct',0) >= 8 else "var(--text)"),
                        ("Hard Hit%", f"{m.get('hard_hit_pct','—')}%",
                         "var(--hit)" if m.get('hard_hit_pct',0) >= 40 else "var(--text)"),
                        ("Avg LA",    f"{m.get('avg_la','—')}°",  "var(--text)"),
                        ("xBA",       f"{m.get('xba','—')}",      "var(--text)"),
                        ("xwOBA",     f"{m.get('xwoba','—')}",    "var(--text)"),
                    ]
                    rows_html = "".join(
                        f'<div style="display:flex;justify-content:space-between;'
                        f'padding:.2rem 0;border-bottom:1px solid #1e2d3d;">'
                        f'<span style="font-size:.69rem;color:#94a3b8">{label}</span>'
                        f'<span style="font-family:\'JetBrains Mono\',monospace;'
                        f'font-size:.72rem;color:{color};font-weight:600">{val}</span>'
                        f'</div>'
                        for label, val, color in rolling_rows
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

    # ─────────────────────────────────────────────────────────────────────────
    # GAME LOG  (full-width below 3-column layout)
    # ─────────────────────────────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("📅 Game Log — This Season", expanded=True):
        if player_id:
            try:
                from mlb_api import get_player_game_log
                with st.spinner(f"Loading game log for {selected}…"):
                    log_df = get_player_game_log(player_id, last_n=15)

                if not log_df.empty:
                    def _hit_style(val):
                        if isinstance(val, (int, float)) and val > 0:
                            return 'color:#10b981;font-weight:700'
                        return ''

                    def _ha_style(val):
                        if val == 'Home': return 'color:#60a5fa;font-weight:600'
                        if val == 'Away': return 'color:#94a3b8'
                        return ''

                    # Mini form summary + home/away splits
                    if 'H' in log_df.columns and 'AB' in log_df.columns:
                        played    = len(log_df[log_df['AB'] > 0])
                        hit_games = len(log_df[log_df['H'] > 0])
                        total_h   = log_df['H'].sum()
                        total_hr  = log_df['HR'].sum()
                        rate      = hit_games / played if played else 0
                        rclr      = ("#4ade80" if rate >= HOT else
                                     "#f87171" if rate <= COLD else "#94a3b8")
                        form_tag  = ("🔥 HOT" if rate >= HOT else
                                     "❄️ COLD" if rate <= COLD else "")
                        tag_html  = (
                            f' <span style="background:{"#052e16" if "🔥" in form_tag else "#1c0000"};'
                            f'color:{rclr};padding:1px 7px;border-radius:20px;'
                            f'font-size:.7rem;font-weight:700">{form_tag}</span>'
                            if form_tag else ""
                        )
                        st.markdown(
                            f'<div style="font-size:.82rem;color:#94a3b8;margin-bottom:.35rem">'
                            f'Last {played} G: '
                            f'<span style="color:{rclr};font-weight:700">'
                            f'{hit_games} with a hit ({rate:.0%})</span>'
                            f' · {int(total_h)} H · {int(total_hr)} HR{tag_html}</div>',
                            unsafe_allow_html=True
                        )

                        # Home / Away split summary when H/A column present
                        if 'H/A' in log_df.columns:
                            home_df = log_df[(log_df['H/A'] == 'Home') & (log_df['AB'] > 0)]
                            away_df = log_df[(log_df['H/A'] == 'Away') & (log_df['AB'] > 0)]

                            def _split_str(sub):
                                if sub.empty: return "—"
                                g  = len(sub)
                                h  = int(sub['H'].sum())
                                hr = int(sub['HR'].sum())
                                hg = len(sub[sub['H'] > 0])
                                return f"{hg}/{g} G w/H · {h} H · {hr} HR"

                            st.markdown(
                                f'<div style="font-size:.76rem;color:#64748b;margin-bottom:.5rem">'
                                f'<span style="color:#60a5fa;font-weight:600">🏠 Home</span> {_split_str(home_df)}'
                                f' &nbsp;·&nbsp; '
                                f'<span style="color:#94a3b8;font-weight:600">✈️ Away</span> {_split_str(away_df)}'
                                f'</div>',
                                unsafe_allow_html=True
                            )

                    styled_log = (
                        log_df.style
                        .map(_hit_style, subset=['H'])
                        .map(_ha_style,  subset=['H/A'] if 'H/A' in log_df.columns else [])
                        .format({'AVG': '{}'})
                    )
                    st.dataframe(styled_log, width='stretch', hide_index=True)
                else:
                    st.info("No game log data available yet for this season.")
            except Exception as e:
                st.warning(f"Could not load game log: {e}")
        else:
            st.info("⏳ MLBAM ID not resolved — game log unavailable.")

    # ── Batter vs Pitcher (BvP) + Season Splits ──────────────────────────────
    st.markdown("---")
    bvp_col1, bvp_col2 = st.columns(2)

    # ── LEFT: BvP — career stats vs today's specific pitcher ─────────────────
    with bvp_col1:
        st.markdown("#### ⚔️ Batter vs Today's Pitcher")
        bvp_ab  = row.get('bvp_ab')
        bvp_avg = row.get('bvp_avg')
        bvp_ops = row.get('bvp_ops')
        bvp_hr  = row.get('bvp_hr')
        bvp_rbi = row.get('bvp_rbi')
        bvp_k   = row.get('bvp_k')
        bvp_bb  = row.get('bvp_bb')
        bvp_obp = row.get('bvp_obp')
        bvp_slg = row.get('bvp_slg')
        bvp_conf= row.get('bvp_conf')

        has_bvp_row = (pd.notna(bvp_ab) and float(bvp_ab or 0) >= 1)
        if has_bvp_row:
            ab   = int(bvp_ab)
            conf = float(bvp_conf or 0)
            # Confidence badge
            conf_color = "#4ade80" if conf >= 0.8 else "#fbbf24" if conf >= 0.4 else "#f87171"
            conf_label = "High" if conf >= 0.8 else "Medium" if conf >= 0.4 else "Low"
            lg_avg = cfg['league_avg']

            bvp_body = (
                f'<div style="font-size:.72rem;color:#64748b;margin-bottom:.4rem">'
                f'Sample: <b style="color:{conf_color}">{ab} AB — {conf_label} confidence</b>'
                f'</div>'
            )
            # AVG with delta vs league
            avg_val = float(bvp_avg or 0)
            avg_delta = avg_val - lg_avg
            avg_good  = avg_delta > 0.015
            bvp_body += _row("Career AVG",
                             f"{avg_val:.3f}",
                             f"{avg_delta:+.3f} vs lg",
                             good=avg_good if abs(avg_delta) > 0.010 else None,
                             vcol="#4ade80" if avg_good else "#f87171")
            bvp_body += _row("Career OPS",
                             f"{float(bvp_ops or 0):.3f}",
                             vcol="#4ade80" if float(bvp_ops or 0) > 0.750 else "#f87171")
            bvp_body += _row("Career OBP", f"{float(bvp_obp or 0):.3f}")
            bvp_body += _row("Career SLG", f"{float(bvp_slg or 0):.3f}")
            bvp_body += _row("Career HR",  str(int(bvp_hr  or 0)))
            bvp_body += _row("Career RBI", str(int(bvp_rbi or 0)))
            bvp_body += _row("Career K",   str(int(bvp_k   or 0)))
            bvp_body += _row("Career BB",  str(int(bvp_bb  or 0)))
            if conf < 1.0:
                bvp_body += _row("Sample Note", sample_note)

            st.markdown(_card("vs Today's Starter", bvp_body, "⚔️"),
                        unsafe_allow_html=True)
        else:
            st.markdown(
                _card("vs Today's Starter",
                      '<div style="color:#64748b;font-size:.8rem;text-align:center;'
                      'padding:.8rem 0">No history vs this pitcher<br>'
                      '<span style="font-size:.72rem">First career matchup or '
                      'insufficient AB (&lt;5)</span></div>', "⚔️"),
                unsafe_allow_html=True
            )

    # ── RIGHT: Season splits (vs L / vs R) ───────────────────────────────────
    with bvp_col2:
        st.markdown("#### 📊 Season Splits")
        split_avg = row.get('split_avg')
        split_ops = row.get('split_ops')
        split_obp = row.get('split_obp')
        split_slg = row.get('split_slg')
        split_ab  = row.get('split_ab')
        split_h   = row.get('split_h')
        split_hr  = row.get('split_hr')
        split_r   = row.get('split_r')
        split_rbi = row.get('split_rbi')
        split_bb_ct = row.get('split_bb')
        split_so_ct = row.get('split_so')
        split_bucket = row.get('split_bucket')
        p_hand    = row.get('_pitcher_hand')
        hand_lbl  = ("vs RHP" if p_hand == 'R' else
                     "vs LHP" if p_hand == 'L' else "vs Pitcher")

        has_splits_row = pd.notna(split_avg)
        if has_splits_row:
            split_avg_val = float(split_avg or 0)
            split_ops_val = float(split_ops or 0)
            lg_avg = cfg['league_avg']

            splits_body = (
                f'<div style="font-size:.72rem;color:#64748b;margin-bottom:.4rem">'
                f'This season · <b style="color:#94a3b8">{hand_lbl}</b></div>'
            )
            avg_delta = split_avg_val - lg_avg
            avg_good  = avg_delta > 0.015
            splits_body += _row(f"{hand_lbl} AVG",
                                f"{split_avg_val:.3f}",
                                f"{avg_delta:+.3f} vs lg",
                                good=avg_good if abs(avg_delta) > 0.010 else None,
                                vcol="#4ade80" if avg_good else "#f87171")
            splits_body += _row(f"{hand_lbl} OPS",
                                f"{split_ops_val:.3f}",
                                vcol="#4ade80" if split_ops_val > 0.750 else "#f87171")
            splits_body += _row(f"{hand_lbl} OBP", f"{float(split_obp or 0):.3f}")
            splits_body += _row(f"{hand_lbl} SLG", f"{float(split_slg or 0):.3f}")
            if pd.notna(split_ab):
                splits_body += _row(f"{hand_lbl} AB", str(int(split_ab or 0)))
                splits_body += _row(f"{hand_lbl} H", str(int(split_h or 0)))
                splits_body += _row(f"{hand_lbl} HR", str(int(split_hr or 0)))
                splits_body += _row(f"{hand_lbl} R", str(int(split_r or 0)))
                splits_body += _row(f"{hand_lbl} RBI", str(int(split_rbi or 0)))
                splits_body += _row(f"{hand_lbl} BB", str(int(split_bb_ct or 0)))
                splits_body += _row(f"{hand_lbl} SO", str(int(split_so_ct or 0)))
            st.markdown(_card(f"Season Splits — {hand_lbl}", splits_body, "📊"),
                        unsafe_allow_html=True)
        else:
            st.markdown(
                _card("Season Splits",
                      f'<div style="color:#64748b;font-size:.8rem;text-align:center;'
                      f'padding:.8rem 0">Splits unavailable'
                      f'{"<br><span style=font-size:.72rem>Pitcher hand not resolved</span>" if not p_hand else ""}'
                      f'</div>', "📊"),
                unsafe_allow_html=True
            )

    # ── Game Environment ──────────────────────────────────────────────────────
    gc_cols = ['gc_hr4','gc_hits20','gc_k20','gc_walks8','gc_runs10','gc_qs']
    if all(c in row.index for c in gc_cols):
        st.markdown("---")
        st.markdown("#### 🌦️ Game Environment")
        gc_c1, gc_c2, gc_c3, gc_c4, gc_c5, gc_c6 = st.columns(6)
        pairs = [
            (gc_c1,"4+ HR %",    float(row['gc_hr4']),    cfg['gc_hr4_anchor'],    True),
            (gc_c2,"20+ Hits %", float(row['gc_hits20']), cfg['gc_hits20_anchor'], True),
            (gc_c3,"10+ Runs %", float(row['gc_runs10']), cfg['gc_runs10_anchor'], True),
            (gc_c4,"20+ Ks %",   float(row['gc_k20']),    cfg['gc_k20_anchor'],    False),
            (gc_c5,"8+ Walks %", float(row['gc_walks8']), cfg['gc_walks8_anchor'], False),
            (gc_c6,"SP QS %",    float(row['gc_qs']),     cfg['gc_qs_anchor'],     False),
        ]
        for col, label, val, anchor, higher_good in pairs:
            good  = val > anchor if higher_good else val < anchor
            icon  = "✅" if good else "⚠️"
            color = "#4ade80" if good else "#f87171"
            with col:
                st.markdown(
                    f'<div style="background:#0f1923;border:1px solid #1e2d3d;'
                    f'border-radius:8px;padding:.6rem;text-align:center">'
                    f'<div style="font-size:.68rem;color:#64748b">{label}</div>'
                    f'<div style="font-size:1.1rem;font-weight:700;color:{color}">'
                    f'{icon} {val:.1f}%</div>'
                    f'<div style="font-size:.64rem;color:#475569">med {anchor:.1f}%</div>'
                    f'</div>', unsafe_allow_html=True
                )
