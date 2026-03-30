"""
ui/styles.py — Dark Precision Theme CSS
"""

import streamlit as st


def inject_css():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');
:root{
  --bg:#080c14;--surf:#0f1623;--surf2:#161e2e;--border:#1e2d3d;
  --text:#e2e8f0;--muted:#64748b;
  --hit:#10b981;--single:#06b6d4;--xb:#f59e0b;--hr:#ef4444;
  --accent:#3b82f6;--pos:#22c55e;--neg:#ef4444;
}
html,body,[class*="css"]{font-family:'Outfit',sans-serif !important;}
.block-container{padding:.75rem 1rem 2rem !important;max-width:1400px;}
[data-testid="stSidebar"]{background:var(--surf) !important;border-right:1px solid var(--border);}
[data-testid="stSidebar"] *{font-size:.85rem !important;}
h1,h2,h3,h4,h5{font-family:'Outfit',sans-serif !important;}
.stat-bar{display:flex;flex-wrap:wrap;gap:.4rem;background:var(--surf);
  border:1px solid var(--border);border-radius:10px;padding:.6rem 1rem;
  margin-bottom:.75rem;align-items:center;}
.stat-item{display:flex;flex-direction:column;align-items:center;
  padding:.3rem .75rem;border-right:1px solid var(--border);min-width:80px;}
.stat-item:last-child{border-right:none;}
.stat-item .val{font-family:'JetBrains Mono',monospace;font-size:1.15rem;
  font-weight:600;color:var(--text);line-height:1;}
.stat-item .lbl{font-size:.65rem;color:var(--muted);text-transform:uppercase;
  letter-spacing:.05em;margin-top:.2rem;}
.score-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:.5rem;margin:.5rem 0;}
@media(max-width:768px){
  .score-grid{grid-template-columns:repeat(2,1fr);}
  .pcard-grid{grid-template-columns:1fr 1fr;}
  .stat-item{min-width:60px;padding:.3rem .4rem;}
  .block-container{padding:.4rem .5rem 2rem !important;}
  .parlay-grid{grid-template-columns:1fr !important;}
}
.scard{background:var(--surf);border:1px solid var(--border);border-radius:10px;
  padding:.7rem .85rem;position:relative;overflow:hidden;transition:border-color .2s;}
.scard:hover{border-color:var(--accent);}
.scard::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;}
.scard-hit::before{background:var(--hit);}
.scard-single::before{background:var(--single);}
.scard-xb::before{background:var(--xb);}
.scard-hr::before{background:var(--hr);}
.scard .sc-type{font-size:.65rem;text-transform:uppercase;letter-spacing:.08em;
  color:var(--muted);margin-bottom:.25rem;}
.scard .sc-type span{font-weight:700;}
.scard-hit .sc-type span{color:var(--hit);}
.scard-single .sc-type span{color:var(--single);}
.scard-xb .sc-type span{color:var(--xb);}
.scard-hr .sc-type span{color:var(--hr);}
.scard .sc-name{font-size:1rem;font-weight:700;color:var(--text);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.scard .sc-meta{font-family:'JetBrains Mono',monospace;font-size:.7rem;
  color:var(--muted);margin-top:.2rem;}
.scard .sc-score{font-family:'JetBrains Mono',monospace;font-size:.8rem;
  font-weight:600;position:absolute;top:.6rem;right:.7rem;}
.scard-hit .sc-score{color:var(--hit);}
.scard-single .sc-score{color:var(--single);}
.scard-xb .sc-score{color:var(--xb);}
.scard-hr .sc-score{color:var(--hr);}
.pcard-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:.5rem;margin:.5rem 0;}
.pcard{background:var(--surf);border:1px solid var(--border);border-radius:10px;
  padding:.75rem;font-size:.8rem;}
.pcard-header{display:flex;justify-content:space-between;align-items:flex-start;
  margin-bottom:.5rem;padding-bottom:.4rem;border-bottom:1px solid var(--border);}
.pcard-name{font-weight:700;color:var(--text);font-size:.9rem;}
.pcard-team{font-size:.65rem;color:var(--muted);margin-top:.1rem;}
.pcard-score{font-family:'JetBrains Mono',monospace;font-size:1.1rem;font-weight:700;}
.pcard-hit .pcard-score{color:var(--hit);}
.pcard-single .pcard-score{color:var(--single);}
.pcard-xb .pcard-score{color:var(--xb);}
.pcard-hr .pcard-score{color:var(--hr);}
.pcard-row{display:flex;justify-content:space-between;padding:.18rem 0;
  border-bottom:1px solid var(--border);color:var(--muted);}
.pcard-row:last-child{border-bottom:none;}
.pcard-row .pk{font-size:.7rem;}
.pcard-row .pv{font-family:'JetBrains Mono',monospace;font-size:.72rem;
  color:var(--text);font-weight:600;}
.pos-val{color:var(--pos) !important;}
.neg-val{color:var(--neg) !important;}
.notice{border-left:3px solid;padding:.4rem .8rem;border-radius:0 6px 6px 0;
  font-size:.78rem;margin:.4rem 0;line-height:1.5;}
