import hashlib
import json
import re
import sqlite3
import secrets
import threading
from functools import wraps
from datetime import datetime,timezone,timedelta
from pathlib import Path
from workflow import WorkflowMixin, official_url, result_text
from election_common import snapshot_key,load_official

def now(): return datetime.now(timezone(timedelta(hours=9))).isoformat()
def canonical(v): return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def sha(v): return hashlib.sha256(canonical(v).encode()).hexdigest()

def locked(fn):
    @wraps(fn)
    def call(self,*args,**kwargs):
        with self.lock:return fn(self,*args,**kwargs)
    return call

class Newsroom(WorkflowMixin):
    def __init__(self,root):
        self.lock=threading.RLock()
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.root/'news.sqlite',check_same_thread=False)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript(Path(__file__).with_name('schema.sql').read_text())
        self.db.executescript(Path(__file__).with_name('platform_schema.sql').read_text())
        self.db.commit()

    def news_catalogue(self):
        items=json.loads((Path(__file__).with_name('static')/'election-news-index.json').read_text(encoding='utf-8'))['items']
        folder=self.root/'google_news'
        if folder.exists():
            for path in folder.glob('*.json'):
                item=json.loads(path.read_text(encoding='utf-8'))
                if item.get('id')=='GOOGLE-'+sha({k:v for k,v in item.items() if k!='id'}):items.append(item)
        return items

    @locked
    def retain_google_news(self,items,region='',candidate=''):
        rows=self.latest('official').get('rows',[])
        known=sorted({row['region_name'] for row in rows})
        if region and region not in known:raise ValueError('공식 선거구를 확인하세요.')
        folder=self.root/'google_news';folder.mkdir(exist_ok=True)
        saved=[]
        for source in items:
            names=[row['candidate_name'] for row in rows if row['candidate_name'] in source['title']]
            related=sorted({row['region_name'] for row in rows if row['candidate_name'] in names or row['region_name'] in source['title']})
            item={**source,'regions':[region] if region else related or known,'candidate_names':sorted(set(names)),
                  'candidate_regions':{name:sorted({row['region_name'] for row in rows if row['candidate_name']==name}) for name in names},
                  'kind':'구글 뉴스 검색 메타데이터','source_kind':'google_news','scope_status':'SEARCH_CONTEXT_ONLY',
                  'search_region':region,'search_candidate':candidate,'body_verified':False}
            item.pop('id',None);item['id']='GOOGLE-'+sha(item)
            target=folder/(item['id']+'.json')
            if not target.exists():target.write_text(canonical(item),encoding='utf-8')
            saved.append(item)
        return saved

    @locked
    def audit(self,kind,actor,details):
        last=self.db.execute('SELECT hash FROM audit ORDER BY id DESC LIMIT 1').fetchone()
        prev=last[0] if last else '0'*64
        payload=dict(at=now(),kind=kind,actor=actor,details=details)
        self.db.execute('INSERT INTO audit(previous_hash,hash,payload) VALUES(?,?,?)',(prev,sha([prev,payload]),canonical(payload)))
        self.db.commit()

    @locked
    def receive(self,event):
        eid=snapshot_key(event)
        if self.db.execute('SELECT 1 FROM snapshot WHERE id=?',(eid,)).fetchone(): return False
        if event.get('mode')=='official' and event.get('stage')=='FINAL_FILE_AGGREGATION':
            expected,ledger=load_official(Path(__file__).resolve().parents[1])
            if event['rows']!=expected or event.get('source_sha256')!=ledger['sha256']:raise ValueError('official archive does not match preserved source')
        self.db.execute('INSERT INTO snapshot VALUES(?,?,?,?,?)',(eid,event['sequence'],event['mode'],canonical(event),now()))
        self.db.commit(); self.audit('snapshot','receiver',dict(id=eid,sequence=event['sequence'],mode=event['mode']))
        if event.get('mode')=='official' and event.get('stage')=='FINAL_FILE_AGGREGATION':
            self.request_review('dataset',eid,'official-file-import',dict(title='2024 인천 공식 파일 집계',source_url=event['rows'][0]['source_url'],raw_sha256=event.get('source_sha256'),rows=len(event['rows']),districts=len({r['region_id'] for r in event['rows']}),snapshot_id=eid))
        return True

    @locked
    def latest(self,mode=None):
        row=self.db.execute('SELECT id,payload FROM snapshot '+('WHERE mode=? ' if mode else '')+'ORDER BY rowid DESC LIMIT 1', (mode,) if mode else ()).fetchone()
        return dict(snapshot_id=row[0],**json.loads(row[1])) if row else dict(rows=[],mode='unavailable')

    @locked
    def add_document(self,doc,actor):
        required=['title','publisher','url','published_at','collected_at','document_type','election_id','region_name','candidate_id','text','is_demo','rights']
        if any(k not in doc for k in required): raise ValueError('document metadata incomplete')
        if any(not isinstance(doc[k],str) or not doc[k].strip() for k in required if k!='is_demo'):raise ValueError('invalid document fields')
        if type(doc['is_demo']) is not bool or len(doc['text'])>300000:raise ValueError('invalid document size or mode')
        if doc['election_id']!='KR-20240410-NA22':raise ValueError('wrong document election')
        try:
            datetime.fromisoformat(doc['collected_at']);datetime.fromisoformat(doc['published_at'])
        except ValueError:raise ValueError('invalid document date')
        if not doc['text'].strip(): raise ValueError('empty document')
        if not doc['is_demo'] and not official_url(doc['url']): raise ValueError('official document URL required')
        if doc['document_type']=='campaign' and not doc['is_demo'] and not doc.get('human_verified'):
            raise ValueError('candidate document requires original verification')
        if doc.get('pdf_sha256'):
            digest=doc['pdf_sha256']
            if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('invalid PDF hash')
            source=self.root/'source_pdf'/(digest+'.pdf')
            if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:raise ValueError('preserved PDF not found')
        docid=sha(doc)[:20]
        raw=self.root/'raw_documents';raw.mkdir(exist_ok=True)
        p=raw/f'{docid}.json'
        if not p.exists():
            p.write_text(canonical(doc),encoding='utf-8'); p.chmod(0o444)
        paragraphs=[p.strip() for p in doc['text'].split('\n\n') if p.strip()]
        paragraphs=[p[i:i+1200] for p in paragraphs for i in range(0,len(p),1200)]
        ids=[]
        for index,text in enumerate(paragraphs):
            cid=f'{docid}-p{index+1}'
            chunk={k:v for k,v in doc.items() if k!='text'}
            chunk.update(id=cid,document_id=docid,text=text,location=f'문단 {index+1}',sha256=sha(text))
            self.db.execute('INSERT OR IGNORE INTO chunk VALUES(?,?,1)',(cid,canonical(chunk)));ids.append(cid)
        self.db.commit();self.audit('document',actor,dict(document_id=docid,chunks=ids))
        if not doc['is_demo']:
            self.request_review('document',docid,actor,dict(title=doc['title'],source_url=doc['url'],candidate_id=doc['candidate_id'],region_name=doc['region_name'],document_sha256=sha(doc)))
        return ids

    @locked
    def search(self,query,region,candidate,election='KR-20240410-NA22',demo=True):
        tokens=set(re.findall(r'[가-힣A-Za-z0-9]+',query))
        results=[]
        for cid,payload in self.db.execute('SELECT id,payload FROM chunk WHERE active=1'):
            c=json.loads(payload)
            if (c['election_id'],c['region_name'],c['candidate_id'],c['is_demo'])!=(election,region,candidate,demo):continue
            score=sum(t in c['text'] for t in tokens) if tokens else 1
            if score: results.append(dict(score=score,**c))
        return sorted(results,key=lambda c:(-c['score'],c['id']))[:5]

    @locked
    def draft(self,region,author,mode=None,article_type="combined",candidate_id=None,news_ids=None,period_from="2024-04-03",period_to="2024-04-17",title=None,explicit_evidence_ids=None):
        snap=self.latest(mode);rows=[r for r in snap['rows'] if r['region_name']==region]
        if not rows: raise ValueError('region not available')
        if article_type not in ('combined','result','pledge','news'):raise ValueError('unknown article type')
        if candidate_id:
            rows=[r for r in rows if r['candidate_id']==candidate_id]
            if not rows:raise ValueError('candidate not available in selected region')
        if title is not None and (not 2<=len(title.strip())<=200):raise ValueError('기사 제목은 2~200자로 입력하세요.')
        references=[]
        if article_type=='news' and not news_ids:raise ValueError('선거 전후 언론 기사에서 참고할 보도를 선택하세요.')
        if news_ids:
            if snap['mode']!='official':raise ValueError('실제 보도 정리는 실제 선거구에서 사용하세요.')
            if not news_ids:raise ValueError('선거 전후 언론 기사에서 참고할 보도를 선택하세요.')
            from datetime import date
            try:
                start=date.fromisoformat(period_from);end=date.fromisoformat(period_to)
                if start>end:raise ValueError()
            except (TypeError,ValueError):raise ValueError('보도 검색 기간을 확인하세요.')
            catalogue=self.news_catalogue()
            for nid in dict.fromkeys(news_ids):
                item=next((item for item in catalogue if item['id']==nid),None)
                if not item or region not in item['regions'] or not period_from<=item['published_date']<=period_to or (candidate_id and rows[0]['candidate_name'] not in item['candidate_names']):raise ValueError('선택 보도의 후보·지역·기간이 일치하지 않습니다.')
                references.append(item)
        sentences=[]
        for r in rows:
            text=result_text(r)
            sentences.append(dict(kind='result',text=text,row_ids=[r['row_id']],values={k:r[k] for k in ['region_name','candidate_id','candidate_name','baseline_at','votes','vote_share','count_rate']}))
            hits=self.search(title or '교통 주거 지역경제',region,r['candidate_id'],demo=r['is_demo']) if article_type in ('combined','pledge','news') else []
            if not hits and article_type in ('combined','pledge','news'):hits=self.search('',region,r['candidate_id'],demo=r['is_demo'])
            if explicit_evidence_ids is not None:
                hits=[]
                for eid in dict.fromkeys(explicit_evidence_ids):
                    record=self.db.execute('SELECT payload,active FROM chunk WHERE id=?',(eid,)).fetchone()
                    if not record or not record[1]:raise ValueError('선택한 공약 근거가 삭제되었거나 비활성입니다.')
                    chunk=json.loads(record[0])
                    if chunk['region_name']!=region or chunk['is_demo']!=(snap['mode']=='demo') or chunk['candidate_id'] not in [row['candidate_id'] for row in rows]:raise ValueError('공약 근거의 후보·지역·자료 종류가 일치하지 않습니다.')
                    if chunk['candidate_id']==r['candidate_id'] and article_type!='result':hits.append(chunk)
            for c in (hits if explicit_evidence_ids is not None else hits[:1]):
                sentences.append(dict(kind='pledge',text=f"{r['candidate_name']}의 공약 자료에는 다음 내용이 제시돼 있다: {c['text']}",candidate_id=r['candidate_id'],region_name=region,evidence_ids=[c['id']],evidence_hashes=[c['sha256']]))
        for reference in references:
            text=f"{reference['published_date']} {reference['publisher']}은 ‘{reference['title']}’ 제목의 보도를 게재했다."
            if reference.get('source_kind')=='google_news':text+=' (구글 뉴스 검색 메타데이터 기준이며 원문 본문은 확인하지 않았다.)'
            sentences.append(dict(kind='news',text=text,evidence_ids=[reference['id']],evidence_hashes=[sha(reference)],region_name=region,candidate_id=candidate_id or '',source_url=reference['url']))
        a=dict(id=secrets.token_hex(8),revision=1,author=author,created_at=now(),snapshot_id=snap['snapshot_id'],mode=snap['mode'],region_name=region,
               title=f"[{('가상 개표' if snap['mode']=='demo' else '실제 결과')}] {region} {rows[0]['candidate_name']+' · ' if candidate_id else ''}"+{'combined':'개표와 공약 확인','result':'후보별 득표 결과','pledge':'후보 공약 근거 비교','news':'선거 전후 보도 참고 초안'}[article_type],
               data_sources=[dict(row_id=r['row_id'],candidate_name=r['candidate_name'],url=r['source_url']) for r in rows],article_type=article_type,candidate_id=candidate_id,candidate_names=[r['candidate_name'] for r in rows],summary=sentences[0]['text'] if sentences else '',
               news_references=references,news_period=dict(start=period_from,end=period_to),generator='근거 기반 문장 템플릿',sentences=sentences,ai_review=dict(verdict='UNAVAILABLE',model=None),status='DRAFT')
        if title is not None:a['title']=title.strip()
        self.save(a);self.audit('draft',author,dict(article_id=a['id'],snapshot_id=a['snapshot_id']))
        return a

    @locked
    def save(self,a):
        self.db.execute('INSERT OR REPLACE INTO article VALUES(?,?,?)',(a['id'],canonical(a),a['status']));self.db.commit()
    @locked
    def get(self,aid):
        r=self.db.execute('SELECT payload FROM article WHERE id=?',(aid,)).fetchone()
        if not r: raise ValueError('article not found')
        return json.loads(r[0])

    @locked
    def validate(self,a,actor='validator'):
        errors=[]
        src=self.db.execute('SELECT payload FROM snapshot WHERE id=?',(a['snapshot_id'],)).fetchone()
        snap=json.loads(src[0]) if src else dict(rows=[])
        rows={r['row_id']:r for r in snap['rows']}
        if a['mode']=='official' and snap.get('stage')=='FINAL_FILE_AGGREGATION' and self.review_state('dataset',a['snapshot_id'])['status']!='APPROVED':errors.append('DATASET_REVIEW_REQUIRED')
        if not a['sentences']: errors.append('EMPTY_ARTICLE')
        if re.search('압승|필승|지지하|무능|당선 확실|당선 예상',a['title']+' '.join(s['text'] for s in a['sentences'])): errors.append('NEUTRALITY')
        for i,s in enumerate(a['sentences']):
            prefix=f'S{i+1}:'
            if not isinstance(s,dict) or not isinstance(s.get('text'),str) or not isinstance(s.get('kind'),str):errors.append(prefix+'INVALID_SENTENCE');continue
            if s['kind']=='result':
                rr=[rows[x] for x in s.get('row_ids',[]) if x in rows]
                if len(rr)!=1: errors.append(prefix+'ROW_NOT_FOUND');continue
                r=rr[0]
                if set(s.get('values',{}))!={'region_name','candidate_id','candidate_name','baseline_at','votes','vote_share','count_rate'}:errors.append(prefix+'MISSING_FIELDS')
                if not r.get('source_url'):errors.append(prefix+'SOURCE_MISSING')
                for k,v in s.get('values',{}).items():
                    if r.get(k)!=v: errors.append(prefix+k.upper()+'_MISMATCH')
                expected=result_text(r)
                if s['text']!=expected: errors.append(prefix+'TEXT_MISMATCH')
                if r['region_name']!=a['region_name']:errors.append(prefix+'REGION_MISMATCH')
                if r['valid_votes']<=0 or abs(r['votes']/r['valid_votes']*100-r['vote_share'])>0.011:errors.append(prefix+'ARITHMETIC')
                try:
                    if r.get('stage')=='FINAL_FILE_AGGREGATION':
                        if r.get('election_date')!='2024-04-10' or r.get('baseline_at') is not None or r.get('count_rate') is not None:raise ValueError()
                    else:
                        dt=datetime.fromisoformat(r['baseline_at'])
                        if dt.tzinfo is None or dt.year!=2024:raise ValueError()
                except (ValueError,TypeError):errors.append(prefix+'DATE')
            elif s['kind']=='pledge':
                ids=s.get('evidence_ids',[])
                if len(ids)!=1:errors.append(prefix+'NO_EVIDENCE');continue
                cr=self.db.execute('SELECT payload,active FROM chunk WHERE id=?',(ids[0],)).fetchone()
                if not cr or not cr[1]:errors.append(prefix+'EVIDENCE_RETIRED');continue
                c=json.loads(cr[0])
                if not c['is_demo'] and self.review_state('document',c['document_id'])['status']!='APPROVED':errors.append(prefix+'DOCUMENT_REVIEW_REQUIRED')
                if c['sha256'] not in s.get('evidence_hashes',[]):errors.append(prefix+'EVIDENCE_VERSION')
                if c['candidate_id']!=s['candidate_id'] or c['region_name']!=a['region_name']:errors.append(prefix+'EVIDENCE_SCOPE')
                if not c.get('url'):errors.append(prefix+'SOURCE_MISSING')
                candidate=next((r['candidate_name'] for r in rows.values() if r['candidate_id']==c['candidate_id']),None)
                if s['text']!=f"{candidate}의 공약 자료에는 다음 내용이 제시돼 있다: {c['text']}":errors.append(prefix+'UNSUPPORTED_TEXT')
                if c['is_demo']!=(a['mode']=='demo'):errors.append(prefix+'MODE_MISMATCH')
            elif s['kind']=='news':
                reference=next((item for item in a.get('news_references',[]) if s.get('evidence_ids')==[item['id']]),None)
                if not reference:errors.append(prefix+'NEWS_REFERENCE_MISSING');continue
                expected=f"{reference['published_date']} {reference['publisher']}은 ‘{reference['title']}’ 제목의 보도를 게재했다."
                if reference.get('source_kind')=='google_news':expected+=' (구글 뉴스 검색 메타데이터 기준이며 원문 본문은 확인하지 않았다.)'
                if s['text']!=expected or s.get('evidence_hashes')!=[sha(reference)] or s.get('source_url')!=reference['url'] or s.get('region_name')!=a['region_name']:errors.append(prefix+'NEWS_REFERENCE_MISMATCH')
            else:errors.append(prefix+'UNSUPPORTED_CLAIM')
        if a.get('article_type','combined') in ('combined','pledge') and not any(s['kind']=='pledge' for s in a['sentences']):errors.append('NO_PLEDGE_EVIDENCE')
        if a.get('article_type')=='news' or a.get('news_references'):
            if not a.get('news_references'):errors.append('NO_NEWS_REFERENCE')
            catalogue=self.news_catalogue()
            for reference in a.get('news_references',[]):
                original=next((item for item in catalogue if item['id']==reference.get('id')),None)
                period=a.get('news_period',{})
                if original!=reference or a['mode']!='official' or a['region_name'] not in reference.get('regions',[]) or not period.get('start','9999')<=reference.get('published_date','')<=period.get('end',''):errors.append('NEWS_REFERENCE_MISMATCH')
        if 'summary' in a and a['summary']!=(a['sentences'][0]['text'] if a['sentences'] else ''):errors.append('SUMMARY_MISMATCH')
        rule='FAIL' if errors else 'PASS'
        ai=a['ai_review']['verdict']
        disagreement=ai in ['PASS','FAIL'] and ai!=rule
        a['validation']=dict(rule=rule,errors=errors,ai=ai,disagreement=disagreement,at=now())
        a['status']='REVIEW_REQUIRED' if errors or disagreement else 'PENDING_HUMAN'
        self.save(a);self.audit('validation',actor,dict(article_id=a['id'],**a['validation']))
        return a

    @locked
    def approve(self,aid,actor,reason,evidence_checked,ai_unavailable_ack=False):
        a=self.validate(self.get(aid),actor)
        if a['validation']['rule']!='PASS' or a['validation']['disagreement']:raise ValueError('approval blocked: failed or disputed')
        if actor==a['author']:raise ValueError('independent reviewer required')
        if not reason.strip() or not evidence_checked:raise ValueError('review reason and evidence confirmation required')
        if a['ai_review']['verdict']=='UNAVAILABLE' and not ai_unavailable_ack:raise ValueError('acknowledge unavailable AI and review manually')
        a.update(status='APPROVED',approved_by=actor,approved_at=now(),approval_reason=reason)
        self.save(a)
        self.db.execute('INSERT INTO approval(article_id,reviewer,reason,created_at) VALUES(?,?,?,?)',(aid,actor,reason,now()));self.db.commit()
        self.audit('approval',actor,dict(article_id=aid,reason=reason,manual_evidence_check=evidence_checked,ai_unavailable_ack=ai_unavailable_ack))
        return a

    @locked
    def retire(self,cid,actor):
        if not self.db.execute('SELECT 1 FROM chunk WHERE id=?',(cid,)).fetchone():raise ValueError('chunk not found')
        self.db.execute('UPDATE chunk SET active=0 WHERE id=?',(cid,))
        for aid,payload in self.db.execute('SELECT id,payload FROM article').fetchall():
            a=json.loads(payload)
            if any(cid in s.get('evidence_ids',[]) for s in a['sentences']):
                a['status']='REVIEW_REQUIRED';a['withdrawn_at']=now();self.save(a)
        self.db.commit();self.audit('retire',actor,dict(chunk_id=cid))

    @locked
    def export(self,aid):
        a=self.get(aid)
        if a['status']!='APPROVED':raise ValueError('only approved article may be exported')
        # Revalidate on a copy. It must not erase a valid existing human approval.
        check=self.validate(dict(a),'export-validator')
        if check['validation']['rule']!='PASS' or check['validation']['disagreement']:raise ValueError('approval invalidated')
        self.save(a)
        return dict(article=a,script='\n'.join(s['text'] for s in a['sentences']),disclosure='시뮬레이션 데이터' if a['mode']=='demo' else '2024년 선거 과거 자료',ai_disclosure='규칙 기반 초안 생성. 생성형 AI 미연결. 사람 검토 후 승인.',snapshot_id=a['snapshot_id'])
