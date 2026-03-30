"""
mlb_api.py — MLB Stats API Integration
========================================
Provides: lineup confirmations, player game logs, player ID lookup.
Uses the mlb-statsapi Python package (free, no auth required).
"""

import streamlit as st
import pandas as pd
from datetime import date

try:
    import statsapi
    _STATSAPI_AVAILABLE = True
except ImportError:
    _STATSAPI_AVAILABLE = False


def _api_ok() -> bool:
    return _STATSAPI_AVAILABLE


# ─────────────────────────────────────────────────────────────────────────────
# PLAYER ID LOOKUP
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400)
def lookup_player_id(full_name: str):
    if not _api_ok():
        return None
    try:
        results = statsapi.lookup_player(full_name)
        if results:
            return results[0]['id']
        last = full_name.strip().split()[-1]
        results = statsapi.lookup_player(last)
        if results:
            return results[0]['id']
    except Exception:
        pass
    return None


@st.cache_data(ttl=86400)
def build_player_id_map(batter_names: tuple) -> dict:
    """Batch-resolve batter names to MLBAM IDs. Cached 24h."""
    id_map = {}
    for name in batter_names:
        pid = lookup_player_id(name)
        if pid:
            id_map[name] = pid
    return id_map


# ─────────────────────────────────────────────────────────────────────────────
# GAME LOG
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800)
def get_player_game_log(player_id: int, last_n: int = 10) -> pd.DataFrame:
    """Last N games hitting log. Columns: Date, Opp, AB, H, 2B, HR, RBI, BB, K, AVG"""
    if not _api_ok():
        return pd.DataFrame()
    season = date.today().year
    try:
        data   = statsapi.get('stats', {
            'personId': player_id, 'stats': 'gameLog',
            'group': 'hitting', 'season': season, 'sportId': 1,
        })
        splits = (data.get('stats', [{}])[0]).get('splits', [])
        if not splits:
            return pd.DataFrame()
        rows = []
        for s in reversed(splits[-last_n:]):
            sd = s.get('stat', {})
            rows.append({
                'Date':  s.get('date', ''),
                'Opp':   s.get('opponent', {}).get('abbreviation', ''),
                'AB':    int(sd.get('atBats', 0)),
                'H':     int(sd.get('hits', 0)),
                '2B':    int(sd.get('doubles', 0)),
                'HR':    int(sd.get('homeRuns', 0)),
                'RBI':   int(sd.get('rbi', 0)),
                'BB':    int(sd.get('baseOnBalls', 0)),
                'K':     int(sd.get('strikeOuts', 0)),
                'AVG':   sd.get('avg', '.000'),
            })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# TODAY'S SCHEDULE + LINEUP STATUS
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def get_todays_schedule() -> list:
    """Returns today's games with lineup posted status and probable pitchers."""
    if not _api_ok():
        return []
    try:
        today = date.today().strftime('%m/%d/%Y')
        sched = statsapi.schedule(date=today, sportId=1,
                                  hydrate='probablePitcher,lineups')
        games = []
        for g in sched:
            games.append({
                'game_pk':        g.get('game_id'),
                'away_team':      g.get('away_name', ''),
                'home_team':      g.get('home_name', ''),
                'game_time':      g.get('game_datetime', ''),
                'status':         g.get('status', ''),
                'away_pitcher':   g.get('away_probable_pitcher', 'TBD'),
                'home_pitcher':   g.get('home_probable_pitcher', 'TBD'),
                'lineups_posted': bool(g.get('lineups')),
            })
        return games
    except Exception:
        return []


@st.cache_data(ttl=300)
def get_confirmed_batters() -> set:
    """Returns set of confirmed batter full names across all today's games."""
    if not _api_ok():
        return set()
    games   = get_todays_schedule()
    batters = set()
    for g in games:
        if not g['lineups_posted'] or not g['game_pk']:
            continue
        try:
            data    = statsapi.get('game', {'gamePk': g['game_pk'],
                                            'hydrate': 'lineups'})
            lineups = data.get('liveData', {}).get('lineups', {})
            for side in ('awayPlayers', 'homePlayers'):
                for p in lineups.get(side, {}).get('battingOrder', []):
                    name = p.get('fullName', '')
                    if name:
                        batters.add(name)
        except Exception:
            continue
    return batters


@st.cache_data(ttl=300)
def get_lineup_status_map() -> dict:
    """Returns { 'Away @ Home': {'status', 'away_sp', 'home_sp', 'game_time'} }"""
    games  = get_todays_schedule()
    result = {}
    for g in games:
        key = f"{g['away_team']} @ {g['home_team']}"
        result[key] = {
            'status':    '✅ Confirmed' if g['lineups_posted'] else '⏳ Pending',
            'away_sp':   g['away_pitcher'] or 'TBD',
            'home_sp':   g['home_pitcher'] or 'TBD',
            'game_time': g['game_time'],
        }
    return result
