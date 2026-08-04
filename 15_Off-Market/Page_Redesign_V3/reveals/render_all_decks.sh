#!/usr/bin/env bash
# Render every emblem to a deck-ready MP4: paper #000, no grain, no vignette,
# so it sits on the deck's ground with no visible panel edge. Mirrors how
# palm_reveal_deck.mp4 was made for the beach-card reference.
set -uo pipefail
cd "$(dirname "$0")"
OUT=out/deck
mkdir -p "$OUT"
# stem:mode:duration_ms
for spec in pandanus:growth:6000 tree:growth:6000 reeds:growth:6000 banksia:growth:6000 \
            golfflag:growth:6000 dog:develop:5000 satchel:develop:5000 whale:develop:5000; do
  stem="${spec%%:*}"; rest="${spec#*:}"; mode="${rest%%:*}"; dur="${rest##*:}"
  if [ -f "$OUT/${stem}.mp4" ] && [ "${1:-}" != "--force" ]; then
    echo "skip  $stem (exists — pass --force to re-render)"; continue
  fi
  echo "=== $stem ($mode, ${dur}ms)"
  node render_reveal.js --html "out/${stem}.html" --mode "$mode" --dur "$dur" \
       --width 900 --fps 30 --hold 1.2 \
       --paper "#000000" --ink "#E6DDD2" --grain 0 --vignette 0 \
       --out "$OUT/${stem}" || echo "FAILED: $stem"
done
echo; ls -la "$OUT" | grep -E '\.mp4$' || echo "no mp4s written"
