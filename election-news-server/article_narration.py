"""Create local Korean PCM narration from pinned approved article sentences."""
import json,os,secrets,shutil,subprocess,threading,wave
from pathlib import Path
from core import sha,now

class ArticleNarration:
    def __init__(self,room):self.room=room;self.guard=threading.Lock()
    def create(self,ids,actor):
        with self.guard:
            bundles=self.room.prepare_render(ids)
            text=('가상 선거 보도입니다.\n\n' if bundles[0]['article']['mode']=='demo' else '2024년 총선 선거 보도입니다.\n\n')+'\n\n'.join(b['article']['title']+'\n'+'\n'.join(s['text'] for s in b['article']['sentences']) for b in bundles)
            if len(text)>30000:raise ValueError('내레이션 대본은 3만 자 이내로 제작하세요.')
            shell=shutil.which('pwsh') or shutil.which('powershell')
            if os.name!='nt' or not shell:raise ValueError('한국어 음성 자동 생성은 Windows Heami 음성이 설치된 PC에서 지원합니다. 녹음한 PCM WAV를 업로드할 수 있습니다.')
            nid=secrets.token_hex(16);folder=self.room.root/'narrations'/nid;folder.mkdir(parents=True)
            script=folder/'script.txt';script.write_text(text,encoding='utf-8')
            audio=folder/'narration.wav'
            try:
                subprocess.run([shell,'-NoProfile','-NonInteractive','-File',str(Path(__file__).resolve().parents[1]/'scripts/synthesize_article.ps1'),'-TextPath',str(script.resolve()),'-OutputPath',str(audio.resolve())],capture_output=True,timeout=180,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                with wave.open(str(audio)) as wav:duration=wav.getnframes()/wav.getframerate()
            except Exception as exc:raise ValueError('한국어 음성 생성에 실패했습니다. Windows Heami 음성을 확인하거나 PCM WAV를 업로드하세요.') from exc
            if not 0<duration<=1200:raise ValueError('음성 길이는 20분 이내여야 합니다.')
            record=dict(id=nid,article_ids=ids,bundle_hashes=[sha(b) for b in bundles],text=text,duration=round(duration,2),created_at=now(),voice='Microsoft Heami Windows TTS',disclosure='synthetic',audio_url='/api/production/narration/'+nid+'/audio')
            # Recheck approval after synthesis rather than return a superseded recording.
            if [sha(b) for b in self.room.prepare_render(ids)]!=record['bundle_hashes']:raise ValueError('음성 생성 중 기사 승인이 변경됐습니다. 다시 생성하세요.')
            (folder/'record.json').write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8')
            self.room.audit('article_narration',actor,dict(narration_id=nid,article_ids=ids,duration=record['duration'],voice=record['voice']))
            return record
    def file(self,nid):
        if len(nid)!=32 or any(c not in '0123456789abcdef' for c in nid):raise ValueError('음성을 찾을 수 없습니다.')
        folder=self.room.root/'narrations'/nid
        if not (folder/'record.json').is_file():raise ValueError('음성을 찾을 수 없습니다.')
        record=json.loads((folder/'record.json').read_text(encoding='utf-8'))
        if [sha(b) for b in self.room.prepare_render(record['article_ids'])]!=record['bundle_hashes']:raise ValueError('기사 승인이 변경되어 음성을 사용할 수 없습니다.')
        return folder/'narration.wav'
