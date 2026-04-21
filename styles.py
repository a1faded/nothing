"""
styles.py — A1PICKS Dark Precision Theme V2
=============================================
Professional sports-analytics dark UI.

Design system:
  - 3-level surface hierarchy (bg / surf / surf2 / surf3)
  - Score color system with matching glow variants
  - Consistent shadow scale
  - Smooth transitions on interactive elements
  - Scrollbar styling
  - Better mobile breakpoints
  - Animated data freshness pulse
  - Improved typography scale
  - Professional card/panel components
"""

import streamlit as st


def inject_css():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* ── DESIGN TOKENS ───────────────────────────────────────────────────────── */
:root {
  /* Backgrounds — 4-level depth system */
  --bg:      #06090f;
  --surf:    #0d1321;
  --surf2:   #131c2e;
  --surf3:   #1a2540;
  --surf4:   #202e4a;

  /* Borders */
  --border:  #1e2d3d;
  --border2: #2a3f57;

  /* Text */
  --text:    #e8eef7;
  --text2:   #a8b8d0;
  --muted:   #5a7090;
  --dim:     #3a5070;

  /* Score palette + matching glows */
  --hit:         #10b981;
  --hit-dim:     rgba(16,185,129,.12);
  --hit-glow:    rgba(16,185,129,.35);
  --single:      #06b6d4;
  --single-dim:  rgba(6,182,212,.12);
  --single-glow: rgba(6,182,212,.35);
  --xb:          #f59e0b;
  --xb-dim:      rgba(245,158,11,.12);
  --xb-glow:     rgba(245,158,11,.35);
  --hr:          #ef4444;
  --hr-dim:      rgba(239,68,68,.12);
  --hr-glow:     rgba(239,68,68,.35);

  /* Accent */
  --accent:      #3b82f6;
  --accent-dim:  rgba(59,130,246,.12);
  --accent-glow: rgba(59,130,246,.30);

  /* Status */
  --pos:  #22c55e;
  --neg:  #ef4444;
  --warn: #f59e0b;

  /* Shadows */
  --shadow-xs: 0 1px 2px rgba(0,0,0,.5);
  --shadow-sm: 0 2px 6px rgba(0,0,0,.5);
  --shadow-md: 0 4px 14px rgba(0,0,0,.55);
  --shadow-lg: 0 8px 28px rgba(0,0,0,.65);
}

/* ── GLOBAL RESETS ───────────────────────────────────────────────────────── */
html, body, [class*="css"] {
  font-family: 'Outfit', sans-serif !important;
  background: var(--bg) !important;
  color: var(--text) !important;
}

/* Remove Streamlit default top padding/decoration */
#MainMenu, footer, header { visibility: hidden; }
.block-container {
  padding: .75rem 1.25rem 3rem !important;
  max-width: 1440px !important;
}

/* ── CUSTOM SCROLLBAR ────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb {
  background: var(--surf3);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover { background: var(--border2); }

/* ── SIDEBAR ─────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
  background: var(--surf) !important;
  border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] > div:first-child {
  padding-top: 1rem !important;
}
[data-testid="stSidebar"] * {
  font-size: .84rem !important;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
  font-size: .9rem !important;
  color: var(--text2) !important;
  text-transform: uppercase;
  letter-spacing: .08em;
}

/* ── SIDEBAR COLLAPSE TOGGLE — make reopen button always visible ─────────── */
/* The collapse/expand arrow button that Streamlit renders at the sidebar edge */
[data-testid="collapsedControl"] {
  display:          flex !important;
  align-items:      center !important;
  justify-content:  center !important;
  width:            2.2rem !important;
  height:           2.2rem !important;
  background:       var(--surf2) !important;
  border:           1px solid var(--border2) !important;
  border-radius:    0 8px 8px 0 !important;
  color:            var(--hit) !important;
  cursor:           pointer !important;
  top:              50% !important;
  transform:        translateY(-50%) !important;
  box-shadow:       2px 0 12px rgba(0,0,0,.4) !important;
  transition:       background .2s, box-shadow .2s !important;
}
[data-testid="collapsedControl"]:hover {
  background:   var(--surf3) !important;
  box-shadow:   2px 0 20px rgba(16,185,129,.25) !important;
}
[data-testid="collapsedControl"] svg {
  width:  1.1rem !important;
  height: 1.1rem !important;
  color:  var(--hit) !important;
  fill:   var(--hit) !important;
}

