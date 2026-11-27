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
from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from core import Newsroom, now
from election_simulation import DEMO_CANDIDATES
from production import Production,korean_font
from article_narration import ArticleNarration
from admin_auth import AdminAuth
from admin_recovery import AdminRecovery
from google_news import search_google_news

ROOT=Path(os.environ.get('NEWS_DIR','runtime/news'))
room=Newsroom(ROOT)
admin_auth=AdminAuth(ROOT)
admin_recovery=AdminRecovery(admin_auth)
production=Production(room)
article_narration=ArticleNarration(room)
Mode=Literal['official','demo']
connection=dict(state='CONNECTING',error=None,last_received_at=None,mode='unavailable')
UPSTREAM=os.environ.get('UPSTREAM_URL','http://127.0.0.1:8101')

LOCAL_WRITER_SESSION=secrets.token_urlsafe(32)
def local_writer_allowed(request):
    from urllib.parse import urlsplit
    return (os.environ.get('LOCAL_WRITER_ACCESS','0')=='1'
            and request.client is not None and request.client.host in ('127.0.0.1','::1')
            and urlsplit(str(request.base_url)).hostname in ('127.0.0.1','localhost','::1'))

def identity(request:Request,authorization:str=Header(default='')):
    token=authorization[6:].strip() if authorization.startswith('Bearer') else authorization.strip()
    if not token:
        admin=admin_auth.session(request.cookies.get('staff_session','')) or admin_auth.session(request.cookies.get('admin_session',''))
        if admin:
            if request.method not in ('GET','HEAD','OPTIONS'):same_origin(request)
            return admin
    if (not token and local_writer_allowed(request)
            and secrets.compare_digest(request.cookies.get('local_writer',''),LOCAL_WRITER_SESSION)):
        return dict(name='local-writer',role='writer')
    p=ROOT/'users.json'
    users=json.loads(p.read_text(encoding='utf-8-sig')) if p.exists() else []
    hashed=hashlib.sha256(token.encode()).hexdigest()
    user=next((u for u in users if u.get('active',True) and secrets.compare_digest(u['token_hash'],hashed)),None)
    if not user:raise HTTPException(401,'로컬 사용자 토큰이 필요합니다')
    return user

def role(user,*roles):
    if user['role'] not in roles and not (user['role']=='admin' and set(roles)&{'writer','editor'}):raise HTTPException(403,'역할 권한이 없습니다')

def seed_demo_documents():
    # Keep original documents in storage, but retire only superseded auto-generated profiles.
    for doc in room.documents():
        if (doc.get('is_demo') and doc.get('publisher')=='VR 선거보도 시스템 가상 자료실'
                and doc.get('url')=='demo://fixtures/pledges'
                and not any(doc.get('title')==f"{doc.get('region_name')} {profile['name']} 가상 공약" for profile in DEMO_CANDIDATES)):
            for chunk in doc['chunks']:room.retire(chunk['id'],'demo-profile-update')
    for i,region in enumerate(['하늘도시갑','연수구을','서구병']):
        for ci,profile in enumerate(DEMO_CANDIDATES):
            room.add_document(dict(title=f"{region} {profile['name']} 가상 공약",publisher='VR 선거보도 시스템 가상 자료실',
                url='demo://fixtures/pledges',published_at='2024-04-01',collected_at='2026-11-25T00:00:00+09:00',
                document_type='campaign',election_id='KR-20240410-NA22',region_name=region,candidate_id=f'DEMO-{i}-{ci}',
                text=f"{profile['name']}({profile['party']}, 가상 정당)은 {profile['pledge']} 이 내용은 사용자 설정의 가상 공약이며 실제 후보의 공약이 아니다. 구체적인 일정·예산은 설정하지 않았다.",
                is_demo=True,rights='프로젝트 제작 가상 자료'), 'demo-bootstrap')

