import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'election-news-server'))
from article_narration import broadcast_text

def test_broadcast_rendition_preserves_numbers_and_removes_spoken_demo_copy():
    text='하늘도시갑 2024-04-10T20:46:48+09:00 기준 서지훈의 득표수는 33,550표, 득표율은 43.01%다.'
    result=broadcast_text(text)
    assert '33,550표' in result and '43.01%입니다.' in result
    assert '2024년 4월 10일 20시 46분' in result
    pledge='서지훈의 공약 자료에는 다음 내용이 제시돼 있다: 서지훈(미래민주연합, 가상 정당)은 교통·생활 인프라 확충을 제시한다. 이 내용은 사용자 설정의 가상 공약이며 실제 후보의 공약이 아니다. 구체적인 일정·예산은 설정하지 않았다.'
    result=broadcast_text(pledge)
    assert '가상' not in result and '실제 후보의 공약이 아니다' not in result
    assert '교통·생활 인프라 확충을 제시했습니다.' in result
    assert '예산은 명시되지 않았습니다' in result
