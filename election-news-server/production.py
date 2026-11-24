"""Create real FHD MP4, SRT, CG stills and a manifest from pinned approved articles."""
import base64
import io
import json
import os
import secrets
import shutil
import subprocess
import threading
import wave
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core import now, canonical, sha

def korean_font():
    candidates=[os.environ.get('NEWS_FONT',''),'C:/Windows/Fonts/malgun.ttf',
        '/usr/share/fonts/truetype/nanum/NanumGothic.ttf','/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/System/Library/Fonts/AppleSDGothicNeo.ttc']
    return next((p for p in candidates if p and Path(p).is_file()),None)

def subtitle_time(seconds):
    ms=round(seconds*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'

def wrap(draw,text,font,width):
    lines=[];line=''
    for c in text:
        if c=='\n' or draw.textlength(line+c,font=font)>width:
            lines.append(line);line='' if c=='\n' else c
        else:line+=c
    if line:lines.append(line)
    return lines

def render_bundle(folder,bundles,seconds,audio=None,audio_disclosure='none'):
    from PIL import Image,ImageDraw,ImageFont
    import imageio_ffmpeg
    font_path=korean_font()
    if not font_path:raise ValueError('Korean font required. Set NEWS_FONT or install fonts-nanum.')
    font=lambda n:ImageFont.truetype(font_path,n)
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    slides=[];subtitles=[];timeline=[];cursor=0
    for bundle in bundles:
        article=bundle['article'];items=[]
        measure=ImageDraw.Draw(Image.new('RGB',(1,1)))
        for sentence in article['sentences']:
            lines=wrap(measure,sentence['text'],font(39),1760)
            items.extend((sentence,lines[i:i+8]) for i in range(0,len(lines),8))
        duration=seconds/len(items)
        for sentence,body_lines in items:
            image=Image.new('RGB',(1920,1080),'#0c213d');draw=ImageDraw.Draw(image)
            draw.rectangle((0,0,1920,105),fill='#163e5d');draw.text((62,25),'VR 선거보도 시스템',font=font(38),fill='white')
            draw.text((62,146),article['region_name']+'  |  '+('시뮬레이션' if article['mode']=='demo' else '2024년 공식 파일 집계'),font=font(32),fill='#57ddd3')
            title_lines=wrap(draw,article['title'],font(46),1780)
            y=215
            for line in title_lines[:2]:draw.text((62,y),line,font=font(46),fill='white');y+=64
            y+=40
            for line in body_lines:draw.text((62,y),line,font=font(39),fill='#eef6ff');y+=61
            refs=sentence.get('row_ids') or sentence.get('evidence_ids',[])
            draw.rectangle((0,900,1920,1080),fill='#113b51')
            draw.text((62,923),'근거 ID  '+', '.join(refs)[:110],font=font(23),fill='#cbe9ed')
            draw.text((62,966),bundle['disclosure']+' · 승인본 '+article['id'],font=font(25),fill='white')
            voice_label={'none':'음성 없음','human':'제작자 확인 녹음 음성','synthetic':'AI 합성 음성 사용'}[audio_disclosure]
            draw.text((62,1010),'규칙 기반 초안 · 생성형 AI 미연결 · '+voice_label,font=font(23),fill='#e1eaf3')
            index=len(slides);filename=f'cg-{index:03}.png';image.save(folder/filename)
            slides.append((filename,duration));end=cursor+duration
            caption='\n'.join(body_lines)
            subtitles.append(f"{len(subtitles)+1}\n{subtitle_time(cursor)} --> {subtitle_time(end)}\n{caption}\n")
            timeline.append(dict(start=cursor,end=end,article_id=article['id'],snapshot_id=article['snapshot_id'],evidence_ids=refs))
            cursor=end
    if cursor>1200.001:raise ValueError('video must not exceed 20 minutes')
    (folder/'subtitles.srt').write_text('\n'.join(subtitles),encoding='utf-8')
    (folder/'script.txt').write_text('\n\n'.join(b['script'] for b in bundles),encoding='utf-8')
    (folder/'approved-bundles.json').write_text(json.dumps(bundles,ensure_ascii=False,indent=2),encoding='utf-8')
    concat=''.join(f"file '{name}'\nduration {duration:.6f}\n" for name,duration in slides)+f"file '{slides[-1][0]}'\n"
    (folder/'slides.txt').write_text(concat,encoding='utf-8')
    command=[imageio_ffmpeg.get_ffmpeg_exe(),'-y','-f','concat','-safe','0','-i','slides.txt']
    if audio:
        (folder/'narration.wav').write_bytes(audio)
        command+=['-i','narration.wav','-af','apad','-c:a','aac']
    command+=['-t',f'{cursor:.6f}','-r','25','-c:v','libx264','-preset','ultrafast','-crf','24','-pix_fmt','yuv420p','-movflags','+faststart','news.mp4']
    with (folder/'ffmpeg.log').open('w',encoding='utf-8') as log:
        subprocess.run(command,cwd=folder,stdout=log,stderr=log,check=True,timeout=1800)
    manifest=dict(created_at=now(),width=1920,height=1080,fps=25,duration_seconds=round(cursor,3),
        narration=audio_disclosure,mode=bundles[0]['article']['mode'],timeline=timeline,
        articles=[dict(id=b['article']['id'],snapshot_id=b['snapshot_id'],bundle_sha256=sha(b)) for b in bundles])
    (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    with zipfile.ZipFile(folder/'news-package.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for p in folder.iterdir():
            if p.suffix in ['.mp4','.srt','.png','.json'] or p.name=='script.txt':archive.write(p,p.name)
    return manifest

class Production:
    def __init__(self,room):
        self.room=room;self.pool=ThreadPoolExecutor(max_workers=1);self.guard=threading.Lock()

    def recover_interrupted(self):
        with self.room.lock:
            # Only the actual service startup recovers jobs, not OpenAPI inspection.
            self.room.db.execute("UPDATE render_job SET status='FAILED' WHERE status IN ('QUEUED','RUNNING')")
            self.room.db.commit()

    def get(self,jid):
        with self.room.lock:
            r=self.room.db.execute('SELECT author,status,payload,created_at FROM render_job WHERE id=?',(jid,)).fetchone()
        if not r:raise ValueError('render job not found')
        return dict(id=jid,author=r[0],status=r[1],**json.loads(r[2]),created_at=r[3])

    def update(self,jid,state,details):
        with self.room.lock:
            self.room.db.execute('UPDATE render_job SET status=?,payload=? WHERE id=?',(state,canonical(details),jid));self.room.db.commit()

    def submit(self,ids,seconds,actor,audio_b64=None,audio_disclosure='none'):
        if type(seconds) is not int or not 5<=seconds<=120 or len(ids)*seconds>1200:raise ValueError('duration must be 5-120 seconds per article, total <=1200')
        bundles=self.room.prepare_render(ids)
        if (audio_b64 and audio_disclosure not in ['human','synthetic']) or (not audio_b64 and audio_disclosure!='none'):raise ValueError('declare provided narration as human or synthetic, or none without audio')
        audio=None
        if audio_b64:
            try:
                if len(audio_b64)>85000000:raise ValueError('audio too large')
                audio=base64.b64decode(audio_b64,validate=True)
                with wave.open(io.BytesIO(audio)) as wav:
                    if wav.getnchannels() not in [1,2] or wav.getsampwidth() not in [1,2,3,4] or wav.getnframes()/wav.getframerate()>1200:raise ValueError('invalid WAV')
            except Exception:raise ValueError('valid PCM WAV required, at most 20 minutes')
        if not korean_font():raise ValueError('Korean font unavailable; configure NEWS_FONT')
        with self.guard,self.room.lock:
            if self.room.db.execute("SELECT COUNT(*) FROM render_job WHERE status IN ('QUEUED','RUNNING')").fetchone()[0]>=4:raise ValueError('render queue full')
            jid=secrets.token_hex(12);details=dict(article_ids=ids,seconds_per_article=seconds,mode=bundles[0]['article']['mode'],narration=audio_disclosure)
            self.room.db.execute('INSERT INTO render_job VALUES(?,?,?,?,?)',(jid,actor,'QUEUED',canonical(details),now()));self.room.db.commit()
        self.room.audit('render_queued',actor,dict(job_id=jid,article_ids=ids))
        self.pool.submit(self.run,jid,details,bundles,audio)
        return self.get(jid)

    def still_valid(self,job):
        return self.room.prepare_render(job['article_ids'])

    def run(self,jid,details,bundles,audio):
        folder=self.room.root/'renders'/jid
        try:
            self.update(jid,'RUNNING',details)
            manifest=render_bundle(folder,bundles,details['seconds_per_article'],audio,details['narration'])
            current=self.still_valid(details)
            if [sha(b) for b in current]!=[sha(b) for b in bundles]:raise ValueError('approved article changed during rendering')
            self.update(jid,'COMPLETED',dict(**details,manifest=manifest))
            self.room.audit('render_completed','renderer',dict(job_id=jid))
        except Exception as exc:
            self.update(jid,'FAILED',dict(**details,error=str(exc)[:500]))
            self.room.audit('render_failed','renderer',dict(job_id=jid,error=str(exc)[:500]))

    def file(self,jid,name):
        if name not in ['news.mp4','news-package.zip','subtitles.srt','manifest.json','script.txt']:raise ValueError('file not available')
        job=self.get(jid)
        if job['status']!='COMPLETED':raise ValueError('render not completed')
        bundles=self.still_valid(job)
        if [sha(b) for b in bundles]!=[a['bundle_sha256'] for a in job['manifest']['articles']]:raise ValueError('render approval changed; re-render required')
        file=self.room.root/'renders'/jid/name
        if not file.exists():raise ValueError('render file missing')
        return file
