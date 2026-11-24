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
