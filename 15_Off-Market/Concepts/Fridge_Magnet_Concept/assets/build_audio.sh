#!/usr/bin/env bash
# =============================================================================
# build_audio.sh — turn Will's raw fridge recordings into web audio.
#
# Sources (kept in assets/source/, never served):
#   Fridge Running.m4a   10.97s  the compressor running
#   fridge_opening.m4a    6.19s  door opening
#   fridge_closing.m4a    5.59s  door closing
#
# All three are 48kHz stereo AAC with the actual event buried in silence.
# Measured onsets (5ms-window RMS envelope, not guessed):
#   opening   onset 1.835s   peak 1.930s   decayed by 2.120s
#   closing   onset 2.135s   peak 2.160s   decayed by 2.295s
# So each door event is under 0.4s. Shipping the 6s files would mean a ~0.5s
# delay between the tap and the sound, which reads as a broken page.
#
# The running loop needs more care: the recording RAMPS in level from start to
# finish (mic AGC settling), so the first half is unusable as a bed and a naive
# loop would pump. We take the steady tail, even it out with dynaudnorm, and
# then build a genuinely seamless loop (see below).
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"
S=source

# ── one-shots: trim tight to the transient, mono, de-clicked ────────────────
# A hard cut at a non-zero sample is an audible click. 8ms fades at both ends
# remove it without softening the attack (the attack is ~25ms).
# NB: use awk, not bc — bc prints "$3 - 0.12" as ".60" with no leading zero and
# ffmpeg refuses to parse that as a duration.
one_shot () {   # $1=in $2=start $3=dur $4=out
  ffmpeg -v error -y -ss "$2" -t "$3" -i "$S/$1" \
    -ac 1 -ar 44100 \
    -af "afade=t=in:st=0:d=0.008,afade=t=out:st=$(awk -v d="$3" 'BEGIN{printf "%.3f", d-0.12}'):d=0.12,loudnorm=I=-14:TP=-1.5:LRA=11" \
    -c:a aac -b:a 96k "$4"
}

one_shot "fridge_opening.m4a" 1.80 0.72 fridge-open.m4a
one_shot "fridge_closing.m4a" 2.10 0.72 fridge-close.m4a

# ── the running bed: a SEAMLESS, LEVEL-FLAT loop ────────────────────────────
# Two separate traps here, and the first one shipped a broken loop.
#
# TRAP 1 — dynaudnorm ramps at the edges of whatever you give it.
#   It normalises over a gaussian window (f=250ms x g=7 = 1.75s), and until that
#   window is full it has nothing to work from, so it fades IN over ~0.9s at the
#   start and OUT at the end. Applying it to an already-sliced 4.8s segment put
#   a fade at both ends of the loop: measured 22.7dB between the middle and the
#   edges, which looped every 4s and was audible as the sound "fading in and
#   out". Fix: normalise the WHOLE file FIRST, so those ramps land at the file's
#   own edges, then slice from well inside.
#
# TRAP 2 — a linear crossfade dips on uncorrelated material.
#   c1=tri is equal-GAIN. Two different bits of a noise recording sum
#   incoherently, so equal-gain loses ~3dB in the middle of the fade. qsin is
#   equal-POWER, which is the correct curve for anything uncorrelated.
#
# Seamless-loop construction, for a loop of length L from a source of L+C:
#   A = S[C .. L+C]   (length L)
#   B = S[0 .. C]     (length C)
#   out = acrossfade(A, B, d=C)      -> length L
# The output ends in a crossfade INTO S[0..C], whose tail lands on S[C] — which
# is exactly where the output begins, so the join is continuous when it repeats.

# 1. FLATTEN DETERMINISTICALLY.
#    dynaudnorm is peak-based and smooths its own gain curve, so a slow swell
#    across the recording survives it: f=250:g=7 left 3.9dB of drift and
#    f=75:g=5 left 3.6dB, both audible as breathing once per loop. A bed has to
#    be boring, so instead of asking a filter nicely, measure the RMS envelope
#    and divide it out. Smoothing is deliberately slow (~1s) so only slow drift
#    is removed and the short-term texture of the compressor survives.
ffmpeg -v error -y -i "$S/Fridge Running.m4a" -ac 1 -ar 44100 -c:a pcm_s16le /tmp/hum_raw.wav
python3 - <<'PYEOF'
import wave, struct, array, math
w = wave.open('/tmp/hum_raw.wav'); n, sr = w.getnframes(), w.getframerate()
d = array.array('h'); d.frombytes(w.readframes(n))

hop = int(sr * 0.05)
env = []
for i in range(0, n - hop, hop):
    acc = 0
    for x in d[i:i + hop]:
        acc += x * x
    env.append(math.sqrt(acc / hop) or 1.0)

# ~1s moving average -> only slow drift is corrected
W = 10
sm = [sum(env[max(0, i - W):i + W + 1]) / len(env[max(0, i - W):i + W + 1])
      for i in range(len(env))]
