# Porting Break Glass into the site footer

Instructions for moving `index.html` (this folder) into the live React site as a
component inside `SiteFooter`.

Prototype: `https://vm.fieldsestate.com.au/concepts/off-market/Break_glass_emergency/prototype/`
Verified working on desktop and phone.

---

## Read this first — three things about *this* codebase that change the port

**1. SSR is on.** `react-router.config.ts` has `ssr: true`. Every browser-only
API in the prototype — `matchMedia`, `AudioContext`, `devicePixelRatio`,
`requestAnimationFrame`, canvas sizing, `performance.now()` — runs on the server
during render and will crash the build or the request. All of it must live
inside `useEffect`, never in the component body.

**2. `SiteFooter` is sitewide.** It is rendered on Property, Market
Intelligence, Analyse Your Home, Decision Feed, Methodology, Valuation Accuracy
and more. The prototype's six frames total **840KB** — shipping that eagerly
puts 840KB on the bottom of every page on the site. It must be lazy. The
component below loads one 163KB frame when the footer scrolls into view, and
fetches the other five only when the user shows intent (hover/focus).

**3. Sound must default to OFF.** The prototype defaults it on, which is fine
for a preview you opened deliberately. A footer element on every page that makes
a glass-smash noise is not. Keep the WebAudio code, flip the default, and only
ever start the `AudioContext` inside the click handler (browsers require a
gesture anyway).

---

## Step 1 — assets

Copy the six WebP files to the site's `public/` directory so they are fetched by
URL and never bundled:

```bash
mkdir -p /home/fields/Feilds_Website/01_Website/public/break-glass
cp /home/fields/Fields_Orchestrator/15_Off-Market/Concepts/Break_glass_emergency/prototype/assets/*.webp \
   /home/fields/Feilds_Website/01_Website/public/break-glass/
```

They become `/break-glass/01_intact.webp` etc. Do **not** put them in
`src/assets/` — that bundles them through Vite and defeats the lazy loading.

| file | size | when it loads |
|---|---|---|
| `01_intact.webp` | 163KB | footer scrolls into view |
| `02_broken.webp` | 223KB | on intent (hover/focus/touch) |
| `03_handle_up.webp` | 138KB | on intent |
| `05_handle_down.webp` | 137KB | on intent |
| `06_plate_clean.webp` | 140KB | on intent |
| `07_handle_sprite.webp` | 20KB | on intent |

If the assets ever need regenerating, run `build_assets.py` in this folder — it
prints the CSS geometry the component needs, so the two cannot drift apart. The
four source PNGs live only on the VM one level up.

## Step 2 — the component

Create `src/components/BreakGlass/BreakGlass.tsx`.

**Keep the animation imperative.** The swing is rAF-driven at 60fps; pushing the
angle through React state would re-render the tree every frame for no benefit.
Refs plus one effect is the correct shape here, and it keeps the ported logic
recognisably the same as the prototype.

```tsx
import { useEffect, useRef, useState } from "react";
import { phCapture } from "../../utils/posthog";
import styles from "./BreakGlass.module.css";

const A = "/break-glass/";
const EAGER = `${A}01_intact.webp`;
const REST  = [
  `${A}02_broken.webp`, `${A}03_handle_up.webp`, `${A}05_handle_down.webp`,
  `${A}06_plate_clean.webp`, `${A}07_handle_sprite.webp`,
];

export function BreakGlass() {
  const stage  = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(false);   // gates the eager frame
  const [ready,  setReady]  = useState(false);   // rest of the frames decoded

  // 1. only mount the artwork once the footer is actually approached
  useEffect(() => {
    const el = stage.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) { setInView(true); io.disconnect(); } },
      { rootMargin: "300px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // 2. fetch the heavy frames on intent, so the break never flashes an
  //    undecoded image
  function warm() {
    if (ready) return;
    Promise.all(REST.map(src => {
      const i = new Image();
      i.src = src;
      return i.decode().catch(() => undefined);
    })).then(() => setReady(true));
  }

  // 3. all interaction + animation lives here (SSR-safe)
  useEffect(() => {
    if (!inView) return;
    const el = stage.current;
    if (!el) return;
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

    // -- paste the prototype's IIFE body here, with two changes:
    //    * replace  $('id')  with  el.querySelector('[data-x="id"]')
    //    * fire analytics at the two moments that matter:
    //        phCapture("break_glass_smashed")
    //        phCapture("break_glass_pulled")
    //    everything else (render/armSprite/autoPull/settle, the drag handlers,
    //    the shard canvas, the WebAudio synths) ports across unchanged.

    return () => { /* cancelAnimationFrame + remove listeners */ };
  }, [inView]);

  return (
    <div className={styles.stage} ref={stage} onPointerEnter={warm} onFocus={warm}>
      {inView && (
        <>
          <img className={styles.layer} data-x="l-intact" src={EAGER} alt="Sealed emergency case behind glass" />
          {/* the other five <img> layers, data-x="l-broken" etc. */}
        </>
      )}
    </div>
  );
}
```

The prototype's JS is otherwise a straight lift. The only structural change is
swapping `getElementById` for `data-x` lookups scoped to the component, because
a sitewide footer must not depend on globally-unique element ids.