.notice-park{background:#1a1a2e;border-color:var(--xb);color:#fde68a;}
.notice-pitcher{background:#0d1a14;border-color:var(--hit);color:#a7f3d0;}
.notice-info{background:#0f1623;border-color:var(--accent);color:#bfdbfe;}
.notice-warn{background:#1c1400;border-color:var(--xb);color:#fde68a;}
.gp{padding:1px 7px;border-radius:20px;font-size:.7rem;font-weight:700;display:inline-block;}
.gp-ap{background:#1a9641;color:white;}
.gp-a{background:#a6d96a;color:#111;}
.gp-b{background:#fef08a;color:#111;}
.gp-c{background:#fdae61;color:#111;}
.gp-d{background:#ef4444;color:white;}
.legend-compact{background:var(--surf);border:1px solid var(--border);border-radius:8px;
  padding:.6rem 1rem;font-size:.76rem;color:var(--muted);line-height:1.7;margin:.5rem 0;}
.legend-compact b{color:var(--text);}
.legend-compact .hit-c{color:var(--hit);}
.legend-compact .xb-c{color:var(--xb);}
.legend-compact .hr-c{color:var(--hr);}
.legend-compact .sl-c{color:var(--single);}
.sbadge{display:inline-flex;align-items:center;gap:.3rem;padding:.25rem .65rem;
  border-radius:20px;font-size:.73rem;font-weight:600;font-family:'JetBrains Mono',monospace;}
.sbadge-green{background:#052e16;color:#4ade80;border:1px solid #166534;}
.sbadge-yellow{background:#1c1400;color:#fbbf24;border:1px solid #713f12;}
.sbadge-red{background:#1c0000;color:#f87171;border:1px solid #7f1d1d;}
.app-header{display:flex;align-items:center;gap:1rem;padding:.4rem 0 .6rem;
  border-bottom:1px solid var(--border);margin-bottom:.75rem;flex-wrap:wrap;}
.app-header .title-wrap h1{font-size:1.15rem !important;font-weight:700;
  color:var(--text);margin:0 !important;line-height:1.2;}
.app-header .title-wrap p{font-size:.68rem;color:var(--muted);margin:.1rem 0 0;}
.app-header .meta{margin-left:auto;display:flex;align-items:center;gap:.5rem;}
.section-head{font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;
  color:var(--muted);margin:.9rem 0 .4rem;display:flex;align-items:center;gap:.4rem;}
.section-head::after{content:'';flex:1;height:1px;background:var(--border);}
.result-head{display:flex;align-items:center;gap:.5rem;margin:.5rem 0 .3rem;}
.result-head .rh-label{font-size:.85rem;font-weight:600;color:var(--text);}
.result-head .rh-count{background:var(--surf2);border:1px solid var(--border);
  border-radius:20px;padding:.1rem .55rem;font-family:'JetBrains Mono',monospace;
  font-size:.72rem;color:var(--muted);}
[data-testid="stDataFrame"] th{font-size:.72rem !important;
  font-family:'Outfit',sans-serif !important;text-transform:uppercase;letter-spacing:.04em;}
[data-testid="stDataFrame"] td{font-family:'JetBrains Mono',monospace !important;
  font-size:.78rem !important;}
.pt-wrap{overflow-x:auto;}
.pt-table{width:100%;border-collapse:collapse;font-size:.78rem;}
.pt-table th{background:var(--surf2);color:var(--muted);text-transform:uppercase;
  letter-spacing:.05em;font-size:.65rem;padding:.45rem .7rem;
  border-bottom:1px solid var(--border);white-space:nowrap;}
.pt-table td{padding:.4rem .7rem;border-bottom:1px solid var(--border);color:var(--text);
  font-family:'JetBrains Mono',monospace;white-space:nowrap;}
.pt-table tr:last-child td{border-bottom:none;}
.pt-table tr:hover td{background:var(--surf2);}
.parlay-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:.75rem;margin:.75rem 0;}
.parlay-leg{background:var(--surf);border:1px solid var(--border);border-radius:10px;
  padding:.75rem;position:relative;}
.parlay-leg .leg-num{position:absolute;top:.5rem;right:.6rem;font-family:'JetBrains Mono',monospace;
  font-size:.65rem;color:var(--muted);}
.parlay-leg .leg-batter{font-weight:700;color:var(--text);font-size:.9rem;}
.parlay-leg .leg-meta{font-size:.7rem;color:var(--muted);margin-top:.15rem;}
.parlay-leg .leg-score{font-family:'JetBrains Mono',monospace;font-size:1.05rem;
  font-weight:700;margin-top:.3rem;}
.parlay-summary{background:var(--surf2);border:1px solid var(--border);border-radius:10px;
  padding:.9rem 1.1rem;margin:.75rem 0;}
.parlay-summary .ps-title{font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;
  color:var(--muted);margin-bottom:.5rem;}
.parlay-summary .ps-conf{font-family:'JetBrains Mono',monospace;font-size:1.6rem;
  font-weight:700;color:var(--accent);}
.parlay-summary .ps-sub{font-size:.72rem;color:var(--muted);margin-top:.2rem;}
.ref-section{background:var(--surf);border:1px solid var(--border);border-radius:10px;
  padding:1rem 1.2rem;margin:.6rem 0;}
.ref-section h3{font-size:.9rem;font-weight:700;color:var(--text);margin:0 0 .5rem;}
.ref-section p,.ref-section li{font-size:.82rem;color:var(--muted);line-height:1.7;}
.ref-section b{color:var(--text);}
.ref-section .col-pill{display:inline-block;padding:1px 8px;border-radius:20px;
  font-family:'JetBrains Mono',monospace;font-size:.7rem;font-weight:600;
  margin:1px 2px;}
.pill-hit{background:#052e16;color:#4ade80;}
.pill-single{background:#083344;color:#67e8f9;}
.pill-xb{background:#1c1400;color:#fbbf24;}
.pill-hr{background:#1c0000;color:#fca5a5;}
.pill-neutral{background:#1e2d3d;color:#94a3b8;}
</style>
""", unsafe_allow_html=True)