target = sorted(sm)[len(sm) // 2]
gains = [max(0.25, min(4.0, target / g)) for g in sm]

out = array.array('h', bytes(2 * n))
for i in range(len(gains)):
    g0, g1 = gains[i], gains[min(i + 1, len(gains) - 1)]
    a = i * hop
    b = min(a + hop, n)
    for j in range(a, b):
        g = g0 + (g1 - g0) * ((j - a) / hop)
        v = int(d[j] * g)
        out[j] = -32768 if v < -32768 else (32767 if v > 32767 else v)
for j in range(len(gains) * hop, n):
    out[j] = d[j]

# Normalise to a TARGET RMS, not to peak. Dividing out the envelope lifts the
# quiet passages, which raises peaks; scaling to peak then dropped the whole bed
# by ~23dB (RMS 3671 -> 250) and made it inaudible under humGain. Set the RMS
# where we want it and only pull back if that would actually clip.
TARGET_RMS = 3600.0
acc = 0
for v in out:
    acc += v * v
rms = math.sqrt(acc / len(out)) or 1.0
k = TARGET_RMS / rms
peak = max(abs(v) for v in out) or 1
if peak * k > 30000:                   # headroom, no clipping
    k = 30000 / peak
out = array.array('h', (max(-32768, min(32767, int(v * k))) for v in out))
final_rms = math.sqrt(sum(v * v for v in out) / len(out))
print(f"  level: rms {rms:.0f} -> {final_rms:.0f} (x{k:.2f}), peak {int(peak*k)}")
o = wave.open('/tmp/hum_flat.wav', 'wb')
o.setnchannels(1); o.setsampwidth(2); o.setframerate(sr)
o.writeframes(out.tobytes()); o.close()
print(f"  flattened {n/sr:.2f}s, gain range {min(gains):.2f}-{max(gains):.2f}")
PYEOF

# 2. SEARCH for the flattest usable window rather than picking one by eye.
L=6.0; C=0.6
START=$(python3 - "$L" "$C" <<'PYEOF'
import wave, struct, math, sys
L, C = float(sys.argv[1]), float(sys.argv[2])
w = wave.open('/tmp/hum_flat.wav'); n = w.getnframes(); sr = w.getframerate()
d = struct.unpack(f"<{n}h", w.readframes(n))
step = int(sr * 0.05)
env = [math.sqrt(sum(x*x for x in d[i:i+step]) / step) or 1e-9
       for i in range(0, n - step, step)]
need  = int((L + C) / 0.05)
guard = int(0.4 / 0.05)
best, best_spread = guard, 1e9
for a in range(guard, len(env) - need - guard):
    seg = env[a:a + need]
    spread = 20 * math.log10(max(seg) / min(seg))
    if spread < best_spread:
        best, best_spread = a, spread
sys.stderr.write(f"  flattest {L+C:.1f}s window at {best*0.05:.2f}s (spread {best_spread:.1f} dB)\n")
print(f"{best*0.05:.3f}")
PYEOF
)

# 3. seamless join, EQUAL-POWER (qsin). c1=tri is equal-gain and loses ~3dB in
#    the middle of a fade between uncorrelated noise.
ffmpeg -v error -y \
  -ss $(awk -v a="$START" -v c="$C" 'BEGIN{printf "%.3f", a+c}') -t $L -i /tmp/hum_flat.wav \
  -ss $START                                                   -t $C -i /tmp/hum_flat.wav \
  -filter_complex "[0:a][1:a]acrossfade=d=$C:c1=qsin:c2=qsin[out]" \
  -map "[out]" -ar 44100 -c:a aac -b:a 80k fridge-hum.m4a

ls -l fridge-open.m4a fridge-close.m4a fridge-hum.m4a
for f in fridge-open.m4a fridge-close.m4a fridge-hum.m4a; do
  printf "%-20s %ss\n" "$f" "$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f")"
done

# ── GATE: the bed must be flat end to end, or it audibly pumps once a loop ──
# This check exists because the first build shipped a 22.7dB edge-to-middle
# swing and it was only caught by a person listening to it on a phone.
ffmpeg -v error -y -i fridge-hum.m4a -ac 1 -ar 44100 -f wav /tmp/hum_check.wav
python3 - <<'PYEOF'
import wave, struct, math, sys
w = wave.open('/tmp/hum_check.wav'); n = w.getnframes(); sr = w.getframerate()
d = struct.unpack(f"<{n}h", w.readframes(n))
def rms(a, b):
    seg = d[a:b]
    return math.sqrt(sum(x * x for x in seg) / len(seg)) or 1e-9
win = int(sr * 0.1)
env = [rms(i, i + win) for i in range(0, n - win, win)]
lo, hi = min(env), max(env)
swing = 20 * math.log10(hi / lo)
head, mid, tail = rms(0, int(sr*.2)), rms(n//2 - sr//4, n//2 + sr//4), rms(n - int(sr*.2), n)
print(f"  hum envelope: min {lo:.0f} max {hi:.0f} -> swing {swing:.1f} dB")
print(f"  head {head:.0f} | mid {mid:.0f} | tail {tail:.0f}")
print("  " + "".join(" .:-=+*#@"[min(8, int(v / hi * 8.999))] for v in env))
if swing > 2.5:
    print(f"  FAIL: {swing:.1f} dB swing across the loop — it will breathe once per cycle")
    sys.exit(1)
for name, v in (("head", head), ("tail", tail)):
    if abs(20 * math.log10(v / mid)) > 1.5:
        print(f"  FAIL: {name} is {20*math.log10(v/mid):+.1f} dB vs middle — edge ramp, loop will breathe")
        sys.exit(1)
print("  PASS: bed is flat")
PYEOF
