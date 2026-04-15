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
def get_confirmed_lineup(game_id: int) -> dict:
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
    {batter_full_name: batting_order_position (1-9)} for all confirmed lineups.
    Players not yet confirmed → absent from dict → engine applies 0 (neutral).

    Position groups that matter for scoring:
      3-5 (cleanup):        +bonus HR/XB
      1-2 (table-setters):  +bonus Hit/Single
      6-9:                   neutral
    """
    if not _STATSAPI_OK:
        return {}
    games, result = get_today_schedule(), {}
    for g in games:
        game_id = g.get('game_id')
        status  = g.get('status','Scheduled')
        if not game_id or status in ('Postponed','Cancelled','Suspended'):
            continue
        lineup = get_confirmed_lineup(game_id)
        for side in ('away','home'):
            for b in lineup[side]:
                name = b.get('name','').strip()
                if name:
                    result[name] = b['order']
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
    {batter_name: {hit_rate, hits, games}} for the last N days.

    Uses pybaseball.batting_stats_range() — one batch call covers all batters.
    hit_rate = H/G. League average ~0.9 hits/game.
    Hot: >1.2  Cold: <0.5  (thresholds in engine.py)

    Missing players → engine applies 0 pts (neutral).
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
            g    = int(row.get('G',0) or 0)
            h    = int(row.get('H',0) or 0)
            if name and g > 0:
                result[name] = {'hit_rate': round(h/g,3), 'hits': h, 'games': g}
        return result
    except Exception:
        return {}


# ── PLAYER GAME LOG ───────────────────────────────────────────────────────────

@st.cache_data(ttl=600)
def get_player_game_log(player_id: int, last_n: int = 10) -> pd.DataFrame:
    if not _STATSAPI_OK or not player_id:
        return pd.DataFrame()
    year = date.today().year
    try:
        raw    = statsapi.get('people',{'personIds':player_id,
                              'hydrate':f'stats(type=gameLog,season={year},group=hitting)'})
        splits = []
        for sb in (raw.get('people') or [{}])[0].get('stats',[]):
            if sb.get('type',{}).get('displayName') == 'gameLog':
                splits = sb.get('splits',[]); break
        rows = []
        for entry in reversed(splits):
            s = entry.get('stat',{})
            rows.append({'Date': entry.get('game',{}).get('gameDate','')[:10],
                         'Opp':  entry.get('opponent',{}).get('abbreviation','?'),
                         'AB':_i(s.get('atBats',0)),'H':_i(s.get('hits',0)),
                         '2B':_i(s.get('doubles',0)),'3B':_i(s.get('triples',0)),
                         'HR':_i(s.get('homeRuns',0)),'RBI':_i(s.get('rbi',0)),
                         'BB':_i(s.get('baseOnBalls',0)),'K':_i(s.get('strikeOuts',0)),
                         'AVG':s.get('avg','.000')})
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
