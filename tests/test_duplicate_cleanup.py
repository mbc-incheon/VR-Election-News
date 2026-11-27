import importlib.util
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'election-news-server'))
from core import Newsroom
spec=importlib.util.spec_from_file_location('cleanup_duplicates',ROOT/'scripts/cleanup_duplicate_articles.py')
cleanup=importlib.util.module_from_spec(spec);spec.loader.exec_module(cleanup)
def test_duplicate_plan_keeps_approved_and_preserves_distinct_sources(tmp_path):
    import copy
    room=Newsroom(tmp_path)
    base=dict(id='approved',status='APPROVED',mode='demo',region_name='하늘도시갑',candidate_id='DEMO-0-0',article_type='result',title='TEST 기사',sentences=[dict(kind='result',text='TEST 100표',values=dict(votes=100))],data_sources=[dict(candidate_name='TEST',url='demo://source/one')])
    room.save(base)
    duplicate=copy.deepcopy(base);duplicate.update(id='duplicate',status='DRAFT');room.save(duplicate)
    changed=copy.deepcopy(duplicate);changed['id']='changed-number';changed['sentences'][0]['values']['votes']=101;room.save(changed)
    source=copy.deepcopy(duplicate);source['id']='other-source';source['data_sources'][0]['url']='demo://source/two';room.save(source)
    plan=cleanup.duplicate_plan(room)
    assert [(p['archive'],p['keep']) for p in plan]==[('duplicate','approved')]
    room.db.close()
