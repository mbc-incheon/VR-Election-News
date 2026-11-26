"""Synthetic count progression only; never substitutes for official election rows."""
import math
from datetime import datetime, timedelta


DEMO_CANDIDATES = (
    dict(name='서지훈', party='미래민주연합', message='지역 현안 연속성과 교통·생활 인프라 확충 강조', character='조직력 우위', pledge='지역 현안의 연속성을 바탕으로 교통·생활 인프라 확충을 제시한다.'),
    dict(name='한도윤', party='국민통합당', message='원도심 재정비·청년 일자리·세금 감축 공약', character='추격자', pledge='원도심 재정비, 청년 일자리 확대, 세금 감축을 제시한다.'),
    dict(name='박채린', party='새길진보당', message='돌봄·환경·서민 주거 안정', character='캐스팅보트·개혁 표심', pledge='돌봄 서비스 확대, 환경 보호, 서민 주거 안정을 제시한다.'),
)


def simulation_rows(progress, sequence):
    progress = max(0, min(100, int(progress)))
    rows = []
    baseline = (datetime.fromisoformat('2024-04-10T20:00:00+09:00') + timedelta(seconds=progress*36)).isoformat()
    for ri, region in enumerate(['하늘도시갑', '연수구을', '서구병']):
        votes = [0, 0, 0]
        for step in range(1, progress+1):
            a = int(1000*(0.43+0.13*math.sin(step/12+ri)))
            b = int(1000*(0.34+0.09*math.cos(step/15+ri)))
            batch = [a, b, 1000-a-b]
            votes = [v+increment for v, increment in zip(votes, batch)]
        total = sum(votes)
        for ci, value in enumerate(votes):
            rows.append(dict(row_id=f'DEMO-{sequence}-{ri}-{ci}', election_id='KR-20240410-NA22',
                region_id=f'DEMO-IC-{ri}', region_name=region, original_region_name='인천광역시 '+region,
                candidate_id=f'DEMO-{ri}-{ci}', candidate_name=DEMO_CANDIDATES[ci]['name'],
                party=DEMO_CANDIDATES[ci]['party'], candidate_number=ci+1,
                profile_message=DEMO_CANDIDATES[ci]['message'], profile_character=DEMO_CANDIDATES[ci]['character'],
                votes=value, valid_votes=total, vote_share=round(value/total*100, 2) if total else 0,
                counted_ballots=total, total_ballots=100000, count_rate=progress,
                turnout=None, baseline_at=baseline, source_url='demo://fixtures/ballots', is_demo=True))
    return rows
