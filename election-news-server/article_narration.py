"""Create local Korean PCM narration from pinned approved article sentences."""
import json,os,secrets,shutil,subprocess,threading,wave,re
from pathlib import Path
from core import sha,now

def broadcast_text(text):
    text=re.sub(r'이 내용은 사용자 설정의 가상 공약이며 실제 후보의 공약이 아니다\.?','',text)
    text=re.sub(r'\(가상 후보\s*\d+\)', ' 후보',text)
    text=re.sub(r',\s*가상 정당', '',text)
    text=re.sub(r'가상\s*후보(?:\s*\d+)?', '후보',text)
    text=text.replace('가상','').replace('시뮬레이션','')
    text=text.replace('구체적인 일정·예산은 설정하지 않았다.','구체적인 일정과 예산은 명시되지 않았습니다.')
    text=re.sub(r'[^.。!?]*의 공약 자료에는 다음 내용이 제시돼 있다:\s*','',text)
    text=text.replace('제시한다.','제시했습니다.').replace('%다.','%입니다.')
    text=re.sub(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):\d{2}(?:[+-]\d{2}:\d{2}|Z)',lambda m:f'{int(m[1])}년 {int(m[2])}월 {int(m[3])}일 {int(m[4])}시 {int(m[5])}분',text)
    text=re.sub(r'[ \t]+',' ',text).strip()
    return text

def broadcast_story(article):
    """A broadcast rendition of approved facts; never rewrites the approved source."""
    from election_simulation import DEMO_CANDIDATES
    names=article.get('candidate_names',[])
    profile=next((p for p in DEMO_CANDIDATES if names==[p['name']]),None)
    generic=dict(title=broadcast_text(article['title']),sentences=[dict(sentence,text=broadcast_text(sentence['text'])) for sentence in article['sentences']])
    if article.get('mode')!='demo' or article.get('region_name')!='하늘도시갑' or not profile:return generic
    name=profile['name'];party=profile['party'];sentences=[]
    keywords={'서지도':['교통','생활','인프라'],'한반도':['원도심','청년','세금'],'박리본':['돌봄','환경','주거']}
    headlines={'서지도':'서지도, 교통·생활 인프라 확충 공약 제시','한반도':'한반도, 원도심 재정비·청년 일자리 공약 제시','박리본':'박리본, 돌봄·환경·서민 주거 안정 공약 제시'}
    pledge=next((item for item in article['sentences'] if item['kind']=='pledge' and all(word in item['text'] for word in keywords[name])),None)
    for source in article['sentences']:
        if source['kind']=='result':
            values=source.get('values',{})
            if values.get('candidate_name')==name and values.get('votes') is not None and values.get('vote_share') is not None:
                baseline=broadcast_text(values.get('baseline_at') or '')
                text=f"하늘도시갑 {party} {name} 후보의 개표 현황입니다. {baseline+' 기준, ' if baseline else ''}{name} 후보는 {values['votes']:,}표를 얻어 득표율 {values['vote_share']:.2f}퍼센트를 기록했습니다."
                if values.get('count_rate') is not None:text+=f" 이 시점의 개표율은 {values['count_rate']:g}퍼센트입니다."
                sentences.append(dict(source,text=text))
        elif source is pledge:
            text=f"{name} 후보는 공약 자료에서 {profile['pledge']}"
            text=broadcast_text(text)
            if '구체적인 일정·예산은 설정하지 않았다' in source['text']:text+=' 구체적인 추진 일정과 예산은 자료에 명시되지 않았습니다.'
            sentences.append(dict(source,text=text))
        elif source['kind']=='pledge':sentences.append(dict(source,text=broadcast_text(source['text'])))
        elif source['kind']=='news' and not source.get('source_url','').startswith('demo://news/'):
            sentences.append(dict(source,text=broadcast_text(source['text'])))
    return dict(title=headlines[name] if pledge else f'하늘도시갑 {name} 후보 개표 현황',sentences=sentences or generic['sentences'])

