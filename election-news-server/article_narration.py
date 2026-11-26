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

def broadcast_script(bundles):
    return '\n\n'.join(broadcast_text(b['article']['title'])+'\n'+'\n'.join(broadcast_text(s['text']) for s in b['article']['sentences']) for b in bundles)

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
            return dict(**records[0],variants=[{k:r[k] for k in ['id','label','rate','duration','audio_url']} for r in records])
    def file(self,nid):
        if len(nid)!=32 or any(c not in '0123456789abcdef' for c in nid):raise ValueError('음성을 찾을 수 없습니다.')
        folder=self.room.root/'narrations'/nid
        if not (folder/'record.json').is_file():raise ValueError('음성을 찾을 수 없습니다.')
        record=json.loads((folder/'record.json').read_text(encoding='utf-8'))
        if [sha(b) for b in self.room.prepare_render(record['article_ids'])]!=record['bundle_hashes']:raise ValueError('기사 승인이 변경되어 음성을 사용할 수 없습니다.')
        return folder/'narration.wav'
