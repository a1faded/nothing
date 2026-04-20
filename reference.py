"""
reference.py — A1PICKS Reference Manual Page
=============================================
Comprehensive documentation for all scoring systems, signal layers,
prop types, and data sources. Rendered as the 📚 Reference Manual page.
"""

import streamlit as st


def info_page():
    st.title("📚 A1PICKS Reference Manual")
    st.markdown(
        '<div style="background:#0f1923;border:1px solid #3730a3;border-radius:8px;'
        'padding:.65rem 1rem;margin-bottom:1rem;font-size:.82rem;color:#a5b4fc">'
        '📖 Complete reference for all scoring systems, signals, and prop types. '
        'Use this to understand how scores are calculated and what each column means.</div>',
        unsafe_allow_html=True
    )

    # ── BETTING TARGETS ───────────────────────────────────────────────────────
    with st.expander("🎯 Betting Targets — Over Side", expanded=True):
        st.markdown("""
| Target | Prop | What Wins | Primary Signal |
|--------|------|-----------|---------------|
| 🎯 Hit Score | Any base hit | Player gets a hit (1B, 2B, 3B, or HR) | `Hit_Score` — contact probability |
| 1️⃣ Single Score | Single only | Player hits specifically a 1B | `Single_Score` — 1B-tilted profile |
| 🔥 XB Score | Extra base hit | Player hits a double or triple | `XB_Score` — XB probability |
| 💣 HR Score | Home run | Player hits a home run | `HR_Score` — HR probability |
| 🔴 H+R+RBI Score | H+R+RBI over 1.5 | Combined Hits + Runs Scored + RBIs ≥ 2 | Composite — batting order × hit prob × game environment |

**Profile Mismatch Warning:** When viewing Single targets, players with `XB_Score` significantly higher than their `Single_Score` are profile mismatches — they're more likely to get an extra-base hit than a single. They appear below eligible candidates in the table with a `⚡ XB Profile` label.
        """)

    with st.expander("🔻 Under Targets", expanded=False):
        st.markdown("""
| Target | Line | What Wins | What Kills It |
|--------|------|-----------|--------------|
| 🔻 XB Under | XB 0.5 | No doubles or triples | Any double or triple |
| 📊 TB Under 1.5 | TB 1.5 | Under 1.5 total bases | 2+ total bases (double=2, HR=4) |
| 📉 TB Under 0.5 | TB 0.5 | Zero total bases | Any base hit (single=1 base already over) |
| ❌ Hit Under | Hit 0.5 | No base hit at all | Any hit type |
| 🔴 H+R+RBI Under | HRR 1.5 | Under 1.5 combined H+R+RBI | Batter accumulates 2+ across all three |

**Key insight on TB Under 1.5:** A single CASHES this bet (1 base = under). Only doubles (2 bases) and HRs (4 bases) lose it. Players with high `Single_Score` but low `XB_Score` are ideal targets.

**Key insight on TB Under 0.5:** Any base hit kills it. Walk = safe (0 bases). Strikeout = safe. This is the hardest to cash — needs strong K% + weak contact profile + pitcher dominance.
        """)

    # ── SCORING ENGINE ────────────────────────────────────────────────────────
    with st.expander("⚙️ Scoring Engine — How Scores Are Computed", expanded=False):
        st.markdown("""
### Stage 1 — BallPark Pal Raw Scores
Base probabilities from BallPark Pal's 3,000-simulation model per matchup:
- `p_1b` (1B probability), `p_xb` (XB prob), `p_hr` (HR prob), `p_bb` (walk prob), `p_k` (K prob)
- Combined into raw scores using weighted formulas emphasizing the relevant probability type
- Park-adjusted versions blend park factors into the raw probabilities

### Stage 2 — Statcast Overlay (±10 pts max per score)
Adjusts each score based on expected outcomes from batted ball data:
- `Barrel%` and `HH%` boost XB/HR scores for power hitters
- `xBA` adjusts Hit_Score for contact quality vs. actual results
- `xSLG` adjusts XB/HR scores for slugging tendency

### Stage 3 — Signal Overlays (all small-capped adjustments)
Applied post-normalization:
1. **xBA Luck** — gap between expected BA and actual BA signals regression. Positive gap = underperforming contact = Hit_Score boost.
2. **Batting Order** — slot 3-5 gets HR/XB bonus. Slot 1-2 gets Hit/Single bonus. Late order (7-9) penalized.
3. **Rolling Form** — 7-day H/G vs league avg (0.9 H/G). Hot hitters get boost. Cold hitters penalized.
4. **Platoon** — opposite-hand matchup = natural advantage (+2.0 pts). Same hand = slight disadvantage.

### Stage 4 — Profile Correction (Single_Score only)
When `XB_Score` significantly exceeds `Single_Score` (gap ≥ 5 pts), the Single_Score is penalized so profile-mismatched players rank below true singles hitters. Gap of 12+ pts → ~4-5 pt penalty.

### Stage 5 — H+R+RBI Composite Score
`HRR_Score = Hit_Score × 0.40 + Order_Bonus + HR_Score × 0.25 + GC_Run_Env + BvP_OPS_Adj`
- Batting order slots 1-5 add +8 pts (most R+RBI opportunities)
- Slots 7-9 subtract 5 pts (fewest at-bats and run production context)
- BvP OPS vs today's starter weighted by confidence (0 when <5 career AB)

### Game Conditions (GC) Layer
Applied via `*_gc` score variants when the GC toggle is ON. Multiplies each score by a factor derived from:
- `gc_hr4` (% chance of 4+ HR), `gc_hits20` (% chance of 20+ hits)
- `gc_runs10` (% chance of 10+ runs), `gc_k20` (% chance of 20+ Ks)
- `gc_qs` (SP quality start probability)
High-run games amplify HR/XB scores. High-K games suppress Hit scores.
        """)

    # ── UNDER SCORE SIGNALS ───────────────────────────────────────────────────
    with st.expander("🔻 Under Score Layers (11 Signals)", expanded=False):
        st.markdown("""
The Under Score is an 11-layer composite. Higher = stronger under candidate.

| Layer | Signal | Effect |
|-------|--------|--------|
| L1 | Inverted offensive scores (GC-adjusted) | Foundation — low Hit/XB/HR_Score = good under |
| L2 | K% bonus + BB% bonus (per-type weights) | Strikeouts and walks = 0 bases = always favorable |
| L3 | Pitcher grade + recent ERA/WHIP + days rest | Elite/rested pitcher = more suppression |
| L4 | Historical matchup AVG vs this pitcher type | Below-.245 avg history = struggles here |
| L5 | Recent XB rate (7-day 2B+3B/G) | Player on XB cold streak = XB/TB Under boost |
| L6 | Recent hit rate (7-day H/G) | Cold hitter = Hit/TB0.5 Under boost |
| L7 | Statcast: Barrel%, HH%, AvgEV, xSLG, xBA, xwOBA | Contact quality — power profile vs finesse |
| L8 | vs Grade + park XB factor | Weak matchup + pitcher-friendly park |
| L9 | Game conditions suppression | Low-run game + high-K environment |
| L10 | Batting order position | Slots 8-9 = fewer at-bats and bases |
| L11 | Platoon | LHP facing lineup = slight under lean |

**BB% weight by type:** XB Under 0.5× · TB 1.5 Under 0.8× · TB 0.5 Under 1.0× · Hit Under 1.2× · HRR Under 0.8×

**Pitcher grade direction:** `P.Grd ↑` in the under table means **higher grade = better for under**. An A+ pitcher facing a weak lineup is a top under signal.
        """)

    # ── DATA SOURCES ─────────────────────────────────────────────────────────
    with st.expander("📊 Data Sources", expanded=False):
        st.markdown("""
| Source | What It Provides | Update Frequency |
|--------|-----------------|-----------------|
| **BallPark Pal CSVs** | Per-matchup probabilities (p_1b, p_xb, p_hr, p_bb, p_k), park factors, historical PA/H/AVG vs pitcher type | Daily push from GitHub |
| **MLB Stats API** | Today's schedule, confirmed lineups, batting order, pitcher handedness, pitcher game log | Real-time (cached 10-60 min) |
| **Statcast (pybaseball)** | Barrel%, HH%, AvgEV, xBA, xSLG, xwOBA — full-season contact quality | Daily batch |
| **pybaseball (form)** | 7-day rolling batting stats: H/G, 2B+3B/G (XB rate) | Daily batch |
| **pybaseball (pitcher)** | 7-day rolling pitching stats: ERA, WHIP, K/9, BB/9 | Daily batch |
| **Tank01 BvP API** | Career stats vs today's specific pitcher: AB, H, AVG, OPS, HR, RBI, K, BB | Cached 24h per batter |
| **Tank01 Splits API** | Season splits by pitcher hand: vs. Left, vs. Right | Cached 12h per player |
| **Tank01 Odds API** | Sportsbook odds for TB, HR, runs props | Cached 30 min |
| **Tank01 Player List** | All 2,603 MLB player IDs (local file) | Static — updated seasonally |
        """)

    # ── COLUMNS REFERENCE ─────────────────────────────────────────────────────
    with st.expander("🗂️ Column Glossary", expanded=False):
        st.markdown("""
### Score Columns
| Column | Meaning |
|--------|---------|
| `🎯 Hit ⛅` | Hit Score with game conditions applied |
| `Base` | Base score before park adjustment |
| `Park Δ` | How much the park affects this specific matchup (±) |
| `Cond Δ` | How much game conditions affect this player today (±) |
| `Tier` | ELITE ≥75 · STRONG ≥60 · GOOD ≥45 · MODERATE ≥30 · WEAK <30 |
| `Profile` | Contact profile fit for this prop. ✅ Clean = ideal. ⚡ XB Lean = player tends toward extra bases |

### Probability Columns
| Column | Meaning |
|--------|---------|
| `Hit%` | Total hit probability (1B + XB + HR) |
| `1B%` | Single probability |
| `XB%` | Extra base (double/triple) probability |
| `HR%` | Home run probability |
| `K%` | Strikeout probability |
| `BB%` | Walk probability |
| `vsPit` | Batter vs pitcher grade (-10 to +10) |
| `P.Grd` | Pitcher quality grade (A+, A, B, C, D) |

### Batting Context
| Column | Meaning |
|--------|---------|
| `Pos` | Confirmed batting order slot (#1-9) |
| `Form` | 🔥 HOT (>1.2 H/G last 7 days) · ❄️ COLD (<0.5 H/G) |
| `PA` / `AVG` | Historical plate appearances and average vs this pitcher type |

### BvP & Splits Columns
| Column | Meaning |
|--------|---------|
| `BvP AB` | Career at-bats vs today's specific starter. ≥15 = high confidence |
| `BvP AVG` | Career batting average vs today's starter |
| `BvP OPS` | Career OPS vs today's starter — best H+R+RBI predictor |
| `BvP HR` | Career home runs vs today's starter |
| `Split AVG` | Season batting average vs this pitcher's hand (L or R) |
| `Split OPS` | Season OPS vs this pitcher's hand |

### Odds & Market Columns
| Column | Meaning |
|--------|---------|
| `TB Line` | Sportsbook total bases line (0.5 or 1.5) |
| `TB Under` | American odds for the under side |
| `TB Over` | American odds for the over side |
| `HR Odds` | Odds to hit any home run (HR target only) |
| `Market Edge` | ⚡ EDGE = model likes under more than market · ✅ CONFIRMED = both agree · 🔄 CONTRARIAN = market heavier on under than model |
| `Rest` | Pitcher days rest: ✅ 4-5+d normal/rested · ⚠️ 3d short · ❌ ≤2d very short |
        """)

    # ── TIER SYSTEM ──────────────────────────────────────────────────────────
    with st.expander("🏆 Score Tier System", expanded=False):
        st.markdown("""
All scores (0–100) map to the same five tiers, displayed in both the main predictor table and under table:

| Tier | Score Range | Meaning |
|------|------------|---------|
| 🟢 ELITE | ≥ 75 | Top-tier candidate — multiple signals strongly aligned |
| 🟡 STRONG | 60-74 | High confidence — most signals pointing the same direction |
| 🟠 GOOD | 45-59 | Solid candidate — more positive than negative signals |
| 🔴 MODERATE | 30-44 | Mixed signals — proceed with caution |
| ⚫ WEAK | < 30 | Unfavorable — most signals against this prop |

**Under Score tiers are inverted:** a score of 75 means the player is unlikely to accumulate bases, NOT that they're likely to hit. The same 0-100 scale applies — higher is always better for the selected prop direction.
        """)

    # ── CONFIDENCE & SAMPLE SIZE ─────────────────────────────────────────────
    with st.expander("📏 Confidence & Sample Size Guidelines", expanded=False):
        st.markdown("""
### BvP Career Stats (vs Today's Pitcher)
Sample size matters enormously for career stats. Use `BvP AB` as a reliability guide:

| AB Range | Confidence | How to Use |
|----------|-----------|------------|
| < 5 AB | None — not shown | No signal applied to scoring |
| 5-9 AB | Low (33-60%) | Small weight — directional signal only |
| 10-14 AB | Medium (67-93%) | Meaningful — patterns likely real |
| ≥ 15 AB | High (100%) | Full weight — strong evidence |

The scoring engine scales each BvP signal by its confidence factor automatically.

### Historical Matchup (BallPark Pal — vs Pitcher Type)
`PA` column shows plate appearances vs this pitcher's handedness:
- **PA < 5**: Signal not applied (too noisy)
- **PA 5-14**: Moderate weight
- **PA ≥ 15**: Full historical signal

### Statcast Data
Players with < 3 batted ball events get neutral (0.0) Statcast signals — no penalty for limited sample. This typically affects bench players and recent call-ups.
        """)

    # ── GAME CONDITIONS ───────────────────────────────────────────────────────
    with st.expander("🌦️ Game Conditions Explained", expanded=False):
        st.markdown("""
Game conditions use BallPark Pal simulation data to estimate today's offensive environment.

| Metric | Anchor (Median) | High = | Low = |
|--------|----------------|--------|-------|
| `20+ Hits %` | 18.6% | Hitter-friendly 🔴 over | Pitcher-friendly ✅ under |
| `10+ Runs %` | 28.4% | High-scoring game | Low-scoring game |
| `4+ HR %` | 12.2% | Power environment | Suppressed power |
| `20+ Ks %` | 23.3% | Pitcher dominates | Hitter-friendly |
| `SP QS %` | 21.5% | Quality start likely | Bullpen game likely |
| `8+ Walks %` | 46.5% | Wild pitching day | Control pitcher |

**Over predictor:** GC multiplies scores up when conditions favor offense, down when pitcher-friendly.

**Under predictor:** Same data flipped — low hits/runs/HR% = green ✅ = favorable for unders.

**GC toggle OFF:** Uses 30% of the full GC weight so it's never fully ignored, but batter/pitcher matchup quality dominates.
        """)

    # ── PITCHER REST SIGNAL ───────────────────────────────────────────────────
    with st.expander("💤 Pitcher Rest & Workload Signal", expanded=False):
        st.markdown("""
Added to all under score types as part of Layer 3 (Pitcher Quality).

| Days Rest | Signal | Meaning |
|-----------|--------|---------|
| 5+ days | +2.0 pts | Well rested — arm is fresh, full velocity |
| 4 days | 0.0 pts | Standard MLB rotation — neutral |
| 3 days | -1.5 pts | Short rest — fatigue risk, command may suffer |
| ≤ 2 days | -2.5 pts | Very short rest — significant concern |

**Workload modifier from last outing:**
- Last start ≥ 7.0 IP → **+1.0 pts** (went deep, arm is conditioned and well-warmed)
- Last start ≤ 3.0 IP → **-1.0 pts** (early exit or bullpen game — arm state uncertain)

The `Rest` column in the under table shows: `✅ 5d` (healthy), `⚠️ 3d` (caution), `❌ 2d` (avoid).

Visible on Player Profile page in the **Pitcher Rest & Workload** card, including the exact adjustment being applied to under scores.
        """)

    # ── PROP ODDS INTEGRATION ─────────────────────────────────────────────────
    with st.expander("💰 Sportsbook Odds Integration", expanded=False):
        st.markdown("""
Odds from Tank01 API are fetched daily and displayed as context — not as a filter or hard rule.

### Available Markets
| Market | Columns | Notes |
|--------|---------|-------|
| Total Bases | `TB Line`, `TB Under`, `TB Over` | Line is 0.5 or 1.5 |
| Home Run | `HR Odds` | Yes/no prop — shown on HR target only |

### Market Edge Badge
Compares our model's under confidence against the market's implied probability:

| Badge | Meaning |
|-------|---------|
| ⚡ EDGE | Model strongly favors under, market doesn't — potential +EV |
| ✅ CONFIRMED | Both model and market agree — high confidence |
| ↔️ NEUTRAL | Model and market roughly aligned |
| 🔄 CONTRARIAN | Market heavier on under than model — market may be right, model disagrees |

**Philosophy:** Market odds are context, not a veto. When our model sees a strong under signal but the market offers value (under at +money or short juice), that's the highest-value target. When the market is at -300 on the under, there may be no edge even if the model agrees.
        """)

    # ── HRR PROP GUIDE ───────────────────────────────────────────────────────
    with st.expander("🔴 H+R+RBI Prop Guide", expanded=False):
        st.markdown("""
The H+R+RBI prop (also called "Hits+Runs+RBIs over 1.5") counts three different offensive contributions.

### Ways to Cash the Over (≥ 2 combined)
- 1 hit + 1 run scored
- 1 hit + 1 RBI
- 2 hits
- 1 RBI + 1 run (e.g. solo HR = +1 RBI +1 run for the batter = 2 total)
- Any HR = automatic +2 minimum (1 run + 1 RBI)

### Best Over Targets
1. **Cleanup hitters (slots 3-5)** with high hit probability — most RBI opportunities
2. **Leadoff/2-hole (slots 1-2)** — score the most runs per game
3. **High-run-environment games** — `gc_runs10` well above 28.4% anchor
4. **Players with strong BvP OPS** vs today's starter (career OPS > .900 = strong historical contributor)

### Best Under Targets (≤ 1 combined)
1. **Bottom of order (slots 7-9)** — fewest at-bats, rarely score or drive in runs
2. **Low-scoring game** (gc_runs10 well below 28.4%)
3. **High K%** matchup — can't score or drive in runs with a strikeout
4. **Pitcher on short rest / dominant ERA** — fewer baserunners = fewer run opportunities

### Disqualification
HRR Under players are flagged ⚠️ when: `Hit_Score > 65` AND batting order slot 1-5. A highly-ranked contact hitter in a prime lineup slot almost always accumulates H+R+RBI — fading them requires very specific circumstances.
        """)

    st.markdown("---")
    st.markdown(
        '<div style="font-size:.72rem;color:#475569;text-align:center">'
        'A1PICKS V7 · BallPark Pal + MLB Stats API + Statcast + Tank01 BvP/Splits/Odds · '
        'Built for MLB prop betting research · Not financial advice</div>',
        unsafe_allow_html=True
    )
