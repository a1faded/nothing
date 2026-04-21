"""
mlb_api.py — MLB Stats API + Player ID Bridge V2

New functions:
  get_batting_order_map()      → {name: 1-9} for confirmed lineups today
  get_pitcher_handedness_map() → {last_name: 'L'/'R'} for today's starters
  get_recent_batting_form()    → {name: {hit_rate, hits, games}} last 7 days
"""

from __future__ import annotations
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from typing import Optional

try:
    import statsapi
    _STATSAPI_OK = True
except ImportError:
    _STATSAPI_OK = False


def _statsapi_available() -> bool:
    return _STATSAPI_OK


# ── SCHEDULE ──────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def get_today_schedule() -> list:
    if not _STATSAPI_OK:
        return []
    today = date.today().strftime('%m/%d/%Y')
    try:
        return statsapi.schedule(date=today, sportId=1) or []
    except Exception:
        return []


# ── LINEUP STATUS ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def get_lineup_status_map() -> dict:
    if not _STATSAPI_OK:
        return {}
    games, result = get_today_schedule(), {}
    for g in games:
        game_id   = g.get('game_id')
        matchup   = f"{g.get('away_name','')} @ {g.get('home_name','')}"
        away_sp   = g.get('away_probable_pitcher') or 'TBD'
        home_sp   = g.get('home_probable_pitcher') or 'TBD'
        status    = g.get('status','Scheduled')
        confirmed = False
        if game_id and status not in ('Postponed','Cancelled','Suspended'):
            try:
                bd        = statsapi.boxscore_data(game_id)
                def _count(side):
                    return sum(1 for b in bd.get(f'{side}Batters',[])
                               if b.get('battingOrder') and str(b['battingOrder']).isdigit()
                               and int(b['battingOrder']) > 0)
                confirmed = _count('away') >= 8 and _count('home') >= 8
            except Exception:
                pass
        icon = '✅' if confirmed else '⏳'
        result[matchup] = {'status':f"{icon} {status}",'away_sp':away_sp,
                           'home_sp':home_sp,'confirmed':confirmed,'game_id':game_id}
    return result


