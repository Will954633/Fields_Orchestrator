"""
vlib — shared helpers for the raw→edited walkthrough video pipeline.

Everything that touches ffmpeg, Gemini/Vertex (transcription + face-centring) and
the circle mask lives here so the stage scripts (00–04) stay thin and declarative.

No state, no side effects on import. Designed to run under /home/fields/venv with
`set -a && source /home/fields/Fields_Orchestrator/.env` already applied (the stage
scripts call load_env() so a bare cron line still works — see CLAUDE.md Rule 7 §3).
"""
from __future__ import annotations
import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

ORCH_ROOT = "/home/fields/Fields_Orchestrator"
if ORCH_ROOT not in sys.path:
    sys.path.insert(0, ORCH_ROOT)

# ----------------------------------------------------------------------------- env
def load_env() -> None:
    """Load Orchestrator .env into os.environ if not already present.
    Mirrors the CLAUDE.md Rule 7 §3 requirement: a job must load its own env."""
    if os.environ.get("_VLIB_ENV_LOADED"):
        return
    envp = Path(ORCH_ROOT) / ".env"
    if envp.exists():
        for line in envp.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)
    os.environ["_VLIB_ENV_LOADED"] = "1"


# ----------------------------------------------------------------------------- shell
def run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a command. Raises on non-zero when check=True. ffmpeg goes to stderr;
    we surface the tail on failure so a broken filtergraph is legible."""
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and proc.returncode != 0:
        tail = (proc.stderr or "")[-2500:]
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd[:6])} …\n{tail}")
    return proc


def ffprobe(path: str) -> dict:
    p = run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture=True,
    )
    return json.loads(p.stdout)


def probe_summary(path: str) -> dict:
    """Compact, pipeline-relevant view of one media file."""
    j = ffprobe(path)
    v = next((s for s in j["streams"] if s["codec_type"] == "video"
              and s.get("codec_name") != "mjpeg"), {})
    a = next((s for s in j["streams"] if s["codec_type"] == "audio"), {})
    num, den = (v.get("r_frame_rate", "0/1").split("/") + ["1"])[:2]
    fps = round(float(num) / float(den or 1), 3) if float(den or 1) else 0.0
    return {
        "path": str(path),
        "duration": round(float(j["format"].get("duration", 0)), 3),
        "size": int(j["format"].get("size", 0)),
        "width": v.get("width"),
        "height": v.get("height"),
        "fps": fps,
        "vcodec": v.get("codec_name"),
        "acodec": a.get("codec_name"),
        "sample_rate": a.get("sample_rate"),
        "channels": a.get("channels"),
    }


# ----------------------------------------------------------------------------- audio for ASR
def extract_audio_for_asr(src: str, dst_mp3: str, start: float | None = None,
                          end: float | None = None) -> str:
    """Mono 16 kHz mp3, low bitrate — small enough for Vertex inline_data (<20 MB).
    32 kbps → ~4 MB per 15 min, comfortably under the limit for a full clip."""
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if end is not None:
        cmd += ["-to", str(end)]
    cmd += ["-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
            "-c:a", "libmp3lame", "-b:a", "32k", str(dst_mp3)]
    run(cmd)
    return dst_mp3


# ----------------------------------------------------------------------------- silence / cut snapping
def detect_silences(src: str, cache_json: str | None = None, noise_db: float = -38.0,
                    min_silence: float = 0.12) -> list[tuple[float, float]]:
    """Map where the audio is SILENT → list of (start, end) intervals (seconds).
    Extracts the audio to a temp wav first (decoding audio through 4K video is ~100× slower).
    Result is cached to cache_json so a clip is analysed once per build. The gaps between
    speech are what every cut must land in — see snap_in/snap_out."""
    if cache_json and Path(cache_json).exists():
        return [tuple(x) for x in json.loads(Path(cache_json).read_text())]
    import tempfile, re as _re
    wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", wav])
    proc = run(["ffmpeg", "-hide_banner", "-i", wav, "-af",
                f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"],
               check=False)
    os.unlink(wav)
    starts, sil = [], []
    for m in _re.finditer(r"silence_(start|end):\s*([0-9.]+)", proc.stderr):
        kind, val = m.group(1), float(m.group(2))
        if kind == "start":
            starts.append(val)
        else:
            s = starts.pop() if starts else 0.0
            sil.append((round(s, 3), round(val, 3)))
    if starts:  # trailing silence to EOF
        sil.append((round(starts[0], 3), 10 ** 9))
    if cache_json:
        Path(cache_json).write_text(json.dumps(sil))
    return sil


def _in_silence(silences, t):
    for s, e in silences:
        if s <= t <= e:
            return (s, e)
    return None


def snap_out(silences, out_t, *, tail_pad=0.22, max_extend=3.0):
    """Move an out-point so the last WORD finishes and the cut lands in the following
    breath. If out_t is mid-speech, extend to the next pause and pad into it; if already
    in a pause, keep (padded). Never extend more than max_extend (avoids swallowing the
    next sentence). Returns (snapped_t, reason)."""
    here = _in_silence(silences, out_t)
    if here:
        s, e = here
        return (min(e - 0.02, max(out_t, s + tail_pad)), "already-in-pause")
    # prefer the next pause forward (completes the sentence in progress)…
    nxt = min((iv for iv in silences if iv[0] > out_t), default=None, key=lambda iv: iv[0])
    if nxt and nxt[0] - out_t <= max_extend:
        s, e = nxt
        return (min(e - 0.02, s + tail_pad), f"extended +{s - out_t:.2f}s to pause")
    # …else fall BACK to the nearest preceding pause, so we end on the previous complete
    # sentence rather than clip mid-word (guarantees the cut lands in silence).
    prev = max((iv for iv in silences if iv[1] < out_t), default=None, key=lambda iv: iv[1])
    if prev and out_t - prev[1] <= max_extend:
        s, e = prev
        return (min(e - 0.02, s + tail_pad), f"backed -{out_t - e:.2f}s to prior pause")
    return (out_t, "no pause within window — left as-is (WARN: may clip)")


def snap_in(silences, in_t, *, preroll=0.18, max_extend=3.0):
    """Move an in-point so the first WORD is whole and there's a short breath of lead-in.
    If in_t is inside a pause, start just before the next word; if mid-speech, back up to
    the onset of the current word. Returns (snapped_t, reason)."""
    here = _in_silence(silences, in_t)
    if here:
        s, e = here
        return (max(0.0, e - preroll), "started at word onset")
    prev_e = 0.0
    for s, e in silences:
        if e <= in_t:
            prev_e = e
        else:
            break
    if in_t - prev_e <= max_extend:
        return (max(0.0, prev_e - preroll), f"backed -{in_t - prev_e:.2f}s to word onset")
    return (in_t, "no pause within window — left as-is")


# ----------------------------------------------------------------------------- Vertex / Gemini
def _vertex_post(parts: list[dict], max_tokens: int = 8192, model: Optional[str] = None) -> str:
    """One generateContent call against Vertex, reusing claude_vision's token/creds.
    `parts` is the user-turn parts array (inline_data blocks + a text prompt)."""
    import requests
    from shared.claude_vision import _vertex_token  # already-wired creds
    proj = os.environ.get("VERTEX_PROJECT_ID", "fields-estate")
    region = os.environ.get("VERTEX_REGION", "global")
    host = "aiplatform.googleapis.com" if region == "global" else f"{region}-aiplatform.googleapis.com"
    model = model or os.environ.get("WALK_ASR_MODEL", "gemini-2.5-flash")
    gen = {"maxOutputTokens": max_tokens, "temperature": 0}
    if "flash" in model:
        gen["thinkingConfig"] = {"thinkingBudget": 0}
    body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": gen}
    url = (f"https://{host}/v1/projects/{proj}/locations/{region}"
           f"/publishers/google/models/{model}:generateContent")
    r = requests.post(url, headers={"Authorization": f"Bearer {_vertex_token()}",
                                    "Content-Type": "application/json"}, json=body, timeout=300)
    r.raise_for_status()
    d = r.json()
    cand = (d.get("candidates") or [{}])[0]
    if cand.get("finishReason") == "MAX_TOKENS":
        raise RuntimeError("Gemini response truncated (raise max_tokens or split the clip)")
    return "".join(p.get("text", "") for p in (cand.get("content", {}).get("parts") or []))


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of a possibly ```json-fenced reply."""
    t = text.strip()
    if "```" in t:
        t = t.split("```", 2)[1]
        if t.startswith("json"):
            t = t[4:]
    t = t.strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in reply: {text[:200]}")
    return json.loads(t[start:end + 1])


