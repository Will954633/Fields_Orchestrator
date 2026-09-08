#!/usr/bin/env python3
import json, sys, time
from faster_whisper import WhisperModel

WAV = "/home/fields/Fields_Orchestrator/10_Market_Report/Video_Production/Video_Editing_Process/qa/audio.wav"
OUT = "/home/fields/Fields_Orchestrator/10_Market_Report/Video_Production/Video_Editing_Process/qa/words.json"

t0 = time.time()
model = WhisperModel("small.en", device="cpu", compute_type="int8")
segments, info = model.transcribe(WAV, word_timestamps=True, beam_size=5,
                                  vad_filter=True, language="en")
words = []
for seg in segments:
    if seg.words:
        for w in seg.words:
            words.append({"w": w.word, "start": round(w.start, 3), "end": round(w.end, 3)})
    print(f"[{seg.start:6.1f}] {seg.text[:70]}", file=sys.stderr)

json.dump(words, open(OUT, "w"), indent=0)
print(f"\n{len(words)} words in {time.time()-t0:.0f}s -> {OUT}", file=sys.stderr)
