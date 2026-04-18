"""
prop_odds.py — Player Prop Odds Integration
=============================================
Fetches daily player prop odds from Tank01 MLB API.
Extracts: bases (TB line + over/under odds) and homeruns (yes/no odds).
Joins to slate df by MLBAM player ID — no name matching needed.

API: GET /getMLBBettingOdds
Params: gameDate=YYYYMMDD, playerProps=true, itemFormat=map
Auth: x-rapidapi-key header

Data extracted per player:
  prop_tb_line        — "0.5" or "1.5"  (the total bases line)
  prop_tb_over_odds   — e.g. "+210"     (raw American odds, over side)
  prop_tb_under_odds  — e.g. "-190"     (raw American odds, under side)
  prop_tb_under_pct   — float 0–100    (implied probability of under)
  prop_tb_over_pct    — float 0–100    (implied probability of over)
  prop_hr_odds        — e.g. "+950"     (odds to hit any HR)
  prop_hr_pct         — float 0–100    (implied HR probability)

Edge signal philosophy:
  Market odds are CONTEXT, not a filter.
  When our model strongly disagrees with the market, that's a potential edge —
  not a red flag. The badge reads as opportunity, not warning.
  Our model is primary. Odds are reference data.

Player list note:
  Tank01 playerIDs are the same MLBAM IDs used by MLB Stats API and Statcast.
  Join is done via player_id_map {batter_name → mlbam_id} — already in pipeline.
  No additional name matching required.
"""

import streamlit as st
import pandas as pd
import requests
from datetime import date


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

RAPIDAPI_KEY  = "aea0b33de0mshbca63a26bd3e2eap110846jsn73cd64e0881d"
RAPIDAPI_HOST = "tank01-mlb-live-in-game-real-time-statistics.p.rapidapi.com"
ODDS_URL      = f"https://{RAPIDAPI_HOST}/getMLBBettingOdds"

HEADERS = {
    "x-rapidapi-key":  RAPIDAPI_KEY,
    "x-rapidapi-host": RAPIDAPI_HOST,
    "Content-Type":    "application/json",
}


# ─────────────────────────────────────────────────────────────────────────────
# ODDS MATH
# ─────────────────────────────────────────────────────────────────────────────

def american_to_implied(odds_str: str) -> float:
    """
    Convert American odds string to implied probability (0–100).

    +210 → 100 / (210 + 100) = 32.3%
    -190 → 190 / (190 + 100) = 65.5%
    Returns 0.0 if the string is missing, malformed, or zero.
    """
    try:
        odds = int(str(odds_str).strip().replace('+', ''))
        if odds == 0:
            return 0.0
        if odds > 0:
            return round(100 / (odds + 100), 1)
        else:
            return round(abs(odds) / (abs(odds) + 100), 1) * 100
    except (ValueError, TypeError):
        return 0.0


def implied_to_american(pct: float) -> str:
    """Convert implied probability (0–100) back to American odds string."""
    if pct <= 0 or pct >= 100:
        return "—"
    try:
        if pct >= 50:
            odds = round(-pct / (1 - pct / 100))
            return f"{odds:+d}"
        else:
            odds = round((100 - pct) / (pct / 100))
            return f"+{odds}"
    except Exception:
        return "—"


# ─────────────────────────────────────────────────────────────────────────────
# FETCH — cached 30 minutes (odds update intraday but not minute-to-minute)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_player_props(game_date: str | None = None) -> dict:
    """
    Fetch all player props for a given date from Tank01.

    Returns: {mlbam_player_id (int): {
        'tb_line':        str   "0.5" | "1.5"
        'tb_over_odds':   str   e.g. "+210"
        'tb_under_odds':  str   e.g. "-190"
        'tb_under_pct':   float implied % of under
        'tb_over_pct':    float implied % of over
        'hr_odds':        str   e.g. "+950"
        'hr_pct':         float implied % of HR
    }}

    Returns {} on any API failure — caller handles gracefully.
    """
    if game_date is None:
        game_date = date.today().strftime("%Y%m%d")

    try:
        params = {
            "gameDate":    game_date,
            "playerProps": "true",
            "itemFormat":  "map",
        }
        resp = requests.get(ODDS_URL, headers=HEADERS, params=params, timeout=12)
        if resp.status_code != 200:
            return {}

        data = resp.json()
        body = data.get("body", {})
        if not body:
            return {}

        result: dict[int, dict] = {}

        # body is a dict of game_key → game data
        for game_key, game_data in body.items():
            player_props = game_data.get("playerProps", [])
            if not isinstance(player_props, list):
                continue

            for entry in player_props:
                pid_raw = entry.get("playerID")
                if not pid_raw:
                    continue
                try:
                    pid = int(pid_raw)
                except (ValueError, TypeError):
                    continue

                bets = entry.get("propBets", {})
                bases_data = bets.get("bases", {})
                hr_data    = bets.get("homeruns", {})

                # Skip if neither bases nor HR data present
                if not bases_data and not hr_data:
                    continue

                tb_line       = str(bases_data.get("total", ""))
                tb_over_odds  = str(bases_data.get("over",  ""))
                tb_under_odds = str(bases_data.get("under", ""))
                hr_odds       = str(hr_data.get("one", ""))

                tb_under_pct = american_to_implied(tb_under_odds) if tb_under_odds else 0.0
                tb_over_pct  = american_to_implied(tb_over_odds)  if tb_over_odds  else 0.0
                hr_pct       = american_to_implied(hr_odds)        if hr_odds       else 0.0

                result[pid] = {
                    "tb_line":       tb_line,
                    "tb_over_odds":  tb_over_odds  or "—",
                    "tb_under_odds": tb_under_odds or "—",
                    "tb_under_pct":  tb_under_pct,
                    "tb_over_pct":   tb_over_pct,
                    "hr_odds":       hr_odds or "—",
                    "hr_pct":        hr_pct,
                }

        return result

    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# ENRICH — join props to slate df by MLBAM ID
