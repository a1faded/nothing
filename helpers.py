"""
helpers.py — Shared utility functions

V2 additions:
  - get_matchups_commit_time()  → ISO timestamp of latest Matchups.csv commit
  - should_auto_invalidate()    → True when GitHub has a newer commit than our cache load
  - Auto-invalidation writes last-seen commit SHA to st.session_state so it persists
    within a Streamlit session without extra API calls on every rerender.
"""

import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timezone
from config import REPO_API


def normalize_0_100(series: pd.Series) -> pd.Series:
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(50.0, index=series.index)
    return ((series - mn) / (mx - mn) * 100).round(1)


def grade_pill(grade: str) -> str:
    css = {'A+': 'gp-ap', 'A': 'gp-a', 'B': 'gp-b',
           'C': 'gp-c',   'D': 'gp-d'}.get(str(grade), 'gp-b')
    return f'<span class="gp {css}">{grade}</span>'


def style_grade_cell(val):
    return {
        'A+': 'background-color:#052e16;color:#4ade80;font-weight:700',
        'A':  'background-color:#1a3a10;color:#86efac;font-weight:700',
        'B':  'background-color:#1c1a00;color:#fde047',
        'C':  'background-color:#1c0e00;color:#fb923c',
        'D':  'background-color:#1c0000;color:#f87171;font-weight:700',
    }.get(str(val), '')


# ─────────────────────────────────────────────────────────────────────────────
# GITHUB COMMIT FRESHNESS
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=120)   # re-check GitHub every 2 minutes max
def _fetch_latest_commit(path: str) -> dict | None:
    """
    Returns the latest commit metadata for a specific file path from REPO_API.
    Keys: sha, date (ISO string), age_str (human-readable).
    Returns None if the API call fails.
    """
    try:
        resp = requests.get(
            REPO_API,
            params={'path': path, 'per_page': 1},
            headers={'Accept': 'application/vnd.github+json'},
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data:
            return None

        commit_time_str = data[0]['commit']['committer']['date']
        sha             = data[0]['sha']
        commit_dt       = datetime.fromisoformat(commit_time_str.replace('Z', '+00:00'))
        now_utc         = datetime.now(timezone.utc)
        diff_sec        = int((now_utc - commit_dt).total_seconds())

        if diff_sec < 60:
            age = "just now"
        elif diff_sec < 3600:
            age = f"{diff_sec // 60}m ago"
        elif diff_sec < 86400:
            age = f"{diff_sec // 3600}h ago"
        else:
            age = f"{diff_sec // 86400}d ago"

        return {'sha': sha, 'date': commit_time_str, 'age_str': age,
                'commit_dt': commit_dt}
    except Exception:
        return None


def get_last_commit_time(path: str) -> str | None:
    """Return human-readable age string for a file's last commit. Used by badge."""
    info = _fetch_latest_commit(path)
    return info['age_str'] if info else None


def should_auto_invalidate() -> bool:
    """
    Returns True if the Matchups.csv on GitHub was updated after the
    last time we cleared the cache in this session.

    Compares the latest commit SHA against the SHA we saw last time.
    When a new commit is detected → clears st.cache_data → returns True
    so the caller can trigger a st.rerun().

    This means users always see fresh data within 2 minutes of a CSV push
    without manually hitting Refresh.
    """
    info = _fetch_latest_commit('Matchups.csv')
    if info is None:
        return False

    current_sha = info['sha']
    seen_sha    = st.session_state.get('_last_matchups_sha')

    if seen_sha is None:
        # First load — record SHA, no invalidation
        st.session_state['_last_matchups_sha'] = current_sha
        return False

    if current_sha != seen_sha:
        # New commit detected — invalidate cache and record new SHA
        st.cache_data.clear()
        st.session_state['_last_matchups_sha'] = current_sha
        return True

    return False


def data_freshness_badge() -> str:
    age = get_last_commit_time('Matchups.csv')
    if age is None:
        return '<span class="sbadge sbadge-yellow">⏱ Updated: unknown</span>'

    is_fresh = ('just' in age) or (age.endswith('m ago') and int(age.replace('m ago','')) < 60)
    is_recent = age.endswith('h ago') and int(age.replace('h ago','')) < 6

    if is_fresh:
        css, icon = 'sbadge-green', '🟢'
    elif is_recent:
        css, icon = 'sbadge-yellow', '🟡'
    else:
        css, icon = 'sbadge-red', '🔴'

    return f'<span class="sbadge {css}">{icon} Data: {age}</span>'
