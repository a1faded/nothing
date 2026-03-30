"""
ui/parlay.py — Parlay Builder V2
"""

import streamlit as st
import pandas as pd
import itertools
import random
from datetime import datetime
from config import CONFIG, SCORE_MAP, LABEL_MAP, SCORE_CSS
from helpers import grade_pill
from engine import gc_adjusted_score

# ─────────────────────────────────────────────────────────────────────────────
# COMBO BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def _build_all_combos(pool: pd.DataFrame, leg_bets: list, sgp: bool,
                      locked: list, env_filter: bool) -> list:
    """Build ALL valid combos ranked by harmonic mean confidence."""
    legs = len(leg_bets)
    if sgp:
        primary_sc = leg_bets[0]
        ranked     = pool.sort_values(primary_sc, ascending=False)
        candidates = ranked['Batter'].unique().tolist()
        if locked:
            candidates = [p for p in locked if p in candidates] + \
                         [p for p in candidates if p not in locked]
        all_combos_raw = list(itertools.combinations(
            candidates[:min(10, len(candidates))], legs))
        leg_candidates = None
    else:
        leg_candidates = []
        for sc in leg_bets:
            if sc not in pool.columns:
                return []
            gc_sc = gc_adjusted_score(pool, sc, use_gc=env_filter)
            ps = pool.copy()
            ps['_gc_adj'] = gc_sc.values
            if locked:
                ps['_locked'] = ps['Batter'].isin(locked).astype(int)
                ps = ps.sort_values(['_locked', '_gc_adj'], ascending=[False, False])
            else:
                ps = ps.sort_values('_gc_adj', ascending=False)
            per_game = ps.drop_duplicates(subset='Game').head(12)
            leg_candidates.append(per_game)
        all_combos_raw = list(itertools.product(
            *[lc['Batter'].tolist() for lc in leg_candidates]))

    ranked_combos = []
    for combo in all_combos_raw:
        if len(set(combo)) < legs:
            continue
        if not sgp:
            games_in_combo, valid = [], True
            for batter, cand in zip(combo, leg_candidates):
                row = cand[cand['Batter'] == batter]
                if row.empty:
                    valid = False
                    break
                games_in_combo.append(row.iloc[0]['Game'])
            if not valid or len(set(games_in_combo)) < legs:
                continue

        scores, valid = [], True
        for batter, sc in zip(combo, leg_bets):
            row = pool[pool['Batter'] == batter]
            if row.empty or sc not in row.columns:
                valid = False
                break
            scores.append(float(row[sc].values[0]))
        if not valid:
            continue

        conf = (len(scores) / sum(1/s for s in scores if s > 0)) \
               if all(s > 0 for s in scores) else 0
        ranked_combos.append((combo, scores, conf))

    ranked_combos.sort(key=lambda x: x[2], reverse=True)
    return ranked_combos


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT PANEL
# ─────────────────────────────────────────────────────────────────────────────

def _render_context_panel(batters: list, pool: pd.DataFrame):
    gc_cols = ['gc_hr4', 'gc_hits20', 'gc_k20', 'gc_walks8', 'gc_runs10', 'gc_qs']
    has_gc  = all(c in pool.columns for c in gc_cols)

    if not has_gc:
        st.markdown("""
<div class="notice notice-warn" style="margin-top:.75rem">
🔜 <b>Game Conditions Context</b> — Upload game condition CSVs to your GitHub repo
to see game context for parlay legs.
</div>""", unsafe_allow_html=True)
        return

    batter_rows = pool[pool['Batter'].isin(batters)][
        ['Batter', 'Team', 'Game'] + gc_cols
    ].drop_duplicates(subset=['Game'])

    if batter_rows.empty:
        return

    display_rows = []
    for _, row in batter_rows.iterrows():
        hr4_flag   = "✅" if row['gc_hr4']    > CONFIG['gc_hr4_anchor']    else "⚠️"
        hits_flag  = "✅" if row['gc_hits20'] > CONFIG['gc_hits20_anchor'] else "⚠️"
        runs_flag  = "✅" if row['gc_runs10'] > CONFIG['gc_runs10_anchor'] else "⚠️"
        k_flag     = "✅" if row['gc_k20']    < CONFIG['gc_k20_anchor']    else "⚠️"
        walks_flag = "✅" if row['gc_walks8'] < CONFIG['gc_walks8_anchor'] else "⚠️"
        display_rows.append({
            'Game':       row['Game'],
            '4+ HR %':    f"{hr4_flag} {row['gc_hr4']:.1f}%",
            '20+ Hits %': f"{hits_flag} {row['gc_hits20']:.1f}%",
            '10+ Runs %': f"{runs_flag} {row['gc_runs10']:.1f}%",
            '20+ Ks %':   f"{k_flag} {row['gc_k20']:.1f}%",
            '8+ Walks %': f"{walks_flag} {row['gc_walks8']:.1f}%",
        })

    if display_rows:
        st.markdown("**🌦️ Game Environment for Parlay Legs**")
        st.dataframe(pd.DataFrame(display_rows), width="stretch", hide_index=True)
        st.markdown(
            '<div class="notice notice-info" style="font-size:.73rem;margin-top:.3rem">'
            '✅ = above median (favourable) · ⚠️ = below median (tighter). '
            'For HR parlays look for ✅ on 4+ HR %. '
            'For Hit/XB parlays look for ✅ on 20+ Hits % and 10+ Runs %.</div>',
            unsafe_allow_html=True
        )


