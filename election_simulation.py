"""Synthetic count progression only; never substitutes for official election rows."""
import math
from datetime import datetime, timedelta


def simulation_rows(progress, sequence):
    progress = max(0, min(100, int(progress)))
    rows = []
    baseline = (datetime.fromisoformat('2024-04-10T20:00:00+09:00') + timedelta(seconds=progress*36)).isoformat()
    for ri, region in enumerate(['계양구을', '연수구을', '서구병']):
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
                candidate_id=f'DEMO-{ri}-{ci}', candidate_name=f'가상후보 {chr(65+ci)}',
                votes=value, valid_votes=total, vote_share=round(value/total*100, 2) if total else 0,
                counted_ballots=total, total_ballots=100000, count_rate=progress,
                turnout=None, baseline_at=baseline, source_url='demo://fixtures/ballots', is_demo=True))
    return rows
