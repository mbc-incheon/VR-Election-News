"""Local teaching service. Historical election, synthetic replay, never a live result."""
import asyncio
import hashlib
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from election_common import load_official
from election_simulation import simulation_rows

from fastapi import FastAPI, HTTPException, Header, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

ROOT = Path(os.environ.get('DATA_DIR', 'runtime/data'))
KST = timezone(timedelta(hours=9))
def now(): return datetime.now(KST).isoformat()
def digest(data): return hashlib.sha256(data).hexdigest()

class SavedEvents:
    """Index preserved files by sequence, reading only requested event pages."""
    def __init__(self,folder):
        self.folder=Path(folder)
        self.paths=sorted(self.folder.glob('*.json'))
        self.sequences=[int(path.stem) for path in self.paths]
        self._cache=(None,None)
    @property
    def cached_event(self):return self._cache[1]
    def __len__(self):return len(self.paths)
    def __getitem__(self,index):
        if index<0:index+=len(self.paths)
        if index<0 or index>=len(self.paths):raise IndexError(index)
        cached_index,cached_event=self._cache
        if index==cached_index:return cached_event
        event=json.loads(self.paths[index].read_text(encoding='utf-8'))
        self._cache=(index,event)
        return event
    def append(self,event):
        self.paths.append(self.folder/f"{event['sequence']:08d}.json")
        self.sequences.append(event['sequence'])
        self._cache=(len(self.paths)-1,event)
    def after(self,sequence,limit=None):
        from bisect import bisect_right
        start=bisect_right(self.sequences,sequence)
        end=len(self.paths) if limit is None else min(len(self.paths),start+limit)
        return [self[index] for index in range(start,end)]

class Store:
    def __init__(self, root):
        self.root = Path(root)
        (self.root / 'raw').mkdir(parents=True, exist_ok=True)
        (self.root / 'clean').mkdir(exist_ok=True)
        self.events = SavedEvents(self.root/'clean')
        self.error = None
        self.demo_step = 0

    def append(self, payload, url, status=200):
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        seq = len(self.events)+1
        stamp = now()
        raw = self.root/'raw'/f'{seq:08d}_{digest(body)[:12]}.json'
        with raw.open('xb') as f: f.write(body)
        raw.chmod(0o444)
        ledger = dict(sequence=seq, url=url, collected_at=stamp, response_status=status,
                      raw_file=str(raw), sha256=digest(body), mode=payload['mode'])
        with (self.root/'ledger.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(ledger, ensure_ascii=False)+'\n')
        event = dict(sequence=seq, collected_at=stamp, **payload)
        (self.root/'clean'/f'{seq:08d}.json').write_text(json.dumps(event,ensure_ascii=False,indent=2),encoding='utf-8')
        self.events.append(event)
        return event

    def demo(self):
        progress = self.demo_step % 101
        self.demo_step += 1
        rows = simulation_rows(progress, len(self.events)+1)
        return self.append(dict(mode='demo', label='시뮬레이션 데이터 · 0~100% 반복',
            election_id='KR-20240410-NA22', historical_replay=True,
            simulation_progress=progress, simulation_cycle=(self.demo_step-1)//101+1,
            rows=rows), 'demo://fixtures/ballots')

    def archive(self):
        rows,ledger=load_official(Path(__file__).resolve().parents[1])
        if any(e.get('stage')=='FINAL_FILE_AGGREGATION' and e.get('source_sha256')==ledger['sha256'] and e['rows']==rows for e in self.events):return
        self.append(dict(mode='official',election_id='KR-20240410-NA22',stage='FINAL_FILE_AGGREGATION',rows=rows,source_sha256=ledger['sha256'],source_collected_at=ledger['collected_at'],label='2024년 공식 결과 파일 집계 · 독립 검수 필요'),ledger['catalog_url'])

def validate_official(payload):
    if payload.get('mode')!='official': raise ValueError('mode must be official')
    rows=payload.get('rows',[])
    if not rows: raise ValueError('empty rows')
    groups={}
    for r in rows:
        if r.get('is_demo') is not False: raise ValueError('official rows require is_demo=false')
        if r['election_id']!='KR-20240410-NA22': raise ValueError('wrong election')
        if not r['source_url'].startswith(('https://info.nec.go.kr/','https://data.nec.go.kr/','https://www.data.go.kr/')):
            raise ValueError('official source required')
        if not all(r.get(x) for x in ['row_id','candidate_id','candidate_name','region_id','region_name']): raise ValueError('missing identity')
        t=datetime.fromisoformat(r['baseline_at'])
        if t.tzinfo is None or t.year!=2024: raise ValueError('historical timezone required')
        if type(r['votes']) is not int or r['votes']<0 or r['valid_votes']<=0: raise ValueError('invalid votes')
        if abs(r['votes']/r['valid_votes']*100-r['vote_share'])>0.011: raise ValueError('share mismatch')
        if not 0<=r['count_rate']<=100: raise ValueError('invalid count rate')
        groups.setdefault(r['region_id'],[]).append(r)
    if len({r['row_id'] for r in rows})!=len(rows): raise ValueError('duplicate row id')
    for group in groups.values():
        if len({r['candidate_id'] for r in group})!=len(group): raise ValueError('duplicate candidate')
        if len({(r['valid_votes'],r['baseline_at'],r['count_rate']) for r in group})!=1: raise ValueError('mixed group')
        if sum(r['votes'] for r in group)!=group[0]['valid_votes']: raise ValueError('incomplete candidates')
    return payload

store=Store(ROOT)
async def clock_loop():
    mode=os.environ.get('DATA_MODE','hybrid')
    while True:
        if mode in ['demo','hybrid']: store.demo()
        await asyncio.sleep(float(os.environ.get('DATA_INTERVAL','1')))

@asynccontextmanager
async def lifespan(app):
    if os.environ.get('DATA_MODE','hybrid') in ['official','hybrid']:store.archive()
    task=asyncio.create_task(clock_loop())
    yield
    task.cancel()

app=FastAPI(title='VR 선거보도 시스템 · 데이터 송신',lifespan=lifespan)
@app.get('/health')
def health(): return dict(status='ok',mode=os.environ.get('DATA_MODE','hybrid'),error=store.error)
@app.get('/snapshot')
def snapshot(): return store.events[-1] if store.events else dict(sequence=0,mode='unavailable',rows=[])
@app.get('/events')
def events(after:int=0,limit:int|None=Query(default=None,ge=1,le=1000)):
    if isinstance(store.events,SavedEvents):return store.events.after(after,limit)
    pending=(e for e in store.events if e['sequence']>after)
    if limit is None:return list(pending)
    from itertools import islice
    return list(islice(pending,limit))
@app.post('/ingest')
def ingest(payload:dict,authorization:str=Header(default='')):
    token=os.environ.get('INGEST_TOKEN')
    if not token or authorization!='Bearer '+token: raise HTTPException(401,'ingest token required')
    try: validate_official(payload)
    except (ValueError,KeyError,TypeError) as e: raise HTTPException(422,str(e))
    return store.append(payload,payload['rows'][0]['source_url'])
@app.websocket('/ws')
async def ws(websocket:WebSocket,after:int=0):
    await websocket.accept()
    try:
        while True:
            pending=store.events.after(after) if isinstance(store.events,SavedEvents) else [e for e in store.events if e['sequence']>after]
            for e in pending:
                await websocket.send_json(e); after=e['sequence']
            if not pending: await websocket.send_json(dict(type='heartbeat',server_at=now()))
            await asyncio.sleep(1)
    except (WebSocketDisconnect,RuntimeError): pass
