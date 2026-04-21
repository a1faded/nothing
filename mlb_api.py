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
import numpy as np
import logging
from datetime import date, timedelta
from typing import Optional

try:
    import statsapi
    _STATSAPI_OK = True
except ImportError:
    _STATSAPI_OK = False

LOGGER = logging.getLogger(__name__)


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


@st.cache_data(ttl=300)
def get_confirmed_lineup(game_id) -> dict:
    if not _STATSAPI_OK or not game_id:
        return {'away': [], 'home': []}
    try:
        bd = statsapi.boxscore_data(game_id)

        def _parse(side):
            out = []
            for b in bd.get(f'{side}Batters', []):
                raw = b.get('battingOrder', '')
                if raw and str(raw).isdigit() and int(raw) > 0:
                    out.append({
                        'name': b.get('name', ''),
                        'position': b.get('position', ''),
                        'order': int(raw) // 100,
                    })
            return sorted(out, key=lambda x: x['order'])

        return {'away': _parse('away'), 'home': _parse('home')}
    except Exception:
        return {'away': [], 'home': []}


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
    Returns a handedness map keyed by full pitcher name, plus unique short-name aliases.
    """
    if not _STATSAPI_OK:
        return {}
    games = get_today_schedule()
    full_map, alias_counts = {}, {}
    for g in games:
        for key in ('away_probable_pitcher','home_probable_pitcher'):
            name = (g.get(key) or '').strip()
            if not name or name in full_map:
                continue
            hand = _lookup_pitcher_hand(name)
            if hand:
                full_map[name] = hand
                alias = name.split()[-1]
                alias_counts[alias] = alias_counts.get(alias, 0) + 1
                if len(name.split()) >= 2 and name.split()[-1].endswith('.'):
                    alias2 = ' '.join(name.split()[-2:])
                    alias_counts[alias2] = alias_counts.get(alias2, 0) + 1
    result = dict(full_map)
    for name, hand in full_map.items():
        alias = name.split()[-1]
        if alias_counts.get(alias) == 1:
            result[alias] = hand
        if len(name.split()) >= 2 and name.split()[-1].endswith('.'):
            alias2 = ' '.join(name.split()[-2:])
            if alias_counts.get(alias2) == 1:
                result[alias2] = hand
    return result


@st.cache_data(ttl=3600)
def get_pitcher_id_map() -> dict:
    """
    {batter_name: pitcher_mlbam_id} — maps each batter to today's opposing starter.

    Built by cross-referencing today's schedule (away/home probable pitcher)
    with confirmed lineups to know which team's batters face which starter.
    Used by tank_stats.py to make targeted BvP and splits API calls.

    Returns {} when MLB Stats API unavailable or no schedule found.
    """
    if not _STATSAPI_OK:
        return {}
    try:
        games  = get_today_schedule()
        result = {}
        for g in games:
            away_sp_name = (g.get('away_probable_pitcher') or '').strip()
            home_sp_name = (g.get('home_probable_pitcher') or '').strip()
            game_id = g.get('game_id')
            if not game_id:
                continue

            # Resolve pitcher names to MLBAM IDs
            away_sp_id = _lookup_player_mlbam(away_sp_name) if away_sp_name else None
            home_sp_id = _lookup_player_mlbam(home_sp_name) if home_sp_name else None

            # Get confirmed lineup for this game
            lineup = get_confirmed_lineup(game_id)

            # Away batters face the HOME starter
            if home_sp_id:
                for b in lineup.get('away', []):
                    name = b.get('name', '').strip()
                    if name:
                        result[name] = home_sp_id
                        last = name.split()[-1]
                        result[last] = home_sp_id   # also map last name

            # Home batters face the AWAY starter
            if away_sp_id:
                for b in lineup.get('home', []):
                    name = b.get('name', '').strip()
                    if name:
                        result[name] = away_sp_id
                        last = name.split()[-1]
                        result[last] = away_sp_id

        return result
    except Exception:
        return {}


def _lookup_player_mlbam(full_name: str) -> int | None:
    """
    Resolve a player's full name to their MLBAM ID.

    Primary: Tank01 player list (tank_player_list.json) — covers all 2,603 MLB
    players including pitchers, loaded once at module level, zero API cost.
    Fallback: statsapi.lookup_player() for players not in the local list
    (e.g. mid-season call-ups added after the list was cached).
    """
    if not full_name:
        return None
    # Primary: local Tank01 player list
    pid = _TANK_PLAYER_MAP.get(full_name.lower())
    if pid:
        return pid
    # Try last-name-only for edge cases like "Framber Valdez" vs "Valdez"
    last = full_name.split()[-1].lower()
    pid  = _TANK_PLAYER_MAP_LAST.get(last)
    if pid:
        return pid
    # Fallback: statsapi call (slower, for recent call-ups)
    try:
        players = statsapi.lookup_player(full_name)
        if not players:
            return None
        for p in players:
            if p.get('active') and p.get('id'):
                return int(p['id'])
        for p in players:
            if p.get('id'):
                return int(p['id'])
    except Exception:
        pass
    return None


# ── Tank01 player list lookup (module-level, loaded once) ─────────────────────
# Covers all 2,603 MLB players + pitchers. Zero API cost per lookup.
# Falls back to statsapi only for call-ups not yet in the list.
_TANK_PLAYER_MAP: dict[str, int] = {}
_TANK_PLAYER_MAP_LAST_UNIQUE: dict[str, int] = {}

def _load_tank_player_list():
    """Load tank_player_list.json into module-level dicts for fast name→ID lookup."""
    global _TANK_PLAYER_MAP, _TANK_PLAYER_MAP_LAST_UNIQUE
    import json, os
    path = os.path.join(os.path.dirname(__file__), "tank_player_list.json")
    if not os.path.exists(path):
        return
    try:
        data    = json.load(open(path))
        players = data.get("body", [])
        full_map: dict[str, int] = {}
        last_buckets: dict[str, list[int]] = {}
        for p in players:
            name = (p.get("longName") or "").strip()
            pid  = p.get("playerID")
            if not name or not pid:
                continue
            try:
                pid_int = int(pid)
            except (ValueError, TypeError):
                continue
            full_map[name.lower()] = pid_int
            last = name.split()[-1].lower()
            last_buckets.setdefault(last, []).append(pid_int)
        _TANK_PLAYER_MAP = full_map
        _TANK_PLAYER_MAP_LAST_UNIQUE = {k:v[0] for k,v in last_buckets.items() if len(set(v)) == 1}
    except Exception:
        pass

# Load immediately on module import — fast, local file read
_load_tank_player_list()


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


@st.cache_data(ttl=86400)
def _lookup_pitcher_hand_by_id(mlbam_id: int) -> str | None:
    """
    Resolve pitcher throwing hand by MLBAM ID — more reliable than name lookup
    because IDs are unambiguous. Cached 24h.

    Used as primary pitcher hand resolution in enrich_with_splits when
    _pitcher_hand wasn't set by the handedness map (e.g. pitcher wasn't
    listed as a probable starter yet in the schedule API).
    """
    try:
        data = statsapi.get_person(mlbam_id)
        hand = (data.get('pitchHand') or {}).get('code')
        if hand in ('L', 'R'):
            return hand
        # Fallback: player_stat_data sometimes has this in bio
        bio = statsapi.player_stat_data(mlbam_id, type='pitching', stats=['career'])
        ph  = bio.get('pitchHand')
        if isinstance(ph, dict):
            hand = ph.get('code')
            if hand in ('L', 'R'):
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


@st.cache_data(ttl=3600)
def get_recent_pitcher_form(days: int = 7) -> dict:
    """
    {pitcher_name: {era, whip, k_per9, bb_per9, games, ip}} for the last N days.

    Uses pybaseball.pitching_stats_range() — one batch call covers all starters.
    Same infrastructure as get_recent_batting_form() — zero extra API calls.

    ERA and WHIP are the most direct under signals:
    - Low ERA  = pitcher has been dominant recently → good for all unders
    - Low WHIP = pitcher suppresses baserunners → good for hit/TB/HRR unders
    - High K/9 = high strikeout rate → good for K-heavy under targets
    - High BB/9 = walks freely → mixed signal (walks good for under, but high
                  counts mean the pitcher is wild and may lose the zone)

    Used in:
      - unders.py Layer 3+ — enhances pitcher grade with recent form
      - engine.py Stage 5 — adjusts HRR_Score for hot/cold starters

    Missing pitchers → 0.0 adjustment (neutral — no penalty for missing data).
    """
    try:
        from pybaseball import pitching_stats_range
        end_dt   = date.today().strftime('%Y-%m-%d')
        start_dt = (date.today() - timedelta(days=days)).strftime('%Y-%m-%d')
        df = pitching_stats_range(start_dt, end_dt)
        if df is None or df.empty:
            return {}
        df.columns = [c.strip() for c in df.columns]
        # Need at minimum: Name, ERA, WHIP, G, IP
        needed = ['Name','ERA','WHIP','G']
        if not all(c in df.columns for c in needed):
            return {}
        result = {}
        for _, row in df.iterrows():
            name = str(row.get('Name', '')).strip()
            g    = int(row.get('G',  0) or 0)
            ip   = float(row.get('IP', 0) or 0)
            if not name or g == 0:
                continue
            era  = float(row.get('ERA',  99.0) or 99.0)
            whip = float(row.get('WHIP',  3.0) or  3.0)
            # K/9 and BB/9 when available
            so   = float(row.get('SO',  0) or 0)
            bb   = float(row.get('BB',  0) or 0)
            k9   = round((so / ip) * 9, 2) if ip > 0 else 0.0
            bb9  = round((bb / ip) * 9, 2) if ip > 0 else 0.0
            result[name] = {
                'era':    round(era,  2),
                'whip':   round(whip, 2),
                'k_per9': k9,
                'bb_per9':bb9,
                'games':  g,
                'ip':     round(ip, 1),
            }
        return result
    except Exception:
        return {}


@st.cache_data(ttl=21600)
def get_pitcher_rest_map() -> dict:
    """
    {pitcher_name: {days_rest, last_ip, rest_signal}} for today's starters.

    Fetches last start data for each probable starter via MLB Stats API game log.
    Computes days of rest and workload from last outing.

    rest_signal values:
      +3.0  = 5+ days rest AND pitched deep last time (fresh, conditioned)
      +2.0  = 5+ days rest (well rested)
       0.0  = 4 days rest (standard rotation)
      -1.5  = 3 days rest (short rest, fatigue risk)
      -2.5  = ≤2 days rest (very short, significant risk)
      Workload modifier: +1.0 if last_ip ≥ 7.0 (went deep = well-warmed arm)
                         -1.0 if last_ip ≤ 3.0 (short outing = unknown state)

    Cached 6 hours — starters don't change once announced.
    Falls back gracefully: missing pitcher → no signal → 0.0 in scoring.
    """
    if not _STATSAPI_OK:
        return {}
    try:
        today  = date.today()
        games  = get_today_schedule()
        result: dict[str, dict] = {}
        seen:   set[str]        = set()

        for g in games:
            for key in ('away_probable_pitcher', 'home_probable_pitcher'):
                name = (g.get(key) or '').strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                last = name.split()[-1]

                player_id = _lookup_player_mlbam(name)
                if not player_id:
                    continue

                try:
                    data = statsapi.player_stat_data(
                        player_id,
                        type='pitching',
                        stats=['gameLog'],
                        group='pitching',
                    )
                    log = (data.get('stats', [{}])[0].get('splits', []))
                    if not log:
                        continue

                    # Sort descending — most recent first, skip today
                    log_sorted = sorted(log,
                                        key=lambda s: s.get('date', ''),
                                        reverse=True)
                    last_start = None
                    for entry in log_sorted:
                        try:
                            d = date.fromisoformat(entry.get('date', '')[:10])
                        except ValueError:
                            continue
                        if d < today:
                            last_start = entry
                            break

                    if not last_start:
                        continue

                    last_date = date.fromisoformat(last_start['date'][:10])
                    days_rest = (today - last_date).days

                    ip_str = str((last_start.get('stat') or {}).get(
                        'inningsPitched', '0') or '0')
                    try:
                        parts   = ip_str.split('.')
                        full    = int(parts[0])
                        thirds  = int(parts[1]) if len(parts) > 1 else 0
                        last_ip = round(full + thirds / 3, 2)
                    except (ValueError, IndexError):
                        last_ip = 0.0

                    # Base rest signal
                    if days_rest >= 5:
                        rest_signal = 2.0
                    elif days_rest == 4:
                        rest_signal = 0.0
                    elif days_rest == 3:
                        rest_signal = -1.5
                    else:
                        rest_signal = -2.5

                    # Workload modifier
                    if last_ip >= 7.0:
                        rest_signal += 1.0
                    elif 0 < last_ip <= 3.0:
                        rest_signal -= 1.0

                    entry_data = {
                        'days_rest':   days_rest,
                        'last_ip':     last_ip,
                        'rest_signal': float(np.clip(rest_signal, -3.0, 3.0)),
                        'last_date':   last_start['date'][:10],
                    }
                    result[name] = entry_data
                    if last not in result:
                        result[last] = entry_data
                    if len(name.split()) >= 2 and name.split()[-1].endswith('.'):
                        alias2 = ' '.join(name.split()[-2:])
                        result.setdefault(alias2, entry_data)

                except Exception:
                    continue

        return result
    except Exception:
        return {}


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

    def _i(val):
        try:
            return int(float(val))
        except (TypeError, ValueError):
            return 0

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
                'R':    _i(s.get('runs',       0)),
                'RBI':  _i(s.get('rbi',        0)),
                'BB':   _i(s.get('baseOnBalls',0)),
                'K':    _i(s.get('strikeOuts', 0)),
                'AVG':  s.get('avg', '.000'),
            })
            if len(rows) >= last_n:
                break

        return pd.DataFrame(rows) if rows else pd.DataFrame()
    except Exception as exc:
        LOGGER.warning('get_player_game_log failed for player_id=%s season=%s: %s', player_id, year, exc)
        return pd.DataFrame()


@st.cache_data(ttl=1800)
def get_hrr_game_log_map(player_ids: tuple, last_n: int = 10) -> dict:
    """
    Batch-fetch game log data for a set of players (top HRR candidates).
    Returns {player_id: hrr_summary} where hrr_summary is:
      {
        'hrr_games':   int,   # games where H+R+RBI >= 2
        'total_games': int,   # total games checked
        'hrr_rate':    float, # games_with_hrr / total_games
        'avg_h':  float, 'avg_r':  float, 'avg_rbi': float,
        'last_n':      int,   # how many games were fetched
      }

    Called lazily — only after scoring/filtering narrows to top candidates.
    Capped at 20 players per call to keep API cost low.
    Cached 30 minutes so repeated filter changes don't re-hit the API.

    A game counts as "HRR ≥ 2" when (H + R + RBI) >= 2 in that game.
    """
    if not _STATSAPI_OK or not player_ids:
        return {}

    result: dict[int, dict] = {}
    for player_id in list(player_ids)[:20]:    # hard cap at 20
        try:
            log_df = get_player_game_log(int(player_id), last_n=last_n)
            if log_df.empty:
                continue

            # Filter to games where the player actually had an at-bat
            played = log_df[log_df.get('AB', pd.Series(dtype=int)) > 0].copy() \
                     if 'AB' in log_df.columns else log_df.copy()
            if played.empty:
                continue

            played = played.head(last_n)    # most recent N
            total  = len(played)

            h_col   = 'H'   if 'H'   in played.columns else None
            r_col   = 'R'   if 'R'   in played.columns else None
            rbi_col = 'RBI' if 'RBI' in played.columns else None

            if not h_col:
                continue

            # Compute H+R+RBI per game
            h_s   = pd.to_numeric(played[h_col],   errors='coerce').fillna(0)
            r_s   = pd.to_numeric(played[r_col],   errors='coerce').fillna(0) \
                    if r_col else pd.Series(0, index=played.index)
            rbi_s = pd.to_numeric(played[rbi_col], errors='coerce').fillna(0) \
                    if rbi_col else pd.Series(0, index=played.index)

            hrr_per_game = h_s + r_s + rbi_s
            hrr_games    = int((hrr_per_game >= 2).sum())

            result[int(player_id)] = {
                'hrr_games':   hrr_games,
                'total_games': total,
                'hrr_rate':    hrr_games / total if total > 0 else 0.0,
                'avg_h':       round(float(h_s.mean()),   2),
                'avg_r':       round(float(r_s.mean()),   2),
                'avg_rbi':     round(float(rbi_s.mean()), 2),
                'last_n':      total,
            }
        except Exception:
            continue

    return result
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
