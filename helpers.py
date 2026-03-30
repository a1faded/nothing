"""
utils/helpers.py — Shared utility functions
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
    css = {'A+': 'gp-ap', 'A': 'gp-a', 'B': 'gp-b', 'C': 'gp-c', 'D': 'gp-d'}.get(str(grade), 'gp-b')
    return f'<span class="gp {css}">{grade}</span>'


def style_grade_cell(val):
    return {
        'A+': 'background-color:#1a9641;color:white;font-weight:700',
        'A':  'background-color:#a6d96a;color:#111;font-weight:700',
        'B':  'background-color:#fef08a;color:#111',
        'C':  'background-color:#fdae61;color:#111',
        'D':  'background-color:#ef4444;color:white;font-weight:700',
    }.get(str(val), '')


@st.cache_data(ttl=300)
def get_last_commit_time(path: str) -> str:
    try:
        resp = requests.get(
            REPO_API,
            params={'path': path, 'per_page': 1},
            headers={'Accept': 'application/vnd.github+json'},
            timeout=8
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data:
            return None
        commit_time_str = data[0]['commit']['committer']['date']
        commit_dt = datetime.fromisoformat(commit_time_str.replace('Z', '+00:00'))
        now_utc   = datetime.now(timezone.utc)
        diff_sec  = int((now_utc - commit_dt).total_seconds())
        if diff_sec < 60:
            return "just now"
        elif diff_sec < 3600:
            return f"{diff_sec // 60}m ago"
        elif diff_sec < 86400:
            return f"{diff_sec // 3600}h ago"
        else:
            return f"{diff_sec // 86400}d ago"
    except Exception:
        return None


def data_freshness_badge() -> str:
    age = get_last_commit_time('Matchups.csv')
    if age is None:
        return '<span class="sbadge sbadge-yellow">⏱ Updated: unknown</span>'
    if 'just' in age or (age.endswith('m ago') and int(age.replace('m ago', '')) < 60):
        css, icon = 'sbadge-green', '🟢'
    elif age.endswith('h ago') and int(age.replace('h ago', '')) < 6:
        css, icon = 'sbadge-yellow', '🟡'
    else:
        css, icon = 'sbadge-red', '🔴'
    return f'<span class="sbadge {css}">{icon} Data: {age}</span>'