# ── CONFIRMED LINEUP ──────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def get_confirmed_game_abbrs() -> set:
    """
    Returns a set of (away_abbr, home_abbr) tuples for games where BOTH
    team lineups are confirmed (≥8 batters with battingOrder submitted).

    Uses get_lineup_status_map() which is known-working — the sidebar
    already shows confirmed ✅ from this function.

    Avoids player-name extraction entirely. Instead matches on team names:
      - lineup_status_map keys:  "Los Angeles Angels @ New York Yankees"
      - df['Game']:               "Angels @ Yankees"
      - NICK_TO_ABBR maps:        'Angels' → 'LAA', 'Yankees' → 'NYY'

    Since every team's nickname is a suffix of its full name (verified for
    all 30 teams), full_name.endswith(nick) is a reliable match.

    Used by the confirmed_only filter in app.py and get_slate_df() in sidebar.py.
    """
    from config import NICK_TO_ABBR

    status_map = get_lineup_status_map()
    if not status_map:
        return set()

    # Build full_team_name → abbr from today's schedule
    # e.g. "Los Angeles Angels" → "LAA"
    full_to_abbr: dict[str, str] = {}
    for matchup in status_map:
        parts = matchup.split(' @ ')
        if len(parts) != 2:
            continue
        for full_name in parts:
            full_name = full_name.strip()
            for nick, abbr in NICK_TO_ABBR.items():
                if full_name.endswith(nick):
                    full_to_abbr[full_name] = abbr
                    break

    # Build set of (away_abbr, home_abbr) for confirmed games
    confirmed: set = set()
    for matchup, info in status_map.items():
        if not info.get('confirmed'):
            continue
        parts = matchup.split(' @ ')
        if len(parts) != 2:
            continue
        away_abbr = full_to_abbr.get(parts[0].strip())
        home_abbr = full_to_abbr.get(parts[1].strip())
        if away_abbr and home_abbr:
            confirmed.add((away_abbr, home_abbr))

    return confirmed
    if not _STATSAPI_OK or not game_id:
        return {'away':[],'home':[]}
    try:
        bd = statsapi.boxscore_data(game_id)
        def _parse(side):
            out = []
            for b in bd.get(f'{side}Batters',[]):
                raw = b.get('battingOrder','')
                if raw and str(raw).isdigit() and int(raw) > 0:
                    out.append({'name':b.get('name',''),'position':b.get('position',''),
                                'order':int(raw)//100})
            return sorted(out, key=lambda x: x['order'])
        return {'away':_parse('away'),'home':_parse('home')}
    except Exception:
        return {'away':[],'home':[]}


# ── BATTING ORDER MAP (NEW) ───────────────────────────────────────────────────

@st.cache_data(ttl=300)
def get_batting_order_map() -> dict:
    """
    Returns batting order positions keyed by BOTH full name AND last name.

    Why both: BallPark Pal CSV uses last name only ('Judge', 'Freeman').
    MLB Stats API boxscore returns full names ('Aaron Judge', 'Freddie Freeman').

    For unambiguous last names (only one player with that last name confirmed today)
    we add a last-name key so the BallPark Pal lookup works.
    For ambiguous last names (e.g. two 'Garcia' in lineups today) we only keep
    the full-name key to avoid wrong assignments.

    Result used by:
      - engine._compute_order_adj()     (maps df['Batter'] = last name)
      - _merge_signal_metadata()         (same)
      - app confirmed_only filter        (isin check against df['Batter'])
    """
    if not _STATSAPI_OK:
        return {}

    games = get_today_schedule()
    full_dict: dict[str, int] = {}   # {full_name: order}

    for g in games:
        game_id = g.get('game_id')
        status  = g.get('status', 'Scheduled')
        if not game_id or status in ('Postponed', 'Cancelled', 'Suspended'):
            continue
        lineup = get_confirmed_lineup(game_id)
        for side in ('away', 'home'):
            for b in lineup[side]:
                name = b.get('name', '').strip()
                if name:
                    full_dict[name] = b['order']

    if not full_dict:
        return {}

    # Count how many confirmed players share each last name today
    last_name_count: dict[str, int] = {}
    for name in full_dict:
        last = name.split()[-1]
        last_name_count[last] = last_name_count.get(last, 0) + 1

    result: dict[str, int] = {}
    for name, pos in full_dict.items():
        result[name] = pos                           # always: full name key
        last = name.split()[-1]
        if last_name_count[last] == 1:
            result[last] = pos                       # unambiguous: last-name key too

    return result


# ── PITCHER HANDEDNESS (NEW) ──────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_pitcher_handedness_map() -> dict:
    """
    {pitcher_last_name: 'L' or 'R'} for today's probable starters.
    Used by engine for platoon advantage adjustment.

    NOTE: If BallPark Pal already models handedness in their simulations,
    set CONFIG['use_platoon'] = False to disable this overlay.
    """
    if not _STATSAPI_OK:
        return {}
    games, result, seen = get_today_schedule(), {}, set()
    for g in games:
        for key in ('away_probable_pitcher','home_probable_pitcher'):
            name = (g.get(key) or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            last = name.split()[-1]
            hand = _lookup_pitcher_hand(name)
            if hand:
                result[last] = hand
    return result


def _lookup_pitcher_hand(full_name: str) -> str | None:
    try:
        players = statsapi.lookup_player(full_name)
        if not players:
            return None
        for p in players:
            hand = (p.get('pitchHand') or {}).get('code')
            if hand in ('L','R') and p.get('active'):
                return hand
        for p in players:
            hand = (p.get('pitchHand') or {}).get('code')
            if hand in ('L','R'):
                return hand
    except Exception:
        pass
    return None


# ── ROLLING 7-DAY FORM (NEW) ──────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_recent_batting_form(days: int = 7) -> dict:
    """
    {batter_name: {hit_rate, hits, games, xb_rate, doubles, triples}} for last N days.

    Uses pybaseball.batting_stats_range() — one batch call covers all batters.
    hit_rate = H/G. xb_rate = (2B+3B)/G.

    xb_rate is used by compute_under_scores() to penalise XB/TB unders for
    players on a recent extra-base tear, and reward players who are hitting
    singles or going hitless.

    League avg xb_rate ~0.25 XB/G (roughly 1 XB every 4 games).
    Hot XB: >0.4/G  |  Cold XB: <0.1/G
    """
    try:
        from pybaseball import batting_stats_range
        end_dt   = date.today().strftime('%Y-%m-%d')
        start_dt = (date.today() - timedelta(days=days)).strftime('%Y-%m-%d')
        df = batting_stats_range(start_dt, end_dt)
        if df is None or df.empty:
            return {}
        df.columns = [c.strip() for c in df.columns]
        if not all(c in df.columns for c in ['Name','G','H']):
            return {}
        result = {}
        for _, row in df.iterrows():
            name = str(row.get('Name','')).strip()
            g    = int(row.get('G',  0) or 0)
            h    = int(row.get('H',  0) or 0)
            d    = int(row.get('2B', 0) or 0)
            t    = int(row.get('3B', 0) or 0)
            if name and g > 0:
                result[name] = {
                    'hit_rate': round(h / g, 3),
                    'hits':     h,
                    'games':    g,
                    'xb_rate':  round((d + t) / g, 3),
                    'doubles':  d,
                    'triples':  t,
                }
        return result
    except Exception:
        return {}


# ── PLAYER GAME LOG ───────────────────────────────────────────────────────────

@st.cache_data(ttl=600)
def get_player_game_log(player_id: int, last_n: int = 15) -> pd.DataFrame:
    """
    Game-by-game hitting log via MLB Stats API gameLog hydration.

    API structure (verified):
      split['date']              → 'YYYY-MM-DD' at top level of split
      split['game']['gamePk']    → game ID (no 'gameDate' key exists here)
      split['opponent']['name']  → full team name, no 'abbreviation' key
      split['stat']              → hitting stats dict

    Previous bugs:
      - entry.get('game',{}).get('gameDate') → key doesn't exist → empty date
      - entry.get('opponent',{}).get('abbreviation') → key doesn't exist → '?'
    """
    if not _STATSAPI_OK or not player_id:
        return pd.DataFrame()

    # Build team name → abbreviation lookup for opponent display
    from config import NICK_TO_ABBR
    # Reverse: last word of full name → abbr (e.g. "Angels" → "LAA")
    name_to_abbr = {nick: abbr for nick, abbr in NICK_TO_ABBR.items()}

    def _abbr_from_name(full_name: str) -> str:
        """Extract abbreviation from full team name using last word."""
        if not full_name:
            return '?'
        last_word = full_name.strip().split()[-1]
        # Handle "White Sox", "Red Sox", "Blue Jays" — check 2-word suffixes too
        words = full_name.strip().split()
        two_word = ' '.join(words[-2:]) if len(words) >= 2 else ''
        return (name_to_abbr.get(two_word)
                or name_to_abbr.get(last_word)
                or full_name[:3].upper())

    year = date.today().year
    try:
        raw = statsapi.get('people', {
            'personIds': player_id,
            'hydrate':   f'stats(type=gameLog,season={year},group=hitting)',
        })
        splits = []
        for sb in (raw.get('people') or [{}])[0].get('stats', []):
            if sb.get('type', {}).get('displayName') == 'gameLog':
                splits = sb.get('splits', [])
                break

        rows = []
        # reversed() → most recent first
        for entry in reversed(splits):
            s    = entry.get('stat', {})
            # date is a top-level key in the split, NOT inside 'game'
            date_str = entry.get('date', '')
            # opponent has 'name' not 'abbreviation'
            opp_name = entry.get('opponent', {}).get('name', '')
            opp_abbr = _abbr_from_name(opp_name)
            # isHome is a top-level boolean in the split
            is_home  = entry.get('isHome', None)
            ha       = 'Home' if is_home is True else 'Away' if is_home is False else '—'

            rows.append({
                'Date': date_str,
                'H/A':  ha,
                'Opp':  opp_abbr,
                'AB':   _i(s.get('atBats',    0)),
                'H':    _i(s.get('hits',       0)),
                '2B':   _i(s.get('doubles',    0)),
                '3B':   _i(s.get('triples',    0)),
                'HR':   _i(s.get('homeRuns',   0)),
                'RBI':  _i(s.get('rbi',        0)),
                'BB':   _i(s.get('baseOnBalls',0)),
                'K':    _i(s.get('strikeOuts', 0)),
                'AVG':  s.get('avg', '.000'),
            })
            if len(rows) >= last_n:
                break

        return pd.DataFrame(rows) if rows else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def _i(val) -> int:
    try:    return int(val)
    except: return 0


# ── PLAYER ID MAP ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def build_player_id_map(batter_names: tuple) -> dict:
    result: dict[str,int] = {}
    for name in batter_names:
        mlbam = _via_statsapi(name) or _via_pybaseball(name)
        if mlbam is not None:
            result[name] = mlbam
    return result


def _via_statsapi(full_name: str) -> Optional[int]:
    if not _STATSAPI_OK:
        return None
    try:
        players = statsapi.lookup_player(full_name)
        if not players:
            return None
        nl = full_name.strip().lower()
        for p in players:
            if p.get('active') and p.get('fullName','').lower() == nl:
                return int(p['id'])
        active = [p for p in players if p.get('active')]
        return int(active[0]['id']) if active else int(players[0]['id'])
    except Exception:
        return None


def _via_pybaseball(full_name: str) -> Optional[int]:
    try:
        from pybaseball import playerid_lookup
        parts = full_name.strip().split()
        if len(parts) < 2:
            return None
        df = playerid_lookup(parts[-1], parts[0])
        if df is not None and not df.empty and 'key_mlbam' in df.columns:
            v = df.iloc[0]['key_mlbam']
            if pd.notna(v):
                return int(v)
    except Exception:
        pass
    return None