async def receive_loop():
    while True:
        try:
            # Resume after preserved events instead of replaying the entire growing archive.
            cursor=room.db.execute('SELECT COALESCE(MAX(sequence),0) FROM snapshot').fetchone()[0]
            async with httpx.AsyncClient(timeout=5) as client:
                while True:
                    r=await client.get(UPSTREAM+'/events',params={'after':cursor,'limit':100});r.raise_for_status()
                    batch=r.json()
                    for event in batch:
                        room.receive(event);cursor=max(cursor,event['sequence'])
                        connection.update(state='CONNECTED',error=None,last_received_at=now(),mode=event['mode'])
                    if len(batch)<100:break
            async with websockets.connect(UPSTREAM.replace('http','ws',1)+'/ws?after='+str(cursor),max_size=2**22) as ws:
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
    if os.environ.get('LOCAL_WRITER_ACCESS','0')=='1':admin_recovery.ensure()
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
    if request.url.path.startswith(('/admin','/api/admin','/login','/api/session')):response.headers['Cache-Control']='no-store'
    return response
@app.get('/')
def home():return FileResponse(Path(__file__).with_name('index.html'))
@app.get('/studio')
def studio():return FileResponse(Path(__file__).with_name('static')/'studio.html')

@app.get('/api/google-news')
async def google_news(region:str=Query(default='',max_length=60),candidate:str=Query(default='',max_length=60),
                      start:str=Query(default='2024-04-03',pattern=r'^\d{4}-\d{2}-\d{2}$'),
                      end:str=Query(default='2024-04-17',pattern=r'^\d{4}-\d{2}-\d{2}$'),
                      period:Literal['all','선거 전','선거 당일','선거 후']='all'):
    try:
        result=await search_google_news(region,candidate,start,end,period)
        return dict(**result, references=room.retain_google_news(result['items'],region,candidate))
    except ValueError:raise HTTPException(400,'검색 날짜 또는 응답 형식을 확인하세요.')
    except Exception:raise HTTPException(502,'구글 뉴스 검색에 연결하지 못했습니다. 잠시 후 다시 검색하거나 구글 뉴스에서 직접 확인하세요.')

def same_origin(request):
    if request.headers.get('origin')!=str(request.base_url).rstrip('/'):
        raise HTTPException(403,'현재 업무 화면에서 다시 요청해 주세요.')

@app.get('/admin/login')
def admin_login_page():return RedirectResponse('/login',status_code=303)

@app.get('/admin')
def admin_page(request:Request):
    if (admin_auth.session(request.cookies.get('admin_session','')) or {}).get('role')!='admin':return RedirectResponse('/login',status_code=303)
    return FileResponse(Path(__file__).with_name('static')/'admin.html')

class AdminLogin(BaseModel):
    name:str=Field(min_length=2,max_length=40)
    token:str=Field(min_length=1,max_length=256)

@app.post('/api/admin/login')
def admin_login(req:AdminLogin,request:Request):
    same_origin(request)
    secret=admin_auth.login(req.name,req.token,request.client.host if request.client else 'unknown')
    room.audit('admin_login',req.name,{})
    response=JSONResponse(dict(name=req.name,role='admin'))
    response.set_cookie('admin_session',secret,max_age=28800,httponly=True,samesite='strict',secure=request.url.scheme=='https')
    admin_auth.logout(request.cookies.get('staff_session',''))
    response.delete_cookie('staff_session')
    response.delete_cookie('local_writer')
    response.headers['Cache-Control']='no-store'
    return response

@app.get('/api/admin/recovery/status')
def admin_recovery_status(request:Request):
    return dict(available=local_writer_allowed(request))

class AdminReset(BaseModel):
    name:str=Field(min_length=2,max_length=40)
    method:Literal['current_token','recovery_code']
    verification:str=Field(min_length=1,max_length=256)
    confirmed:bool

@app.post('/api/admin/recovery/reset')
def admin_recovery_reset(req:AdminReset,request:Request):
    if not local_writer_allowed(request):raise HTTPException(403,'관리자 복구는 시스템을 실행한 PC에서만 사용할 수 있습니다.')
    same_origin(request)
    if not req.confirmed:raise HTTPException(422,'기존 관리자 토큰과 세션 만료를 확인해 주세요.')
    result=admin_recovery.reset(req.name,req.verification,req.method,request.client.host)
    room.audit('admin_token_recovered',req.name,dict(method=req.method))
    response=JSONResponse(result,headers={'Cache-Control':'no-store'})
    response.delete_cookie('admin_session')
    return response

@app.post('/api/admin/logout')
def admin_logout(request:Request):
    same_origin(request)
    admin_auth.logout(request.cookies.get('admin_session',''))
    response=JSONResponse(dict(ok=True))
    response.delete_cookie('admin_session')
    return response

