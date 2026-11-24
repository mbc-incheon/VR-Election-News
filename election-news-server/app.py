import asyncio
import hashlib
import json
import os
import secrets
import base64
import io
import zipfile
import sqlite3
from typing import Literal
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import websockets
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from core import Newsroom, now
from production import Production,korean_font

ROOT=Path(os.environ.get('NEWS_DIR','runtime/news'))
room=Newsroom(ROOT)
production=Production(room)
Mode=Literal['official','demo']
connection=dict(state='CONNECTING',error=None,last_received_at=None,mode='unavailable')
UPSTREAM=os.environ.get('UPSTREAM_URL','http://127.0.0.1:8101')

def identity(authorization:str=Header(default='')):
    p=ROOT/'users.json'
    users=json.loads(p.read_text()) if p.exists() else []
    token=authorization.removeprefix('Bearer ')
    hashed=hashlib.sha256(token.encode()).hexdigest()
    user=next((u for u in users if secrets.compare_digest(u['token_hash'],hashed)),None)
    if not user:raise HTTPException(401,'로컬 사용자 토큰이 필요합니다')
    return user

def role(user,*roles):
    if user['role'] not in roles:raise HTTPException(403,'역할 권한이 없습니다')

def seed_demo_documents():
    for i,region in enumerate(['계양구을','연수구을','서구병']):
        for ci in range(2):
            room.add_document(dict(title=f'{region} 가상후보 {chr(65+ci)} 시뮬레이션 공약',publisher='VR 선거보도 시스템 가상 자료실',
                url='demo://fixtures/pledges',published_at='2024-04-01',collected_at='2026-11-20T00:00:00+09:00',
                document_type='campaign',election_id='KR-20240410-NA22',region_name=region,candidate_id=f'DEMO-{i}-{ci}',
                text=('교통 분야에서 환승 편의를 개선하겠다는 가상 공약이다. 추진 일정과 재원은 명시하지 않았다.' if ci==0 else '주거 분야에서 공공임대 상담을 확대하겠다는 가상 공약이다. 추진 일정과 재원은 명시하지 않았다.'),
                is_demo=True,rights='프로젝트 제작 가상 자료'), 'demo-bootstrap')

async def receive_loop():
    while True:
        try:
            # Catch-up before the streaming connection. Replays of duplicate events are idempotent.
            async with httpx.AsyncClient(timeout=5) as client:
                r=await client.get(UPSTREAM+'/events',params={'after':0});r.raise_for_status()
                for event in r.json():room.receive(event)
            async with websockets.connect(UPSTREAM.replace('http','ws',1)+'/ws?after=0',max_size=2**22) as ws:
                connection.update(state='CONNECTED',error=None)
                async for raw in ws:
                    event=json.loads(raw)
                    if event.get('type')=='heartbeat':continue
                    if room.receive(event):connection.update(last_received_at=now(),mode=event['mode'])
        except asyncio.CancelledError:raise
        except Exception as e:
            connection.update(state='DISCONNECTED',error=type(e).__name__+': '+str(e)[:180])
            if os.environ.get('ALLOW_DEMO_FALLBACK','1')=='1':
                # Separate, unmistakably labelled fixture, never relabel old official rows.
                sample=Path(__file__).with_name('fixtures')/'fallback_snapshot.json'
                if sample.exists():
                    event=json.loads(sample.read_text(encoding='utf-8'));event['fallback_at']=now()
                    room.receive(event);connection['mode']='demo'
            await asyncio.sleep(3)

@asynccontextmanager
async def lifespan(app):
    production.recover_interrupted()
    repo=Path(__file__).resolve().parents[1]
    room.import_official_archive(repo/'data/clean/incheon_final_results.json',repo/'data/official_csv_ledger.json',repo/'data/official_raw/NEC_NA22_20240410.csv')
    seed_demo_documents()
    task=asyncio.create_task(receive_loop())
    yield
    task.cancel()
    production.pool.shutdown(wait=False,cancel_futures=True)

