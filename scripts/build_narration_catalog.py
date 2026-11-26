"""Inspect generated PCM WAV samples and record reproducible catalog metadata."""
import hashlib,json,wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'election-news-server/static/samples/narration'
data=json.loads((folder/'scripts.json').read_text(encoding='utf-8'))
for item in data['items']:
    path=folder/(item['id']+'.wav')
    with wave.open(str(path)) as wav:
        assert wav.getcomptype()=='NONE' and wav.getnchannels() in [1,2]
        item.update(duration=round(wav.getnframes()/wav.getframerate(),2),sample_rate=wav.getframerate(),channels=wav.getnchannels(),sample_width=wav.getsampwidth(),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),audio='/static/samples/narration/'+path.name,transcript='/static/samples/narration/'+item['id']+'.txt')
    (folder/(item['id']+'.txt')).write_text(item['text']+'\n',encoding='utf-8')
(folder/'index.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print('Narration catalog:',len(data['items']),'PCM WAV samples')