@app.get('/api/admin/users')
def admin_users(user=Depends(identity)):
    role(user,'admin')
    return admin_auth.listing()

class NewUser(BaseModel):
    name:str=Field(min_length=2,max_length=40)
    role:Literal['writer','editor']
    display_name:str=Field(default='',max_length=80)

@app.post('/api/admin/users')
def admin_create_user(req:NewUser,user=Depends(identity)):
    role(user,'admin')
    created=admin_auth.create(req.name,req.role,req.display_name.strip() or req.name)
    room.audit('account_created',user['name'],dict(name=req.name,role=req.role))
    return JSONResponse(created,headers={'Cache-Control':'no-store'})


class UserProfile(BaseModel):
    display_name:str=Field(min_length=1,max_length=80)
    active:bool

@app.post('/api/admin/users/{name}/profile')
def update_account(name:str,req:UserProfile,user=Depends(identity)):
    role(user,'admin')
    if not req.display_name.strip():raise HTTPException(422,'담당자 이름을 입력하세요.')
    result=admin_auth.profile(name,req.display_name.strip(),req.active)
    room.audit('account_updated',user['name'],dict(name=name,display_name=result['display_name'],active=req.active))
    return result

@app.post('/api/admin/users/{name}/token')
def rotate_account_token(name:str,user=Depends(identity)):
    role(user,'admin')
    result=admin_auth.rotate(name)
    room.audit('account_token_rotated',user['name'],dict(name=name))
    return JSONResponse(result,headers={'Cache-Control':'no-store'})

@app.get('/api/admin/history')
def account_history(user=Depends(identity)):
    role(user,'admin')
    rows=room.db.execute('SELECT payload FROM audit ORDER BY rowid DESC').fetchall()
    kinds={'admin_login','staff_login','account_created','account_updated','account_token_rotated','session_logout','admin_token_recovered'}
    return [json.loads(row[0]) for row in rows if json.loads(row[0]).get('kind') in kinds][:100]

@app.get('/login')
def staff_login_page():return FileResponse(Path(__file__).with_name('static')/'login.html')

@app.post('/api/session/login')
def staff_login(req:AdminLogin,request:Request):
    same_origin(request)
    secret=admin_auth.login(req.name,req.token,request.client.host if request.client else 'unknown',roles=('admin','writer','editor'))
    staff=admin_auth.session(secret)
    for cookie in ('admin_session','staff_session'):admin_auth.logout(request.cookies.get(cookie,''))
    cookie='admin_session' if staff['role']=='admin' else 'staff_session'
    response=JSONResponse(dict(**staff,next='/admin' if staff['role']=='admin' else '/'))
    response.set_cookie(cookie,secret,max_age=28800,httponly=True,samesite='strict',secure=request.url.scheme=='https')
    response.delete_cookie('staff_session' if cookie=='admin_session' else 'admin_session');response.delete_cookie('local_writer')
    response.headers['Cache-Control']='no-store'
    room.audit('admin_login' if staff['role']=='admin' else 'staff_login',req.name,dict(role=staff['role']))
    return response

@app.post('/api/session/logout')
def staff_logout(request:Request):
    same_origin(request)
    user=admin_auth.session(request.cookies.get('staff_session','')) or admin_auth.session(request.cookies.get('admin_session',''))
    for cookie in ('staff_session','admin_session'):admin_auth.logout(request.cookies.get(cookie,''))
    response=JSONResponse(dict(ok=True))
    for cookie in ('staff_session','admin_session','local_writer'):response.delete_cookie(cookie)
    if user:room.audit('session_logout',user['name'],{})
    return response

@app.post('/api/session/local-writer')
def local_writer_session(request:Request):
    if not local_writer_allowed(request):raise HTTPException(403,'이 PC의 로컬 실행에서만 작성자 연결을 사용할 수 있습니다.')
    if request.headers.get('origin')!=str(request.base_url).rstrip('/'):
        raise HTTPException(403,'업무 화면에서 작성자 연결을 요청해 주세요.')
    response=JSONResponse(dict(name='local-writer',role='writer'))
    response.set_cookie('local_writer',LOCAL_WRITER_SESSION,httponly=True,samesite='strict',max_age=28800)
    room.audit('local_writer_login','local-writer',dict(role='writer'))
    return response

class AdminWorkMode(BaseModel):
    mode:Literal['writer','editor','approval']

