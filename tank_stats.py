"""
tank_stats.py — Tank01 Batter vs Pitcher & Splits API
======================================================
Two endpoints from Tank01:

  GET /getMLBBatterVsPitcher
    params: playerID (batter), playerRole="batting", opponent (pitcher ID)
    returns: career stats for this specific batter vs this specific pitcher
    call pattern: per-batter, cached 24h per batter MLBAM ID

  GET /getMLBSplits
    params: playerID, splitType ("batting"|"pitching"), season (optional)
    returns: season splits by Home/Away/Day/Night/vs.Left/vs.Right
    call pattern: per player, cached 12h

Both use the same MLBAM IDs as the MLB Stats API, Statcast, and prop_odds.py.

Rate budget estimate:
  BvP calls:        ~135/day (confirmed batters, cached)
  Batter splits:    ~135/day (same batters)
  Pitcher splits:   ~30/day  (today's starters)
  Total:            ~300/day — well within 1,000/day limit

Confidence weighting for BvP (AB-gated):
  AB < 5:  signal = 0.0  (too small — neutral)
  AB 5-14: confidence = AB / 15.0  (partial weight)
  AB >= 15: confidence = 1.0  (full weight)

All data is joined to the df by MLBAM player ID — no name matching needed.
Missing data (no history, API failure) → NaN columns → neutral in scoring.
"""

import streamlit as st
import pandas as pd
import requests
from datetime import date


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

_HOST    = "tank01-mlb-live-in-game-real-time-statistics.p.rapidapi.com"
_KEY     = "aea0b33de0mshbca63a26bd3e2eap110846jsn73cd64e0881d"
_HEADERS = {
    "x-rapidapi-key":  _KEY,
    "x-rapidapi-host": _HOST,
    "Content-Type":    "application/json",
}
_BVP_URL    = f"https://{_HOST}/getMLBBatterVsPitcher"
_SPLITS_URL = f"https://{_HOST}/getMLBSplits"

_CURRENT_SEASON = str(date.today().year)
_BVP_MIN_AB     = 5      # minimum AB for signal to fire
_BVP_FULL_AB    = 15     # AB at which confidence reaches 1.0


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _safe_float(val, default: float = 0.0) -> float:
    """Convert string stat like '.333' or '1.467' to float safely."""
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return default


def _safe_int(val, default: int = 0) -> int:
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return default


def _bvp_confidence(ab: int) -> float:
    """
    AB-gated confidence weight.
    Below _BVP_MIN_AB → 0.0 (neutral, don't fire).
    _BVP_MIN_AB to _BVP_FULL_AB → partial weight.
    Above _BVP_FULL_AB → 1.0 (full weight).
    """
    if ab < _BVP_MIN_AB:
        return 0.0
    return min(1.0, ab / _BVP_FULL_AB)


# ─────────────────────────────────────────────────────────────────────────────
# BvP FETCH — cached per batter per day
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_bvp_raw(batter_mlbam: int) -> dict:
    """
    Fetch all BvP data for one batter. Cached 24h — data doesn't change mid-day.
    Returns raw opponents list: [{playerID, stats}] or [].
    """
    try:
        resp = requests.get(
            _BVP_URL,
            headers=_HEADERS,
            params={"playerID": str(batter_mlbam), "playerRole": "batting"},
            timeout=10,
        )
        if resp.status_code != 200:
            return {}
        body = resp.json().get("body", {})
        opponents = body.get("opponents", [])
        # Build a dict keyed by pitcher MLBAM for O(1) lookup
        return {
            int(o["playerID"]): o["stats"]
            for o in opponents
            if "playerID" in o and "stats" in o
        }
    except Exception:
        return {}


