import hashlib,json,wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_narration_samples_are_non_silent_pcm_and_match_transcripts():
    folder=ROOT/'election-news-server/static/samples/narration'
    catalog=json.loads((folder/'index.json').read_text(encoding='utf-8'))
    assert catalog['mode']=='demo' and catalog['disclosure']=='synthetic'
    assert {item['id'] for item in catalog['items']}=={'opening','candidates','closing'}
    for item in catalog['items']:
        audio=folder/Path(item['audio']).name
        assert hashlib.sha256(audio.read_bytes()).hexdigest()==item['sha256']
        assert (folder/Path(item['transcript']).name).read_text(encoding='utf-8').strip()==item['text']
        assert '가상' in item['text']
        with wave.open(str(audio)) as wav:
            assert wav.getcomptype()=='NONE' and wav.getsampwidth()==2
            assert wav.getnchannels()==1 and wav.getframerate()==22050
            assert abs(wav.getnframes()/wav.getframerate()-item['duration'])<.01
            frames=wav.readframes(wav.getnframes())
            assert sum(value!=0 for value in frames)>len(frames)*.1
