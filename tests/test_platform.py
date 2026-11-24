import base64
import hashlib
import importlib.util
import io
import json
import sqlite3
import sys
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'election-news-server'))
from core import Newsroom
from production import Production,korean_font,render_bundle

@pytest.fixture
def official(tmp_path):
    room=Newsroom(tmp_path)
    room.import_official_archive(ROOT/'data/clean/incheon_final_results.json',ROOT/'data/official_csv_ledger.json',ROOT/'data/official_raw/NEC_NA22_20240410.csv')
    yield room
    room.db.close()

def add_test_pledge(room):
    row=room.latest('official')['rows'][0]
    ids=room.add_document(dict(title='TEST fixture, not an actual pledge',publisher='TEST',url='https://library.nec.go.kr/TEST-NOT-A-REAL-DOCUMENT',
        published_at='2024-04-01',collected_at='2026-11-24T00:00:00+09:00',document_type='campaign',election_id=row['election_id'],
        region_name=row['region_name'],candidate_id=row['candidate_id'],text='TEST 교통 검증용 문장이다. 실제 후보의 공약으로 보도하지 않는다.',
        is_demo=False,rights='TEST fixture',human_verified=True),'TEST-writer')
    return row,ids

def approve_inputs(room):
    for review in room.reviews():
        room.decide_review(review['id'],'TEST-editor',True,'TEST 자동시험, 실제 편집 검수 아님',True)

def test_official_mode_keeps_missing_time_and_counts(official):
    snapshot=official.latest('official')
    assert len(snapshot['rows'])==38
    assert len({r['region_name'] for r in snapshot['rows']})==14
    assert all(r['baseline_at'] is None and r['count_rate'] is None for r in snapshot['rows'])
    row=snapshot['rows'][0]
    article=official.draft(row['region_name'],'TEST-writer','official')
    validated=official.validate(article)
    assert 'DATASET_REVIEW_REQUIRED' in validated['validation']['errors']
    assert 'NO_PLEDGE_EVIDENCE' in validated['validation']['errors']
    assert 'None' not in article['sentences'][0]['text']
    assert '공식 파일 집계' in article['sentences'][0]['text']

def test_official_input_independent_review_and_revocation(official):
    row,ids=add_test_pledge(official)
    article=official.draft(row['region_name'],'TEST-writer','official')
    with pytest.raises(ValueError):official.approve(article['id'],'TEST-editor','TEST 승인 차단 확인',True,True)
    document_review=next(r for r in official.reviews() if r['kind']=='document')
    with pytest.raises(ValueError,match='independent'):official.decide_review(document_review['id'],'TEST-writer',True,'TEST 자기 검수 시도',True)
    approve_inputs(official)
    assert official.validate(official.get(article['id']))['validation']['rule']=='PASS'
    official.approve(article['id'],'TEST-editor','TEST 자동 승인, 사람 승인 아님',True,True)
    assert official.export(article['id'])['article']['mode']=='official'
    official.decide_review(document_review['id'],'TEST-editor',False,'TEST 근거 검수 철회 확인',True)
    assert official.get(article['id'])['status']=='REVIEW_REQUIRED'
    with pytest.raises(ValueError):official.export(article['id'])

def test_dataset_revocation_blocks_export(official):
    row,_=add_test_pledge(official);approve_inputs(official)
    article=official.draft(row['region_name'],'TEST-writer','official');official.approve(article['id'],'TEST-editor','TEST 독립 승인 확인',True,True)
    review=next(r for r in official.reviews() if r['kind']=='dataset')
    official.decide_review(review['id'],'TEST-editor',False,'TEST 집계 재검토 요청',True)
    with pytest.raises(ValueError):official.export(article['id'])

def test_archive_hash_tampering_rejected(official,tmp_path):
    altered=tmp_path/'modified.csv';altered.write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash mismatch'):official.import_official_archive(ROOT/'data/clean/incheon_final_results.json',ROOT/'data/official_csv_ledger.json',altered)
    event=official.latest('official');event.pop('snapshot_id');event['rows'][0]['votes']+=1
    with pytest.raises(ValueError):official.receive(event)