def get_bvp_stats(batter_mlbam: int, pitcher_mlbam: int) -> dict | None:
    """
    Return career BvP stats for one specific batter vs one specific pitcher.
    Returns None when no history exists or AB < _BVP_MIN_AB.

    Returned dict (all numeric):
      ab, h, avg, ops, hr, rbi, k, bb, obp, slg, doubles, triples, confidence
    """
    opponents = _fetch_bvp_raw(batter_mlbam)
    if not opponents:
        return None

    raw = opponents.get(pitcher_mlbam)
    if not raw:
        return None

    ab = _safe_int(raw.get("AB", 0))
    if ab < _BVP_MIN_AB:
        return None

    return {
        "ab":         ab,
        "h":          _safe_int(raw.get("H",   0)),
        "avg":        _safe_float(raw.get("AVG", "0")),
        "ops":        _safe_float(raw.get("OPS", "0")),
        "hr":         _safe_int(raw.get("HR",   0)),
        "rbi":        _safe_int(raw.get("RBI",  0)),
        "k":          _safe_int(raw.get("K",    0)),
        "bb":         _safe_int(raw.get("BB",   0)),
        "obp":        _safe_float(raw.get("OBP", "0")),
        "slg":        _safe_float(raw.get("SLG", "0")),
        "doubles":    _safe_int(raw.get("2B",   0)),
        "triples":    _safe_int(raw.get("3B",   0)),
        "confidence": _bvp_confidence(ab),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SPLITS FETCH — cached per player per day
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=43200, show_spinner=False)
def get_splits(player_mlbam: int, split_type: str = "batting") -> dict:
    """
    Fetch season splits for one player. Cached 12h.
    split_type: "batting" or "pitching"

    Returns {split_name: {stat: value}} e.g.:
      {"vs. Right": {"AVG": 0.283, "OPS": 1.076, "K": 120, ...},
       "vs. Left":  {"AVG": 0.279, "OPS": 0.898, ...}}

    All numeric values (strings converted). Missing stats → 0.0.
    """
    try:
        resp = requests.get(
            _SPLITS_URL,
            headers=_HEADERS,
            params={
                "playerID":  str(player_mlbam),
                "splitType": split_type,
                "season":    _CURRENT_SEASON,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return {}
        splits_raw = resp.json().get("body", {}).get("splits", {})
        result = {}
        for split_name, stats in splits_raw.items():
            result[split_name] = {
                k: (_safe_float(v) if "." in str(v) else _safe_int(v))
                for k, v in stats.items()
            }
        return result
    except Exception:
        return {}


def get_pitcher_splits(pitcher_mlbam: int) -> dict:
    """Convenience wrapper — pitcher splits (vs. Left / vs. Right)."""
    return get_splits(pitcher_mlbam, split_type="pitching")


def get_batter_splits(batter_mlbam: int) -> dict:
    """Convenience wrapper — batter splits (vs. Left / vs. Right)."""
    return get_splits(batter_mlbam, split_type="batting")


# ─────────────────────────────────────────────────────────────────────────────
# BUILD BVP MAP — orchestrator for full slate
# ─────────────────────────────────────────────────────────────────────────────

def build_bvp_map(df: pd.DataFrame,
                  player_id_map: dict,
                  pitcher_id_map: dict) -> dict:
    """
    Build {batter_mlbam: bvp_stats_dict} for every batter in df.

    player_id_map:  {batter_name → batter_mlbam}
    pitcher_id_map: {batter_name → pitcher_mlbam}  (today's starter for each batter)

    Calls get_bvp_stats() per batter — each call is individually cached 24h
    so repeated calls (e.g. sidebar filter changes) don't re-hit the API.
    """
    result: dict[int, dict] = {}
    for _, row in df.iterrows():
        batter = row.get("Batter", "")
        batter_id  = player_id_map.get(batter)
        pitcher_id = pitcher_id_map.get(batter)
        if not batter_id or not pitcher_id:
            continue
        try:
            stats = get_bvp_stats(int(batter_id), int(pitcher_id))
            if stats:
                result[int(batter_id)] = stats
        except Exception:
            continue
    return result


# ─────────────────────────────────────────────────────────────────────────────
# BUILD SPLITS MAP — orchestrator for batters + pitchers
# ─────────────────────────────────────────────────────────────────────────────

def build_splits_map(df: pd.DataFrame,
                     player_id_map: dict,
                     pitcher_id_map: dict) -> tuple[dict, dict]:
    """
    Build two maps:
      batter_splits_map:  {batter_mlbam → splits_dict}
      pitcher_splits_map: {pitcher_mlbam → splits_dict}

    Returns (batter_splits_map, pitcher_splits_map).
    Each pitcher is only fetched once even if they face multiple batters.
    """
    batter_splits:  dict[int, dict] = {}
    pitcher_splits: dict[int, dict] = {}
    seen_pitchers:  set[int]        = set()

    for _, row in df.iterrows():
        batter = row.get("Batter", "")
        batter_id  = player_id_map.get(batter)
        pitcher_id = pitcher_id_map.get(batter)

        if batter_id:
            try:
                splits = get_batter_splits(int(batter_id))
                if splits:
                    batter_splits[int(batter_id)] = splits
            except Exception:
                pass

        if pitcher_id:
            pid = int(pitcher_id)
            if pid not in seen_pitchers:
                seen_pitchers.add(pid)
                try:
                    splits = get_pitcher_splits(pid)
                    if splits:
                        pitcher_splits[pid] = splits
                except Exception:
                    pass

    return batter_splits, pitcher_splits


# ─────────────────────────────────────────────────────────────────────────────
# ENRICH WITH BVP — join to slate df
# ─────────────────────────────────────────────────────────────────────────────

def enrich_with_bvp(df: pd.DataFrame,
                    player_id_map: dict,
                    bvp_map: dict) -> pd.DataFrame:
    """
    Join BvP stats to slate df by batter MLBAM ID.

    Adds columns:
      bvp_ab, bvp_h, bvp_avg, bvp_ops, bvp_hr, bvp_rbi,
      bvp_k, bvp_bb, bvp_obp, bvp_slg, bvp_conf

    Players with no history → NaN in all bvp_* columns.
    NaN is neutral — scoring treats missing BvP as 0 adjustment.
    """
    if not bvp_map or df.empty:
        return df

    df = df.copy()
    bvp_cols = {
        "bvp_ab": float("nan"), "bvp_h": float("nan"),
        "bvp_avg": float("nan"), "bvp_ops": float("nan"),
        "bvp_hr": float("nan"), "bvp_rbi": float("nan"),
        "bvp_k": float("nan"), "bvp_bb": float("nan"),
        "bvp_obp": float("nan"), "bvp_slg": float("nan"),
        "bvp_conf": float("nan"),
    }
    for col, default in bvp_cols.items():
        df[col] = default

    for idx, row in df.iterrows():
        batter   = row.get("Batter", "")
        mlbam    = player_id_map.get(batter)
        if mlbam is None:
            continue
        stats = bvp_map.get(int(mlbam))
        if not stats:
            continue
        df.at[idx, "bvp_ab"]   = stats["ab"]
        df.at[idx, "bvp_h"]    = stats["h"]
        df.at[idx, "bvp_avg"]  = stats["avg"]
        df.at[idx, "bvp_ops"]  = stats["ops"]
        df.at[idx, "bvp_hr"]   = stats["hr"]
        df.at[idx, "bvp_rbi"]  = stats["rbi"]
        df.at[idx, "bvp_k"]    = stats["k"]
        df.at[idx, "bvp_bb"]   = stats["bb"]
        df.at[idx, "bvp_obp"]  = stats["obp"]
        df.at[idx, "bvp_slg"]  = stats["slg"]
        df.at[idx, "bvp_conf"] = stats["confidence"]

    return df


# ─────────────────────────────────────────────────────────────────────────────
# ENRICH WITH SPLITS — join to slate df
# ─────────────────────────────────────────────────────────────────────────────

def enrich_with_splits(df: pd.DataFrame,
                       player_id_map: dict,
                       pitcher_id_map: dict,
                       batter_splits_map: dict,
                       pitcher_splits_map: dict) -> pd.DataFrame:
    """
    Join split stats to slate df.

    Batter splits → batter's season AVG/OPS/K/BB vs pitcher's hand (L or R).
    Pitcher splits → pitcher's season AVG-against/K/BB vs batter's hand.

    Columns added (batter perspective):
      split_avg, split_ops, split_k, split_bb, split_obp, split_slg
      (these reflect the batter's stats vs THIS pitcher's hand this season)

    Columns added (pitcher perspective):
      pitcher_split_avg_against, pitcher_split_k_pct, pitcher_split_bb_pct
      (how this pitcher performs vs THIS batter's hand)

    _pitcher_hand must already be in df from _merge_signal_metadata().
    """
    if df.empty:
        return df

    df = df.copy()
    split_cols = {
        "split_avg": float("nan"), "split_ops": float("nan"),
        "split_k": float("nan"), "split_bb": float("nan"),
        "split_obp": float("nan"), "split_slg": float("nan"),
        "pitcher_split_avg": float("nan"),
        "pitcher_split_k":   float("nan"),
        "pitcher_split_bb":  float("nan"),
    }
    for col, default in split_cols.items():
        df[col] = default

    for idx, row in df.iterrows():
        batter     = row.get("Batter", "")
        batter_id  = player_id_map.get(batter)
        pitcher_id = pitcher_id_map.get(batter)
        p_hand     = row.get("_pitcher_hand")  # 'L' or 'R'

        # Batter splits: how does this batter hit vs this pitcher's hand?
        if batter_id and p_hand in ("L", "R"):
            splits = batter_splits_map.get(int(batter_id), {})
            split_key = f"vs. {'Right' if p_hand == 'R' else 'Left'}"
            s = splits.get(split_key, {})
            if s:
                # AB > 0 check — splits with 0 AB are empty categories
                ab_s = _safe_int(s.get("AB", 0))
                if ab_s > 0:
                    df.at[idx, "split_avg"] = _safe_float(str(s.get("AVG", 0)))
                    df.at[idx, "split_ops"] = _safe_float(str(s.get("OPS", 0)))
                    df.at[idx, "split_k"]   = _safe_int(s.get("SO", 0))
                    df.at[idx, "split_bb"]  = _safe_int(s.get("BB", 0))
                    df.at[idx, "split_obp"] = _safe_float(str(s.get("OBP", 0)))
                    df.at[idx, "split_slg"] = _safe_float(str(s.get("SLG", 0)))

        # Pitcher splits: how does this pitcher perform vs this batter's hand?
        # We don't have batter hand yet — use pitcher's overall splits for now.
        # When batter hand data is available, update split_key accordingly.
        if pitcher_id:
            p_splits = pitcher_splits_map.get(int(pitcher_id), {})
            # Use overall "All Splits" or best available
            ps = p_splits.get("All Splits", p_splits.get("vs. Right", {}))
            if ps:
                ab_p = _safe_int(ps.get("AB", 0))
                if ab_p > 0:
                    df.at[idx, "pitcher_split_avg"] = _safe_float(
                        str(ps.get("AVG", 0)))
                    df.at[idx, "pitcher_split_k"]   = _safe_int(ps.get("SO", 0))
                    df.at[idx, "pitcher_split_bb"]  = _safe_int(ps.get("BB", 0))

    return df