# ─────────────────────────────────────────────────────────────────────────────
# PARLAY CARD
# ─────────────────────────────────────────────────────────────────────────────

def _show_parlay_card(combo_batters, combo_scores, leg_bets, conf,
                      parlay_type, game_label, pool, sgp, env_filter):
    LG   = CONFIG
    legs = len(combo_batters)

    if not sgp:
        player_games = [pool[pool['Batter'] == b].iloc[0]['Game']
                        for b in combo_batters if not pool[pool['Batter'] == b].empty]
        if len(player_games) != len(set(player_games)):
            st.markdown(
                '<div class="notice notice-warn">⚠️ <b>Correlation Warning</b> — '
                'Two or more legs are from the same game.</div>',
                unsafe_allow_html=True)

    conf_lbl, conf_note = (
        ("🟢 Strong",   "All legs have solid backing.")      if conf >= 70 else
        ("🟡 Moderate", "Most legs solid — check flagged.") if conf >= 50 else
        ("🔴 Weak",     "One or more legs have limited support.")
    )
    env_note = " · 🌦️ conditions weighted" if env_filter else ""
    st.markdown(f"""
<div class="parlay-summary">
  <div class="ps-title">{parlay_type} · {legs}-Leg{(' · ' + game_label) if game_label else ''}{env_note}</div>
  <div class="ps-conf">{conf:.1f} <span style="font-size:.8rem;color:var(--muted)">/ 100</span></div>
  <div class="ps-sub">{conf_lbl} — {conf_note}</div>
  <div class="ps-sub" style="font-size:.7rem;margin-top:.2rem">
    Harmonic mean of leg scores. Weak legs penalised heavily. Not a win probability.
  </div>
</div>""", unsafe_allow_html=True)

    leg_htmls  = ""
    clip_lines = []

    for i, (batter, sc, score) in enumerate(zip(combo_batters, leg_bets, combo_scores)):
        m2 = pool[pool['Batter'] == batter]
        if m2.empty:
            leg_htmls += f'<div class="parlay-leg"><div class="leg-num">Leg {i+1}</div>' \
                         f'<div class="leg-batter">{batter}</div>' \
                         f'<div class="leg-meta">Data unavailable</div></div>'
            continue
        row = m2.iloc[0]

        def _s(col, default=0.0):
            v = row.get(col, default)
            try:
                return float(v)
            except Exception:
                return default

        k_lg   = LG['league_k_avg']  - _s('p_k')
        hr_lg  = _s('p_hr') - LG['league_hr_avg']
        k_cls  = "pos-val" if k_lg  >= 0 else "neg-val"
        hr_cls = "pos-val" if hr_lg >= 0 else "neg-val"
        col_css = SCORE_CSS.get(sc, 'var(--accent)')
        lbl     = LABEL_MAP.get(sc, sc)
        gph     = grade_pill(str(row.get('pitch_grade', 'B')))
        pa_val  = _s('PA')
        hist_row = (
            f'<div class="pcard-row"><span class="pk">Hist</span>'
            f'<span class="pv">{int(pa_val)} PA · {_s("AVG"):.3f}</span></div>'
        ) if pa_val >= LG['hist_min_pa'] else ""

        if score >= 70:
            sbadge = '<span style="background:#052e16;color:#4ade80;padding:1px 6px;border-radius:10px;font-size:.65rem;font-weight:700">STRONG</span>'
        elif score >= 50:
            sbadge = '<span style="background:#1c1400;color:#fbbf24;padding:1px 6px;border-radius:10px;font-size:.65rem;font-weight:700">OK</span>'
        else:
            sbadge = '<span style="background:#1c0000;color:#f87171;padding:1px 6px;border-radius:10px;font-size:.65rem;font-weight:700">⚠️ WEAK</span>'

        gc_adj     = float(gc_adjusted_score(pool, sc, use_gc=env_filter).loc[m2.index[0]])
        cond_delta = gc_adj - _s(sc)
        cond_str   = ""
        if env_filter and abs(cond_delta) >= 0.5:
            cc = "var(--pos)" if cond_delta > 0 else "var(--neg)"
            cond_str = f'<div class="pcard-row"><span class="pk">🌦️ Cond Δ</span>' \
                       f'<span class="pv" style="color:{cc}">{cond_delta:+.1f}</span></div>'

        leg_htmls += f"""
<div class="parlay-leg">
  <div class="leg-num">Leg {i+1} {sbadge}</div>
  <div class="leg-batter">{batter}</div>
  <div class="leg-meta">{row.get('Team','?')} vs {row.get('Pitcher','?')} {gph}</div>
  <div class="leg-score" style="color:{col_css}">{lbl} &nbsp; {score:.1f}</div>
  <div style="margin-top:.45rem">
    <div class="pcard-row"><span class="pk">Hit Prob</span><span class="pv">{_s('total_hit_prob'):.1f}%</span></div>
    <div class="pcard-row"><span class="pk">1B/XB/HR</span><span class="pv">{_s('p_1b'):.1f}/{_s('p_xb'):.1f}/{_s('p_hr'):.1f}%</span></div>
    <div class="pcard-row"><span class="pk">K%</span><span class="pv">{_s('p_k'):.1f}% <span class="{k_cls}">({k_lg:+.1f})</span></span></div>
    <div class="pcard-row"><span class="pk">HR vs Lg</span><span class="pv {hr_cls}">{hr_lg:+.2f}%</span></div>
    <div class="pcard-row"><span class="pk">vs Grade</span><span class="pv">{int(_s('vs Grade'))}</span></div>
    {cond_str}{hist_row}
  </div>
</div>"""
        clip_lines.append(
            f"Leg {i+1}: {batter} ({row.get('Team','?')}) — {lbl} — Score {score:.1f}"
        )

    st.markdown(f'<div class="parlay-grid">{leg_htmls}</div>', unsafe_allow_html=True)

    clip_text = "\n".join(clip_lines) + f"\nConfidence: {conf:.1f}/100"
    st.download_button(
        "📋 Export this Parlay (txt)", clip_text,
        file_name=f"parlay_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
        mime="text/plain",
        key=f"parlay_export_{hash(str(combo_batters))}"
    )
    _render_context_panel(list(combo_batters), pool)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PAGE
