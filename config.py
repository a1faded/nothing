"""
config.py — A1PICKS MLB Hit Predictor V7
"""

REPO     = "a1faded/a1picks-hits-bot"
REPO_RAW = f"https://raw.githubusercontent.com/{REPO}/main"
REPO_API = f"https://api.github.com/repos/{REPO}/commits"

CONFIG = {
    # ── Main data ──────────────────────────────────────────────────────────────
    'matchups_url':       f"{REPO_RAW}/Matchups.csv",
    'pitcher_hits_url':   f"{REPO_RAW}/pitcher_hits.csv",
    'pitcher_hrs_url':    f"{REPO_RAW}/pitcher_hrs.csv",
    'pitcher_walks_url':  f"{REPO_RAW}/pitcher_walks.csv",
    'pitcher_qs_url':     f"{REPO_RAW}/pitcher_quality_start.csv",
    'game_4hr_url':       f"{REPO_RAW}/game_4plusHR.csv",
    'game_20hits_url':    f"{REPO_RAW}/game_20plushits.csv",
    'game_20k_url':       f"{REPO_RAW}/game_20plusK.csv",
    'game_8walks_url':    f"{REPO_RAW}/game_8pluswalks.csv",
    'game_10runs_url':    f"{REPO_RAW}/game_10plusruns.csv",

    # ── Game conditions ───────────────────────────────────────────────────────
    'gc_hr4_anchor':       12.2,  'gc_hits20_anchor':   18.6,
    'gc_k20_anchor':       23.3,  'gc_walks8_anchor':   46.5,
    'gc_runs10_anchor':    28.4,  'gc_qs_anchor':       21.5,
    'gc_hit_max_range':    0.40,  'gc_hr_max_range':    0.35,
    'gc_reduced_strength': 0.30,  'gc_max_mult':        0.40,
    'gc_cap':              0.40,

    # ── Cache ─────────────────────────────────────────────────────────────────
    'cache_ttl': 900,

    # ── Historical tiebreaker ─────────────────────────────────────────────────
    'hist_min_pa': 10, 'hist_bonus_max': 3.0,

    # ── Pitcher multiplier ────────────────────────────────────────────────────
    'pitcher_hit_neutral': 2.8, 'pitcher_hr_neutral': 12.0,
    'pitcher_walk_neutral':18.0, 'pitcher_max_mult':   0.08,

    # ── League averages — BallPark Pal context ────────────────────────────────
    'league_k_avg': 22.8, 'league_bb_avg': 8.6,
    'league_hr_avg': 3.15,'league_avg':    0.2445,

    # ── League averages — Statcast ────────────────────────────────────────────
    'league_barrel_pct': 7.5,  'league_hh_pct':  38.0,
    'league_avgev':      88.5, 'league_maxev':  108.0,
    'league_xslg':       0.400,'league_xba':    0.248,
    'league_xwoba':      0.320,

    # ── Statcast overlay cap ──────────────────────────────────────────────────
    'sc_max_total_adj': 10.0,

    # ── Batting order position signal ─────────────────────────────────────────
    # Applied post-normalization. Only active when confirmed lineup is available.
    # Cleanup (3-5): +bonus HR/XB.  Table-setters (1-2): +bonus Hit/Single.
    'order_cleanup_bonus':  1.5,   # pts for positions 3-5 on HR/XB
    'order_leadoff_bonus':  1.0,   # pts for positions 1-2 on Hit/Single
    'order_max_adj':        2.0,   # total cap ±pts

    # ── Rolling 7-day form signal ─────────────────────────────────────────────
    # Applied post-normalization on Hit/Single. Cap small to avoid recency bias.
    'form_hot_threshold':  1.2,    # H/G above this = hot streak
    'form_cold_threshold': 0.5,    # H/G below this = cold streak
    'form_hot_bonus':      2.5,    # pts for hot streak
    'form_cold_penalty':  -2.5,    # pts for cold streak
    'form_max_adj':        2.5,    # cap ±pts

    # ── xBA luck signal (xBA - fg_AVG) ───────────────────────────────────────
    # Positive gap = underperforming contact quality = regression candidate.
    # Applied on Hit Score only.
    'luck_weight':  18.0,          # multiplier for (xBA - fg_AVG)
    'luck_max_adj':  2.0,          # cap ±pts

    # ── Pitcher handedness / platoon ──────────────────────────────────────────
    # Opposite-hand batter vs pitcher = natural platoon advantage.
    # Set use_platoon=False if BallPark Pal already models handedness splits.
    'use_platoon':        True,
    'platoon_bonus':      2.0,     # pts for opposite-hand advantage
    'platoon_penalty':   -1.5,     # pts for same-hand disadvantage
    'platoon_max_adj':    2.0,     # cap ±pts
}

# ── Park / team / score maps (unchanged) ─────────────────────────────────────
PARK_TO_TEAM = {
    'Fenway Park':'BOS','Camden Yards':'BAL','Oriole Park':'BAL',
    'Yankee Stadium':'NYY','Citi Field':'NYM','Rogers Centre':'TOR',
    'Tropicana Field':'TB','Guaranteed Rate Fld':'CWS',
    'Progressive Field':'CLE','Comerica Park':'DET','Kauffman Stadium':'KC',
    'Target Field':'MIN','Daikin Park':'HOU','Minute Maid Park':'HOU',
    'Angel Stadium':'LAA','Oakland Coliseum':'ATH','T-Mobile Park':'SEA',
    'Globe Life Field':'TEX','Truist Park':'ATL','LoanDepot Park':'MIA',
    'Marlins Park':'MIA','Citizens Bank Park':'PHI','Nationals Park':'WSH',
    'Wrigley Field':'CHC','Great American BP':'CIN','American Family Fld':'MIL',
    'PNC Park':'PIT','Busch Stadium':'STL','Chase Field':'ARI',
    'Coors Field':'COL','Dodger Stadium':'LAD','Petco Park':'SD','Oracle Park':'SF',
}
NICK_TO_ABBR = {
    'Red Sox':'BOS','Yankees':'NYY','Rays':'TB','Orioles':'BAL','Blue Jays':'TOR',
    'White Sox':'CWS','Guardians':'CLE','Tigers':'DET','Royals':'KC','Twins':'MIN',
    'Astros':'HOU','Angels':'LAA','Athletics':'ATH','Mariners':'SEA','Rangers':'TEX',
    'Braves':'ATL','Marlins':'MIA','Mets':'NYM','Phillies':'PHI','Nationals':'WSH',
    'Cubs':'CHC','Reds':'CIN','Brewers':'MIL','Pirates':'PIT','Cardinals':'STL',
    'Diamondbacks':'ARI','Rockies':'COL','Dodgers':'LAD','Padres':'SD','Giants':'SF',
}
SCORE_MAP = {
    '🎯 Hit':'Hit_Score','1️⃣ Single':'Single_Score',
    '🔥 XB (Double/Triple)':'XB_Score','💣 HR':'HR_Score',
}
LABEL_MAP = {v:k for k,v in SCORE_MAP.items()}
SCORE_CSS = {
    'Hit_Score':'var(--hit)','Single_Score':'var(--single)',
    'XB_Score':'var(--xb)','HR_Score':'var(--hr)',
}
