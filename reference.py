"""
ui/reference.py — Reference Manual page
"""

import streamlit as st
from config import CONFIG


def info_page():
    st.title("📚 A1PICKS MLB Reference Manual")
    LG = CONFIG

    with st.expander("📖 What is this tool?", expanded=True):
        st.markdown("""
This app takes BallPark Pal's daily simulation data (3,000 runs per game before first pitch)
and filters + weights it to surface the best targets for four MLB player prop bet types:
**Base Hit · Single · Double/Triple · Home Run**.

BallPark Pal already accounts for weather, park factors, recent performance, pitcher tendencies,
and head-to-head matchup data. **We are not trying to out-predict BallPark Pal** — we are
extracting and ranking their output specifically for betting use cases.
        """)

    with st.expander("📊 Understanding the Data Columns", expanded=False):
        st.markdown(f"""
<div class="ref-section">
<h3>Probability Columns</h3>
<p>These come directly from BallPark Pal's 3,000-simulation output:</p>
<ul>
<li><b>1B Prob %</b> — Probability this batter gets a single in today's game</li>
<li><b>XB Prob %</b> — Probability of a double or triple</li>
<li><b>HR Prob %</b> — Probability of a home run</li>
<li><b>BB Prob %</b> — Probability of a walk (penalises scores)</li>
<li><b>K Prob %</b>  — Probability of a strikeout (penalises scores)</li>
<li><b>Hit%</b>      — Combined: 1B% + XB% + HR%</li>
</ul>
</div>

<div class="ref-section">
<h3>Modifier Columns</h3>
<ul>
<li><b>vsPit</b> — BallPark Pal's batter vs pitcher rating (−10 to +10)</li>
<li><b>RC</b> — Runs Created matchup quality score (supporting signal)</li>
<li><b>PA / AVG vs P</b> — Historical record vs this exact pitcher.
  Bonus when PA ≥ {LG['hist_min_pa']} with hits. Penalty when PA ≥ 3 with zero hits.</li>
</ul>
</div>

<div class="ref-section">
<h3>Park Δ Column</h3>
<p>How many score points park factors added or removed. Toggle <b>Park Factors</b> OFF
to see base scores without environmental influence.</p>
</div>

<div class="ref-section">
<h3>Pitcher Grade (P.Grd)</h3>
<p>A+ through D — how likely the pitcher allows 8+ hits, 2+ HRs, or 3+ walks game-wide.
Applied as a mild ±5% multiplier. Batter probabilities always dominate.</p>
</div>

<div class="ref-section">
<h3>K% ↓Lg / BB% ↓Lg / HR% ↑Lg</h3>
<ul>
<li><b>K% ↓Lg</b>  — League avg {LG['league_k_avg']}%. <span style="color:var(--pos)">Positive = better contact.</span></li>
<li><b>BB% ↓Lg</b> — League avg {LG['league_bb_avg']}%. <span style="color:var(--pos)">Positive = more aggressive.</span></li>
<li><b>HR% ↑Lg</b> — League avg {LG['league_hr_avg']}%. <span style="color:var(--pos)">Positive = above average HR rate.</span></li>
</ul>
</div>
""", unsafe_allow_html=True)

    with st.expander("🎯 The Four Scores — How They Work", expanded=False):
        st.markdown(f"""
<div class="ref-section">
<h3><span style="color:var(--hit)">🎯 Hit Score</span> — Any Base Hit</h3>
<p><b>Formula:</b> (1B×3.0 + XB×2.0 + HR×1.0 − K×2.5 − BB×1.0) × pitcher_hit_mult</p>
<p><b>Best targets:</b> High 1B%, moderate XB%, well below-average K%. Green K% ↓Lg is a strong signal.</p>
</div>

<div class="ref-section">
<h3><span style="color:var(--single)">1️⃣ Single Score</span> — Single Specifically</h3>
<p><b>Formula:</b> (1B×5.0 − K×2.5 − BB×1.0 − XB×0.8 − HR×0.5) × pitcher_hit_mult</p>
<p><b>Key:</b> High XB% and HR% are <b>penalised</b>. You want a true contact hitter, not a power bat.</p>
</div>

<div class="ref-section">
<h3><span style="color:var(--xb)">🔥 XB Score</span> — Extra Base Hit</h3>
<p><b>Formula:</b> (XB×5.0 + HR×0.8 − K×1.5 − BB×1.0) × pitch_xb_mult</p>
<p><b>Note:</b> K% tolerance is moderate here — power/XB hitters naturally K more.</p>
</div>

<div class="ref-section">
<h3><span style="color:var(--hr)">💣 HR Score</span> — Home Run</h3>
<p><b>Formula:</b> (HR×6.0 + XB×0.8 − K×0.8 − BB×1.0 + XBBoost×0.03) × pitcher_hr_mult</p>
<p><b>Why light K% penalty:</b> Power hitters (Stanton, Judge) K at 25–35%+ but are legitimate HR threats.
vs Grade also weighted lightly — power is less matchup-dependent than contact.</p>
</div>
""", unsafe_allow_html=True)

    with st.expander("🗺️ How to Navigate the App", expanded=False):
        st.markdown("""
<div class="ref-section">
<h3>Step 1 — Choose Your Betting Target</h3>
<p>The first sidebar dropdown is the most important decision. Pick the score type matching your bet.</p>
</div>

<div class="ref-section">
<h3>Step 2 — Set Your Filters</h3>
<ul>
<li><b>Max K %</b>: Hit/Single ≤ 25–30%. XB ≤ 35%. HR ≤ 40%+.</li>
<li><b>Max BB %</b>: Consistent across all types — walks kill all props.</li>
<li><b>Min vs Grade</b>: Leave at −10 for HR bets. Negative grades don't disqualify power.</li>
</ul>
</div>

<div class="ref-section">
<h3>Step 3 — Read the Results Table</h3>
<p>Active score column is left of the table. Green cells = top percentile for today's slate.
<b>Park Δ</b> &gt; +5 means score relies on park — toggle OFF to verify merit.</p>
</div>

<div class="ref-section">
<h3>Step 4 — Parlay Builder</h3>
<p>Cross-Game: independent legs from different games.
SGP Stack: correlated players from same team.
SGP Split: both teams in same high-run game.</p>
<p><b>Confidence</b> uses harmonic mean — one weak leg drags the whole card down significantly.</p>
</div>
""", unsafe_allow_html=True)

    with st.expander("⚖️ Strategy by Bet Type", expanded=False):
        st.markdown(f"""
<div class="ref-section">
<h3>Cash / Solo Props</h3>
<ul>
<li><b>Hit props</b>: Hit Score ≥ 60, Hit% ≥ 28%, K% ≤ 25%, Grade B+</li>
<li><b>Single props</b>: Single Score ≥ 55, 1B% ≥ 14%, XB% ≤ 6%, K% ≤ 22%</li>
<li><b>XB/Double props</b>: XB Score ≥ 60, XB% ≥ 5%, Grade B+</li>
<li><b>HR props</b>: HR Score ≥ 60, HR% ≥ 3.5% (above lg avg {LG['league_hr_avg']}%), don't cap K% tightly</li>
</ul>
</div>

<div class="ref-section">
<h3>Multi-Game Parlays</h3>
<ul>
<li>Each leg ≥ 60 in target category</li>
<li>Avoid D pitcher grade in parlays — 5% drag compounds</li>
<li>Don't stack large positive Park Δ across all legs</li>
</ul>
</div>

<div class="ref-section">
<h3>SGP Guidelines</h3>
<ul>
<li><b>Stack</b>: Stacking same-team players = positive correlation. A+ opposing pitcher grade favours hits.</li>
<li><b>Split</b>: Use when game props show high 20+ Hits probability — both offenses may perform.</li>
</ul>
</div>

<div class="ref-section">
<h3>Score Benchmarks</h3>
<ul>
<li>≥ 80 — Elite. Top tier confidence.</li>
<li>65–79 — Strong. Solid statistical foundation.</li>
<li>50–64 — Average. Good supporting leg, not a primary anchor.</li>
<li>35–49 — Weak. GPP differentiation only.</li>
<li>≤ 34 — Avoid in any serious bet.</li>
</ul>
</div>

**League Baselines (4-year stable)** — K% {LG['league_k_avg']}% · BB% {LG['league_bb_avg']}% · HR% {LG['league_hr_avg']}% · AVG {LG['league_avg']}
""", unsafe_allow_html=True)
