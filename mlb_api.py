"""
mlb_api.py — MLB Stats API + Player ID Bridge
===============================================
Uses the MLB-StatsAPI package (statsapi) as the primary source:
  - statsapi.schedule()          → today's games, probable pitchers
  - statsapi.boxscore_data()     → lineup confirmation (batting orders set?)
  - statsapi.lookup_player()     → MLBAM player IDs
  - statsapi.get('people', ...)  → per-player game log (hitting splits)

The MLBAM ID is the shared key between MLB Stats API and pybaseball/Statcast.
Once we have it: statcast_batter(start, end, mlbam_id) gives pitch-level data.

Fallback chain for player ID lookup:
  1. statsapi.lookup_player()   — fast, no scraping, always available
  2. pybaseball playerid_lookup — slower (hits Chadwick Bureau CSV)

All functions are @st.cache_data cached at appropriate TTLs.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd
from datetime import date, datetime
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# AVAILABILITY CHECK
# ─────────────────────────────────────────────────────────────────────────────

try:
    import statsapi
    _STATSAPI_OK = True
except ImportError:
    _STATSAPI_OK = False


def _statsapi_available() -> bool:
    return _STATSAPI_OK

# ─────────────────────────────────────────────────────────────────────────────
# TODAY'S SCHEDULE
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def get_today_schedule() -> list:
    """
    Fetch today's MLB schedule via statsapi.schedule().
    Returns list of game dicts from the statsapi package.

    Each dict includes:
      game_id, away_name, home_name, status,
      away_probable_pitcher, home_probable_pitcher,
      venue_name, game_datetime, game_date
    """
    if not _STATSAPI_OK:
        return []
    today = date.today().strftime('%m/%d/%Y')
    try:
        games = statsapi.schedule(date=today, sportId=1)
        return games if isinstance(games, list) else []
    except Exception:
        return []

# ─────────────────────────────────────────────────────────────────────────────
# LINEUP STATUS MAP
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def get_lineup_status_map() -> dict:
    """
    Returns {matchup_string → {status, away_sp, home_sp, confirmed, game_id}}.

    Lineup is confirmed when boxscore_data() shows ≥8 batters with a battingOrder
    set for BOTH teams — meaning the manager has submitted the lineup card.

    Used by:
      - renders.render_stat_bar()       (lineup badge)
      - sidebar.render_lineup_status_sidebar()
    """
    if not _STATSAPI_OK:
        return {}

    games   = get_today_schedule()
    result  = {}

    for g in games:
        game_id  = g.get('game_id')
        away     = g.get('away_name', '')
        home     = g.get('home_name', '')
        away_sp  = g.get('away_probable_pitcher') or 'TBD'
        home_sp  = g.get('home_probable_pitcher') or 'TBD'
        status   = g.get('status', 'Scheduled')
        matchup  = f"{away} @ {home}"
        confirmed = False

        # Only check boxscore for games that are close to/past start
        if game_id and status not in ('Postponed', 'Cancelled', 'Suspended'):
            try:
                bd = statsapi.boxscore_data(game_id)
                # battingOrder is a number like 100, 200, … 900 for positions 1-9
                away_set = [
                    b for b in bd.get('awayBatters', [])
                    if b.get('battingOrder') and str(b['battingOrder']).isdigit()
                    and int(b['battingOrder']) > 0
                ]
                home_set = [
                    b for b in bd.get('homeBatters', [])
                    if b.get('battingOrder') and str(b['battingOrder']).isdigit()
                    and int(b['battingOrder']) > 0
                ]
                confirmed = len(away_set) >= 8 and len(home_set) >= 8
            except Exception:
                pass

        icon = '✅' if confirmed else '⏳'
        result[matchup] = {
            'status':    f"{icon} {status}",
            'away_sp':   away_sp,
            'home_sp':   home_sp,
            'confirmed': confirmed,
            'game_id':   game_id,
        }

    return result

# ─────────────────────────────────────────────────────────────────────────────
# CONFIRMED LINEUP (batting order)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def get_confirmed_lineup(game_id: int) -> dict:
    """
    Returns {'away': [...], 'home': [...]} with batting order positions.
    Each entry: {'name': str, 'position': str, 'order': int (1-9)}

    Used by Player Profile and Predictor to flag lineup slot.
    """
    if not _STATSAPI_OK or not game_id:
        return {'away': [], 'home': []}

    try:
        bd = statsapi.boxscore_data(game_id)

        def _parse(side: str) -> list:
            batters = []
            for b in bd.get(f'{side}Batters', []):
                raw_order = b.get('battingOrder', '')
                if raw_order and str(raw_order).isdigit() and int(raw_order) > 0:
                    batters.append({
                        'name':     b.get('name', ''),
                        'position': b.get('position', ''),
                        'order':    int(raw_order) // 100,   # 100→1, 200→2 …
                    })
            return sorted(batters, key=lambda x: x['order'])

        return {'away': _parse('away'), 'home': _parse('home')}
    except Exception:
        return {'away': [], 'home': []}

# ─────────────────────────────────────────────────────────────────────────────
# PLAYER GAME LOG
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=600)
def get_player_game_log(player_id: int, last_n: int = 10) -> pd.DataFrame:
    """
    Fetch hitting game log for a player via the MLB Stats API people endpoint.

    Uses statsapi.get('people', ...) with a gameLog hydration rather than
    player_stat_data() because it gives us structured game-by-game splits
    with opponent info and we can control season + group.

    Returns DataFrame columns:
      Date | Opp | AB | H | 2B | 3B | HR | RBI | BB | K | AVG
    """
    if not _STATSAPI_OK or not player_id:
        return pd.DataFrame()

    year = date.today().year
    try:
        raw = statsapi.get('people', {
            'personIds': player_id,
            'hydrate':   f'stats(type=gameLog,season={year},group=hitting)',
        })

        people = raw.get('people', [])
        if not people:
            return pd.DataFrame()

        splits = []
        for stat_block in people[0].get('stats', []):
            if stat_block.get('type', {}).get('displayName') == 'gameLog':
                splits = stat_block.get('splits', [])
                break

        if not splits:
            return pd.DataFrame()

        rows = []
        for entry in reversed(splits):   # most recent first
            s    = entry.get('stat', {})
            game = entry.get('game', {})
            opp  = entry.get('opponent', {})
            rows.append({
                'Date': game.get('gameDate', '')[:10],
                'Opp':  opp.get('abbreviation', '?'),
                'AB':   _int(s.get('atBats',     0)),
                'H':    _int(s.get('hits',        0)),
                '2B':   _int(s.get('doubles',     0)),
                '3B':   _int(s.get('triples',     0)),
                'HR':   _int(s.get('homeRuns',    0)),
                'RBI':  _int(s.get('rbi',         0)),
                'BB':   _int(s.get('baseOnBalls', 0)),
                'K':    _int(s.get('strikeOuts',  0)),
                'AVG':  s.get('avg', '.000'),
            })
            if len(rows) >= last_n:
                break

        return pd.DataFrame(rows) if rows else pd.DataFrame()

    except Exception:
        return pd.DataFrame()


def _int(val) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0

# ─────────────────────────────────────────────────────────────────────────────
# PLAYER ID MAP  (name → MLBAM ID)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def build_player_id_map(batter_names: tuple) -> dict:
    """
    Build {batter_full_name → MLBAM_id} for the current slate.

    Primary:  statsapi.lookup_player()     — no scraping, instant
    Fallback: pybaseball.playerid_lookup() — scrapes Chadwick Bureau CSV

    The MLBAM ID is the bridge that lets us call:
      statcast_batter(start_dt, end_dt, player_id=mlbam_id)
    from savant.py for rolling pitch-level data.

    Args:
        batter_names: tuple of full player names (must be hashable for cache)
    Returns:
        dict[str, int]  e.g. {'Freddie Freeman': 518692, ...}
    """
    result: dict[str, int] = {}

    for name in batter_names:
        mlbam_id = _lookup_via_statsapi(name)
        if mlbam_id is None:
            mlbam_id = _lookup_via_pybaseball(name)
        if mlbam_id is not None:
            result[name] = mlbam_id

    return result


def _lookup_via_statsapi(full_name: str) -> Optional[int]:
    """
    Use statsapi.lookup_player(name) → player dict list.
    Returns player['id'] (MLBAM) for the best match.

    Preference order:
      1. Active player whose fullName exactly matches
      2. Any active player in results
      3. First result regardless of active status
    """
    if not _STATSAPI_OK:
        return None
    try:
        players = statsapi.lookup_player(full_name)
        if not players:
            return None

        name_lower = full_name.strip().lower()

        # Exact match on fullName, active
        for p in players:
            if p.get('active') and p.get('fullName', '').lower() == name_lower:
                return int(p['id'])

        # Any active
        active = [p for p in players if p.get('active')]
        if active:
            return int(active[0]['id'])

        # First result
        return int(players[0]['id'])

    except Exception:
        return None


def _lookup_via_pybaseball(full_name: str) -> Optional[int]:
    """
    Fallback: pybaseball.playerid_lookup(last, first) → Chadwick Bureau data.
    Returns key_mlbam (= MLBAM ID).
    """
    try:
        from pybaseball import playerid_lookup
        parts = full_name.strip().split()
        if len(parts) < 2:
            return None
        last, first = parts[-1], parts[0]
        df = playerid_lookup(last, first)
        if df is not None and not df.empty and 'key_mlbam' in df.columns:
            mlbam = df.iloc[0]['key_mlbam']
            if pd.notna(mlbam):
                return int(mlbam)
    except Exception:
        pass
    return None