## Step 3 — the styles

Create `src/components/BreakGlass/BreakGlass.module.css` from the prototype's
`<style>` block, with these changes:

- Delete the `body`, `h1`, `.dev` and `#reveal` rules — they are preview
  chrome. **Strip the whole dev bar** (Reset / scrub / sound toggle).
- Replace `--copper:#c9803f` with the site token **`var(--copper-on-dark)`**
  (`#dd8f6d`, defined in `src/styles/theme.css`). The footer is a dark surface
  and that token is mandatory there.
- Use `var(--font-mono)` for the prompt text, matching `SiteFooter.module.css`.
- Keep the geometry variables exactly as they are:

  ```css
  --spr-l:34.8129%; --spr-t:43.9737%; --spr-w:41.8625%; --spr-h:22.3521%;
  --pivot:13.4%;
  ```

  These are measured off the source render. `build_assets.py` reprints them.
- Constrain the width — the prototype uses `min(560px,92vw)`. In a footer,
  something nearer `min(340px,70vw)` sits better; check it against the slogan
  bar and subscribe form.
- Keep the `@media (prefers-reduced-motion: reduce)` block.

## Step 4 — drop it into the footer

In `src/components/SiteFooter/SiteFooter.tsx`, import it and place it. It wants
to sit **below `.bottom`**, as a full-width closing beat — putting it above the
columns pushes the actual navigation down the page on every route.

```tsx
import { BreakGlass } from "../BreakGlass/BreakGlass";
// ...
        </div>{/* .bottom */}

        <BreakGlass />

      </div>
    </footer>
```

## Step 5 — decide what is behind the glass

**This is the open question and it is yours, not a technical one.** `#reveal` in
the prototype is a placeholder. On a sitewide footer the payload has to make
sense from any page. Candidates, in rough order of fit:

- the off-market panel / address field (matches the concept's origin)
- a direct line — phone + email, framed as "in case of emergency"
- the newsletter subscribe, as a second bite

Whatever goes in must clear the editorial rules in `CLAUDE.md` §5 — no advice,
no predictions, no single valuation figure in a headline.

## Step 6 — deploy and verify (mandatory)

Website files sit at the **repo root**, not under `01_Website/`:
`01_Website/src/…` → `src/…`.

```bash
export GH_CONFIG_DIR=/home/projects/.config/gh && unset GITHUB_TOKEN
# per file:
SHA=$(gh api 'repos/Will954633/Website_Version_Feb_2026/contents/PATH' --jq '.sha')
CONTENT=$(base64 -w0 < /home/fields/Feilds_Website/01_Website/LOCAL_PATH)
gh api 'repos/Will954633/Website_Version_Feb_2026/contents/PATH' \
  --method PUT --field message="feat(footer): break-glass interaction" \
  --field content="$CONTENT" --field sha="$SHA"
```

The WebP files are binary — base64 them the same way; each is well under the
100KB threshold that needs the Python `--input` payload route, except
`02_broken.webp` (223KB) and `01_intact.webp` (163KB), which do need it.

Before pushing, run the real verification gates — **bare `tsc` checks zero
files**:

```bash
cd /home/fields/Feilds_Website/01_Website
npx tsc -p tsconfig.app.json --noEmit
npm run build
```

After pushing (all four steps are required by `CLAUDE.md` §4):

```bash
python3 scripts/website-deploy-tracker.py log --commit SHA --files "..." --message "..."
python3 scripts/website-change-log.py log --title "Break glass footer" --type feature \
  --hypothesis "..." --files "..." --pages "/" --commit SHA
node scripts/site-inspector.js --url /
# then read the screenshot PNG and check console.log + network-errors.log
```

## Verification checklist

- [ ] Server render does not crash — load any page with JS disabled; the footer
      must still render (the box simply will not appear until `inView`).
- [ ] Network tab on first paint shows **no** `/break-glass/` requests until the
      footer is approached.
- [ ] Hover the box, then break it — no flash of an undecoded frame.
- [ ] Sound is silent until the user opts in.
- [ ] `prefers-reduced-motion: reduce` — no shake, short swing.
- [ ] Keyboard: Tab to the glass, Enter breaks it; Tab to the bail, Enter pulls.
- [ ] Phone: drag works, and the box does not fight page scroll
      (`touch-action:none` is already set on the stage).
- [ ] Lighthouse on `/` — confirm CLS is unchanged. The stage has a fixed
      `aspect-ratio`, so it should reserve its space, but verify.

## Known issues carried over

- The bail collapses to a line at exactly 90° (flat sprite). Covered by a
  specular streak and motion blur; ~30ms at speed.
- Faint smudge on the repaired plate below-left of the sign, visible only
  mid-swing.
- The break phase is a crossfade plus canvas triangles. **`15_Off-Market/Page_Redesign_V3/outro/crack.js`
  is a much better shatter** — 75 tiling polygons cut from Will's artwork, with
  `glass-audio.js`. Consider swapping the break phase for it before this ships;
  the handle swing is the part that is unique to this prototype.

---

**Status:** the component and CSS above are a port plan, not a built-and-tested
build — they have not been compiled against the site yet. Steps 1, 2 and 3 need
doing and then the Step 6 gates run.