/* Sidebar radio — style like a nav menu */
[data-testid="stSidebar"] [data-testid="stRadio"] label {
  display: flex !important;
  align-items: center !important;
  padding: .45rem .75rem !important;
  border-radius: 8px !important;
  margin: .15rem 0 !important;
  transition: background .15s, color .15s !important;
  cursor: pointer !important;
  color: var(--text2) !important;
  font-weight: 500 !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
  background: var(--surf2) !important;
  color: var(--text) !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] [aria-checked="true"] + div label,
[data-testid="stSidebar"] [data-testid="stRadio"] input:checked + div {
  background: var(--accent-dim) !important;
  color: var(--accent) !important;
  border-left: 2px solid var(--accent) !important;
}

/* ── TYPOGRAPHY ──────────────────────────────────────────────────────────── */
h1, h2, h3, h4, h5 { font-family: 'Outfit', sans-serif !important; }
h1 { font-size: 1.15rem !important; font-weight: 800 !important; }
h2 { font-size: 1rem !important; font-weight: 700 !important; }
h3 { font-size: .9rem !important; font-weight: 700 !important; }
h4 { font-size: .85rem !important; font-weight: 600 !important; }

/* ── BUTTONS ─────────────────────────────────────────────────────────────── */
[data-testid="stButton"] button,
[data-testid="stDownloadButton"] button {
  background: var(--surf2) !important;
  border: 1px solid var(--border2) !important;
  color: var(--text2) !important;
  border-radius: 8px !important;
  font-family: 'Outfit', sans-serif !important;
  font-weight: 600 !important;
  font-size: .82rem !important;
  padding: .4rem 1rem !important;
  transition: all .15s !important;
  box-shadow: var(--shadow-xs) !important;
}
[data-testid="stButton"] button:hover,
[data-testid="stDownloadButton"] button:hover {
  background: var(--surf3) !important;
  border-color: var(--accent) !important;
  color: var(--text) !important;
  box-shadow: 0 0 0 2px var(--accent-dim) !important;
}

/* ── EXPANDERS ───────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
  background: var(--surf) !important;
  border: 1px solid var(--border) !important;
  border-radius: 10px !important;
  margin: .4rem 0 !important;
  overflow: hidden !important;
  box-shadow: var(--shadow-xs) !important;
}
[data-testid="stExpander"] summary {
  padding: .65rem 1rem !important;
  font-size: .84rem !important;
  font-weight: 600 !important;
  color: var(--text2) !important;
  border-radius: 10px !important;
  transition: background .15s !important;
}
[data-testid="stExpander"] summary:hover {
  background: var(--surf2) !important;
  color: var(--text) !important;
}
[data-testid="stExpander"][open] summary {
  border-bottom: 1px solid var(--border) !important;
  border-radius: 10px 10px 0 0 !important;
}

/* ── SELECTBOX / SLIDERS ─────────────────────────────────────────────────── */
[data-testid="stSelectbox"] > div,
[data-testid="stMultiSelect"] > div {
  background: var(--surf2) !important;
  border: 1px solid var(--border2) !important;
  border-radius: 8px !important;
  color: var(--text) !important;
  font-size: .83rem !important;
}
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {
  background: var(--accent) !important;
  border-color: var(--accent) !important;
}

