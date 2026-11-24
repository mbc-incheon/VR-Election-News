"""Build the single-file page served by the news server, without frontend dependencies."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'election-news-server'

def build():
    return (ROOT/'dashboard.template.html').read_text(encoding='utf-8').replace(
        '/* DASHBOARD_CSS */',(ROOT/'dashboard.css').read_text(encoding='utf-8')).replace(
        '/* DASHBOARD_JS */',(ROOT/'dashboard.js').read_text(encoding='utf-8'))

if __name__=='__main__':
    (ROOT/'index.html').write_text(build(),encoding='utf-8')
    print('Dashboard built')
