#!/usr/bin/env python3
"""
build_voice.py — the ship's computer. Four fixed lines, generated once.

The lines never change and are the same for every reader, so this is a build
step, not a runtime call: no API key in the browser, no per-view cost, no
latency, and the same voice on every device. The browser's own
`speechSynthesis` would have been free but its voices differ wildly between
macOS, Windows and Android, which is no way to run a brand moment.

  Google Cloud TTS  ->  raw speech
  ffmpeg            ->  the sci-fi treatment

The treatment, and why each part is there:

  pitch -2 semitones, rate 1.0    Slightly low, normal pace. 0.86 was the first
                                  attempt and read as laboured rather than calm
                                  — a ship's computer is unhurried, not slow,
                                  and the difference is audible.
  highpass 180 / lowpass 6800     It is coming out of a speaker in a bulkhead,
                                  not standing next to you. Band-limiting is the
                                  single biggest "this is a machine talking" cue.
  chorus, very light              Two voices a few milliseconds apart. Enough to
                                  stop it sounding like a person, far short of a
                                  robot. This is the line most worth tuning.
  aecho, small                    A hard-surfaced room. Places it somewhere.

Run:
  set -a && source /home/fields/Fields_Orchestrator/.env && set +a
  python3 build_voice.py            # writes voice/*.mp3 + voice/index.json
  python3 build_voice.py --audition        # rebuild the candidate set
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
OUT = HERE / "voice"

# Must match SCRIPT in crack-demo.html.
LINES = [
    ("01", "Analysing selling strategy."),
    ("02", "Construction sequence initiated."),
    # "T minus" spelled out: the TTS reads a literal "T-3" as "tee dash three".
    ("03", "Approaching completion in T minus 3 seconds."),
    # The countdown, one clip per number so the on-screen pulse can land on each
    # one. A single "three, two, one" clip would need the beats guessed from its
    # waveform, and they would drift the moment the voice or rate changed.
    ("c3", "Three."),
    ("c2", "Two."),
    ("c1", "One."),
    ("04", "Construction completed."),
]

# Will's pick from the audition, 2026-08-04. Studio is Google's most produced
# family — a read with intent behind it rather than a flat rendering — and the
# British one carries that without the warmth the Australian voices bring.
# Right for a machine telling you what it is doing; wrong for anything where
# Fields is speaking as itself.
DEFAULT_VOICE = "en-GB-Studio-C"

# Candidates for the audition. Deliberately spread across accent and family
# rather than eight near-identical reads: Chirp3 is the newest and most natural,
# Studio is the most produced, News is clipped and impersonal, Neural2 is the
# plainest. A ship's computer could credibly be any of them and it is not my
# call to make.
CANDIDATES = [
    ("gb-neural2-a",  "en-GB-Neural2-A",            "British · plain"),
    ("gb-neural2-f",  "en-GB-Neural2-F",            "British · lower"),
    ("gb-studio-c",   "en-GB-Studio-C",             "British · produced"),
    ("gb-news-h",     "en-GB-News-H",               "British · clipped, newsreader"),
    ("gb-chirp-aoede","en-GB-Chirp3-HD-Aoede",      "British · newest model"),
    ("gb-chirp-kore", "en-GB-Chirp3-HD-Kore",       "British · newest, cooler"),
    ("us-neural2-c",  "en-US-Neural2-C",            "American · plain"),
    ("us-studio-o",   "en-US-Studio-O",             "American · produced"),
    ("us-chirp-kore", "en-US-Chirp3-HD-Kore",       "American · newest model"),
    ("au-neural2-c",  "en-AU-Neural2-C",            "Australian · plain"),
    ("au-chirp-kore", "en-AU-Chirp3-HD-Kore",       "Australian · newest model"),
]

FILTER = (
    "highpass=f=180,"
    "lowpass=f=6800,"
    "chorus=0.6:0.9:14:0.35:0.25:2,"
    "aecho=0.42:0.85:38:0.16,"
    "acompressor=threshold=-18dB:ratio=3:attack=8:release=180,"
    "loudnorm=I=-18:TP=-2:LRA=9"
)


def token() -> str:
    return subprocess.run(["gcloud", "auth", "print-access-token"],
                          capture_output=True, text=True, check=True).stdout.strip()


def synth(text: str, voice: str, tok: str, rate: float, pitch: float) -> bytes:
    lang = "-".join(voice.split("-")[:2])
    r = requests.post(
        "https://texttospeech.googleapis.com/v1/text:synthesize",
        headers={"Authorization": f"Bearer {tok}",
                 "x-goog-user-project": "fields-estate"},
        json={
            "input": {"text": text},
            "voice": {"languageCode": lang, "name": voice},
            "audioConfig": {
                "audioEncoding": "LINEAR16",
                # 0.86 was too slow — it read as laboured rather than calm.
                "speakingRate": rate,
                # Chirp3 rejects pitch; it is a different model class.
                **({} if "Chirp3" in voice else {"pitch": pitch}),
                "sampleRateHertz": 24000,
            },
        }, timeout=45)
    if r.status_code != 200:
        raise SystemExit(f"TTS failed {r.status_code}: {r.text[:300]}")
    return base64.b64decode(r.json()["audioContent"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default=DEFAULT_VOICE)
    ap.add_argument("--rate", type=float, default=1.0)
    ap.add_argument("--pitch", type=float, default=-2.0)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--audition", action="store_true",
                    help="build every candidate into voice/auditions/<slug>/")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.audition:
        for slug, voice, note in CANDIDATES:
            d = OUT / "auditions" / slug
            build_set(voice, d, a.rate, a.pitch, note)
        idx = [{"slug": s, "voice": v, "note": n} for s, v, n in CANDIDATES]
        (OUT / "auditions" / "index.json").write_text(
            json.dumps({"rate": a.rate, "pitch": a.pitch, "candidates": idx}, indent=2))
        print(f"\n{len(CANDIDATES)} candidates at rate {a.rate}")
        return

    build_set(a.voice, a.out_dir or OUT, a.rate, a.pitch, "")


def build_set(voice: str, out: Path, rate: float, pitch: float, note: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    tok = token()
    index = []
    for slug, text in LINES:
        raw = out / f"{slug}.raw.wav"
        raw.write_bytes(synth(text, voice, tok, rate, pitch))
        mp3 = out / f"{slug}.mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
                        "-af", FILTER, "-c:a", "libmp3lame", "-b:a", "64k",
                        "-ac", "1", str(mp3)], check=True)
        dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                              "format=duration", "-of", "csv=p=0", str(mp3)],
                             capture_output=True, text=True).stdout.strip()
        raw.unlink()
        index.append({"id": slug, "text": text, "file": f"{slug}.mp3",
                      "seconds": round(float(dur), 2),
                      "kb": round(mp3.stat().st_size / 1024, 1)})

    (out / "index.json").write_text(json.dumps(
        {"voice": voice, "note": note, "rate": rate, "filter": FILTER,
         "lines": index}, indent=2))
    total = sum(l["kb"] for l in index)
    secs = sum(l["seconds"] for l in index)
    print(f"  {voice:<26} {secs:>5.2f}s total  {total:>5.1f} KB  {note}")


if __name__ == "__main__":
    main()