def transcribe_audio(mp3_path: str, model: Optional[str] = None) -> list[dict]:
    """Verbatim, timecoded transcription of one audio file via Gemini/Vertex.
    Returns [{start, end, text}, …] with times in seconds relative to the clip."""
    b64 = base64.b64encode(Path(mp3_path).read_bytes()).decode()
    prompt = (
        "Transcribe this audio VERBATIM (Australian English, real-estate context; "
        "keep every word, including false starts and repeated takes). Return STRICT "
        "JSON only, no prose:\n"
        '{"segments":[{"start":<seconds float>,"end":<seconds float>,"text":"..."}]}\n'
        "Break segments at natural sentence/clause boundaries. Times are relative to "
        "the start of THIS audio."
    )
    parts = [{"inline_data": {"mime_type": "audio/mp3", "data": b64}}, {"text": prompt}]
    # A full ~10-min assembled transcript in timecoded JSON can exceed 8k tokens; give it
    # headroom so the caption pass doesn't fail late with a MAX_TOKENS truncation.
    reply = _vertex_post(parts, max_tokens=32768, model=model)
    return _extract_json(reply).get("segments", [])


def detect_face_cx(src: str, at: float = 1.0) -> float:
    """Ask Gemini where Will's face is, horizontally, in a sample frame.
    Returns normalised x in [0,1] (0=left edge, 1=right edge). Used to centre the
    square/circle crop on him even though he sits left-of-centre in the raw 4K."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
        frame = tf.name
    run(["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-i", str(src),
         "-frames:v", "1", "-vf", "scale=960:-1", frame])
    data = base64.b64encode(Path(frame).read_bytes()).decode()
    media = "image/jpeg"
    os.unlink(frame)
    prompt = ("A person is on camera. Return STRICT JSON only: "
              '{"face_cx":<0..1>,"face_cy":<0..1>} — the CENTRE of their face as a '
              "fraction of image width (face_cx) and height (face_cy). No prose.")
    parts = [{"inline_data": {"mime_type": media, "data": data}}, {"text": prompt}]
    try:
        j = _extract_json(_vertex_post(parts, max_tokens=256))
        cx = float(j.get("face_cx", 0.5))
        return min(0.95, max(0.05, cx))
    except Exception:
        return 0.5  # centred fallback


# ----------------------------------------------------------------------------- circle mask
def make_circle_mask(dst_png: str, size: int = 1080, feather: int = 3) -> str:
    """A white disc on black, used as an alpha matte for the baked-circle master.
    Slight gaussian feather softens the rim (matches the Aug '26 look)."""
    r = size // 2 - 2
    geq = f"lum='if(lte(hypot(X-{size//2}\\,Y-{size//2})\\,{r})\\,255\\,0)'"
    vf = f"format=gray,geq={geq}"
    if feather > 0:
        vf += f",gblur=sigma={feather}"
    run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", f"color=black:s={size}x{size}", "-vf", vf,
         "-frames:v", "1", str(dst_png)])
    return dst_png


