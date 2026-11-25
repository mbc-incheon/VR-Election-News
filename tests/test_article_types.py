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
 assert any(s['kind']=='news' for s in article['sentences'])
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

def test_custom_title_and_news_reference_text_have_traceable_sources(room):
 article=room.draft('연수구을','TEST-writer','official','news',news_ids=['NEWS24-017'],title='연수구을 선거 보도와 결과 확인')
 assert article['title']=='연수구을 선거 보도와 결과 확인'
 news=next(s for s in article['sentences'] if s['kind']=='news')
 assert news['evidence_ids']==['NEWS24-017'] and news['source_url'].startswith('https://')
 news['text']='확인되지 않은 내용'
 assert any('NEWS_REFERENCE_MISMATCH' in value for value in room.validate(article)['validation']['errors'])
 with pytest.raises(ValueError):room.draft('연수구을','TEST-writer','official',title=' ')

def test_explicit_evidence_cannot_point_to_another_candidate(room):
 with pytest.raises(ValueError):room.draft('연수구을','TEST-writer','official',title='공약과 근거 확인',explicit_evidence_ids=['unknown'])

def test_checked_pledge_content_and_custom_title_are_used(room):
 row=next(r for r in room.latest('official')['rows'] if r['region_name']=='연수구을')
 ids=room.add_document(dict(title='TEST 확인 공약',publisher='TEST',url='https://library.nec.go.kr/TEST-CONTENT',published_at='2024-04-01',collected_at='2026-11-25T00:00:00+09:00',document_type='campaign',election_id=row['election_id'],region_name=row['region_name'],candidate_id=row['candidate_id'],text='TEST 환승 편의 개선을 검토한다. 실제 공약이 아닌 검증용 문장이다.',is_demo=False,rights='TEST',human_verified=True),'TEST-writer')
 article=room.draft(row['region_name'],'TEST-writer','official','combined',row['candidate_id'],title='선택 공약과 개표 결과 확인',explicit_evidence_ids=ids)
 pledge=next(s for s in article['sentences'] if s['kind']=='pledge')
 assert pledge['evidence_ids']==ids and '환승 편의 개선' in pledge['text']
 errors=room.validate(article)['validation']['errors']
 assert any('DOCUMENT_REVIEW_REQUIRED' in error for error in errors)


def test_google_metadata_is_persisted_scoped_and_tamper_checked(room):
 source=dict(id='external-id',title='연수구을 선거 결과',publisher='테스트 언론사',published_date='2024-04-11',url='https://news.google.com/rss/articles/test')
 item=room.retain_google_news([source],'연수구을')[0]
 assert item['body_verified'] is False
 assert item['id']==room.retain_google_news([source],'연수구을')[0]['id']
 article=room.draft('연수구을','TEST-writer','official','news',news_ids=[item['id']])
 assert article['news_references']==[item]
 assert '원문 본문은 확인하지 않았다' in article['sentences'][-1]['text']
 assert 'NEWS_REFERENCE_MISMATCH' not in room.validate(article)['validation']['errors']
 with pytest.raises(ValueError):room.draft('계양구갑','TEST-writer','official','news',news_ids=[item['id']])
 with pytest.raises(ValueError):room.draft('연수구을','TEST-writer','official','news',news_ids=['GOOGLE-forged'])
 article['news_references'][0]['title']='변조 제목'
 assert 'NEWS_REFERENCE_MISMATCH' in room.validate(article)['validation']['errors']