def broadcast_script(bundles):
    stories=[broadcast_story(bundle['article']) for bundle in bundles]
    return '\n\n'.join(story['title']+'\n'+'\n'.join(sentence['text'] for sentence in story['sentences']) for story in stories)

class ArticleNarration:
    def __init__(self,room):self.room=room;self.guard=threading.Lock()
    def create(self,ids,actor):
        with self.guard:
            bundles=self.room.prepare_render(ids)
            text=broadcast_script(bundles)
            if len(text)>30000:raise ValueError('내레이션 대본은 3만 자 이내로 제작하세요.')
            shell=shutil.which('pwsh') or shutil.which('powershell')
            if os.name!='nt' or not shell:raise ValueError('한국어 음성 자동 생성은 Windows Heami 음성이 설치된 PC에서 지원합니다. 녹음한 PCM WAV를 업로드할 수 있습니다.')
            records=[]
            for label,rate in [('표준 보도',0),('차분한 해설',-2),('빠른 브리핑',2)]:
                nid=secrets.token_hex(16);folder=self.room.root/'narrations'/nid;folder.mkdir(parents=True)
                script=folder/'script.txt';script.write_text(text,encoding='utf-8')
                audio=folder/'narration.wav'
                try:
                    subprocess.run([shell,'-NoProfile','-NonInteractive','-File',str(Path(__file__).resolve().parents[1]/'scripts/synthesize_article.ps1'),'-TextPath',str(script.resolve()),'-OutputPath',str(audio.resolve()),'-Rate',str(rate)],capture_output=True,timeout=180,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    with wave.open(str(audio)) as wav:duration=wav.getnframes()/wav.getframerate()
                except Exception as exc:raise ValueError('한국어 음성 생성에 실패했습니다. Windows Heami 음성을 확인하거나 PCM WAV를 업로드하세요.') from exc
                if not 0<duration<=1200:raise ValueError('음성 길이는 20분 이내여야 합니다.')
                record=dict(id=nid,article_ids=ids,bundle_hashes=[sha(b) for b in bundles],text=text,duration=round(duration,2),created_at=now(),voice='Microsoft Heami Windows TTS',label=label,rate=rate,disclosure='synthetic',source_mode=bundles[0]['article']['mode'],script_kind='broadcast rendition of approved text',audio_url='/api/production/narration/'+nid+'/audio')
                if [sha(b) for b in self.room.prepare_render(ids)]!=record['bundle_hashes']:raise ValueError('음성 생성 중 기사 승인이 변경됐습니다. 다시 생성하세요.')
                (folder/'record.json').write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8')
                records.append(record)
            self.room.audit('article_narration',actor,dict(narration_ids=[r['id'] for r in records],article_ids=ids,voice=records[0]['voice']))
            result=dict(**records[0],variants=[{k:r[k] for k in ['id','label','rate','duration','audio_url']} for r in records])
            latest=self.room.root/'narrations'/'latest-broadcast.json'
            temporary=latest.with_suffix('.tmp')
            temporary.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');temporary.replace(latest)
            return result
    def cached(self,ids):
        path=self.room.root/'narrations'/'latest-broadcast.json'
        if not path.is_file():return None
        record=json.loads(path.read_text(encoding='utf-8'))
        bundles=self.room.prepare_render(ids)
        if record.get('article_ids')!=ids or record.get('text')!=broadcast_script(bundles) or record.get('bundle_hashes')!=[sha(b) for b in bundles]:return None
        if len(record.get('variants',[]))!=3:return None
        for variant in record['variants']:self.file(variant['id'])
        return record

    def file(self,nid):
        if len(nid)!=32 or any(c not in '0123456789abcdef' for c in nid):raise ValueError('음성을 찾을 수 없습니다.')
        folder=self.room.root/'narrations'/nid
        if not (folder/'record.json').is_file():raise ValueError('음성을 찾을 수 없습니다.')
        record=json.loads((folder/'record.json').read_text(encoding='utf-8'))
        if [sha(b) for b in self.room.prepare_render(record['article_ids'])]!=record['bundle_hashes']:raise ValueError('기사 승인이 변경되어 음성을 사용할 수 없습니다.')
        return folder/'narration.wav'
