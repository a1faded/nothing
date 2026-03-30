"""
player_profile.py — Player Profile Page
=========================================
Dedicated page showing full player intel for any batter on today's slate:
  1. Today's matchup summary (from BallPark Pal slate data)
  2. Season stats (AVG, OBP, SLG, HR, K%, BB%) from MLB Stats API
  3. Statcast quality metrics (EV, Barrel%, HH%, xBA) — last 30 days
  4. Last 10 game log from MLB Stats API
"""

import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from config import CONFIG
from helpers import grade_pill


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _metric_color(val, good_above, warn_above=None):
    """Return CSS color string based on thresholds."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "var(--muted)"
    if val >= good_above:
        return "var(--hit)"
    if warn_above and val >= warn_above:
        return "var(--xb)"
    return "var(--neg)"


def _pcard_row(label, value, color="var(--text)"):
    return (f'<div class="pcard-row">'
            f'<span class="pk">{label}</span>'
            f'<span class="pv" style="color:{color}">{value}</span>'
            f'</div>')


def _safe(val, fmt="{}", fallback="—"):
    try:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return fallback
        return fmt.format(val)
    except Exception:
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — Today's Matchup
# ─────────────────────────────────────────────────────────────────────────────

def _render_matchup_section(row: pd.Series, filters: dict):
    st.markdown("### 🎯 Today's Matchup")
    LG = CONFIG

    use_gc  = filters.get('use_gc', False)
    scores = []
    for sc, label, color in [
        ('Hit_Score',    '🎯 Hit',    'var(--hit)'),
        ('Single_Score', '1️⃣ Single', 'var(--single)'),
        ('XB_Score',     '🔥 XB',     'var(--xb)'),
        ('HR_Score',     '💣 HR',     'var(--hr)'),
    ]:
        gc_sc = sc + '_gc'
        val   = row.get(gc_sc if use_gc and gc_sc in row.index else sc, None)
        scores.append((label, val, color))

    # Score cards row
    score_html = '<div style="display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:.75rem">'
    for label, val, color in scores:
        score_html += f"""
<div style="background:var(--surf);border:1px solid var(--border);border-radius:10px;
  padding:.6rem .9rem;min-width:90px;text-align:center">
  <div style="font-size:.65rem;color:var(--muted);margin-bottom:.2rem">{label}</div>
  <div style="font-family:JetBrains Mono,monospace;font-size:1.3rem;font-weight:700;
    color:{color}">{_safe(val, '{:.1f}')}</div>
