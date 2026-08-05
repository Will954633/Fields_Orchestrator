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

# ── the running bed: a SEAMLESS loop ────────────────────────────────────────
# For a loop of length L built from a source segment of length L+C:
#   A = S[C .. L+C]   (length L)
#   B = S[0 .. C]     (length C)
#   out = acrossfade(A, B, d=C)      -> length L
# The output ends in a crossfade INTO S[0..C], whose tail lands on S[C] — which
# is exactly where the output begins. So the join is continuous when it repeats.
# Without this, an 11s room recording clicks audibly every time round.
L=4.0; C=0.8; START=6.0                 # steady tail of the recording
ffmpeg -v error -y \
  -ss $(awk -v a="$START" -v c="$C" 'BEGIN{printf "%.3f", a+c}') -t $L -i "$S/Fridge Running.m4a" \
  -ss $START                    -t $C -i "$S/Fridge Running.m4a" \
  -filter_complex "[0:a]aformat=channel_layouts=mono,dynaudnorm=f=250:g=7[a]; \
                   [1:a]aformat=channel_layouts=mono,dynaudnorm=f=250:g=7[b]; \
                   [a][b]acrossfade=d=$C:c1=tri:c2=tri[out]" \
  -map "[out]" -ar 44100 -c:a aac -b:a 80k fridge-hum.m4a

ls -l fridge-open.m4a fridge-close.m4a fridge-hum.m4a
for f in fridge-open.m4a fridge-close.m4a fridge-hum.m4a; do
  printf "%-20s %ss\n" "$f" "$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f")"
done
