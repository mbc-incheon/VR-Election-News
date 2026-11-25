import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'election-news-server'))
from google_news import search_query, parse_items

def test_google_query_dates_period_and_empty_overlap():
    query=search_query('계양구을','이재명','2024-04-03','2024-04-17','선거 전')
    assert '계양구을 이재명' in query and 'before:2024-04-10' in query
    assert 'after:2024-04-10 before:2024-04-11' in search_query('','','2024-04-03','2024-04-17','선거 당일')
    assert search_query('','','2024-04-11','2024-04-17','선거 전') is None
    with pytest.raises(ValueError):search_query('','','2024-04-20','2024-04-17')
    with pytest.raises(ValueError):search_query('','','2024-02-31','2024-04-17')

def test_rss_filters_dates_unsafe_links_duplicates_and_invalid_dates():
    def item(link='https://news.google.com/rss/articles/abc',date='Wed, 10 Apr 2024 23:30:00 GMT'):
        return f'<item><title>기사 제목 - 신문</title><link>{link}</link><source>신문</source><pubDate>{date}</pubDate></item>'
    xml='<rss><channel>'+item()+item()+item('javascript:alert(1)')+item('https://evil.example')+item('https://news.google.com/rss/articles/old','Mon, 01 Apr 2024 00:00:00 GMT')+item('https://news.google.com/rss/articles/bad','invalid')+'</channel></rss>'
    items=parse_items(xml.encode(),'2024-04-11','2024-04-11')
    assert len(items)==1 and items[0]['title']=='기사 제목'
    assert items[0]['publisher']=='신문' and items[0]['published_date']=='2024-04-11'
    assert items[0]['id'].startswith('GOOGLE-')