# ─────────────────────────────────────────────────────────────────────────────

def enrich_with_props(df: pd.DataFrame, player_id_map: dict,
                      props: dict) -> pd.DataFrame:
    """
    Join player prop odds to the slate df using MLBAM IDs.

    player_id_map: {batter_name: mlbam_id}  — already in pipeline
    props:         {mlbam_id: prop_dict}     — from fetch_player_props()

    Adds columns: prop_tb_line, prop_tb_over_odds, prop_tb_under_odds,
                  prop_tb_under_pct, prop_tb_over_pct,
                  prop_hr_odds, prop_hr_pct

    Players with no odds data get NaN — displays as "—" in table.
    No player is excluded or penalised for missing odds.
    """
    if not props or df.empty:
        return df

    df = df.copy()

    # Initialise columns
    prop_cols = {
        "prop_tb_line":       "",
        "prop_tb_over_odds":  "",
        "prop_tb_under_odds": "",
        "prop_tb_under_pct":  float("nan"),
        "prop_tb_over_pct":   float("nan"),
        "prop_hr_odds":       "",
        "prop_hr_pct":        float("nan"),
    }
    for col, default in prop_cols.items():
        df[col] = default

    # Build mlbam_id → df index map for vectorised assignment
    for idx, row in df.iterrows():
        batter  = row.get("Batter", "")
        mlbam   = player_id_map.get(batter)
        if mlbam is None:
            continue
        p = props.get(int(mlbam))
        if not p:
            continue
        df.at[idx, "prop_tb_line"]       = p["tb_line"]
        df.at[idx, "prop_tb_over_odds"]  = p["tb_over_odds"]
        df.at[idx, "prop_tb_under_odds"] = p["tb_under_odds"]
        df.at[idx, "prop_tb_under_pct"]  = p["tb_under_pct"]
        df.at[idx, "prop_tb_over_pct"]   = p["tb_over_pct"]
        df.at[idx, "prop_hr_odds"]       = p["hr_odds"]
        df.at[idx, "prop_hr_pct"]        = p["hr_pct"]

    return df


# ─────────────────────────────────────────────────────────────────────────────
# EDGE BADGE — model vs market, framed as opportunity not warning
# ─────────────────────────────────────────────────────────────────────────────

def edge_badge(under_score: float, tb_under_pct: float) -> str:
    """
    HTML badge version — for use in st.markdown() contexts only.
    For st.dataframe() use edge_label() instead.
    """
    if tb_under_pct <= 0 or pd.isna(tb_under_pct):
        return ""

    model_pct = under_score
    diff      = model_pct - tb_under_pct

    if model_pct >= 60 and tb_under_pct >= 55:
        return (
            '<span style="background:#052e16;color:#4ade80;padding:1px 7px;'
            'border-radius:20px;font-size:.65rem;font-weight:700;'
            'font-family:\'JetBrains Mono\',monospace">✅ CONFIRMED</span>'
        )
    elif diff >= 18:
        return (
            '<span style="background:#1c1a00;color:#facc15;padding:1px 7px;'
            'border-radius:20px;font-size:.65rem;font-weight:700;'
            'font-family:\'JetBrains Mono\',monospace">⚡ EDGE</span>'
        )
    elif diff <= -18:
        return (
            '<span style="background:#0f1623;color:#94a3b8;padding:1px 7px;'
            'border-radius:20px;font-size:.65rem;font-weight:700;'
            'font-family:\'JetBrains Mono\',monospace">🔄 CONTRARIAN</span>'
        )
    else:
        return (
            '<span style="background:#131c2e;color:#64748b;padding:1px 7px;'
            'border-radius:20px;font-size:.65rem;font-weight:700;'
            'font-family:\'JetBrains Mono\',monospace">↔️ NEUTRAL</span>'
        )


def edge_label(under_score: float, tb_under_pct: float) -> str:
    """
    Plain-text version of the edge signal — safe for st.dataframe() columns.
    Returns a short emoji + label string that renders cleanly in a table cell.
    """
    if tb_under_pct <= 0 or pd.isna(tb_under_pct):
        return "—"

    model_pct = under_score
    diff      = model_pct - tb_under_pct

    if model_pct >= 60 and tb_under_pct >= 55:
        return "✅ Confirmed"
    elif diff >= 18:
        return "⚡ Edge"
    elif diff <= -18:
        return "🔄 Contrarian"
    else:
        return "↔️ Neutral"
