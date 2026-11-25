"""Google News RSS metadata search; fixed upstream, bounded input and response."""
import asyncio
import hashlib
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
import httpx

_cache = {}
_gate = asyncio.Semaphore(4)

def search_query(region, candidate, start, end, period='all'):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last: raise ValueError('시작일과 종료일을 확인하세요.')
    day = date(2024,4,10)
    if period == '선거 전': last = min(last, day-timedelta(days=1))
    elif period == '선거 당일': first, last = max(first,day), min(last,day)
    elif period == '선거 후': first = max(first,day+timedelta(days=1))
    if first > last: return None
    return ' '.join(filter(None,['인천',region,candidate,'총선','after:'+first.isoformat(),'before:'+(last+timedelta(days=1)).isoformat()]))

def parse_items(content, start, end):
    result, seen = [], set()
    for node in ET.fromstring(content).findall('./channel/item'):
        title, link = (node.findtext('title') or '').strip(), (node.findtext('link') or '').strip()
        parsed = urlsplit(link)
        if parsed.scheme != 'https' or parsed.hostname != 'news.google.com' or link in seen: continue
        try: published = parsedate_to_datetime(node.findtext('pubDate') or '').astimezone(timezone(timedelta(hours=9))).date().isoformat()
        except (ValueError,TypeError,OverflowError): continue
        if not start <= published <= end: continue
        publisher = (node.findtext('source') or '언론사 미제공').strip()
        if title.endswith(' - '+publisher): title = title[:-len(' - '+publisher)]
        if not title: continue
        seen.add(link)
        result.append(dict(id='GOOGLE-'+hashlib.sha256(link.encode()).hexdigest()[:16],title=title[:500],url=link,publisher=publisher[:150],published_date=published))
        if len(result) >= 30: break
    return sorted(result,key=lambda item:item['published_date'],reverse=True)

async def search_google_news(region, candidate, start, end, period='all'):
    query = search_query(region,candidate,start,end,period)
    if query is None: return dict(items=[],cached=False)
    key=(query,start,end)
    async with _gate:
        cached=_cache.get(key)
        if cached and time.monotonic()-cached[0]<300: return dict(items=cached[1],cached=True)
        async with httpx.AsyncClient(timeout=12,follow_redirects=False) as client:
            async with client.stream('GET','https://news.google.com/rss/search',params={'q':query,'hl':'ko','gl':'KR','ceid':'KR:ko'}) as response:
                response.raise_for_status()
                body=bytearray()
                async for part in response.aiter_bytes():
                    body.extend(part)
                    if len(body)>1_000_000: raise ValueError('검색 응답 크기 제한을 초과했습니다.')
        effective_start=query.split('after:')[-1].split()[0]
        effective_end=(date.fromisoformat(query.split('before:')[-1].split()[0])-timedelta(days=1)).isoformat()
        items=parse_items(bytes(body),effective_start,effective_end)
        if len(_cache)>=100: _cache.pop(next(iter(_cache)))
        _cache[key]=(time.monotonic(),items)
        return dict(items=items,cached=False)
