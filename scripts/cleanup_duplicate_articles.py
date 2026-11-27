"""Archive exact duplicate article copies with an operator audit and SQLite backup.

Run without --apply first. Different titles, text, numbers, sources and modes stay separate.
"""
import argparse,json,sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'election-news-server'))
from core import Newsroom,canonical

def duplicate_plan(room):
    groups=defaultdict(list)
    for row in room.db.execute('SELECT payload FROM article ORDER BY rowid DESC'):
        article=json.loads(row[0])
        if article.get('deleted_at'):continue
        key=[article.get(k) for k in ['mode','region_name','candidate_id','article_type','title']]
        key.append([{k:s.get(k) for k in ['kind','text','values','evidence_ids','evidence_hashes','source_url']} for s in article['sentences']])
        key.append([{k:source.get(k) for k in ['candidate_name','url']} for source in article.get('data_sources',[])])
        groups[canonical(key)].append(article)
    plan=[]
    for group in groups.values():
        if len(group)<2:continue
        keep=next((a for a in group if a['status']=='APPROVED'),group[0])
        for article in group:
            if article['id']!=keep['id']:plan.append(dict(archive=article['id'],keep=keep['id'],title=keep['title']))
    return plan

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    room=Newsroom(ROOT/'runtime/news');plan=duplicate_plan(room)
    if args.apply and plan:
        import sqlite3
        folder=ROOT/'runtime/backups';folder.mkdir(parents=True,exist_ok=True)
        stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
        backup=folder/f'before-duplicate-cleanup-{stamp}.sqlite'
        with sqlite3.connect(backup) as destination:room.db.backup(destination)
        for item in plan:
            room.archive_article(item['archive'],'maintenance:duplicate-cleanup',admin=True)
            room.audit('duplicate_archived','maintenance:duplicate-cleanup',dict(article_id=item['archive'],retained_article_id=item['keep'],user_requested=True))
        (folder/f'duplicate-cleanup-{stamp}.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(duplicates=len(plan),applied=args.apply,retained=len({p['keep'] for p in plan})),ensure_ascii=True))
    room.db.close()
