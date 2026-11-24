"""Persistent independent review of official inputs; no synthetic approvals."""
import copy
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from election_common import verify_lineage,snapshot_key

OFFICIAL_HOSTS={'www.data.go.kr','data.nec.go.kr','info.nec.go.kr','library.nec.go.kr','policy.nec.go.kr','dl.nanet.go.kr','www.nec.go.kr'}

def official_url(url):
    u=urlparse(url)
    return u.scheme=='https' and u.hostname in OFFICIAL_HOSTS and not u.username and not u.password

def result_text(row):
    if row.get('stage')=='FINAL_FILE_AGGREGATION':
        return f"2024년 제22대 총선 {row['region_name']} 공식 파일 집계에서 {row['candidate_name']}의 득표수는 {row['votes']:,}표, 계산 득표율은 {row['vote_share']:.2f}%다."
    return f"{row['region_name']} {row['baseline_at']} 기준 {row['candidate_name']}의 득표수는 {row['votes']:,}표, 득표율은 {row['vote_share']:.2f}%다."

class WorkflowMixin:
    def request_review(self,kind,target_id,author,details):
        from core import canonical,now,sha
        rid=sha([kind,target_id])[:24]
        with self.lock:
            self.db.execute('INSERT OR IGNORE INTO review_record VALUES(?,?,?,?,?,?)',
                (rid,kind,target_id,author,'REVIEW_REQUIRED',canonical(dict(**details,submitted_at=now()))))
            self.db.commit()
        return rid

    def review_state(self,kind,target_id):
        with self.lock:
            r=self.db.execute('SELECT id,author,status,payload FROM review_record WHERE kind=? AND target_id=?',(kind,target_id)).fetchone()
            return dict(id=r[0],author=r[1],status=r[2],**json.loads(r[3])) if r else dict(status='REVIEW_REQUIRED')

    def reviews(self):
        with self.lock:
            return [dict(id=r[0],kind=r[1],target_id=r[2],author=r[3],status=r[4],**json.loads(r[5])) for r in self.db.execute('SELECT * FROM review_record ORDER BY rowid DESC')]

    def decide_review(self,rid,actor,approve,reason,checked):
        from core import canonical,now
        with self.lock:
            r=self.db.execute('SELECT kind,target_id,author,payload FROM review_record WHERE id=?',(rid,)).fetchone()
            if not r: raise ValueError('review not found')
            if actor==r[2]: raise ValueError('independent reviewer required')
            if not checked or len(reason.strip())<5:raise ValueError('original confirmation and review reason required')
            state='APPROVED' if approve else 'REJECTED'
            payload=json.loads(r[3]);payload.update(reviewer=actor,reviewed_at=now(),reason=reason)
            self.db.execute('UPDATE review_record SET status=?,payload=? WHERE id=?',(state,canonical(payload),rid));self.db.commit()
            self.audit('input_review',actor,dict(review_id=rid,kind=r[0],target_id=r[1],status=state,reason=reason))
            # Revoked inputs also invalidate published articles and finished exports.
            if not approve:
                for aid, in self.db.execute("SELECT id FROM article WHERE status='APPROVED'").fetchall():
                    try:self.export(aid)
                    except ValueError:pass
            return dict(id=rid,status=state,**payload)

    def import_official_archive(self,path,ledger_path,raw_path):
        from core import sha
        rows=json.loads(Path(path).read_text(encoding='utf-8'))
        ledger=json.loads(Path(ledger_path).read_text(encoding='utf-8'))
        digest=hashlib.sha256(Path(raw_path).read_bytes()).hexdigest()
        if digest!=ledger['sha256']:raise ValueError('official raw file hash mismatch')
        verify_lineage(rows,Path(raw_path).read_bytes())
        if not rows:raise ValueError('official archive empty')
        groups={}
        for row in rows:
            if row['election_id']!='KR-20240410-NA22' or row['is_demo'] is not False or not official_url(row['source_url']):raise ValueError('invalid archive scope')
            if row['stage']!='FINAL_FILE_AGGREGATION' or row['election_date']!='2024-04-10':raise ValueError('invalid archive stage')
            if type(row['votes']) is not int or row['votes']<0 or row['valid_votes']<=0 or abs(row['votes']/row['valid_votes']*100-row['vote_share'])>.011:raise ValueError('archive arithmetic')
            if not row.get('source_rows'):raise ValueError('archive lineage required')
            groups.setdefault(row['region_id'],[]).append(row)
        if len({r['row_id'] for r in rows})!=len(rows):raise ValueError('duplicate archive row')
        for group in groups.values():
            if len({r['candidate_id'] for r in group})!=len(group) or len({r['valid_votes'] for r in group})!=1 or sum(r['votes'] for r in group)!=group[0]['valid_votes']:raise ValueError('archive candidate total')
        event=dict(sequence=0,mode='official',election_id='KR-20240410-NA22',rows=rows,stage='FINAL_FILE_AGGREGATION',
            collected_at=ledger['collected_at'],source_sha256=digest,archive_sha256=sha(rows),label='2024년 공식 결과 파일 집계 · 독립 검수 필요')
        self.receive(event)
        sid=snapshot_key(event)
        self.request_review('dataset',sid,'official-file-import',dict(title='2024 인천 14개 지역구 공식 파일 집계',source_url=ledger['catalog_url'],raw_sha256=digest,rows=len(rows),districts=len(groups),snapshot_id=sid))
        return sid

    def documents(self,include_inactive=False):
        with self.lock:
            docs={}
            for payload,active in self.db.execute('SELECT payload,active FROM chunk ORDER BY rowid DESC'):
                c=json.loads(payload)
                if not include_inactive and not active:continue
                doc=docs.setdefault(c['document_id'],dict(**{k:v for k,v in c.items() if k not in ['id','text','location','sha256']},chunks=[]))
                doc['chunks'].append(dict(id=c['id'],text=c['text'],location=c['location'],active=bool(active),sha256=c['sha256']))
            return list(docs.values())

    def audit_integrity(self):
        from core import sha
        with self.lock:
            previous='0'*64;total=0
            for i,prev,digest,payload in self.db.execute('SELECT * FROM audit ORDER BY id'):
                if prev!=previous or digest!=sha([prev,json.loads(payload)]):return dict(valid=False,failed_id=i,total=total)
                previous=digest;total+=1
            return dict(valid=True,total=total,head=previous)

    def prepare_render(self,article_ids):
        if not article_ids or len(set(article_ids))!=len(article_ids) or len(article_ids)>30:raise ValueError('select 1 to 30 distinct approved articles')
        bundles=[self.export(aid) for aid in article_ids]
        if len({b['article']['mode'] for b in bundles})!=1:raise ValueError('do not mix official and simulation in one news package')
        return bundles

    def pledge_context(self,region,candidate,mode):
        with self.lock:
            snapshot=self.latest(mode)
            row=next((r for r in snapshot['rows'] if r['region_name']==region and r['candidate_id']==candidate),None)
            if not row:raise ValueError('선택한 지역과 후보의 자료를 찾을 수 없습니다.')
            docs=[d for d in self.documents() if (d['election_id'],d['region_name'],d['candidate_id'],d['is_demo'])==(row['election_id'],region,candidate,mode=='demo')]
            states={d['document_id']:('DEMO' if mode=='demo' else self.review_state('document',d['document_id'])['status']) for d in docs}
            entry=None
            if mode=='official':
                root=Path(__file__).resolve().parents[1]
                ledger=json.loads((root/'data/campaign_directory_ledger.json').read_text(encoding='utf-8'))
                raw=(root/'data/official_raw'/ledger['source_file']).read_bytes()
                if hashlib.sha256(raw).hexdigest()!=ledger['sha256']:raise ValueError('공식 공보 목차 원본 해시가 일치하지 않습니다.')
                entries=json.loads((root/'data/clean/campaign_directory.json').read_text(encoding='utf-8'))
                from scripts.collect_campaign_directory import build_directory
                preserved_rows=json.loads((root/'data/clean/incheon_final_results.json').read_text(encoding='utf-8'))
                if entries!=build_directory(raw,preserved_rows,ledger['collected_at']):raise ValueError('공보 목차 정제본이 보존된 원문과 일치하지 않습니다.')
                entry=next((e for e in entries if (e['candidate_id'],e['region_name'])==(candidate,region)),None)
            return dict(candidate_id=candidate,candidate_name=row['candidate_name'],region_name=region,mode=mode,
                registered_documents=len(docs),active_chunks=sum(len(d['chunks']) for d in docs),approved_documents=sum(v=='APPROVED' for v in states.values()),document_states=states,
                directory=entry,catalogue_is_pledge_evidence=False)