@app.get('/api/admin/work-mode')
def admin_work_mode(request:Request,user=Depends(identity)):
    role(user,'admin')
    secret=request.cookies.get('staff_session','') or request.cookies.get('admin_session','')
    return dict(mode=admin_auth.work_mode(secret),account=user['name'])

@app.post('/api/admin/work-mode')
def set_admin_work_mode(req:AdminWorkMode,request:Request,user=Depends(identity)):
    role(user,'admin');same_origin(request)
    secret=request.cookies.get('staff_session','') or request.cookies.get('admin_session','')
    previous=admin_auth.work_mode(secret)
    mode=admin_auth.work_mode(secret,req.mode)
    room.audit('admin_work_mode',user['name'],dict(previous=previous,mode=mode,account_role='admin'))
    return dict(mode=mode,account=user['name'])

@app.get('/api/me')
def me(user=Depends(identity)):return dict(name=user['name'],role=user['role'])
@app.get('/api/capabilities')
def capabilities(request:Request):return dict(local_writer_available=local_writer_allowed(request),studio='PC_3D',video=bool(korean_font()),ai='UNAVAILABLE',version='2.0.0',official_regions=14)
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

@app.get('/api/pledge-context')
def pledge_context(region:str,candidate:str,mode:Mode='official'):
    try:return room.pledge_context(region,candidate,mode)
    except ValueError as error:raise HTTPException(422,str(error))

class Draft(BaseModel):
    region:str=Field(min_length=1,max_length=80)
    mode:Mode|None=None
    article_type:Literal['combined','result','pledge','news']='combined'
    candidate_id:str|None=Field(default=None,max_length=100)
    news_ids:list[str]=Field(default_factory=list,max_length=60)
    period_from:str='2024-04-03'
    period_to:str='2024-04-17'
    title:str|None=Field(default=None,min_length=2,max_length=200)
    evidence_ids:list[str]|None=Field(default=None,max_length=100)
@app.post('/api/articles')
def draft(req:Draft,user=Depends(identity)):
    role(user,'writer')
    try:return room.draft(req.region,user['name'],req.mode,req.article_type,req.candidate_id,req.news_ids,req.period_from,req.period_to,req.title,req.evidence_ids)
    except ValueError as e:raise HTTPException(422,str(e))
@app.post('/api/production/default-articles')
def production_default_articles(user=Depends(identity)):
    role(user,'writer')
    try:return room.ensure_haneul_articles(user['name'])
    except ValueError as error:raise HTTPException(422,str(error))

@app.get('/api/articles')
def articles(user=Depends(identity)):
    return [a for r in room.db.execute('SELECT payload FROM article ORDER BY rowid DESC') if not (a:=json.loads(r[0])).get('deleted_at')]
@app.post('/api/articles/{aid}/delete')
def delete_article(aid:str,user=Depends(identity)):
    role(user,'writer')
    try:return room.archive_article(aid,user['name'],admin=user['role']=='admin')
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(404,str(e))

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
            if s.get('kind') not in ['result','pledge','news'] or not isinstance(s.get('text'),str) or not 1<=len(s['text'])<=5000:raise ValueError('invalid sentence')
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
        a.update(summary=req.sentences[0]['text'],id=secrets.token_hex(8),parent_id=old,revision=a['revision']+1,author=user['name'],title=req.title,sentences=req.sentences,status='DRAFT',created_at=now(),ai_review=dict(verdict='UNAVAILABLE',model=None))
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

class NarrationRequest(BaseModel):
    article_ids:list[str]=Field(min_length=1,max_length=30)

@app.post('/api/production/narration/cached')
def cached_article_narration(req:NarrationRequest,user=Depends(identity)):
    try:return article_narration.cached(req.article_ids)
    except ValueError as error:raise HTTPException(409,str(error))

@app.post('/api/production/narration')
async def create_article_narration(req:NarrationRequest,request:Request,user=Depends(identity)):
    same_origin(request)
    try:return await asyncio.to_thread(article_narration.create,req.article_ids,user['name'])
    except ValueError as e:raise HTTPException(409,str(e))

@app.get('/api/production/narration/{nid}/audio')
def get_article_narration(nid:str,user=Depends(identity)):
    try:return FileResponse(article_narration.file(nid),media_type='audio/wav',headers={'Cache-Control':'no-store'})
    except ValueError as e:raise HTTPException(409,str(e))

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
