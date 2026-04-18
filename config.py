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

    # ── Under targets — disqualification cutoffs ──────────────────────────────
    # A player is DISQUALIFIED from an under target when their score in an
    # offsetting category is too high — meaning they can still accumulate
    # bases through a different route than the one being targeted.
    #
    # XB Under: looking for players unlikely to hit a double or triple.
    #   Disqualify if HR_Score > 55 (they can still clear the fence)
    #   Disqualify if Hit_Score > 68 (high general contact volume is dangerous)
    #
    # TB Under (total bases under 1.5 or 2.0):
    #   Disqualify if ANY of Hit/XB/HR_Score > 55 (any route produces bases)
    #
    # Hit Under (no hit, 0.5 line):
    #   Disqualify if Hit_Score > 42 (any meaningful hit probability is too risky)
    #
    # These are tunable — tighten them to be more selective, loosen for more candidates.
    'under_xb_disq_hr':    55.0,   # XB Under: disqualify if HR_Score above this
    'under_xb_disq_hit':   68.0,   # XB Under: disqualify if Hit_Score above this
    'under_tb_disq_any':   55.0,   # TB Under: disqualify if ANY score above this
    'under_hit_disq_hit':  42.0,   # Hit Under: disqualify if Hit_Score above this

    # Under scoring weights
    # Under_Score = weighted sum of (100 - offensive_score) + signal layers
    'under_k_weight':      0.6,    # K% bonus per point above league avg
    'under_pitcher_bonus': 4.0,    # pts for facing A+ pitcher
    'under_pitcher_a':     2.0,    # pts for facing A pitcher

    # BB% bonus weights per under type (walk = 0 bases = always favorable)
    'under_bb_weight_xb':   0.5,
    'under_bb_weight_tb15': 0.8,
    'under_bb_weight_tb05': 1.0,
    'under_bb_weight_hit':  1.2,

    # Historical matchup signal (BallPark Pal PA/AVG)
    'under_hist_weight':    18.0,  # pts per AVG unit below league avg
    'under_hist_min_pa':     5,    # min PA to apply — below this = neutral
    'under_hist_max_adj':    5.0,  # cap ±5 pts

    # Recent XB rate (7-day 2B+3B/G from pybaseball batch)
    'under_xb_rate_lg_avg':  0.25, # league avg ~1 XB per 4 games
    'under_xb_rate_weight':  8.0,
    'under_xb_rate_max_adj': 4.0,

    # Recent hit rate (7-day H/G) — cold hitters boost Hit Under
    'under_hit_rate_lg_avg': 0.90, # league avg ~0.9 H/G
    'under_hit_rate_weight': 4.0,  # lighter weight — form is noisy
    'under_hit_rate_max_adj':3.0,  # cap ±3 pts

    # Statcast signal weights (all gracefully neutral when NaN)
    # XB / power signals — used for XB Under and TB 1.5
    'under_barrel_weight':  1.2,   # Barrel% — strongest XB predictor
    'under_barrel_max':     6.0,   # cap ±6 pts
    'under_hh_weight':      0.8,   # HardHit% — hard contact = XBs
    'under_hh_max':         4.0,
    'under_avgev_weight':   0.15,  # AvgEV — velocity drives XBs
    'under_avgev_max':      3.0,
    'under_xslg_weight':   12.0,   # xSLG — overall power/XB tendency
    'under_xslg_max':       4.0,

    # Contact quality signals — used for Hit Under and TB 0.5
    'under_xba_weight':    15.0,   # xBA — contact quality → hit probability
    'under_xba_max':        5.0,
    'under_xwoba_weight':  12.0,   # xwOBA — overall offensive quality
    'under_xwoba_max':      4.0,

    # vs Grade signal — negative grade = pitcher dominates = under boost
    'under_vsgrade_weight': 0.3,   # pts per grade point below zero
    'under_vsgrade_max':    3.0,   # cap ±3 pts (grade ranges -10 to +10)

    # xb_boost park factor penalty for XB unders
    # High park factor for XBs = more opportunities even for weak XB hitters
    'under_parkxb_weight':  0.5,   # pts per xb_boost unit
    'under_parkxb_max':     2.0,   # cap —only a small modifier

    # ── Hot park extra boost (gc_hr4 > 2× median = 24.4%) ────────────────────
    # Applied as flat +pts to HR_Score_gc for ALL batters in that game.
    # Rewards entire lineups in genuinely HR-friendly park/game environments.
    # Evidence: multiple same-team HR clusters when gc_hr4 is very elevated.
    'hot_park_boost': 1.5,

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