</div>"""
    score_html += '</div>'
    st.markdown(score_html, unsafe_allow_html=True)

    # Matchup details
    pitcher   = row.get('Pitcher', '—')
    grade     = grade_pill(str(row.get('pitch_grade', 'B')))
    game      = row.get('Game', '—')
    p_1b      = row.get('p_1b', 0)
    p_xb      = row.get('p_xb', 0)
    p_hr      = row.get('p_hr', 0)
    p_k       = row.get('p_k', 0)
    p_bb      = row.get('p_bb', 0)
    hit_prob  = row.get('total_hit_prob', 0)
    vs_grade  = int(row.get('vs Grade', 0)) if pd.notna(row.get('vs Grade')) else 0
    pa        = int(row.get('PA', 0))
    avg_vs    = row.get('AVG', 0)
    park_d    = row.get('Park Δ', 0)

    k_lg  = LG['league_k_avg']  - p_k
    hr_lg = p_hr - LG['league_hr_avg']

    col1, col2 = st.columns(2)
    with col1:
        rows  = _pcard_row("Game", game)
        rows += _pcard_row("Pitcher", f"{pitcher} {grade}")
        rows += _pcard_row("Hit Prob", f"{hit_prob:.1f}%",
                           _metric_color(hit_prob, 30, 22))
        rows += _pcard_row("1B / XB / HR", f"{p_1b:.1f}% / {p_xb:.1f}% / {p_hr:.1f}%")
        rows += _pcard_row("K%", f"{p_k:.1f}% (K%↓Lg {k_lg:+.1f})",
                           "var(--hit)" if k_lg >= 0 else "var(--neg)")
        rows += _pcard_row("BB%", f"{p_bb:.1f}%")
        st.markdown(f'<div class="pcard">{rows}</div>', unsafe_allow_html=True)

    with col2:
        rows  = _pcard_row("vs Grade", f"{vs_grade:+d}")
        rows += _pcard_row("Park Δ", f"{park_d:+.1f}" if park_d else "—",
                           "var(--pos)" if (park_d or 0) >= 0 else "var(--neg)")
        rows += _pcard_row("HR% vs Lg", f"{hr_lg:+.2f}%",
                           "var(--hit)" if hr_lg >= 0 else "var(--neg)")

        # Historical matchup
        if pa >= 3:
            rows += _pcard_row("Hist vs Pitcher",
                               f"{pa} PA · {avg_vs:.3f} AVG",
                               "var(--hit)" if (avg_vs or 0) > 0.250 else
                               "var(--neg)" if pa >= 3 and (avg_vs or 0) == 0
                               else "var(--text)")
        else:
            rows += _pcard_row("Hist vs Pitcher", "No history")

        # Statcast snapshot from slate join
        for col, label, thresh_good, fmt in [
            ('Barrel%', 'Barrel%',  8.0,  '{:.1f}%'),
            ('HH%',     'HardHit%', 40.0, '{:.1f}%'),
            ('AvgEV',   'Avg EV',   90.0, '{:.1f} mph'),
        ]:
            if col in row.index and pd.notna(row.get(col)):
                val = row[col]
                rows += _pcard_row(label, fmt.format(val),
                                   "var(--hit)" if val >= thresh_good else "var(--text)")
        st.markdown(f'<div class="pcard">{rows}</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — Season Stats
# ─────────────────────────────────────────────────────────────────────────────

def _render_season_stats(player_id: int, player_name: str):
    st.markdown("### 📊 2026 Season Stats")
    if not player_id:
        st.info("⏳ Player ID not resolved — season stats unavailable.")
        return
    try:
        from mlb_api import get_player_game_log
        # We derive season totals from game log since player_stat_data is tricky
        log_df = get_player_game_log(player_id, last_n=200)
        if log_df.empty:
            st.info("No season stats available yet — season may have just started.")
            return

        # Aggregate season totals
        num = log_df[log_df['AB'] > 0]
        if num.empty:
            st.info("No at-bat data yet this season.")
            return

        tot_ab  = int(num['AB'].sum())
        tot_h   = int(num['H'].sum())
        tot_2b  = int(num['2B'].sum())
        tot_hr  = int(num['HR'].sum())
        tot_rbi = int(num['RBI'].sum())
        tot_bb  = int(num['BB'].sum())
        tot_k   = int(num['K'].sum())
        avg     = tot_h / tot_ab if tot_ab else 0
        obp_approx = (tot_h + tot_bb) / (tot_ab + tot_bb) if (tot_ab + tot_bb) else 0
        kpct    = tot_k / (tot_ab + tot_bb) * 100 if (tot_ab + tot_bb) else 0
        bbpct   = tot_bb / (tot_ab + tot_bb) * 100 if (tot_ab + tot_bb) else 0

        cols = st.columns(4)
        cols[0].metric("AVG",  f"{avg:.3f}")
        cols[1].metric("OBP",  f"{obp_approx:.3f}")
        cols[2].metric("HR",   tot_hr)
        cols[3].metric("RBI",  tot_rbi)

        cols2 = st.columns(4)
        cols2[0].metric("K%",   f"{kpct:.1f}%")
        cols2[1].metric("BB%",  f"{bbpct:.1f}%")
        cols2[2].metric("2B",   tot_2b)
        cols2[3].metric("AB",   tot_ab)

        # Also show FanGraphs season stats if available from Statcast join
        # (shown in matchup section above)

    except Exception as e:
        st.info(f"Season stats unavailable: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — Statcast Quality Metrics
# ─────────────────────────────────────────────────────────────────────────────

def _render_statcast_section(player_id: int, player_name: str, slate_row: pd.Series):
    st.markdown("### ⚡ Statcast Quality Metrics")

    col1, col2 = st.columns([1, 2])

    with col1:
        st.markdown("**Last 30 Days (Pitch-level)**")
        if player_id:
            try:
                from savant import get_batter_quality_metrics
                metrics = get_batter_quality_metrics(player_id, days_back=30)
                if metrics:
                    rows  = _pcard_row("Avg EV",
                        f"{metrics.get('avg_ev', '—')} mph",
                        _metric_color(metrics.get('avg_ev'), 92, 88))
                    rows += _pcard_row("Max EV",
                        f"{metrics.get('max_ev', '—')} mph",
                        _metric_color(metrics.get('max_ev'), 108, 100))
                    rows += _pcard_row("Barrel%",
                        f"{metrics.get('barrel_pct', '—')}%",
                        _metric_color(metrics.get('barrel_pct'), 10, 6))
                    rows += _pcard_row("Hard Hit%",
                        f"{metrics.get('hard_hit_pct', '—')}%",
                        _metric_color(metrics.get('hard_hit_pct'), 45, 38))
                    rows += _pcard_row("Avg LA",
                        f"{metrics.get('avg_la', '—')}°")
                    rows += _pcard_row("xBA",
                        _safe(metrics.get('xba'), '{:.3f}'))
                    rows += _pcard_row("xwOBA",
                        _safe(metrics.get('xwoba'), '{:.3f}'))
                    rows += _pcard_row("Sample",
                        f"{metrics.get('sample_size', 0)} balls in play",
                        "var(--muted)")
                    st.markdown(f'<div class="pcard">{rows}</div>', unsafe_allow_html=True)
                else:
                    st.info("No Statcast data in last 30 days.")
            except Exception:
                st.info("Statcast (pybaseball) unavailable.")
        else:
            st.info("⏳ Player ID not resolved.")

    with col2:
        st.markdown("**Season Statcast (FanGraphs)**")
        sc_available = any(
            c in slate_row.index and pd.notna(slate_row.get(c))
            for c in ['Barrel%', 'HH%', 'AvgEV', 'xBA', 'xSLG']
        )
        if sc_available:
            rows = ""
            for col, label, good, warn, fmt in [
                ('Barrel%', 'Barrel%',      8.0,  4.0,  '{:.1f}%'),
                ('HH%',     'Hard Hit%',    42.0, 36.0, '{:.1f}%'),
                ('AvgEV',   'Avg EV',       91.0, 87.0, '{:.1f} mph'),
                ('maxEV',   'Max EV',       108.0,100.0,'{:.1f} mph'),
                ('xBA',     'xBA',          0.270,0.230,'{:.3f}'),
                ('xSLG',    'xSLG',         0.480,0.380,'{:.3f}'),
                ('OBP',     'OBP',          0.350,0.320,'{:.3f}'),
                ('SLG',     'SLG',          0.480,0.400,'{:.3f}'),
            ]:
                if col in slate_row.index and pd.notna(slate_row.get(col)):
                    val = slate_row[col]
                    rows += _pcard_row(label, fmt.format(val),
                                       _metric_color(val, good, warn))
            rows += _pcard_row("Source", "FanGraphs 2025 season", "var(--muted)")
            st.markdown(f'<div class="pcard">{rows}</div>', unsafe_allow_html=True)

            # Contact profile visual — Barrel% vs HH% scatter context
            if 'Barrel%' in slate_row.index and 'HH%' in slate_row.index:
                bpct = slate_row.get('Barrel%')
                hhpct = slate_row.get('HH%')
                if pd.notna(bpct) and pd.notna(hhpct):
                    profile = (
                        "💥 Elite Power Profile"    if bpct >= 12 and hhpct >= 45 else
                        "🔥 Hard Contact Profile"   if bpct >= 7  and hhpct >= 40 else
                        "📐 Line Drive Profile"     if bpct <= 5  and hhpct >= 38 else
                        "⚡ Developing Power"       if bpct >= 7 else
                        "🎯 Contact Profile"
                    )
                    st.markdown(
                        f'<div class="notice notice-info" style="margin-top:.5rem">'
                        f'Contact type: <b>{profile}</b> — '
                        f'Barrel% {bpct:.1f}% · HH% {hhpct:.1f}%</div>',
                        unsafe_allow_html=True
                    )
        else:
            st.info("Season Statcast data not yet matched for this player. "
                    "This is common early in the season or for players with "
                    "uncommon last names. The last-30-day metrics above use "
                    "pitch-level data directly from Baseball Savant.")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — Game Log
# ─────────────────────────────────────────────────────────────────────────────

def _render_game_log(player_id: int, player_name: str):
    st.markdown("### 📅 Last 10 Games")
    if not player_id:
        st.info("⏳ Player ID not resolved — game log unavailable.")
        return
    try:
        from mlb_api import get_player_game_log
        log_df = get_player_game_log(player_id, last_n=10)
        if log_df.empty:
            st.info("No game log data available yet — season may have just started.")
            return

        # Colour hit column
        def _style_row(row):
            styles = [''] * len(row)
            if 'H' in row.index:
                h_idx = row.index.get_loc('H')
                if row['H'] > 0:
                    styles[h_idx] = 'color:#10b981;font-weight:700'
                if row.get('HR', 0) > 0:
                    hr_idx = row.index.get_loc('HR')
                    styles[hr_idx] = 'color:#ef4444;font-weight:700'
            return styles

        styled = log_df.style.apply(_style_row, axis=1)
        st.dataframe(styled, width='stretch', hide_index=True)

        # Form summary
        gp   = len(log_df[log_df['AB'] > 0])
        hits = len(log_df[log_df['H'] > 0])
        hrs  = log_df['HR'].sum() if 'HR' in log_df.columns else 0
        if gp > 0:
            rate  = hits / gp
            color = ("var(--hit)" if rate >= 0.6 else
                     "var(--xb)"  if rate >= 0.4 else "var(--neg)")
            st.markdown(
                f'<div class="notice notice-info" style="margin-top:.4rem">'
                f'Last {gp} games: '
                f'<span style="color:{color};font-weight:700">'
                f'hit in {hits}/{gp} games ({rate*100:.0f}%)</span>'
                f' · {int(log_df["H"].sum())} total hits · {int(hrs)} HR</div>',
                unsafe_allow_html=True
            )

        # Hit trend mini chart
        if len(log_df) >= 3 and 'H' in log_df.columns:
            chart_df = log_df[['Date', 'H']].copy()
            chart_df['Date'] = chart_df['Date'].astype(str)
            ch = alt.Chart(chart_df).mark_bar(color='#10b981', opacity=0.8).encode(
                alt.X('Date:N', axis=alt.Axis(labelAngle=-45, labelFontSize=8,
                                               labelColor='#64748b')),
                alt.Y('H:Q', scale=alt.Scale(domain=[0, max(3, chart_df['H'].max())]),
                      axis=alt.Axis(labelFontSize=8, labelColor='#64748b',
                                    gridColor='#1e2d3d', title='Hits')),
                tooltip=['Date', 'H']
            ).properties(height=120)
            st.altair_chart(ch.configure_view(strokeWidth=0), use_container_width=True)

    except Exception as e:
        st.info(f"Game log unavailable: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — Pitch Split vs Today's Pitcher
# ─────────────────────────────────────────────────────────────────────────────

def _render_pitch_split(row: pd.Series, df: pd.DataFrame):
    """
    Show BallPark Pal split data for this batter's matchup with today's pitcher.
    Surfaces all available prob columns in a clear table.
    """
    st.markdown("### 🔀 Matchup Split vs Today's Pitcher")

    batter  = row.get('Batter', '?')
    pitcher = row.get('Pitcher', '?')
    team    = row.get('Team', '?')

    split_cols = {
        '1B Prob':           '1B% (park)',
        '1B Prob (no park)': '1B% (base)',
        'XB Prob':           'XB% (park)',
        'XB Prob (no park)': 'XB% (base)',
        'HR Prob':           'HR% (park)',
        'HR Prob (no park)': 'HR% (base)',
        'BB Prob':           'BB%',
        'K Prob':            'K%',
        'vs Grade':          'vs Grade',
        'RC':                'RC (park)',
        'RC (no park)':      'RC (base)',
        'PA':                'PA vs P',
        'H':                 'H vs P',
        'AVG':               'AVG vs P',
    }

    # Get the raw row from the full df if available
    full_rows = df[(df['Batter'] == batter) & (df['Pitcher'] == pitcher)]
    if full_rows.empty:
        full_rows = df[df['Batter'] == batter].head(1)

    if full_rows.empty:
        st.info("No split data available.")
        return

    raw = full_rows.iloc[0]
    table_rows = []
    for col, label in split_cols.items():
        if col in raw.index:
            val = raw[col]
            if pd.notna(val):
                if col in ['AVG']:
                    table_rows.append({'Stat': label, 'Value': f"{float(val):.3f}"})
                elif col in ['vs Grade', 'PA', 'H']:
                    table_rows.append({'Stat': label, 'Value': str(int(float(val))) if val else '0'})
                elif col in ['RC', 'RC (no park)']:
                    table_rows.append({'Stat': label, 'Value': f"{float(val):.2f}"})
                else:
                    table_rows.append({'Stat': label, 'Value': f"{float(val):.1f}%"})

    if table_rows:
        split_df = pd.DataFrame(table_rows)
        st.markdown(
            f'<div class="notice notice-info" style="margin-bottom:.5rem">'
            f'<b>{batter}</b> ({team}) vs <b>{pitcher}</b> · '
            f'Data from BallPark Pal 3,000-simulation matchup</div>',
            unsafe_allow_html=True
        )
        st.dataframe(split_df, width='stretch', hide_index=True)
    else:
        st.info("No split data columns found.")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PAGE
# ─────────────────────────────────────────────────────────────────────────────

def player_profile_page(df: pd.DataFrame, player_id_map: dict, filters: dict):
    st.title("👤 Player Profile")
    st.markdown(
        '<div class="notice notice-info">Full intel on any batter from today\'s slate — '
        'BallPark Pal projections · Season stats · Statcast quality metrics · Game log</div>',
        unsafe_allow_html=True
    )

    if df is None or df.empty:
        st.error("No slate data loaded.")
        return

    # ── Player selector ────────────────────────────────────────────────────────
    all_batters = sorted(df['Batter'].unique().tolist())
    col1, col2  = st.columns([3, 1])
    with col1:
        selected = st.selectbox("Select Player", all_batters, key="profile_player_select")
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        show_raw = st.checkbox("Show raw data", value=False)

    player_rows = df[df['Batter'] == selected]
    if player_rows.empty:
        st.warning(f"No data found for {selected}.")
        return

    row       = player_rows.iloc[0]
    player_id = player_id_map.get(selected)

    # Show player ID status
    if not player_id:
        st.warning(
            f"⚠️ Could not resolve MLB player ID for **{selected}**. "
            "Game log and pitch-level Statcast unavailable. "
            "Season Statcast metrics (from the table) may still show if the name matched FanGraphs."
        )

    st.markdown("---")

    # ── Four sections ──────────────────────────────────────────────────────────
    _render_matchup_section(row, filters)
    st.markdown("---")
    _render_season_stats(player_id, selected)
    st.markdown("---")
    _render_statcast_section(player_id, selected, row)
    st.markdown("---")
    _render_game_log(player_id, selected)
    st.markdown("---")
    _render_pitch_split(row, df)

    # ── Raw data (debug) ───────────────────────────────────────────────────────
    if show_raw:
        with st.expander("🔧 Raw row data", expanded=False):
            st.dataframe(player_rows.T, width='stretch')
