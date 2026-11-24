"""Real HTTP integration and a real video; TEST actors, never editorial approval."""
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime,timezone,timedelta
from pathlib import Path
import httpx
import imageio_ffmpeg

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs';OUT.mkdir(exist_ok=True)
(ROOT/'build').mkdir(exist_ok=True)
RUN=Path(tempfile.mkdtemp(prefix='platform-',dir=ROOT/'build'))
users=[dict(name='TEST-platform-'+role,role=role,token_hash=hashlib.sha256(('TEST-platform-'+role).encode()).hexdigest()) for role in ['writer','editor']]
(RUN/'users.json').write_text(json.dumps(users))
env=dict(os.environ,NEWS_DIR=str(RUN),UPSTREAM_URL='http://127.0.0.1:9',ALLOW_DEMO_FALLBACK='1')
base='http://127.0.0.1:18112';checks=[]
def check(name,condition):
    checks.append(dict(name=name,passed=bool(condition)))
    if not condition:raise AssertionError(name)
def call(path,body=None,role='writer'):
    return httpx.request('GET' if body is None else 'POST',base+path,json=body,headers={'Authorization':'Bearer TEST-platform-'+role},timeout=30)
log=(RUN/'server.log').open('w',encoding='utf-8')
process=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--app-dir',str(ROOT/'election-news-server'),'--host','127.0.0.1','--port','18112'],env=env,stdout=log,stderr=log)
try:
    for _ in range(100):
        try:
            if httpx.get(base+'/health',timeout=1).status_code==200:break
        except httpx.HTTPError:pass
        time.sleep(.15)
    check('PC studio page served',httpx.get(base+'/studio').status_code==200)
    check('Offline Three.js served',httpx.get(base+'/static/vendor/three.module.js').status_code==200)
    check('Workstation script served',httpx.get(base+'/static/workbench.js').status_code==200)
    official=call('/api/snapshot?mode=official').json()
    check('Official archive 14 districts',len({r['region_name'] for r in official['rows']})==14)
    check('Official archive missing baseline retained',all(r['baseline_at'] is None and r['count_rate'] is None for r in official['rows']))
    check('Dataset requires independent review',official['review']['status']=='REVIEW_REQUIRED')
    official_article=call('/api/articles',dict(region='계양구을',mode='official')).json()
    check('Official unreviewed article blocked',call('/api/articles/'+official_article['id']+'/approve',dict(reason='TEST 차단 확인 사유',evidence_checked=True,ai_unavailable_ack=True),'editor').status_code==409)
    review=call('/api/reviews').json()[0]
    check('Writer cannot decide input review',call('/api/reviews/'+review['id'],dict(approve=True,reason='TEST 요청',original_checked=True)).status_code==403)
    for _ in range(50):
        demo=call('/api/snapshot?mode=demo').json()
        if demo.get('rows'):break
        time.sleep(.1)
    article=call('/api/articles',dict(region='계양구을',mode='demo')).json();aid=article['id']
    check('Simulation article validation passes',call('/api/articles/'+aid+'/validate',{}).json()['validation']['rule']=='PASS')
    check('Render rejects unapproved article',call('/api/production/jobs',dict(article_ids=[aid],seconds_per_article=5)).status_code==409)
    check('TEST independent editor approval',call('/api/articles/'+aid+'/approve',dict(reason='TEST 자동 시험 전용. 실제 사람의 편집 승인이 아닙니다.',evidence_checked=True,ai_unavailable_ack=True),'editor').status_code==200)
    check('Approved simulation visible in studio',any(b['article']['id']==aid for b in call('/api/studio/articles').json()))
    response=call('/api/production/jobs',dict(article_ids=[aid],seconds_per_article=5))
    check('Real encoder queued',response.status_code==200);job=response.json()
    for _ in range(200):
        job=call('/api/production/jobs/'+job['id']).json()
        if job['status'] in ['COMPLETED','FAILED']:break
        time.sleep(.15)
    check('Real encoder completed',job['status']=='COMPLETED')
    video=call('/api/production/jobs/'+job['id']+'/files/news.mp4')
    check('Approved video download',video.status_code==200)
    samples=OUT/'production_sample';samples.mkdir(exist_ok=True)
    for name in ['news.mp4','news-package.zip','subtitles.srt','script.txt','manifest.json']:
        result=call('/api/production/jobs/'+job['id']+'/files/'+name)
        if result.status_code!=200:raise AssertionError('sample download '+name)
        (samples/name).write_bytes(result.content)
    reader=imageio_ffmpeg.read_frames(str(samples/'news.mp4'));meta=next(reader);reader.close()
    check('FHD encoded frame dimensions',meta['size']==(1920,1080))
    check('Five second sample has real duration',abs(meta['duration']-5)<.15)
    with zipfile.ZipFile(samples/'news-package.zip') as z:check('Production package includes CG and subtitles','subtitles.srt' in z.namelist() and any(n.endswith('.png') for n in z.namelist()))
    evidence=next(s['evidence_ids'][0] for s in article['sentences'] if s['kind']=='pledge')
    check('Evidence retirement',call('/api/chunks/'+evidence+'/retire',{},'editor').status_code==200)
    check('Revoked source blocks finished video download',call('/api/production/jobs/'+job['id']+'/files/news.mp4').status_code==409)
    check('Revoked article removed from studio',not any(b['article']['id']==aid for b in call('/api/studio/articles').json()))
    check('Audit chain valid after production',call('/api/audit/integrity',role='editor').json()['valid'])
    backup=call('/api/backup',role='editor');check('Editor backup available',backup.status_code==200)
    with zipfile.ZipFile(io.BytesIO(backup.content)) as z:check('Backup excludes credentials','users.json' not in z.namelist() and 'news.sqlite' in z.namelist())
    (samples/'README.txt').write_text('TEST 자동 검증용 시뮬레이션 영상입니다. 실제 후보·공약·사람 승인·최종 보도본이 아닙니다. 승인 철회 전 생성한 불변 시험 증빙이며, 실제 서비스에서는 해당 철회 후 파일 다운로드가 차단되는 것을 확인했습니다.',encoding='utf-8')
finally:
    if process.poll() is None:process.terminate();process.wait(timeout=10)
    log.close()
    result=dict(at=datetime.now(timezone(timedelta(hours=9))).isoformat(),test_actors_only=True,total=len(checks),passed=sum(c['passed'] for c in checks),checks=checks)
    (OUT/'platform_integration_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
