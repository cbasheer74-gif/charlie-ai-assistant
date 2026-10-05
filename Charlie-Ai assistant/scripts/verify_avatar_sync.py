"""Audible controlled replay of the real HUD/viseme pipeline, not a Gemini test.

WordBoundary-derived reference shapes are estimates, not phoneme ground truth.
Run from the repository: python scripts/verify_avatar_sync.py
"""
import ast
import asyncio
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import miniaudio
import numpy as np
import sounddevice as sd
from PyQt6.QtWidgets import QApplication
from core.tts import EdgeTTSEngine
from core.viseme import VisemeStream, text_to_visemes
from ui import HudCanvas


def audio_analyser():
    # Load only the actual production functions, without starting agent services.
    tree = ast.parse((ROOT / 'main.py').read_text(encoding='utf-8-sig'))
    names = {'_pcm_level', '_pcm_visemes'}
    constants = {'_LEVEL_FLOOR', '_LEVEL_FULL', '_VIS_WIN', '_VIS_HOP'}
    nodes = [n for n in tree.body if
             isinstance(n, ast.FunctionDef) and n.name in names or
             isinstance(n, ast.Assign) and any(
                 isinstance(t, ast.Name) and t.id in constants for t in n.targets)]
    namespace = {'np': np}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'main.py', 'exec'), namespace)
    return namespace['_pcm_visemes']


def main():
    app = QApplication.instance() or QApplication([])
    hud = HudCanvas('')
    hud.resize(600, 600)
    hud.show()
    analyse = audio_analyser()
    sentence = 'Mama, papa, baby. Open the blue box. We are happy. Please stop now.'
    reports = []
    for persona, voice in [('male', 'en-US-GuyNeural'), ('female', 'en-US-JennyNeural')]:
        hud.setWindowTitle('CHARLIE lip-sync diagnostic - ' + persona)
        hud.set_persona(persona)
        app.processEvents()
        data, words = asyncio.run(asyncio.wait_for(
            EdgeTTSEngine(voice)._synth_with_boundaries(sentence), timeout=45))
        decoded = miniaudio.decode(data, output_format=miniaudio.SampleFormat.SIGNED16,
                                   nchannels=1, sample_rate=24000)
        pcm = np.asarray(decoded.samples, dtype=np.int16)
        stream_vis = VisemeStream()
        stream_vis.feed_text(sentence)  # Best case: full transcript already available.
        frames = stream_vis.frames(analyse(pcm), .02)
        reference = ['REST'] * len(frames)
        for word in words:
            shapes = text_to_visemes(word['text'])
            duration = word['duration'] / 1e7
            cursor = word['offset'] / 1e7
            weight_sum = sum(weight for _, weight in shapes)
            for name, weight in shapes:
                end = cursor + duration * weight / weight_sum
                for i in range(max(0, int(cursor / .02)), min(len(frames), int(end / .02))):
                    reference[i] = name
                cursor = end
        active = [i for i, frame in enumerate(frames)
                  if frame[0] > .01 and reference[i] != 'REST']
        mismatch = sum(frames[i][3] != reference[i] for i in active)
        position = [0]
        anchor = []
        statuses = []

        def callback(outdata, count, timing, status):
            if status:
                statuses.append(str(status))
            if not anchor:
                anchor.append(time.time() + timing.outputBufferDacTime - timing.currentTime)
            amount = min(count, len(pcm) - position[0])
            outdata.fill(0)
            outdata[:amount, 0] = pcm[position[0]:position[0] + amount]
            position[0] += amount
            if position[0] >= len(pcm):
                raise sd.CallbackStop

        hud._visemes = None
        hud.speaking = True
        hud.state = 'SPEAKING'
        ticks = []
        with sd.OutputStream(samplerate=24000, channels=1, dtype='int16', callback=callback) as output:
            scheduled = False
            deadline = time.monotonic() + len(pcm) / 24000 + 10
            while output.active and time.monotonic() < deadline:
                if anchor and not scheduled:
                    hud.push_visemes(frames, .02, anchor[0])
                    scheduled = True
                app.processEvents()
                ticks.append(time.monotonic())
                time.sleep(.005)
            completed = position[0] == len(pcm) and not output.active
        hud.speaking = False
        hud.state = 'IDLE'
        app.processEvents()
        report = {
            'persona': persona, 'voice': voice, 'words': len(words),
            'speech_seconds': round(len(pcm) / 24000, 3),
            'speaker_playback_completed': completed, 'audio_statuses': statuses,
            'reference_shape_mismatch_percent': round(100 * mismatch / max(1, len(active)), 1),
            'remaining_text_shapes': stream_vis.pending,
            'ui_event_gap_p95_ms': round(float(np.percentile(np.diff(ticks), 95)) * 1000, 1),
            'exact_live_gemini_sync_confirmed': False,
        }
        reports.append(report)
        print(json.dumps(report), flush=True)
    artifact = ROOT / 'avatar-sync-verification.json'
    artifact.write_text(json.dumps({
        'method': 'Real speaker playback and production HUD; full-transcript heuristic vs word-timed estimated shapes.',
        'limits': 'Not a Gemini network session, phoneme ground truth, physical audio loopback or perceptual confirmation.',
        'results': reports,
    }, indent=2), encoding='utf-8')
    hud.close()


if __name__ == '__main__':
    main()
