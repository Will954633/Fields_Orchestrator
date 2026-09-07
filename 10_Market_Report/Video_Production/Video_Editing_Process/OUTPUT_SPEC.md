# Output spec — every deliverable, and where it goes

All paths are under `out/` after a build. `<slug>` = `config.project.slug`
(e.g. `robina_2026-08_dom`).

## Deliverables

| File | Format | Purpose | Matches Aug '26 artefact |
|---|---|---|---|
| `<slug>.mp4` | **512×512** square, H.264, yuv420p, 30 fps, AAC, faststart, **no captions** | **The website embed.** Dropped into `public/walkthrough/`. | `public/walkthrough/robina_2026-08_dom.mp4` |
| `<slug>_circle.mov` | 1920×1080, HEVC (hvc1), baked circle-on-black, **no captions**, AAC | Standalone / social (LinkedIn, email), no page behind it | `Robina_August_No_Captions.mov` |
| `<slug>_circle_captions.mov` | as above **+ burned captions** below the circle | Social where sound is off by default | `Robina_August_01_Captions_Mask.mov` |
| `<slug>.srt` | SubRip | Caption source (re-usable for YouTube, re-styling) | — |
| `<slug>_transcript.md` | Timecoded markdown (`m:ss`) | The transcript for the storyboard / SEO / article embed | `Robina_August_Transcript.md` |
| `outputs.json` / `qc_report.json` | JSON | Build manifest + QC result | — |

Intermediate `work/master_square.mp4` (1080×1080) is the **source of truth**: every
deliverable is derived from it, so audio/grade are identical across all of them. Safe to
delete `work/` after a build; keep `out/`.

## Why two shapes (square vs baked-circle)

The **live page draws the circle itself** — the avatar `<video>` is a plain **square**
that CSS rounds:

```css
/* src/components/MarketFlowProto/MarketFlowProto.css */
.mktp .tour-avatar .ta-vid { width:100%; height:100%; border-radius:50%; object-fit:cover; }
#walkLayer .wk-avatar      { border-radius:50%; overflow:hidden; }
```

```js
// MarketFlowProto.engine.ts
var WALK_SRC = "/walkthrough/robina_2026-08_dom.mp4";        // the 512² square
```

So the **web mp4 must stay a square with no baked circle and no captions** — the page
supplies the circular clip and its own guided-tour captions. The baked-circle `.mov`s are
for contexts with **no page around them** (social, email); there the circle and captions
have to live in the pixels.

## Deploy the embed

```bash
SLUG=robina_2026-08_dom
LOCAL=out/$SLUG.mp4
cp "$LOCAL" /home/fields/Feilds_Website/01_Website/public/walkthrough/$SLUG.mp4

# push to the Website repo (git push hangs on this VM — use gh api, CLAUDE.md §2)
CONTENT=$(base64 -w0 < "$LOCAL")
python3 - "$SLUG" <<'PY' > /tmp/wk_payload.json
import json,base64,sys
slug=sys.argv[1]
data=base64.b64encode(open(f"out/{slug}.mp4","rb").read()).decode()
print(json.dumps({"message":f"add: walkthrough embed {slug}","content":data}))
PY
# new file (no sha) — or fetch sha first if replacing:
SHA=$(gh api "repos/Will954633/Website_Version_Feb_2026/contents/public/walkthrough/$SLUG.mp4" --jq '.sha' 2>/dev/null)
[ -n "$SHA" ] && python3 -c "import json;d=json.load(open('/tmp/wk_payload.json'));d['sha']='$SHA';json.dump(d,open('/tmp/wk_payload.json','w'))"
gh api "repos/Will954633/Website_Version_Feb_2026/contents/public/walkthrough/$SLUG.mp4" \
  --method PUT --input /tmp/wk_payload.json
```

If it's a **new** suburb/month, also point the page at it — update `WALK_SRC` in
`src/components/MarketFlowProto/MarketFlowProto.engine.ts` (currently hard-coded to
Robina Aug), then follow the website verification gates in CLAUDE.md §4 (deploy tracker,
screenshot `?walkthrough=1`, read the PNG).

## Editorial guardrails (CLAUDE.md §5)

The transcript and any captions are **public-facing content**. Before publishing:
- No advice, no predictions — the Aug script already uses directional/conditional language
  ("suggests", "very unlikely to be rising", "not measures of certainty"). Keep it.
- Numbers exact and correctly formatted (`$1,492,000`, not "1.492").
- Verify the auto-transcription against the audio — Gemini is good but not perfect on
  figures and suburb names.

## Encode knobs (in `config.yaml`)

- **Sharper/softer look:** `look.sharpen`, `look.contrast`, `look.saturation`
- **Brighter:** `look.brightness`, `look.gamma`
- **Warmer/cooler:** `look.warmth`
- **Cleaner audio (more aggressive):** `audio.denoise: anlmdn` or lower `audio.denoise_nf`
- **Louder/quieter:** `audio.target_lufs` (−16 is the web/dialogue norm)
- **Bigger/smaller circle:** `framing.circle_diameter`, `framing.circle_cy_frac`
- **Tighter framing:** `framing.zoom` (1.05–1.15 punches in) — set per-segment in the EDL
  to break up adjacent same-topic takes so a hard cut doesn't read as a jump.
