from election_simulation import simulation_rows


def test_full_cycle_count_and_shares():
    previous = [0]*9
    shares = []
    for progress in range(101):
        rows = simulation_rows(progress, progress+1)
        assert len(rows) == 9
        assert all(r['is_demo'] and r['source_url'].startswith('demo:') for r in rows)
        for start in range(0, 9, 3):
            group = rows[start:start+3]
            total = sum(r['votes'] for r in group)
            assert total == progress*1000
            assert all(r['count_rate']==progress and r['valid_votes']==total and r['counted_ballots']==total for r in group)
            assert abs(sum(r['vote_share'] for r in group)-(100 if total else 0)) < .02
            assert all(r['vote_share']==(round(r['votes']/total*100,2) if total else 0) for r in group)
        assert all(row['votes']>=old for row,old in zip(rows,previous))
        previous = [r['votes'] for r in rows]
        if progress: shares.append(rows[0]['vote_share'])
    assert len(set(shares)) > 20
    assert rows[0]['baseline_at']=='2024-04-10T21:00:00+09:00'
    assert simulation_rows(0,102)[0]['votes']==0


def test_fictional_profiles_are_consistent_in_each_region():
 rows=simulation_rows(50,100)
 for start in range(0,9,3):
  assert [r['candidate_name'] for r in rows[start:start+3]]==['서지훈','한도윤','박채린']
  assert [r['party'] for r in rows[start:start+3]]==['미래민주연합','국민통합당','새길진보당']
  assert [r['candidate_number'] for r in rows[start:start+3]]==[1,2,3]
  assert all(r['is_demo'] and r['profile_message'] for r in rows[start:start+3])


def test_fictional_district_rename_does_not_change_official_results():
    import json
    from pathlib import Path
    rows=simulation_rows(60,1)
    assert all(row['region_name']=='하늘도시갑' for row in rows[:3])
    official=json.loads((Path(__file__).resolve().parents[1]/'data/clean/incheon_final_results.json').read_text(encoding='utf-8'))
    assert any(row['region_name']=='계양구을' for row in official)
    assert all(row['region_name']!='하늘도시갑' for row in official)
