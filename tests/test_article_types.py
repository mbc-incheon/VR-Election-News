import copy,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'election-news-server'))
from core import Newsroom
from election_simulation import simulation_rows

@pytest.fixture
def room(tmp_path):
 room=Newsroom(tmp_path)
 room.import_official_archive(ROOT/'data/clean/incheon_final_results.json',ROOT/'data/official_csv_ledger.json',ROOT/'data/official_raw/NEC_NA22_20240410.csv')
 yield room
 room.db.close()

def test_result_type_targets_candidate_and_preserves_data_review(room):
 row=next(row for row in room.latest('official')['rows'] if row['region_name']=='연수구을')
 article=room.draft(row['region_name'],'TEST-writer','official','result',row['candidate_id'])
 assert len(article['sentences'])==1 and article['candidate_names']==[row['candidate_name']]
 assert article['summary']==article['sentences'][0]['text']
 errors=room.validate(article)['validation']['errors']
 assert 'DATASET_REVIEW_REQUIRED' in errors and 'NO_PLEDGE_EVIDENCE' not in errors
 review=next(r for r in room.reviews() if r['kind']=='dataset')
 room.decide_review(review['id'],'TEST-editor',True,'TEST 원본 대조 완료',True)
 assert room.validate(article)['validation']['rule']=='PASS'
 with pytest.raises(ValueError):room.approve(article['id'],'TEST-writer','TEST 자기 승인 불가',True,True)

def test_pledge_type_does_not_invent_missing_evidence(room):
 article=room.draft('연수구을','TEST-writer','official','pledge')
 assert all(s['kind']=='result' for s in article['sentences'])
 assert 'NO_PLEDGE_EVIDENCE' in room.validate(article)['validation']['errors']

def test_news_selection_is_scoped_and_cannot_be_fabricated(room):
 with pytest.raises(ValueError):room.draft('연수구을','TEST-writer','official','news',news_ids=[])
 with pytest.raises(ValueError):room.draft('연수구을','TEST-writer','official','news',news_ids=['NEWS24-001'])
 with pytest.raises(ValueError):room.draft('연수구을','TEST-writer','official','news',news_ids=['NEWS24-017'],period_from='2024-04-10')
 article=room.draft('연수구을','TEST-writer','official','news',news_ids=['NEWS24-017'])
 assert article['news_references'][0]['publisher']=='뉴스1'
 assert all(s['kind']=='result' for s in article['sentences'])
 article['news_references'][0]['url']='https://example.invalid/changed'
 assert 'NEWS_REFERENCE_MISMATCH' in room.validate(article)['validation']['errors']

def test_snapshot_is_fixed_while_demo_continues(room):
 room.receive(dict(sequence=901,mode='demo',rows=simulation_rows(10,901)))
 article=room.draft('계양구을','TEST-writer','demo','result')
 saved=copy.deepcopy(article['sentences'])
 room.receive(dict(sequence=902,mode='demo',rows=simulation_rows(80,902)))
 assert room.get(article['id'])['sentences']==saved
 assert room.validate(article)['validation']['rule']=='PASS'

def test_wrong_candidate_and_summary_are_blocked(room):
 with pytest.raises(ValueError):room.draft('연수구을','TEST-writer','official','result','wrong')
 article=room.draft('연수구을','TEST-writer','official','result')
 article['summary']='근거 없는 변경'
 assert 'SUMMARY_MISMATCH' in room.validate(article)['validation']['errors']
