"""Shared official-file verification for producer and newsroom."""
import csv
import hashlib
import json
from pathlib import Path

SPECIAL={'선거인수','투표수','무효 투표수','기권자수'}

def load_official(root):
    root=Path(root)
    ledger=json.loads((root/'data/official_csv_ledger.json').read_text(encoding='utf-8'))
    raw=(root/'data/official_raw/NEC_NA22_20240410.csv').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ledger['sha256']:raise ValueError('official raw file hash mismatch')
    rows=json.loads((root/'data/clean/incheon_final_results.json').read_text(encoding='utf-8'))
    verify_lineage(rows,raw)
    return rows,ledger

def verify_lineage(rows,raw):
    originals=list(csv.DictReader(raw.decode('cp949').splitlines()))
    expected={i+2 for i,r in enumerate(originals) if r['시도명']=='인천광역시' and r['후보자'] not in SPECIAL}
    seen=set();groups={}
    for row in rows:
        if row.get('is_demo') is not False or row.get('election_id')!='KR-20240410-NA22' or row.get('stage')!='FINAL_FILE_AGGREGATION' or row.get('election_date')!='2024-04-10':raise ValueError('invalid official archive scope')
        if row.get('baseline_at') is not None or row.get('count_rate') is not None:raise ValueError('archive must preserve unavailable fields')
        if row.get('source_url')!='https://www.data.go.kr/data/15025527/fileData.do':raise ValueError('wrong archive source')
        if type(row.get('votes')) is not int or row['valid_votes']<=0 or abs(row['votes']/row['valid_votes']*100-row['vote_share'])>.011:raise ValueError('archive vote share mismatch')
        groups.setdefault(row['region_name'],[]).append(row)
        ids=row.get('source_rows',[])
        if not ids or len(ids)!=len(set(ids)):raise ValueError('invalid source lineage')
        total=0
        for i in ids:
            if type(i) is not int or i<2 or i>len(originals)+1 or i in seen:raise ValueError('invalid source row')
            r=originals[i-2]
            if r['시도명']!='인천광역시' or r['선거구명']!=row['region_name'] or r['후보자']!=row['party']+' '+row['candidate_name']:raise ValueError('source candidate or region mismatch')
            total+=int(r['득표수'].replace(',',''));seen.add(i)
        if total!=row['votes']:raise ValueError('source vote sum mismatch')
    if seen!=expected:raise ValueError('official candidate source coverage mismatch')
    if len({r['row_id'] for r in rows})!=len(rows):raise ValueError('duplicate archive identity')
    for group in groups.values():
        if len({r['candidate_id'] for r in group})!=len(group) or len({r['valid_votes'] for r in group})!=1 or sum(r['votes'] for r in group)!=group[0]['valid_votes']:raise ValueError('archive candidate total mismatch')

def snapshot_key(event):
    body=event
    if event.get('mode')=='official' and event.get('stage')=='FINAL_FILE_AGGREGATION':
        body=dict(mode='official',stage=event['stage'],source_sha256=event.get('source_sha256'),rows=event['rows'])
    return hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
