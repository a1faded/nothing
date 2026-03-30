"""
data/mlb_api.py — MLB Stats API Integration
=============================================
Phase 1: Supplementary data layer alongside BallPark Pal CSVs.
Provides: player season stats, game logs, pitch arsenal, lineup confirmations.

Uses the MLB Stats API (statsapi.mlb.com) via the mlb-statsapi Python package.
No auth required — public API.

Phase 2 (future): This file becomes the primary data source when
BallPark Pal API + SportsScreen API are integrated.
"""

import streamlit as st
import pandas as pd
from datetime import date

# ── Lazy import so app doesn't crash if package not installed yet ──────────────
try:
    import statsapi
    _STATSAPI_AVAILABLE = True
except ImportError:
    _STATSAPI_AVAILABLE = False


def _check_available():
    if not _STATSAPI_AVAILABLE:
        st.warning("⚠️ mlb-statsapi not installed. Run: pip install mlb-statsapi")
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# PLAYER LOOKUP
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def lookup_player_id(full_name: str) -> int | None:
    """Resolve a player's full name to their MLBAM player ID."""
    if not _check_available():
        return None
    try:
        parts = full_name.strip().split()
        if len(parts) < 2:
            return None
        last, first = parts[-1], parts[0]
        results = statsapi.lookup_player(full_name)
        if results:
            return results[0]['id']
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# SEASON STATS
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_player_season_stats(player_id: int, season: int = None) -> dict | None:
    """
    Returns a dict of season hitting stats for a given MLBAM player ID.
    Falls back to current season if season not specified.
    """
    if not _check_available():
        return None
    if season is None:
        season = date.today().year
    try:
        data = statsapi.player_stat_data(
            player_id,
            group='hitting',
            type='season',
            sportId=1
        )
        if data and 'stats' in data:
            for stat_group in data['stats']:
                if stat_group.get('group') == 'hitting':
                    splits = stat_group.get('splits', [])
                    if splits:
                        return splits[0].get('stat', {})
    except Exception as e:
        st.warning(f"⚠️ Could not fetch season stats for player {player_id}: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# GAME LOG (recent form)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800)
def get_player_game_log(player_id: int, last_n: int = 10, season: int = None) -> pd.DataFrame:
    """
    Returns a DataFrame of the player's last N games with hitting stats.
    Columns: date, opponent, AB, H, HR, RBI, BB, K, AVG
    """
    if not _check_available():
        return pd.DataFrame()
    if season is None:
        season = date.today().year
    try:
        data = statsapi.get('stats', {
            'personId':  player_id,
            'stats':     'gameLog',
            'group':     'hitting',
            'season':    season,
            'sportId':   1,
        })
        splits = (data.get('stats', [{}])[0]).get('splits', [])
        rows = []
        for s in splits[-last_n:]:
            st_data = s.get('stat', {})
            rows.append({
                'Date':     s.get('date', ''),
                'Opponent': s.get('opponent', {}).get('name', ''),
                'AB':       st_data.get('atBats', 0),
                'H':        st_data.get('hits', 0),
                'HR':       st_data.get('homeRuns', 0),
                'RBI':      st_data.get('rbi', 0),
                'BB':       st_data.get('baseOnBalls', 0),
                'K':        st_data.get('strikeOuts', 0),
                'AVG':      st_data.get('avg', '.000'),
            })
        return pd.DataFrame(rows)
    except Exception as e:
        st.warning(f"⚠️ Could not fetch game log for player {player_id}: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# TODAY'S SCHEDULE + LINEUP CONFIRMATIONS
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=600)
def get_todays_schedule() -> list:
    """
    Returns today's MLB schedule with probable pitchers and lineup status.
    Each item: { game_pk, away_team, home_team, game_time, status,
                 away_pitcher, home_pitcher, lineups_posted }
    """
    if not _check_available():
        return []
    try:
        today = date.today().strftime('%m/%d/%Y')
        sched = statsapi.schedule(
            date=today,
            sportId=1,
            hydrate='probablePitcher,lineups,linescore'
        )
        games = []
        for g in sched:
            games.append({
                'game_pk':        g.get('game_id'),
                'away_team':      g.get('away_name', ''),
                'home_team':      g.get('home_name', ''),
                'game_time':      g.get('game_datetime', ''),
                'status':         g.get('status', ''),
                'away_pitcher':   g.get('away_probable_pitcher', ''),
                'home_pitcher':   g.get('home_probable_pitcher', ''),
                'lineups_posted': bool(g.get('lineups')),
            })
        return games
    except Exception as e:
        st.warning(f"⚠️ Could not fetch today's schedule: {e}")
        return []


@st.cache_data(ttl=600)
def get_confirmed_lineup(game_pk: int) -> dict:
    """
    Returns confirmed batting orders for a specific game.
    { 'away': [player_names], 'home': [player_names] }
    Returns empty lists if lineups not yet posted.
    """
    if not _check_available():
        return {'away': [], 'home': []}
    try:
        data = statsapi.get('game', {'gamePk': game_pk, 'hydrate': 'lineups'})
        lineups = data.get('liveData', {}).get('lineups', {})
        def extract_names(side):
            return [p.get('fullName', '') for p in lineups.get(side, {}).get('battingOrder', [])]
        return {
            'away': extract_names('awayPlayers'),
            'home': extract_names('homePlayers'),
        }
    except Exception:
        return {'away': [], 'home': []}


# ─────────────────────────────────────────────────────────────────────────────
# LINEUP STATUS HELPER (for sidebar indicator)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=600)
def get_lineup_status_map() -> dict:
    """
    Returns a dict mapping game string → lineup status emoji.
    '✅ Confirmed' or '⏳ Pending'
    Used to display lineup confirmation status in the UI.
    """
    games = get_todays_schedule()
    status_map = {}
    for g in games:
        key = f"{g['away_team']} @ {g['home_team']}"
        status_map[key] = '✅ Confirmed' if g['lineups_posted'] else '⏳ Pending'
    return status_map