app=FastAPI(title='VR 선거보도 시스템',lifespan=lifespan)
app.mount('/static',StaticFiles(directory=Path(__file__).with_name('static')),name='static')
@app.middleware('http')
async def response_headers(request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['X-Frame-Options']='DENY'
    return response
@app.get('/')
def home():return FileResponse(Path(__file__).with_name('index.html'))
@app.get('/studio')
def studio():return FileResponse(Path(__file__).with_name('static')/'studio.html')
@app.get('/api/me')
def me(user=Depends(identity)):return dict(name=user['name'],role=user['role'])
@app.get('/api/capabilities')
def capabilities():return dict(studio='PC_3D',video=bool(korean_font()),ai='UNAVAILABLE',version='2.0.0',official_regions=14)
@app.get('/health')
def health():return dict(status='ok',connection=connection,ai='UNAVAILABLE')
@app.get('/api/snapshot')
def snapshot(mode:Mode|None=None):
    result=room.latest(mode)
    if result.get('mode')=='official':
        return dict(**result,connection=dict(state='ARCHIVE',error=None,mode='official'),review=room.review_state('dataset',result['snapshot_id']))
    return dict(**result,connection=connection)
@app.get('/api/official-results')
def official_results():
    p=Path(__file__).with_name('reference_data')/'incheon_final_results.json'
    return dict(label='공식 파일 집계본 · 독립 검수 전 · 기사 생성에 자동 사용하지 않음',rows=json.loads(p.read_text(encoding='utf-8')) if p.exists() else [])
@app.websocket('/ws')
async def ws(websocket:WebSocket,mode:Mode|None=None):
    await websocket.accept();last=None
    try:
        while True:
            result=dict(**snapshot(mode),screen_updated_at=now())
            value=json.dumps(result,ensure_ascii=False)
            if value!=last:await websocket.send_text(value);last=value
            await asyncio.sleep(1)
    except (WebSocketDisconnect,RuntimeError):pass
@app.get('/api/search')
def search(q:str,region:str,candidate:str,mode:Mode|None=None):return room.search(q,region,candidate,demo=room.latest(mode).get('mode')=='demo')

class Draft(BaseModel):
    region:str=Field(min_length=1,max_length=80)
    mode:Mode|None=None
@app.post('/api/articles')
def draft(req:Draft,user=Depends(identity)):
    role(user,'writer')
    try:return room.draft(req.region,user['name'],req.mode)
    except ValueError as e:raise HTTPException(422,str(e))
@app.get('/api/articles')
def articles(user=Depends(identity)):
    return [json.loads(r[0]) for r in room.db.execute('SELECT payload FROM article ORDER BY rowid DESC')]
@app.get('/api/articles/{aid}')
def get(aid:str,user=Depends(identity)):
    try:return room.get(aid)
    except ValueError as e:raise HTTPException(404,str(e))
@app.post('/api/articles/{aid}/validate')
def validate(aid:str,user=Depends(identity)):
    try:return room.validate(room.get(aid),user['name'])
    except ValueError as e:raise HTTPException(404,str(e))
class Revision(BaseModel):
    title:str=Field(min_length=2,max_length=200)
    sentences:list[dict]=Field(min_length=1,max_length=100)
    reason:str=Field(min_length=5,max_length=2000)
    @field_validator('sentences')
    @classmethod
    def valid_sentences(cls,items):
        for s in items:
            if s.get('kind') not in ['result','pledge'] or not isinstance(s.get('text'),str) or not 1<=len(s['text'])<=5000:raise ValueError('invalid sentence')
            if s['kind']=='result':
                if not isinstance(s.get('values'),dict) or not isinstance(s.get('row_ids'),list) or any(not isinstance(x,str) for x in s['row_ids']):raise ValueError('result reference required')
            else:
                if not all(isinstance(s.get(k),str) for k in ['candidate_id','region_name']) or not all(isinstance(s.get(k),list) and all(isinstance(x,str) for x in s[k]) for k in ['evidence_ids','evidence_hashes']):raise ValueError('pledge reference required')
        return items
@app.post('/api/articles/{aid}/revisions')
def revision(aid:str,req:Revision,user=Depends(identity)):
    role(user,'writer')
    try:
        a=room.get(aid);old=a['id']
        a.update(id=secrets.token_hex(8),parent_id=old,revision=a['revision']+1,author=user['name'],title=req.title,sentences=req.sentences,status='DRAFT',created_at=now(),ai_review=dict(verdict='UNAVAILABLE',model=None))
        for key in ['validation','approved_by','approved_at','approval_reason']:a.pop(key,None)
        room.save(a);room.audit('revision',user['name'],dict(article_id=a['id'],parent_id=old,reason=req.reason));return a
    except ValueError as e:raise HTTPException(404,str(e))
class Approval(BaseModel):
    reason:str=Field(min_length=5)
    evidence_checked:bool
    ai_unavailable_ack:bool=False
@app.post('/api/articles/{aid}/approve')
def approve(aid:str,req:Approval,user=Depends(identity)):
    role(user,'editor')
    try:return room.approve(aid,user['name'],req.reason,req.evidence_checked,req.ai_unavailable_ack)
    except ValueError as e:raise HTTPException(409,str(e))
@app.get('/api/articles/{aid}/export')
def export(aid:str,user=Depends(identity)):
    role(user,'editor')
    try:return room.export(aid)
    except ValueError as e:raise HTTPException(409,str(e))
@app.post('/api/documents')
def document(doc:dict,user=Depends(identity)):
    role(user,'writer')
    try:return dict(chunk_ids=room.add_document(doc,user['name']))
    except ValueError as e:raise HTTPException(422,str(e))
@app.post('/api/chunks/{cid}/retire')
def retire(cid:str,user=Depends(identity)):
    role(user,'editor')
    try:room.retire(cid,user['name']);return dict(status='retired')
    except ValueError as e:raise HTTPException(404,str(e))
@app.get('/api/audit')
def audit(user=Depends(identity)):
    role(user,'editor');return [dict(id=r[0],previous_hash=r[1],hash=r[2],payload=json.loads(r[3])) for r in room.db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 150')]

@app.get('/api/documents')
def documents(user=Depends(identity)):return room.documents(include_inactive=True)

@app.get('/api/reviews')
def reviews(user=Depends(identity)):return room.reviews()

class ReviewDecision(BaseModel):
    approve:bool
    reason:str=Field(min_length=5,max_length=2000)
    original_checked:bool

@app.post('/api/reviews/{rid}')
def review(rid:str,req:ReviewDecision,user=Depends(identity)):
    role(user,'editor')
    try:return room.decide_review(rid,user['name'],req.approve,req.reason,req.original_checked)
    except ValueError as e:raise HTTPException(409,str(e))

class PDFInput(BaseModel):
    content_base64:str=Field(max_length=7000000)
    filename:str=Field(max_length=150)

@app.post('/api/documents/extract-pdf')
def extract_pdf(req:PDFInput,user=Depends(identity)):
    role(user,'writer')
    try:
        from pypdf import PdfReader
        raw=base64.b64decode(req.content_base64,validate=True)
        if len(raw)>5000000 or not raw.startswith(b'%PDF-'):raise ValueError('PDF up to 5 MB required')
        reader=PdfReader(io.BytesIO(raw))
        if reader.is_encrypted or not 1<=len(reader.pages)<=100:raise ValueError('unencrypted PDF, 1-100 pages required')
        pages=[page.extract_text() for page in reader.pages]
        if not any(text.strip() for text in pages):raise ValueError('no text; scanned PDF requires OCR before registration')
        text='\n\n'.join(f'[PDF {i+1}쪽]\n'+text for i,text in enumerate(pages))
        if len(text)>300000:raise ValueError('PDF text too large')
        digest=hashlib.sha256(raw).hexdigest();folder=ROOT/'source_pdf';folder.mkdir(exist_ok=True)
        p=folder/(digest+'.pdf')
        if not p.exists():p.write_bytes(raw);p.chmod(0o444)
        room.audit('pdf_extract',user['name'],dict(sha256=digest,filename=req.filename,pages=len(reader.pages)))
        return dict(text=text,sha256=digest,pages=len(reader.pages))
    except Exception as e:raise HTTPException(422,str(e)[:200])

@app.get('/api/documents/{did}/source')
def document_source(did:str,user=Depends(identity)):
    if not all(c in '0123456789abcdef' for c in did) or len(did)!=20:raise HTTPException(404,'source not found')
    p=ROOT/'raw_documents'/(did+'.json')
    if not p.exists():raise HTTPException(404,'source not found')
    return json.loads(p.read_text(encoding='utf-8'))

@app.get('/api/documents/{did}/pdf')
def document_pdf(did:str,user=Depends(identity)):
    doc=document_source(did,user)
    digest=doc.get('pdf_sha256','')
    if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise HTTPException(404,'PDF not registered')
    p=ROOT/'source_pdf'/(digest+'.pdf')
    if not p.exists():raise HTTPException(404,'PDF not found')
    return FileResponse(p,filename='source.pdf')

@app.get('/api/audit/integrity')
def integrity(user=Depends(identity)):
    role(user,'editor');return room.audit_integrity()

class RenderRequest(BaseModel):
    article_ids:list[str]=Field(min_length=1,max_length=30)
    seconds_per_article:int=Field(default=30,ge=5,le=120)
    narration_wav_base64:str|None=Field(default=None,max_length=85000000)
    narration_disclosure:Literal['none','human','synthetic']='none'

@app.post('/api/production/jobs')
def render(req:RenderRequest,user=Depends(identity)):
    try:return production.submit(req.article_ids,req.seconds_per_article,user['name'],req.narration_wav_base64,req.narration_disclosure)
    except ValueError as e:raise HTTPException(409,str(e))

@app.get('/api/production/jobs')
def render_jobs(user=Depends(identity)):
    with room.lock:ids=[r[0] for r in room.db.execute('SELECT id FROM render_job ORDER BY rowid DESC LIMIT 50')]
    return [production.get(jid) for jid in ids]

@app.get('/api/production/jobs/{jid}')
def render_job(jid:str,user=Depends(identity)):
    try:return production.get(jid)
    except ValueError as e:raise HTTPException(404,str(e))

@app.get('/api/production/jobs/{jid}/files/{name}')
def render_file(jid:str,name:str,user=Depends(identity)):
    try:return FileResponse(production.file(jid,name),filename=name)
    except ValueError as e:raise HTTPException(409,str(e))

@app.get('/api/studio/articles')
def studio_articles():
    with room.lock:ids=[r[0] for r in room.db.execute("SELECT id FROM article WHERE status='APPROVED' ORDER BY rowid DESC LIMIT 100")]
    bundles=[]
    for aid in ids:
        try:bundles.append(room.export(aid))
        except ValueError:pass
    return bundles

@app.get('/api/backup')
def backup(user=Depends(identity)):
    role(user,'editor')
    folder=ROOT/'backups'/secrets.token_hex(8);folder.mkdir(parents=True)
    dbfile=folder/'news.sqlite'
    with room.lock,sqlite3.connect(dbfile) as target:room.db.backup(target)
    destination=folder/'news-backup.zip'
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.write(dbfile,'news.sqlite')
        for directory in ['raw_documents','source_pdf']:
            for p in (ROOT/directory).glob('*') if (ROOT/directory).exists() else []:
                if p.is_file():archive.write(p,directory+'/'+p.name)
        archive.writestr('README.txt','DB와 원문 백업입니다. users.json과 토큰, 제작 영상은 포함하지 않습니다. 복구 전 서비스를 중지하고 기존 파일을 보존하세요.')
    room.audit('backup',user['name'],dict(filename=destination.name))
    return FileResponse(destination,filename='news-backup.zip')