/* ── DATAFRAME / TABLE ───────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
  border-radius: 10px !important;
  overflow: hidden !important;
  border: 1px solid var(--border) !important;
  box-shadow: var(--shadow-sm) !important;
}
[data-testid="stDataFrame"] th {
  background: var(--surf2) !important;
  font-size: .72rem !important;
  font-family: 'Outfit', sans-serif !important;
  text-transform: uppercase !important;
  letter-spacing: .05em !important;
  color: var(--muted) !important;
  border-bottom: 1px solid var(--border) !important;
  padding: .5rem .7rem !important;
  font-weight: 600 !important;
}
[data-testid="stDataFrame"] td {
  font-family: 'JetBrains Mono', monospace !important;
  font-size: .78rem !important;
  padding: .4rem .6rem !important;
  border-bottom: 1px solid var(--border) !important;
}
[data-testid="stDataFrame"] tr:last-child td { border-bottom: none !important; }
[data-testid="stDataFrame"] tr:hover td {
  background: var(--surf2) !important;
  transition: background .1s !important;
}

/* ── SPINNER ─────────────────────────────────────────────────────────────── */
[data-testid="stSpinner"] p {
  color: var(--text2) !important;
  font-size: .84rem !important;
}

/* ── ALERTS / INFO ───────────────────────────────────────────────────────── */
[data-testid="stAlert"] {
  border-radius: 8px !important;
  border: 1px solid var(--border2) !important;
}

/* ── TOGGLE / CHECKBOX ───────────────────────────────────────────────────── */
[data-testid="stCheckbox"] label,
[data-testid="stToggle"] label {
  color: var(--text2) !important;
  font-size: .84rem !important;
}

/* ═══════════════════════════════════════════════════════════════════════════
   CUSTOM COMPONENTS
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── APP HEADER ──────────────────────────────────────────────────────────── */
.app-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: .5rem 0 .75rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: .85rem;
  flex-wrap: wrap;
}
.app-header .title-wrap h1 {
  font-size: 1.2rem !important;
  font-weight: 800 !important;
  color: var(--text) !important;
  margin: 0 !important;
  line-height: 1.2;
  letter-spacing: -.01em;
}
.app-header .title-wrap p {
  font-size: .68rem;
  color: var(--muted);
  margin: .15rem 0 0;
  letter-spacing: .02em;
}
.app-header .meta {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: .5rem;
}

/* ── STAT BAR ────────────────────────────────────────────────────────────── */
.stat-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
  background: var(--surf);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: .5rem .25rem;
  margin-bottom: .85rem;
  align-items: stretch;
  box-shadow: var(--shadow-xs);
}
.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: .35rem .9rem;
  border-right: 1px solid var(--border);
  min-width: 88px;
  transition: background .15s;
}
.stat-item:last-child { border-right: none; }
.stat-item:hover { background: var(--surf2); border-radius: 8px; }
.stat-item .val {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--text);
  line-height: 1;
}
.stat-item .lbl {
  font-size: .62rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .06em;
  margin-top: .2rem;
  white-space: nowrap;
}

/* ── SCORE SUMMARY CARDS ─────────────────────────────────────────────────── */
.score-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: .6rem;
  margin: .6rem 0;
}
.scard {
  background: var(--surf);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: .8rem .95rem;
  position: relative;
  overflow: hidden;
  transition: border-color .2s, box-shadow .2s, transform .15s;
  box-shadow: var(--shadow-xs);
}
.scard:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}
/* Top accent stripe */
.scard::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  border-radius: 12px 12px 0 0;
}
.scard-hit   { border-color: var(--border); }
.scard-hit:hover   { border-color: var(--hit);    box-shadow: 0 4px 20px var(--hit-dim); }
.scard-single:hover { border-color: var(--single); box-shadow: 0 4px 20px var(--single-dim); }
.scard-xb:hover    { border-color: var(--xb);     box-shadow: 0 4px 20px var(--xb-dim); }
.scard-hr:hover    { border-color: var(--hr);     box-shadow: 0 4px 20px var(--hr-dim); }
.scard-hit::before    { background: var(--hit); }
.scard-single::before { background: var(--single); }
.scard-xb::before     { background: var(--xb); }
.scard-hr::before     { background: var(--hr); }

.scard .sc-type {
  font-size: .64rem;
  text-transform: uppercase;
  letter-spacing: .08em;
  color: var(--muted);
  margin-bottom: .3rem;
}
.scard .sc-type span { font-weight: 700; }
.scard-hit    .sc-type span { color: var(--hit); }
.scard-single .sc-type span { color: var(--single); }
.scard-xb     .sc-type span { color: var(--xb); }
.scard-hr     .sc-type span { color: var(--hr); }

