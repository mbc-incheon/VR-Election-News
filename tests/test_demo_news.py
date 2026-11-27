import json
import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'election-news-server'))
from core import Newsroom

def test_demo_news_sources_and_candidates_remain_separate():
    original=json.loads((ROOT/'election-news-server/static/election-news-index.json').read_text(encoding='utf-8'))['items']
    demo=json.loads((ROOT/'election-news-server/static/election-news-demo-index.json').read_text(encoding='utf-8'))['items']
    assert len(demo)==4
    for item in demo:
        source=next(row for row in original if row['id']==item['source_original']['id'])
        assert '계양구을' in source['regions'] and item['source_original']['url']==source['url']
        assert item['is_demo'] and item['source_kind']=='demo_adaptation'
        assert item['candidate_names']==['서지도','한반도','박리본']
        assert item['regions']==['하늘도시갑'] and source['regions']!=['하늘도시갑']
        assert item['publisher']!='' and item['publisher']!=source['publisher']

def test_demo_reference_draft_validation_and_cross_mode_rejection(tmp_path):
    room=Newsroom(tmp_path)
    room.receive(json.loads((ROOT/'fixtures/fallback_snapshot.json').read_text(encoding='utf-8')))
    references=[r for r in room.news_catalogue() if r.get('is_demo')]
    article=room.draft('하늘도시갑','TEST-writer','demo','news','DEMO-0-2',[r['id'] for r in references],'2024-04-01','2024-04-17')
    assert article['candidate_names']==['박리본'] and len(article['news_references'])==4
    assert all('가상 참고자료' in s['text'] and '보도를 게재했다' not in s['text'] for s in article['sentences'] if s['kind']=='news')
    checked=room.validate(article,'TEST-writer')
    assert checked['validation']['rule']=='PASS',checked['validation']
    with pytest.raises(ValueError):
        room.draft('하늘도시갑','TEST-writer','demo','news',None,['NEWS24-002'])
    changed=json.loads(json.dumps(checked));changed['sentences'][-1]['text']='박리본이 실제 선거에서 당선됐다.'
    assert room.validate(changed,'TEST-writer')['validation']['rule']=='FAIL'

def test_event_catchup_pagination_preserves_order(tmp_path,monkeypatch):
    import importlib.util
    from fastapi.testclient import TestClient
    monkeypatch.setenv('DATA_DIR',str(tmp_path/'data'))
    spec=importlib.util.spec_from_file_location('test_data_pagination',ROOT/'election-data-server/app.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.store.events=[dict(sequence=i) for i in range(1,241)]
    client=TestClient(module.app)
    first=client.get('/events?after=0&limit=100').json()
    second=client.get('/events?after=100&limit=100').json()
    last=client.get('/events?after=200&limit=100').json()
    assert [r['sequence'] for r in first+second+last]==list(range(1,241))
    assert len(client.get('/events').json())==240
    assert client.get('/events?limit=0').status_code==422

def test_preserved_event_files_are_loaded_only_when_requested(tmp_path,monkeypatch):
    import importlib.util
    monkeypatch.setenv('DATA_DIR',str(tmp_path/'data'))
    spec=importlib.util.spec_from_file_location('test_data_lazy',ROOT/'election-data-server/app.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    folder=tmp_path/'events';folder.mkdir()
    for i in range(1,5):(folder/f'{i:08d}.json').write_text(json.dumps({'sequence':i}),encoding='utf-8')
    saved=module.SavedEvents(folder)
    assert len(saved)==4 and saved.cached_event is None
    assert saved.after(2,1)==[{'sequence':3}]
    assert saved[-1]=={'sequence':4}
    assert saved.after(4)==[]