@pytest.mark.parametrize('change',[{'url':'https://untrusted.invalid/claim'},{'election_id':'WRONG'},{'published_at':'bad-date'},{'is_demo':'false'}])
def test_invalid_official_documents(official,change):
    row=official.latest('official')['rows'][0]
    doc=dict(title='TEST',publisher='TEST',url='https://library.nec.go.kr/TEST',published_at='2024-04-01',collected_at='2026-11-24T00:00:00+09:00',document_type='campaign',election_id=row['election_id'],region_name=row['region_name'],candidate_id=row['candidate_id'],text='TEST 교통',is_demo=False,rights='TEST',human_verified=True)
    doc.update(change)
    with pytest.raises(ValueError):official.add_document(doc,'TEST-writer')

def test_unapproved_render_rejected(official):
    row=official.latest('official')['rows'][0];article=official.draft(row['region_name'],'TEST-writer','official')
    with pytest.raises(ValueError):official.prepare_render([article['id']])
    with pytest.raises(ValueError):official.prepare_render([])

def test_platform_schema_matches_distribution(tmp_path):
    assert (ROOT/'election-news-server/platform_schema.sql').read_bytes()==(ROOT/'db/004_workflow.sql').read_bytes()
    room=Newsroom(tmp_path)
    room.db.execute("INSERT INTO render_job VALUES('TEST-interrupted','TEST','RUNNING','{}','2026-11-24')");room.db.commit()
    producer=Production(room)
    try:
        assert producer.get('TEST-interrupted')['status']=='RUNNING'
        producer.recover_interrupted()
        assert producer.get('TEST-interrupted')['status']=='FAILED'
    finally:producer.pool.shutdown();room.db.close()

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('NEWS_DIR',str(tmp_path));monkeypatch.setenv('UPSTREAM_URL','http://127.0.0.1:9')
    users=[dict(name='TEST-'+role,role=role,token_hash=hashlib.sha256(('TEST-'+role).encode()).hexdigest()) for role in ['writer','editor']]
    (tmp_path/'users.json').write_text(json.dumps(users))
    spec=importlib.util.spec_from_file_location('platform_api_'+tmp_path.name,ROOT/'election-news-server/app.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with TestClient(module.app) as c:yield c,module
    module.room.db.close()

def auth(role='writer'):return {'Authorization':'Bearer TEST-'+role}

def test_platform_api_auth_and_modes(client):
    c,module=client
    assert c.get('/api/snapshot?mode=official').json()['mode']=='official'
    assert len(c.get('/api/snapshot?mode=official').json()['rows'])==38
    assert c.get('/api/me').status_code==401
    assert c.get('/api/me',headers=auth()).json()['role']=='writer'
    assert c.get('/api/reviews').status_code==401
    review=c.get('/api/reviews',headers=auth()).json()[0]
    body=dict(approve=True,reason='TEST fixture reason',original_checked=True)
    assert c.post('/api/reviews/'+review['id'],json=body,headers=auth()).status_code==403
    assert c.get('/studio').status_code==200
    assert c.get('/static/vendor/three.module.js').status_code==200
    assert c.get('/api/capabilities').json()['studio']=='PC_3D'

def test_bad_pdf_and_revision_do_not_crash(client):
    c,module=client
    assert c.post('/api/documents/extract-pdf',headers=auth(),json=dict(filename='bad.pdf',content_base64='invalid')).status_code==422
    body=dict(title='TEST title',reason='TEST reason',sentences=[dict(kind='result',text='TEST')])
    assert c.post('/api/articles/missing/revisions',headers=auth(),json=body).status_code==422
    assert c.post('/api/chunks/missing/retire',headers=auth('editor')).status_code==404

def test_scanned_pdf_requires_ocr(client):
    from pypdf import PdfWriter
    c,module=client;writer=PdfWriter();writer.add_blank_page(width=100,height=100);stream=io.BytesIO();writer.write(stream)
    response=c.post('/api/documents/extract-pdf',headers=auth(),json=dict(filename='scan.pdf',content_base64=base64.b64encode(stream.getvalue()).decode()))
    assert response.status_code==422
    assert 'OCR' in response.json()['detail']

def test_text_pdf_preserved_and_extracted(client):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
    c,module=client;writer=PdfWriter();page=writer.add_blank_page(width=300,height=200)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream=DecodedStreamObject();stream.set_data(b'BT /F1 14 Tf 10 100 Td (TEST original PDF source.) Tj ET');page[NameObject('/Contents')]=writer._add_object(stream)
    output=io.BytesIO();writer.write(output)
    response=c.post('/api/documents/extract-pdf',headers=auth(),json=dict(filename='test.pdf',content_base64=base64.b64encode(output.getvalue()).decode()))
    assert response.status_code==200,response.text
    data=response.json();assert 'TEST original PDF source.' in data['text']
    assert (module.ROOT/'source_pdf'/(data['sha256']+'.pdf')).read_bytes()==output.getvalue()

def test_backup_and_audit_protected(client):
    c,module=client
    assert c.get('/api/backup',headers=auth()).status_code==403
    response=c.get('/api/backup',headers=auth('editor'));assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        assert 'news.sqlite' in z.namelist()
        assert not any('users.json' in name for name in z.namelist())
    assert c.get('/api/audit/integrity',headers=auth('editor')).json()['valid']

def test_real_fhd_video_and_approval_recheck(tmp_path):
    if not korean_font():pytest.skip('Korean font not installed')
    import imageio_ffmpeg
    room=Newsroom(tmp_path/'news')
    event=json.loads((ROOT/'fixtures/fallback_snapshot.json').read_text(encoding='utf-8'));room.receive(event)
    for row in event['rows']:
        room.add_document(dict(title='TEST video fixture',publisher='TEST',url='demo://TEST',published_at='2024-04-01',collected_at='2026-11-24T00:00:00+09:00',document_type='campaign',election_id=row['election_id'],region_name=row['region_name'],candidate_id=row['candidate_id'],text='TEST 교통 공약, 실제 보도 아님.',is_demo=True,rights='TEST'), 'TEST-writer')
    article=room.draft('계양구을','TEST-writer');room.approve(article['id'],'TEST-editor','TEST 자동 시험 전용',True,True)
    producer=Production(room)
    try:
        with pytest.raises(ValueError,match='declare'):
            producer.submit([article['id']],5,'TEST-writer',audio_disclosure='synthetic')
        job=producer.submit([article['id']],5,'TEST-writer')
        for _ in range(200):
            job=producer.get(job['id'])
            if job['status'] in ['COMPLETED','FAILED']:break
            time.sleep(.15)
        assert job['status']=='COMPLETED',job
        video=producer.file(job['id'],'news.mp4');reader=imageio_ffmpeg.read_frames(str(video));meta=next(reader);reader.close()
        assert meta['size']==(1920,1080) and abs(meta['duration']-5)<.15
        with zipfile.ZipFile(producer.file(job['id'],'news-package.zip')) as z:assert {'news.mp4','subtitles.srt','manifest.json','script.txt'}<=set(z.namelist())
        room.retire(article['sentences'][1]['evidence_ids'][0],'TEST-editor')
        with pytest.raises(ValueError):producer.file(job['id'],'news.mp4')
    finally:producer.pool.shutdown();room.db.close()

def test_local_writer_session_origin_scope_and_permissions(client,monkeypatch):
    monkeypatch.delenv('LOCAL_WRITER_ACCESS',raising=False)
    c,module=client
    from fastapi.testclient import TestClient
    with TestClient(module.app,base_url='http://127.0.0.1',client=('127.0.0.1',50000)) as local:
        origin={'Origin':'http://127.0.0.1'}
        assert local.post('/api/session/local-writer',headers=origin).status_code==403
        monkeypatch.setenv('LOCAL_WRITER_ACCESS','1')
        assert local.get('/api/capabilities').json()['local_writer_available'] is True
        assert local.post('/api/session/local-writer',headers={'Origin':'https://untrusted.example'}).status_code==403
        assert local.post('/api/session/local-writer').status_code==403
        response=local.post('/api/session/local-writer',headers=origin)
        assert response.status_code==200
        assert 'HttpOnly' in response.headers['set-cookie']
        assert local.get('/api/me').json()==dict(name='local-writer',role='writer')
        assert local.get('/api/me',headers={'Authorization':'Bearer'}).status_code==200
        row=local.get('/api/snapshot?mode=official').json()['rows'][0]
        draft=local.post('/api/articles',json=dict(region=row['region_name'],mode='official'))
        assert draft.status_code==200,draft.text
        assert draft.json()['author']=='local-writer'
        assert draft.json()['status']=='DRAFT'
        assert any(a['id']==draft.json()['id'] for a in local.get('/api/articles').json())
        assert local.post('/api/articles/'+draft.json()['id']+'/approve',json=dict(reason='TEST no editor privilege',evidence_checked=True,ai_unavailable_ack=True)).status_code==403
        assert local.get('/api/me',headers={'Authorization':'Bearer invalid'}).status_code==401
    with TestClient(module.app,base_url='http://127.0.0.1',client=('203.0.113.3',50000)) as remote:
        assert remote.post('/api/session/local-writer',headers=origin).status_code==403

def test_admin_login_accounts_logout_and_role_boundaries(client):
    c,module=client
    import hashlib,json
    users=json.loads((module.ROOT/'users.json').read_text())
    users.append(dict(name='admin',role='admin',token_hash=hashlib.sha256(b'TEST-admin-secret').hexdigest()))
    (module.ROOT/'users.json').write_text(json.dumps(users))
    origin={'Origin':'http://testserver'}
    assert c.get('/admin',follow_redirects=False).status_code==303
    assert c.get('/admin/login').status_code==200
    assert c.get('/api/admin/users').status_code==401
    assert c.get('/api/admin/users',headers=auth()).status_code==403
    assert c.post('/api/admin/login',json=dict(name='admin',token='TEST-admin-secret')).status_code==403
    assert c.post('/api/admin/login',headers=origin,json=dict(name='writer',token='TEST-writer')).status_code==401
    login=c.post('/api/admin/login',headers=origin,json=dict(name='admin',token='TEST-admin-secret'))
    assert login.status_code==200
    assert 'HttpOnly' in login.headers['set-cookie']
    assert 'SameSite=strict' in login.headers['set-cookie']
    secret=c.cookies.get('admin_session')
    assert c.get('/admin').status_code==200
    assert c.get('/api/me').json()['role']=='admin'
    listed=c.get('/api/admin/users').json()
    assert all({'name','role','active','display_name'}<=set(u) and 'token_hash' not in u and 'token' not in u for u in listed)
    assert c.post('/api/admin/users',json=dict(name='new-reporter',role='writer')).status_code==403
    issued=c.post('/api/admin/users',headers=origin,json=dict(name='new-reporter',role='writer'))
    assert issued.status_code==200,issued.text
    token=issued.json()['token']
    assert c.get('/api/me',headers={'Authorization':'Bearer '+token}).json()==dict(name='new-reporter',role='writer')
    assert token not in (module.ROOT/'users.json').read_text()
    assert c.post('/api/admin/users',headers=origin,json=dict(name='new-reporter',role='editor')).status_code==409
    assert c.post('/api/admin/users',headers=origin,json=dict(name='bad<script>',role='writer')).status_code==422
    assert c.post('/api/admin/users',headers=origin,json=dict(name='anotheradmin',role='admin')).status_code==422
    assert c.post('/api/articles',headers=origin,json=dict(region='계양구갑',mode='official')).status_code==403
    assert c.post('/api/admin/logout',headers=origin,json={}).status_code==200
    assert c.get('/api/admin/users',headers={'Cookie':'admin_session='+secret}).status_code==401
    assert token not in str(module.room.db.execute('SELECT payload FROM audit').fetchall())


def test_admin_throttle_and_session_revocation(client):
    c,module=client
    from admin_auth import AdminAuth
    from fastapi import HTTPException
    manager=AdminAuth(module.ROOT)
    users=manager.users();users.append(dict(name='admin',role='admin',token_hash=hashlib.sha256(b'TEST-admin').hexdigest()));manager.write(users)
    for _ in range(5):
        with pytest.raises(HTTPException) as error:manager.login('admin','wrong','TEST-peer')
        assert error.value.status_code==401
    with pytest.raises(HTTPException) as error:manager.login('admin','TEST-admin','TEST-peer')
    assert error.value.status_code==429
    secret=manager.login('admin','TEST-admin','other-peer')
    assert manager.session(secret)['role']=='admin'
    users[-1]['token_hash']=hashlib.sha256(b'rotated').hexdigest();manager.write(users)
    assert manager.session(secret) is None


def test_admin_bootstrap_preserves_existing_users(tmp_path):
    import subprocess
    root=tmp_path/'accounts';root.mkdir();existing=[dict(name='writer',role='writer',token_hash='TEST-preserved')]
    (root/'users.json').write_text(json.dumps(existing))
    command=[sys.executable,str(ROOT/'scripts/init_users.py'),'--root',str(root),'--add-admin']
    first=subprocess.run(command,capture_output=True,text=True)
    assert first.returncode==0,first.stderr
    users=json.loads((root/'users.json').read_text())
    assert users[0]==existing[0]
    assert users[1]['role']=='admin'
    before=(root/'users.json').read_bytes()
    assert subprocess.run(command,capture_output=True).returncode!=0
    assert (root/'users.json').read_bytes()==before

def test_staff_accounts_session_lifecycle_and_secret_redaction(client):
    c,module=client
    origin={'Origin':'http://testserver'}
    users=module.admin_auth.users();users.append(dict(name='admin',role='admin',token_hash=hashlib.sha256(b'TEST-admin').hexdigest()));module.admin_auth.write(users)
    admin_headers={'Authorization':'Bearer TEST-admin'}
    assert c.get('/login').status_code==200
    created=c.post('/api/admin/users',headers=admin_headers,json=dict(name='reporter01',role='writer',display_name='TEST 취재 담당')).json()
    token=created['token']
    assert c.post('/api/session/login',json=dict(name='reporter01',token=token)).status_code==403
    login=c.post('/api/session/login',headers=origin,json=dict(name='reporter01',token=token))
    assert login.status_code==200 and login.json()['role']=='writer'
    assert c.get('/api/me').json()['name']=='reporter01'
    assert c.get('/api/admin/users').status_code==403
    # Both cookie and direct-token access are revoked by account suspension.
    changed=c.post('/api/admin/users/reporter01/profile',headers=admin_headers,json=dict(display_name='TEST 담당자 변경',active=False))
    assert changed.status_code==200
    assert c.get('/api/me').status_code==401
    assert c.get('/api/me',headers={'Authorization':'Bearer '+token}).status_code==401
    assert c.post('/api/session/login',headers=origin,json=dict(name='reporter01',token=token)).status_code==401
    assert c.post('/api/admin/users/reporter01/token',headers=admin_headers,json={}).status_code==409
    assert c.post('/api/admin/users/reporter01/profile',headers=admin_headers,json=dict(display_name='TEST 담당자 변경',active=True)).status_code==200
    assert c.post('/api/session/login',headers=origin,json=dict(name='reporter01',token=token)).status_code==200
    rotated=c.post('/api/admin/users/reporter01/token',headers=admin_headers,json={}).json()['token']
    assert rotated!=token
    assert c.get('/api/me').status_code==401
    assert c.get('/api/me',headers={'Authorization':'Bearer '+token}).status_code==401
    assert c.post('/api/session/login',headers=origin,json=dict(name='reporter01',token=rotated)).status_code==200
    session=c.cookies.get('staff_session')
    assert c.post('/api/session/logout',headers=origin,json={}).status_code==200
    assert c.get('/api/me',headers={'Cookie':'staff_session='+session}).status_code==401
    assert c.post('/api/admin/users/admin/profile',headers=admin_headers,json=dict(display_name='no',active=False)).status_code==403
    assert c.post('/api/admin/users/admin/token',headers=admin_headers,json={}).status_code==403
    assert c.post('/api/admin/users/missing/token',headers=admin_headers,json={}).status_code==404
    history=c.get('/api/admin/history',headers=admin_headers).json()
    assert {'account_created','account_updated','account_token_rotated','staff_login','session_logout'}<={x['kind'] for x in history}
    assert all(secret not in json.dumps(history) for secret in (token,rotated,session))


def test_issued_roles_complete_draft_review_approval_without_shared_token(client):
    c,module=client
    origin={'Origin':'http://testserver'}
    writer=module.admin_auth.create('TEST-reporter','writer','TEST 취재 담당')
    editor=module.admin_auth.create('TEST-desk','editor','TEST 편집 담당')
    module.room.receive(json.loads((ROOT/'election-news-server/fixtures/fallback_snapshot.json').read_text(encoding='utf-8')))
    assert c.post('/api/session/login',headers=origin,json=dict(name=writer['name'],token=writer['token'])).status_code==200
    draft=c.post('/api/articles',headers=origin,json=dict(region='계양구을',mode='demo'))
    assert draft.status_code==200,draft.text
    article=draft.json()
    assert article['author']==writer['name']
    validated=c.post('/api/articles/'+article['id']+'/validate',headers=origin,json={})
    assert validated.status_code==200
    assert validated.json()['validation']['rule']=='PASS',validated.text
    approval=dict(reason='TEST 자동 검증: 실제 편집 승인 아님',evidence_checked=True,ai_unavailable_ack=True)
    assert c.post('/api/articles/'+article['id']+'/approve',headers=origin,json=approval).status_code==403
    assert c.post('/api/session/logout',headers=origin,json={}).status_code==200
    assert c.post('/api/session/login',headers=origin,json=dict(name=editor['name'],token=editor['token'])).status_code==200
    assert c.post('/api/articles',headers=origin,json=dict(region='계양구을',mode='demo')).status_code==403
    approved=c.post('/api/articles/'+article['id']+'/approve',headers=origin,json=approval)
    assert approved.status_code==200,approved.text
    assert approved.json()['status']=='APPROVED'
    assert c.get('/api/articles/'+article['id']+'/export').status_code==200
    assert c.post('/api/articles/'+article['id']+'/validate',json={}).status_code==403


def test_campaign_directory_verified_candidate_scope_and_no_fake_evidence(client):
    c,module=client
    from scripts.collect_campaign_directory import build_directory
    rows=json.loads((ROOT/'data/clean/incheon_final_results.json').read_text(encoding='utf-8'))
    directory=json.loads((ROOT/'data/clean/campaign_directory.json').read_text(encoding='utf-8'))
    ledger=json.loads((ROOT/'data/campaign_directory_ledger.json').read_text(encoding='utf-8'))
    raw=(ROOT/'data/official_raw'/ledger['source_file']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==ledger['sha256']
    assert directory==build_directory(raw,rows,ledger['collected_at'])
    assert len(directory)==38 and len({r['region_name'] for r in directory})==14
    for entry in directory:
        response=c.get('/api/pledge-context',params=dict(region=entry['region_name'],candidate=entry['candidate_id'],mode='official'))
        assert response.status_code==200,response.text
        context=response.json()
        assert context['directory']['candidate_name']==entry['candidate_name']
        assert context['directory']['catalog_start_page']>0
        assert context['registered_documents']==0
        assert context['directory']['usable_as_pledge_evidence'] is False
        assert context['catalogue_is_pledge_evidence'] is False
        assert c.get('/api/search',params=dict(region=entry['region_name'],candidate=entry['candidate_id'],mode='official',q='')).json()==[]
    first=directory[0]
    assert c.get('/api/pledge-context',params=dict(region='wrong',candidate=first['candidate_id'],mode='official')).status_code==422
    article=module.room.draft(first['region_name'],'TEST-writer','official')
    assert all(s['kind']=='result' for s in article['sentences'])
    assert 'NO_PLEDGE_EVIDENCE' in module.room.validate(article)['validation']['errors']


def test_pledge_context_shows_actual_document_review_and_demo_separation(client):
    c,module=client
    row,ids=add_test_pledge(module.room)
    params=dict(region=row['region_name'],candidate=row['candidate_id'],mode='official')
    context=c.get('/api/pledge-context',params=params).json()
    assert context['registered_documents']==1 and context['active_chunks']==len(ids)
    assert context['approved_documents']==0
    assert set(context['document_states'].values())=={'REVIEW_REQUIRED'}
    assert len(c.get('/api/search',params=dict(**params,q='')).json())==len(ids)
    approve_inputs(module.room)
    assert c.get('/api/pledge-context',params=params).json()['approved_documents']==1
    module.room.retire(ids[0],'TEST-editor')
    assert c.get('/api/pledge-context',params=params).json()['active_chunks']==0
    fallback=json.loads((ROOT/'election-news-server/fixtures/fallback_snapshot.json').read_text(encoding='utf-8'))
    module.room.receive(fallback)
    demo=fallback['rows'][0]
    context=c.get('/api/pledge-context',params=dict(region=demo['region_name'],candidate=demo['candidate_id'],mode='demo')).json()
    assert context['directory'] is None
    assert context['registered_documents']>0


def test_admin_web_recovery_proof_origin_local_scope_and_session_revocation(client,monkeypatch):
    c,module=client
    from fastapi.testclient import TestClient
    monkeypatch.setenv('LOCAL_WRITER_ACCESS','1')
    users=module.admin_auth.users();users.append(dict(name='admin',role='admin',token_hash=hashlib.sha256(b'TEST-old-admin').hexdigest()));module.admin_auth.write(users)
    module.admin_recovery.ensure()
    before=module.admin_auth.users()[:2]
    local=TestClient(module.app,base_url='http://127.0.0.1',client=('127.0.0.1',50000))
    origin={'Origin':'http://127.0.0.1'}
    body=dict(name='admin',method='current_token',verification='TEST-old-admin',confirmed=True)
    assert local.get('/api/admin/recovery/status').json()['available'] is True
    assert local.post('/api/admin/recovery/reset',json=body).status_code==403
    assert local.post('/api/admin/recovery/reset',headers={'Origin':'https://other.example'},json=body).status_code==403
    assert local.post('/api/admin/recovery/reset',headers=origin,json=dict(body,confirmed=False)).status_code==422
    assert local.post('/api/admin/recovery/reset',headers=origin,json=dict(body,verification='wrong')).status_code==401
    assert local.post('/api/admin/login',headers=origin,json=dict(name='admin',token='TEST-old-admin')).status_code==200
    old_session=local.cookies.get('admin_session')
    response=local.post('/api/admin/recovery/reset',headers=origin,json=body)
    assert response.status_code==200,response.text
    token=response.json()['token']
    assert response.headers['cache-control']=='no-store'
    assert module.admin_auth.users()[:2]==before
    assert module.admin_auth.session(old_session) is None
    assert c.get('/api/me',headers={'Authorization':'Bearer TEST-old-admin'}).status_code==401
    assert local.post('/api/admin/login',headers=origin,json=dict(name='admin',token=token)).status_code==200
    assert token in (module.ROOT/'admin-access.txt').read_text(encoding='utf-8-sig')
    assert token not in str(module.room.db.execute('SELECT payload FROM audit').fetchall())
    remote=TestClient(module.app,base_url='http://127.0.0.1',client=('203.0.113.5',50000))
    assert remote.post('/api/admin/recovery/reset',headers=origin,json=dict(body,verification=token)).status_code==403
    monkeypatch.setenv('LOCAL_WRITER_ACCESS','0')
    assert local.post('/api/admin/recovery/reset',headers=origin,json=dict(body,verification=token)).status_code==403
    local.close();remote.close()


def test_admin_web_recovery_code_is_rotated_and_attempts_throttled(client,monkeypatch):
    c,module=client
    import re
    monkeypatch.setenv('LOCAL_WRITER_ACCESS','1')
    users=module.admin_auth.users();users.append(dict(name='admin',role='admin',token_hash=hashlib.sha256(b'TEST-old-admin').hexdigest()));module.admin_auth.write(users)
    module.admin_recovery.ensure()
    code=re.search(r'^recovery: (\S+)',module.admin_recovery.guide.read_text(encoding='utf-8-sig'),re.MULTILINE).group(1)
    result=module.admin_recovery.reset('admin',code,'recovery_code','TEST-peer')
    assert result['token']!='TEST-old-admin'
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:module.admin_recovery.reset('admin',code,'recovery_code','TEST-new-peer')
    assert error.value.status_code==401
    for _ in range(5):
        with pytest.raises(HTTPException) as error:module.admin_recovery.reset('admin','wrong','recovery_code','TEST-brute')
        assert error.value.status_code==401
    with pytest.raises(HTTPException) as error:module.admin_recovery.reset('admin',result['token'],'current_token','TEST-brute')
    assert error.value.status_code==429
    assert code not in module.admin_recovery.secret_path.read_text(encoding='utf-8')
