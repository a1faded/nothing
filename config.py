"""
config.py — A1PICKS MLB Hit Predictor
======================================
All constants, CONFIG dict, and team/park mappings live here.
Swap values here only — nothing else needs to change.

FIX: REPO_RAW now uses canonical raw.githubusercontent.com domain
     (previous github.com/…/raw/main relied on a redirect).
"""

REPO     = "a1faded/a1picks-hits-bot"
REPO_RAW = f"https://raw.githubusercontent.com/{REPO}/main"   # ← FIXED
REPO_API = f"https://api.github.com/repos/{REPO}/commits"

CONFIG = {
    # ── Main data ──────────────────────────────────────────────────────────────
    'matchups_url':       f"{REPO_RAW}/Matchups.csv",

    # ── Pitcher CSVs ──────────────────────────────────────────────────────────
    'pitcher_hits_url':   f"{REPO_RAW}/pitcher_hits.csv",
    'pitcher_hrs_url':    f"{REPO_RAW}/pitcher_hrs.csv",
    'pitcher_walks_url':  f"{REPO_RAW}/pitcher_walks.csv",

    # ── Game & pitcher context CSVs ───────────────────────────────────────────
    'pitcher_qs_url':     f"{REPO_RAW}/pitcher_quality_start.csv",
    'game_4hr_url':       f"{REPO_RAW}/game_4plusHR.csv",
    'game_20hits_url':    f"{REPO_RAW}/game_20plushits.csv",
    'game_20k_url':       f"{REPO_RAW}/game_20plusK.csv",
    'game_8walks_url':    f"{REPO_RAW}/game_8pluswalks.csv",
    'game_10runs_url':    f"{REPO_RAW}/game_10plusruns.csv",

    # ── Game conditions multiplier anchors (median across all games) ──────────
    'gc_hr4_anchor':      12.2,
    'gc_hits20_anchor':   18.6,
    'gc_k20_anchor':      23.3,
    'gc_walks8_anchor':   46.5,
    'gc_runs10_anchor':   28.4,
    'gc_qs_anchor':       21.5,

    # ── Game conditions architecture ─────────────────────────────────────────
    'gc_hit_max_range':   0.40,
    'gc_hr_max_range':    0.35,
    'gc_reduced_strength':0.30,
    'gc_max_mult':        0.40,
    'gc_cap':             0.40,

    # ── Cache ─────────────────────────────────────────────────────────────────
    'cache_ttl':          900,

    # ── Historical tiebreaker ─────────────────────────────────────────────────
    'hist_min_pa':        10,
    'hist_bonus_max':     3.0,

    # ── Pitcher multiplier anchors ────────────────────────────────────────────
    'pitcher_hit_neutral':  2.8,
    'pitcher_hr_neutral':  12.0,
    'pitcher_walk_neutral':18.0,
    'pitcher_max_mult':    0.05,

    # ── League averages (4-year stable) ──────────────────────────────────────
    'league_k_avg':   22.8,
    'league_bb_avg':   8.6,
    'league_hr_avg':   3.15,
    'league_avg':      0.2445,
}

# ── Park name → home team abbreviation (all 30 MLB parks) ─────────────────────
PARK_TO_TEAM = {
    # AL East
    'Fenway Park':         'BOS', 'Camden Yards':       'BAL',
    'Oriole Park':         'BAL', 'Yankee Stadium':     'NYY',
    'Citi Field':          'NYM', 'Rogers Centre':      'TOR',
    'Tropicana Field':     'TB',
    # AL Central
    'Guaranteed Rate Fld': 'CWS', 'Progressive Field':  'CLE',
    'Comerica Park':       'DET', 'Kauffman Stadium':   'KC',
    'Target Field':        'MIN',
    # AL West
    'Daikin Park':         'HOU', 'Minute Maid Park':   'HOU',
    'Angel Stadium':       'LAA', 'Oakland Coliseum':   'ATH',
    'T-Mobile Park':       'SEA', 'Globe Life Field':   'TEX',
    # NL East
    'Truist Park':         'ATL', 'LoanDepot Park':     'MIA',
    'Marlins Park':        'MIA', 'Citizens Bank Park': 'PHI',
    'Nationals Park':      'WSH',
    # NL Central
    'Wrigley Field':       'CHC', 'Great American BP':  'CIN',
    'American Family Fld': 'MIL', 'PNC Park':          'PIT',
    'Busch Stadium':       'STL',
    # NL West
    'Chase Field':         'ARI', 'Coors Field':        'COL',
    'Dodger Stadium':      'LAD', 'Petco Park':         'SD',
    'Oracle Park':         'SF',
}

# ── Team nickname (as it appears in Matchups 'Game' column) → abbreviation ────
NICK_TO_ABBR = {
    'Red Sox':      'BOS', 'Yankees':      'NYY', 'Rays':         'TB',
    'Orioles':      'BAL', 'Blue Jays':    'TOR', 'White Sox':    'CWS',
    'Guardians':    'CLE', 'Tigers':       'DET', 'Royals':       'KC',
    'Twins':        'MIN', 'Astros':       'HOU', 'Angels':       'LAA',
    'Athletics':    'ATH', 'Mariners':     'SEA', 'Rangers':      'TEX',
    'Braves':       'ATL', 'Marlins':      'MIA', 'Mets':         'NYM',
    'Phillies':     'PHI', 'Nationals':    'WSH', 'Cubs':         'CHC',
    'Reds':         'CIN', 'Brewers':      'MIL', 'Pirates':      'PIT',
    'Cardinals':    'STL', 'Diamondbacks': 'ARI', 'Rockies':      'COL',
    'Dodgers':      'LAD', 'Padres':       'SD',  'Giants':       'SF',
}

# ── Score / label maps (shared across UI modules) ─────────────────────────────
SCORE_MAP = {
    '🎯 Hit':                'Hit_Score',
    '1️⃣ Single':             'Single_Score',
    '🔥 XB (Double/Triple)': 'XB_Score',
    '💣 HR':                 'HR_Score',
}

LABEL_MAP  = {v: k for k, v in SCORE_MAP.items()}

SCORE_CSS = {
    'Hit_Score':    'var(--hit)',
    'Single_Score': 'var(--single)',
    'XB_Score':     'var(--xb)',
    'HR_Score':     'var(--hr)',
}