.scard .sc-name {
  font-size: 1rem;
  font-weight: 700;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.scard .sc-meta {
  font-family: 'JetBrains Mono', monospace;
  font-size: .68rem;
  color: var(--muted);
  margin-top: .2rem;
}
.scard .sc-score {
  font-family: 'JetBrains Mono', monospace;
  font-size: .85rem;
  font-weight: 700;
  position: absolute;
  top: .65rem; right: .75rem;
}
.scard-hit    .sc-score { color: var(--hit); }
.scard-single .sc-score { color: var(--single); }
.scard-xb     .sc-score { color: var(--xb); }
.scard-hr     .sc-score { color: var(--hr); }

/* ── PITCHER GRADE PILLS ─────────────────────────────────────────────────── */
.gp {
  padding: 2px 8px;
  border-radius: 20px;
  font-size: .68rem;
  font-weight: 700;
  display: inline-block;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: .02em;
}
.gp-ap { background: #052e16; color: #4ade80; border: 1px solid #166534; }
.gp-a  { background: #1a3a10; color: #86efac; border: 1px solid #15803d; }
.gp-b  { background: #1c1a00; color: #fde047; border: 1px solid #713f12; }
.gp-c  { background: #1c0e00; color: #fb923c; border: 1px solid #7c2d12; }
.gp-d  { background: #1c0000; color: #f87171; border: 1px solid #7f1d1d; }

/* ── BEST-PER-TARGET CARDS ───────────────────────────────────────────────── */
.pcard-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: .6rem;
  margin: .6rem 0;
}
.pcard {
  background: var(--surf);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: .85rem;
  font-size: .8rem;
  box-shadow: var(--shadow-xs);
  transition: border-color .2s, box-shadow .2s;
  position: relative;
  overflow: hidden;
}
.pcard::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
}
.pcard-hit::before    { background: linear-gradient(90deg, var(--hit), transparent); }
.pcard-single::before { background: linear-gradient(90deg, var(--single), transparent); }
.pcard-xb::before     { background: linear-gradient(90deg, var(--xb), transparent); }
.pcard-hr::before     { background: linear-gradient(90deg, var(--hr), transparent); }

.pcard:hover { box-shadow: var(--shadow-md); }
.pcard-hit:hover    { border-color: var(--hit); }
.pcard-single:hover { border-color: var(--single); }
.pcard-xb:hover     { border-color: var(--xb); }
.pcard-hr:hover     { border-color: var(--hr); }

.pcard-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: .55rem;
  padding-bottom: .45rem;
  border-bottom: 1px solid var(--border);
}
.pcard-name  { font-weight: 700; color: var(--text); font-size: .92rem; }
.pcard-team  { font-size: .64rem; color: var(--muted); margin-top: .1rem; }
.pcard-score {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1.15rem;
  font-weight: 700;
  line-height: 1;
}
.pcard-hit    .pcard-score { color: var(--hit); text-shadow: 0 0 12px var(--hit-glow); }
.pcard-single .pcard-score { color: var(--single); text-shadow: 0 0 12px var(--single-glow); }
.pcard-xb     .pcard-score { color: var(--xb); text-shadow: 0 0 12px var(--xb-glow); }
.pcard-hr     .pcard-score { color: var(--hr); text-shadow: 0 0 12px var(--hr-glow); }

.pcard-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: .2rem 0;
  border-bottom: 1px solid var(--border);
}
.pcard-row:last-child { border-bottom: none; }
.pcard-row .pk { font-size: .69rem; color: var(--muted); }
.pcard-row .pv {
  font-family: 'JetBrains Mono', monospace;
  font-size: .72rem;
  color: var(--text);
  font-weight: 600;
}

/* ── VALUE INDICATORS ────────────────────────────────────────────────────── */
.pos-val { color: var(--pos) !important; }
.neg-val { color: var(--neg) !important; }

/* ── NOTICE / ALERT BANNERS ──────────────────────────────────────────────── */
.notice {
  border-left: 3px solid;
  padding: .5rem .9rem;
  border-radius: 0 8px 8px 0;
  font-size: .78rem;
  margin: .45rem 0;
  line-height: 1.55;
}
.notice-park    { background: rgba(245,158,11,.07);  border-color: var(--xb);    color: #fde68a; }
.notice-pitcher { background: rgba(16,185,129,.07);  border-color: var(--hit);   color: #a7f3d0; }
.notice-info    { background: rgba(59,130,246,.07);  border-color: var(--accent); color: #bfdbfe; }
.notice-warn    { background: rgba(245,158,11,.07);  border-color: var(--warn);  color: #fde68a; }

/* ── DATA FRESHNESS BADGE ────────────────────────────────────────────────── */
.sbadge {
  display: inline-flex;
  align-items: center;
  gap: .3rem;
  padding: .3rem .75rem;
  border-radius: 20px;
  font-size: .72rem;
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
  box-shadow: var(--shadow-xs);
}
.sbadge-green {
  background: #052e16; color: #4ade80;
  border: 1px solid #166534;
  box-shadow: 0 0 8px rgba(74,222,128,.15);
}
.sbadge-yellow { background: #1c1400; color: #fbbf24; border: 1px solid #713f12; }
.sbadge-red    { background: #1c0000; color: #f87171; border: 1px solid #7f1d1d; }

/* Animated pulse dot for fresh data */
@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: .5; transform: scale(.75); }
}
.pulse-dot {
  display: inline-block;
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #4ade80;
  animation: pulse-dot 2s ease-in-out infinite;
  flex-shrink: 0;
}

/* ── SECTION HEADERS ─────────────────────────────────────────────────────── */
.section-head {
  font-size: .68rem;
  text-transform: uppercase;
  letter-spacing: .1em;
  color: var(--muted);
  margin: 1rem 0 .45rem;
  display: flex;
  align-items: center;
  gap: .5rem;
  font-weight: 600;
}
.section-head::after {
  content: '';
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, var(--border), transparent);
}

/* ── RESULT HEADER ───────────────────────────────────────────────────────── */
.result-head {
  display: flex;
  align-items: center;
  gap: .6rem;
  margin: .6rem 0 .35rem;
}
.result-head .rh-label {
  font-size: .9rem;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -.005em;
}
.result-head .rh-count {
  background: var(--surf2);
  border: 1px solid var(--border2);
  border-radius: 20px;
  padding: .15rem .6rem;
  font-family: 'JetBrains Mono', monospace;
  font-size: .72rem;
  color: var(--muted);
}

/* ── LEGEND ──────────────────────────────────────────────────────────────── */
.legend-compact {
  background: var(--surf);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: .65rem 1.1rem;
  font-size: .74rem;
  color: var(--muted);
  line-height: 1.75;
  margin: .5rem 0;
}
.legend-compact b  { color: var(--text2); }
.legend-compact .hit-c    { color: var(--hit); font-weight: 700; }
.legend-compact .xb-c     { color: var(--xb); font-weight: 700; }
.legend-compact .hr-c     { color: var(--hr); font-weight: 700; }
.legend-compact .sl-c     { color: var(--single); font-weight: 700; }

/* ── PITCHER TABLE ───────────────────────────────────────────────────────── */
.pt-wrap { overflow-x: auto; border-radius: 10px; border: 1px solid var(--border); box-shadow: var(--shadow-xs); }
.pt-table { width: 100%; border-collapse: collapse; font-size: .78rem; }
.pt-table th {
  background: var(--surf2);
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .06em;
  font-size: .64rem;
  font-weight: 700;
  padding: .5rem .75rem;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.pt-table td {
  padding: .42rem .75rem;
  border-bottom: 1px solid var(--border);
  color: var(--text);
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
  transition: background .1s;
}
.pt-table tr:last-child td { border-bottom: none; }
.pt-table tr:hover td { background: var(--surf2); }

/* ── PARLAY COMPONENTS ───────────────────────────────────────────────────── */
.parlay-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: .85rem;
  margin: .85rem 0;
}
.parlay-leg {
  background: var(--surf);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: .85rem;
  position: relative;
  box-shadow: var(--shadow-xs);
  transition: border-color .2s, box-shadow .2s;
}
.parlay-leg:hover {
  border-color: var(--border2);
  box-shadow: var(--shadow-sm);
}
.parlay-leg .leg-num {
  position: absolute;
  top: .55rem; right: .65rem;
  font-family: 'JetBrains Mono', monospace;
  font-size: .65rem;
  color: var(--dim);
}
.parlay-leg .leg-batter { font-weight: 700; color: var(--text); font-size: .92rem; }
.parlay-leg .leg-meta   { font-size: .69rem; color: var(--muted); margin-top: .15rem; }
.parlay-leg .leg-score  {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1.05rem;
  font-weight: 700;
  margin-top: .35rem;
}
.parlay-summary {
  background: var(--surf2);
  border: 1px solid var(--border2);
  border-radius: 12px;
  padding: 1rem 1.25rem;
  margin: .85rem 0;
  box-shadow: var(--shadow-sm);
}
.parlay-summary .ps-title {
  font-size: .68rem;
  text-transform: uppercase;
  letter-spacing: .09em;
  color: var(--muted);
  margin-bottom: .5rem;
  font-weight: 600;
}
.parlay-summary .ps-conf {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1.8rem;
  font-weight: 700;
  color: var(--accent);
  line-height: 1;
  text-shadow: 0 0 20px var(--accent-glow);
}
.parlay-summary .ps-sub { font-size: .74rem; color: var(--muted); margin-top: .25rem; }

/* ── REFERENCE SECTION ───────────────────────────────────────────────────── */
.ref-section {
  background: var(--surf);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 1.1rem 1.3rem;
  margin: .65rem 0;
  box-shadow: var(--shadow-xs);
}
.ref-section h3  { font-size: .92rem; font-weight: 700; color: var(--text); margin: 0 0 .55rem; }
.ref-section p,
.ref-section li  { font-size: .82rem; color: var(--text2); line-height: 1.75; }
.ref-section b   { color: var(--text); }
.ref-section .col-pill {
  display: inline-block;
  padding: 2px 9px;
  border-radius: 20px;
  font-family: 'JetBrains Mono', monospace;
  font-size: .68rem;
  font-weight: 600;
  margin: 1px 2px;
}
.pill-hit    { background: #052e16; color: #4ade80; }
.pill-single { background: #083344; color: #67e8f9; }
.pill-xb     { background: #1c1400; color: #fbbf24; }
.pill-hr     { background: #1c0000; color: #fca5a5; }
.pill-neutral{ background: #1e2d3d; color: #94a3b8; }

/* ── MOBILE RESPONSIVE ───────────────────────────────────────────────────── */
@media (max-width: 768px) {
  /* ── Layout ────────────────────────────────────────────────────────────── */
  .block-container { padding: .3rem .4rem 3rem !important; }

  /* ── Stat bar — horizontal scroll on small screens ────────────────────── */
  .stat-bar {
    flex-wrap: nowrap;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    gap: .3rem;
    padding: .4rem .5rem;
  }
  .stat-item    { min-width: 58px; padding: .25rem .4rem; flex-shrink: 0; }
  .stat-item .val { font-size: .95rem; }
  .stat-item .lbl { font-size: .56rem; }

  /* ── Score summary cards — 2-col grid ─────────────────────────────────── */
  .score-grid   { grid-template-columns: 1fr 1fr; gap: .35rem; }
  .scard        { padding: .65rem .7rem .5rem; min-height: 90px; }
  .scard .sc-name { font-size: .85rem; }
  .scard .sc-type { font-size: .58rem; }
  .scard .sc-score { font-size: .75rem; top: .5rem; right: .55rem; }

  /* ── Best per target cards — 2-col ────────────────────────────────────── */
  .pcard-grid   { grid-template-columns: 1fr 1fr; gap: .35rem; }
  .pcard        { padding: .7rem .75rem .55rem; }

  /* ── Parlay legs — 1-col ───────────────────────────────────────────────── */
  .parlay-grid  { grid-template-columns: 1fr; }

  /* ── Tables — horizontal scroll ───────────────────────────────────────── */
  [data-testid="stDataFrame"] > div {
    overflow-x: auto !important;
    -webkit-overflow-scrolling: touch;
  }

  /* ── App header ─────────────────────────────────────────────────────────── */
  .app-header h1 { font-size: 1.2rem !important; }
  .app-header .meta { font-size: .62rem; }

  /* ── Section headings ───────────────────────────────────────────────────── */
  .section-head { font-size: .7rem !important; }

  /* ── Pitcher table ──────────────────────────────────────────────────────── */
  .pt-table th, .pt-table td { padding: .3rem .4rem; font-size: .68rem; }

  /* ── Sidebar toggle — larger tap target ────────────────────────────────── */
  [data-testid="collapsedControl"] {
    width:  2.8rem !important;
    height: 2.8rem !important;
    top: 50% !important;
  }

  /* ── Buttons — full width on mobile ─────────────────────────────────────── */
  [data-testid="stButton"] button,
  [data-testid="stDownloadButton"] button {
    width: 100%;
    min-height: 44px;
    font-size: .8rem;
  }

  /* ── Selectboxes / sliders — touch-friendly ─────────────────────────────── */
  [data-testid="stSelectbox"] > div { min-height: 42px; }
  [data-testid="stSlider"] [data-baseweb="slider"] { padding: 0 .5rem; }

  /* ── Expanders ───────────────────────────────────────────────────────────── */
  [data-testid="stExpander"] summary { font-size: .8rem; padding: .6rem .8rem; }

  /* ── Metrics in 3-col layouts → wrap naturally ─────────────────────────── */
  [data-testid="stMetric"] { min-width: 90px; }
}

@media (max-width: 480px) {
  /* ── Phones in portrait — single column everything ─────────────────────── */
  .score-grid  { grid-template-columns: 1fr; }
  .pcard-grid  { grid-template-columns: 1fr; }
  .app-header .meta { display: none; }

  /* ── Stat bar pills — even more compact ─────────────────────────────────── */
  .stat-item { min-width: 50px; }
  .stat-item .val { font-size: .85rem; }

  /* ── Typography scale down ──────────────────────────────────────────────── */
  .block-container p, .block-container li { font-size: .82rem; }
  h1 { font-size: 1.1rem !important; }
  h2 { font-size: .95rem !important; }
  h3 { font-size: .85rem !important; }

  /* ── Sidebar: ensure it opens as overlay, not push ─────────────────────── */
  [data-testid="stSidebar"] {
    position: fixed !important;
    z-index: 999 !important;
    width: min(85vw, 320px) !important;
    height: 100vh !important;
    overflow-y: auto;
    box-shadow: 4px 0 24px rgba(0,0,0,.6) !important;
  }

  /* ── Make the reopen button more prominent on phone ────────────────────── */
  [data-testid="collapsedControl"] {
    width:  3rem !important;
    height: 3rem !important;
    border-radius: 0 12px 12px 0 !important;
  }

  /* ── Card body font size ────────────────────────────────────────────────── */
  .scard .sc-name { font-size: .82rem; }
  .pcard { padding: .6rem .65rem .5rem; }

  /* ── Download / action button row ──────────────────────────────────────── */
  [data-testid="column"] { padding: .15rem !important; }
}

/* ── Landscape phone / small tablet (568-768px) ─────────────────────────── */
@media (min-width: 568px) and (max-width: 768px) {
  .score-grid { grid-template-columns: repeat(3, 1fr); }
  .pcard-grid { grid-template-columns: repeat(2, 1fr); }
}

/* ── Touch device optimisations (applies regardless of screen size) ──────── */
@media (hover: none) and (pointer: coarse) {
  /* Increase tap targets for all interactive elements */
  [data-testid="stButton"] button,
  [data-testid="stDownloadButton"] button  { min-height: 44px; }
  [data-testid="stCheckbox"] label         { min-height: 40px; line-height: 40px; }
  [data-testid="stToggle"]   label         { min-height: 36px; }

  /* Remove hover transforms — they feel buggy on touch */
  .scard:hover, .pcard:hover { transform: none; }

  /* Larger sidebar toggle ─────────────────────────────────────────────────── */
  [data-testid="collapsedControl"] {
    width:  2.8rem !important;
    height: 2.8rem !important;
  }
}
</style>
""", unsafe_allow_html=True)