# ----------------------------------------------------------------------------- SRT
def segments_to_srt(segments: list[dict], dst_srt: str, max_chars: int = 40,
                    max_lines: int = 2) -> str:
    """Write burn-ready SRT. A transcription segment can be long (10 s / 40 words); a
    caption cue must be short (≤2 lines) or libass wraps it into a wall of text that
    covers the frame. So each segment is SPLIT into cues of ≤max_lines×max_chars, with
    each cue's time proportional to its share of the segment's characters. Times are on
    the FINAL timeline when called post-assembly."""
    def ts(sec: float) -> str:
        sec = max(0.0, float(sec))
        h = int(sec // 3600); m = int(sec % 3600 // 60)
        s = int(sec % 60); ms = int(round((sec - int(sec)) * 1000))
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    def cue_texts(text: str) -> list[str]:
        """Pack words into cues of ≤max_lines lines, each ≤max_chars. Builds lines
        directly (no post-truncation) so NO word is ever dropped — the previous
        chunk-then-wrap approach silently lost the overflow word."""
        words = text.split()
        cues, lines, cur = [], [], ""
        for w in words:
            if cur and len(cur) + 1 + len(w) > max_chars:
                lines.append(cur); cur = w
                if len(lines) == max_lines:
                    cues.append("\n".join(lines)); lines = []
            else:
                cur = f"{cur} {w}".strip()
        if cur:
            lines.append(cur)
        if lines:
            cues.append("\n".join(lines))
        return cues or [""]

    entries = []
    for seg in segments:
        start, end = float(seg["start"]), float(seg["end"])
        parts = cue_texts(seg["text"].strip())
        span = max(0.4, end - start)
        total = sum(len(p.replace("\n", " ")) for p in parts) or 1
        t = start
        for p in parts:
            dt = span * (len(p.replace("\n", " ")) / total)
            entries.append((t, min(end, t + dt), p))
            t += dt

    out = [f"{i}\n{ts(a)} --> {ts(b)}\n{p}\n" for i, (a, b, p) in enumerate(entries, 1)]
    Path(dst_srt).write_text("\n".join(out))
    return dst_srt


def segments_to_ass(segments: list[dict], dst_ass: str, *, width: int = 1920,
                    height: int = 1080, font: str = "DejaVu Sans", fontsize: int = 54,
                    primary: str = "&H00FFFFFF", outline_col: str = "&H00000000",
                    outline: int = 3, margin_v: int = 90, max_chars: int = 40,
                    max_lines: int = 2) -> str:
    """Burn-ready ASS with an EXPLICIT PlayResX/Y, so Fontsize is in real pixels and does
    NOT get scaled by libass's 288px default (which turned fontsize=40 into ~150px and
    re-wrapped SRT captions into a wall of text). Reuses the SRT chunker for cue timing
    so wording/splits are identical; here we just render to .ass geometry."""
    # produce the same cues the SRT would have (write to a temp SRT, parse back)
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".srt", delete=False).name
    segments_to_srt(segments, tmp, max_chars=max_chars, max_lines=max_lines)
    blocks = [b for b in Path(tmp).read_text().split("\n\n") if b.strip()]
    os.unlink(tmp)

    def to_ass_ts(srt_ts: str) -> str:  # 00:00:01,280 -> 0:00:01.28
        hms, ms = srt_ts.split(",")
        h, m, s = hms.split(":")
        return f"{int(h)}:{m}:{s}.{ms[:2]}"

    header = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 2\n"
        f"PlayResX: {width}\nPlayResY: {height}\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Cap,{font},{fontsize},{primary},&H000000FF,{outline_col},&H64000000,"
        f"-1,0,0,0,100,100,0,0,1,{outline},0,2,60,60,{margin_v},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = [header]
    for b in blocks:
        rows = b.split("\n")
        start, _, end = rows[1].partition(" --> ")
        text = "\\N".join(r for r in rows[2:] if r.strip())
        lines.append(f"Dialogue: 0,{to_ass_ts(start)},{to_ass_ts(end)},Cap,,0,0,0,,{text}")
    Path(dst_ass).write_text("\n".join(lines) + "\n")
    return dst_ass


def segments_to_transcript_md(segments: list[dict], dst_md: str, title: str) -> str:
    """The storyboard-style timecoded markdown transcript (m:ss headers)."""
    def mmss(sec: float) -> str:
        sec = int(round(sec)); return f"{sec // 60}:{sec % 60:02d}"
    lines = [f"# {title} — Video Transcript", "",
             "Verbatim, timecoded. Auto-transcribed via Gemini/Vertex; verify before publishing.", "", "---", ""]
    for seg in segments:
        lines.append(f"**[{mmss(seg['start'])}]** {seg['text'].strip()}")
        lines.append("")
    Path(dst_md).write_text("\n".join(lines))
    return dst_md
