import sys
import types
import unittest
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _noop_decorator(*args, **kwargs):
    def decorator(func):
        return func
    return decorator


streamlit_stub = types.SimpleNamespace(
    cache_data=_noop_decorator,
    warning=lambda *a, **k: None,
    error=lambda *a, **k: None,
    session_state={},
    secrets={},
)
sys.modules.setdefault("streamlit", streamlit_stub)

from loader import merge_game_conditions
from prop_odds import american_to_implied


class RegressionTests(unittest.TestCase):
    def test_qs_join_handles_duplicate_last_names(self):
        df = pd.DataFrame({
            "Game": ["Athletics @ Nationals", "Mariners @ Rangers"],
            "Pitcher": ["Lopez", "Lopez"],
        })
        qs = pd.DataFrame({
            "last_name": ["Lopez", "Lopez"],
            "home_team": ["WAS", "TEX"],
            "qs_prob": [51.0, 44.0],
        })
        out = merge_game_conditions(df, game_cond=None, pitcher_qs=qs)
        self.assertIn("gc_qs", out.columns)
        self.assertEqual(list(out["gc_qs"]), [51.0, 44.0])

    def test_american_odds_conversion(self):
        self.assertAlmostEqual(american_to_implied("+210"), 32.3, places=1)
        self.assertAlmostEqual(american_to_implied("-190"), 65.5, places=1)


if __name__ == "__main__":
    unittest.main()



def test_pitcher_key_handles_multi_token():
    from loader import _build_pitcher_key
    assert _build_pitcher_key('Simeon Woods Rich.') == 'Woods Rich.'
    assert _build_pitcher_key('Reynaldo Lopez') == 'Lopez'


def test_safe_game_log_parser_helper_exists():
    from mlb_api import get_player_game_log
    assert callable(get_player_game_log)
