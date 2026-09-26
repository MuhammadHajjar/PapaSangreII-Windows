"""Transcribe the game's narration offline with faster-whisper.

    python tools/transcribe.py [model]      -> build/transcripts/<model>.json

Every file under sounds/ whose name says it is speech (SPEECH, prompt, tuto,
warning, fail, UOS narration in global_sounds) is transcribed.  Two models are
run and compared by tools/compare_transcripts.py; a line the models disagree on
is checked by ear before it is trusted.
"""
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLE = os.path.join(ROOT, 'reference', 'Payload', 'Papa Sangre II.app', 'sounds')
PAT = re.compile(r'SPEECH|prompt|tuto|warning|fail|lost_memory|_speak|narrat|voice', re.I)


def wanted():
    out = []
    for dp, _d, fs in os.walk(BUNDLE):
        rel = os.path.relpath(dp, BUNDLE).replace(os.sep, '/')
        for f in sorted(fs):
            if not f.endswith(('.m4a', '.mp3')):
                continue
            if PAT.search(f) or rel.startswith(('ps2_Intro', 'global_sounds', 'menu')):
                out.append(os.path.join(dp, f))
    return sorted(out)


def main():
    model_name = sys.argv[1] if len(sys.argv) > 1 else 'medium.en'
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device='cpu', compute_type='int8')
    files = wanted()
    print(len(files), 'files', flush=True)
    res = {}
    t0 = time.time()
    for i, p in enumerate(files):
        rel = os.path.relpath(p, BUNDLE).replace(os.sep, '/')
        try:
            segs, info = model.transcribe(p, language='en', beam_size=5, vad_filter=False)
            text = ' '.join(s.text.strip() for s in segs).strip()
            res[rel] = {'text': text, 'duration': round(info.duration, 2)}
        except Exception as e:                       # noqa: BLE001
            res[rel] = {'text': '', 'error': repr(e)}
        print(f'{i + 1}/{len(files)} {rel}: {res[rel]["text"][:90]}', flush=True)
    out = os.path.join(ROOT, 'build', 'transcripts', model_name + '.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(res, fh, indent=1, ensure_ascii=False)
    print('wrote', out, f'{time.time() - t0:.0f}s')


if __name__ == '__main__':
    main()
