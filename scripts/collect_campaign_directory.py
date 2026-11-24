"""Collect official catalogue locations; never manufacture candidate pledge text."""
import hashlib,json,re,sys
from datetime import datetime,timezone,timedelta
from html.parser import HTMLParser
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
URL='https://dl.nanet.go.kr/detail/NONB12025000019286'
class Text(HTMLParser):
    def __init__(self):super().__init__();self.parts=[]
    def handle_data(self,data):
        if data.strip():self.parts.append(data.strip())

def build_directory(raw,rows,collected_at):
    parser=Text();parser.feed(raw.decode('utf-8'))
    start=parser.parts.index('인천광역시 1')
    normalize=lambda s:re.sub(r'[·ㆍ\s]','',s)
    region_names={normalize(r['region_name']):r['region_name'] for r in rows}
    region=None;locations={}
    for text in parser.parts[start+1:]:
        match=re.fullmatch(r'(.+?)\s+(\d+)',text)
        if not match:
            if locations:break
            continue
        name,page=match.group(1),int(match.group(2))
        if normalize(name) in region_names:region=region_names[normalize(name)]
        elif region:locations[(region,name)]=page
    entries=[]
    for row in rows:
        page=locations.get((row['region_name'],row['candidate_name']))
        if not page:raise ValueError('candidate catalogue location missing: '+row['candidate_name'])
        entries.append(dict(source_id='NANET22-'+row['candidate_id'],election_id=row['election_id'],region_name=row['region_name'],candidate_id=row['candidate_id'],candidate_name=row['candidate_name'],party=row['party'],
            title='제22대 국회의원선거 인천 선거공보 · '+row['candidate_name'],publisher='중앙선거관리위원회',catalog_provider='국회도서관',publication_year=2024,published_at=None,source_url=URL,original_portal_url='https://library.nec.go.kr/neweps/3/1/paper.do',policy_url='https://policy.nec.go.kr/',catalog_start_page=page,location='국회도서관 목차 수록 시작 '+str(page)+'쪽',collected_at=collected_at,status='INDEX_VERIFIED_BODY_NOT_COLLECTED',usable_as_pledge_evidence=False,rights='국회도서관 상세 페이지의 저작권·초상권 및 자료 이용 조건 확인 필요'))
    return entries

def main():
    timestamp=datetime.now(timezone(timedelta(hours=9))).isoformat()
    with httpx.Client(timeout=25,follow_redirects=True) as client:
        response=client.get(URL);response.raise_for_status()
    raw=response.content;digest=hashlib.sha256(raw).hexdigest()
    entries=build_directory(raw,json.loads((ROOT/'data/clean/incheon_final_results.json').read_text(encoding='utf-8')),timestamp)
    name='NANET-CAMPAIGN-INDEX-'+digest[:16]+'.html'
    (ROOT/'data/official_raw'/name).write_bytes(raw)
    (ROOT/'data/clean/campaign_directory.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding='utf-8')
    ledger=dict(source_url=URL,collected_at=timestamp,response_status=response.status_code,final_url=str(response.url),content_type=response.headers.get('content-type'),source_file=name,sha256=digest,candidates=len(entries),districts=len({x['region_name'] for x in entries}),scope='Official catalogue metadata only; no pledge body or human approval',usable_as_pledge_evidence=False)
    (ROOT/'data/campaign_directory_ledger.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(candidates=len(entries),districts=ledger['districts'],status='INDEX_ONLY')))
if __name__=='__main__':main()
