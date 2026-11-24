"""The served page must match the maintained dashboard sources."""
import runpy
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_served_dashboard_is_current():
    builder=runpy.run_path(str(ROOT/'scripts/build_dashboard.py'))
    assert builder['build']()==(ROOT/'election-news-server/index.html').read_text(encoding='utf-8')