# ─────────────────────────────────────────────────────────────────────────────

def parlay_page(df: pd.DataFrame):
    st.title("⚡ Parlay Builder")
    st.markdown(
        '<div class="notice notice-info">ℹ️ Scores are a statistical foundation — not a guarantee. '
        'Parlay risk compounds with each leg. Use as research, not a tip sheet.</div>',
        unsafe_allow_html=True
    )
    if df is None or df.empty:
        st.error("No data loaded.")
        return

    all_batters = sorted(df['Batter'].unique().tolist())
    global_excl = st.session_state.get('excluded_players', [])

    with st.expander("🚫 Exclude Players (Parlay Builder)", expanded=False):
        parlay_excl = st.multiselect(
            "Exclude from parlay candidates",
            options=all_batters,
            default=global_excl,
            help="Exclusions apply only inside Parlay Builder.",
            key="parlay_exclusions"
        )
    pool = df[~df['Batter'].isin(parlay_excl)].copy()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        parlay_type = st.selectbox(
            "Parlay Type",
            ["Cross-Game", "SGP — Stack (same team)", "SGP — Split (both teams)"]
        )
    with c2:
        legs = st.selectbox("Number of Legs", [2, 3, 4], index=1)
    with c3:
        bet_mode = st.selectbox(
            "Bet Mode", ["Same bet on all legs", "Mixed — I'll choose per leg"]
        )
    with c4:
        env_filter = st.toggle(
            "🌦️ Weight Game Conditions", value=True,
            help="Hit bets: 20+ Hits signal weighted 1.8×. HR bets: 4+ HR signal weighted 1.8×."
        )

    if bet_mode == "Same bet on all legs":
        all_bet  = st.selectbox("Bet Type (all legs)", list(SCORE_MAP.keys()))
        leg_bets = [SCORE_MAP[all_bet]] * legs
    else:
        leg_cols = st.columns(legs)
        leg_bets = []
        for i, lc in enumerate(leg_cols):
            with lc:
                choice = st.selectbox(f"Leg {i+1}", list(SCORE_MAP.keys()), key=f"lb_{i}")
                leg_bets.append(SCORE_MAP[choice])

    with st.expander("🔒 Lock Players (anchor specific players)", expanded=False):
        st.caption("Locked players are prioritised. Leave empty for fully automatic.")
        max_lock = min(legs - 1, 2)
        locked   = st.multiselect(
            f"Lock up to {max_lock} player(s)", options=all_batters,
            max_selections=max_lock, key="parlay_locked"
        ) if max_lock > 0 else []

    st.markdown("---")

    sgp         = parlay_type.startswith("SGP")
    chosen_game = None
    if sgp:
        games = sorted(pool['Game'].unique().tolist())
        if not games:
            st.warning("No games available.")
            return
        chosen_game = st.selectbox("Select Game for SGP", games)
        game_pool   = pool[pool['Game'] == chosen_game].copy()
        if parlay_type == "SGP — Stack (same team)":
            primary_sc = leg_bets[0]
            team_avg   = game_pool.groupby('Team')[primary_sc].mean()
            build_pool = game_pool[game_pool['Team'] == team_avg.idxmax()].copy()
        else:
            build_pool = game_pool.copy()
    else:
        build_pool = pool

    cache_key = (
        f"parlay_{parlay_type}_{legs}_{'-'.join(leg_bets)}_{env_filter}_"
        f"{'-'.join(sorted(locked))}_{chosen_game or 'cg'}_{'-'.join(sorted(parlay_excl))}"
    )

    if st.session_state.get('parlay_cache_key') != cache_key:
        combos = _build_all_combos(build_pool, leg_bets, sgp, locked, env_filter)
        st.session_state['parlay_combos']    = combos
        st.session_state['parlay_combo_idx'] = 0
        st.session_state['parlay_cache_key'] = cache_key
    else:
        combos = st.session_state.get('parlay_combos', [])

    if not combos:
        st.warning("⚠️ Could not build any valid combinations. Try relaxing exclusions or adding more games.")
        return

    total_combos = min(len(combos), 50)
    idx          = min(st.session_state.get('parlay_combo_idx', 0), total_combos - 1)

    nav_c1, nav_c2, nav_c3, nav_c4 = st.columns([2, 1, 1, 2])
    with nav_c1:
        st.markdown(
            f'<div style="font-family:JetBrains Mono,monospace;font-size:.85rem;'
            f'color:var(--muted);padding:.4rem 0">Combo {idx+1} of {total_combos}</div>',
            unsafe_allow_html=True
        )
    with nav_c2:
        if st.button("◀ Prev", disabled=(idx == 0)):
            st.session_state['parlay_combo_idx'] = max(0, idx - 1)
            st.rerun()
    with nav_c3:
        if st.button("Next ▶", disabled=(idx >= total_combos - 1)):
            st.session_state['parlay_combo_idx'] = min(total_combos - 1, idx + 1)
            st.rerun()
    with nav_c4:
        if st.button("🎲 Random"):
            st.session_state['parlay_combo_idx'] = random.randint(0, total_combos - 1)
            st.rerun()

    combo_batters, combo_scores, conf = combos[idx]
    _show_parlay_card(
        combo_batters, combo_scores, leg_bets, conf,
        parlay_type, chosen_game, pool, sgp, env_filter
    )
