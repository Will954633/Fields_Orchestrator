/**
 * fruit_roll.js — the pandanus fruit leaves the tree and rolls into card 04.
 *
 * Card 03 draws a pandanus. Card 04 says why being near the beach is priced in.
 * This is the join: a fruit drops out of the crown, bounces, and rolls into the
 * empty left column of card 04, where it stays as foreground beside the copy.
 *
 * BEACHSIDE DECKS ONLY, for now. Of the eight emblems only three have anything
 * that could plausibly detach — this fruit, the golf ball, the dog's ball. The
 * reeds, banksia and bushbirds would each need an element drawn; the satchel and
 * whale have none and need a different idea entirely. So this ships for one
 * angle and the rest keep the plain cut. See PLAN.md "Still open".
 *
 * Three things worth knowing before changing it:
 *
 *   THE READER DRIVES IT, NOT A TIMER. This was a clock first, and the clock was
 *   wrong for two reasons that only showed up on screen. The tree is in card 03
 *   and the target is in card 04, a full viewport apart, so they are never both
 *   comfortably visible — a timed run either started before the palm had finished
 *   drawing itself, or ended with the fruit landing below the fold where nobody
 *   saw it arrive. Tying progress to scroll position fixes both at once: the
 *   fruit cannot leave before the reader has been shown the tree, and it cannot
 *   land somewhere they are not looking, because the thing moving the fruit IS
 *   the thing moving the view.
 *
 *   IT LANDS ON A TARGET, IT IS NOT SIMULATED. A real projectile would need its
 *   launch velocity solved backwards to hit the slot, and would miss the moment
 *   the layout changed. Instead the drop, the bounces and the roll are phases
 *   over the scroll distance between the two cards, so it always arrives exactly
 *   in the column however the page has reflowed. The bounce heights are what
 *   sell it; the trajectory being authored rather than solved is invisible.
 *
 *   THE ROTATION COMES FROM THE DISTANCE. Once it is on the ground, angle =
 *   travelled / radius. That is what rolling IS, and eyeballing a spin rate
 *   instead is the thing that makes CSS ball animations look like sliding
 *   stickers. Before it lands it tumbles slowly instead, because it is in
 *   the air and nothing is driving it.
 */
(function () {
  "use strict";

  // Resolved against a base the host sets, so the same file works from the
  // preview (a relative folder) and from the site (the blob host).
  const SPRITE = (window.FIELDS_MEDIA_BASE || "../media/") + "pandanus_fruit.png";
  const BALL_FRAC = 0.390;       // ball radius as a fraction of sprite width
                                 // (from build_fruit_sprite.py — keep in step)

  // The fruit's spot inside the rendered frame, and the patch that covers it.
  // Both come from the original beach-card concept, which measured them against
  // the encoded video rather than the master — the patch is cloned from the
  // video's own pixels, so it only lands if these agree with it. Our clip is a
  // different size (900x976 vs 1024x1110) but the same framing, so the
  // fractions carry over; verified by compositing the patch onto our own last
  // frame before wiring any of it up.
  const PATCH = { x: 0.5029, y: 0.2180, w: 0.0957, h: 0.0919 };
  const FROM = { x: PATCH.x + PATCH.w / 2, y: PATCH.y + PATCH.h / 2 };

  // Phases as shares of the scroll journey: `p` is how far through we are, `x`
  // is the cumulative share of the horizontal trip completed by the END of that
  // phase, `up` is the bounce height as a fraction of the original drop.
  const PHASES = [
    { id: "hang",    p: 0.10, x: 0.00, up: null },   // still on the tree
    { id: "drop",    p: 0.44, x: 0.12, up: 0 },
    { id: "bounce1", p: 0.64, x: 0.42, up: 0.24 },
    { id: "bounce2", p: 0.79, x: 0.68, up: 0.075 },
    { id: "roll",    p: 0.94, x: 1.00, up: 0 },   // settled before the end,
                                                  // so the last of the scroll
                                                  // is the fruit sitting still
  ];
  const HANG = PHASES[0].p;             // before this, the DRAWN fruit is the fruit
  const LAND = PHASES[1].p;             // first contact with the ground
  const SETTLED = PHASES[PHASES.length - 1].p;
  const MIN_W = 900;                    // two-column breakpoint, matching deck.css

  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const easeOut = (t) => 1 - Math.pow(1 - t, 2.2);
  const easeIn = (t) => t * t;

  function centreOf(el, scrollX, scrollY) {
    const r = el.getBoundingClientRect();
    return { x: r.left + scrollX + r.width / 2, y: r.top + scrollY + r.height / 2, r };
  }

  function run() {
    const card4 = document.getElementById("card-04");
    const slot = card4 && card4.querySelector(".colFruit");
    const media = document.getElementById("media");
    const emblem = document.getElementById("emblem");
    const patch = document.getElementById("fruitPatch");
    const frame = emblem && emblem.parentElement;
    if (!card4 || !slot || !media || !emblem) return;

    // The rest state is a plain <img> in the column, not a canvas that has to be
    // redrawn on every scroll for the rest of the page. The canvas only exists
    // while the fruit is moving.
    const rest = document.createElement("img");
    rest.src = SPRITE;
    rest.alt = "";
    rest.className = "fruitRest";
    slot.appendChild(rest);

    if (reduced) {
      // A screen-crossing object is exactly what this setting exists to prevent.
      // The fruit is simply already in place, and the tree already patched.
      rest.classList.add("on");
      if (patch) {
        const place = () => {
          const er = emblem.getBoundingClientRect();
          const fr = frame.getBoundingClientRect();
          if (!er.width) return false;
          patch.style.left = (er.left - fr.left + er.width * PATCH.x) + "px";
          patch.style.top = (er.top - fr.top + er.height * PATCH.y) + "px";
          patch.style.width = (er.width * PATCH.w) + "px";
          patch.style.height = (er.height * PATCH.h) + "px";
          patch.classList.add("on");
          return true;
        };
        // The video is preload="none" and has no size until it attaches.
        if (!place()) emblem.addEventListener("loadeddata", place, { once: true });
      }
      return;
    }

    const img = new Image();
    img.src = SPRITE;

    const cv = document.createElement("canvas");
    cv.className = "fruitCanvas";
    cv.setAttribute("aria-hidden", "true");
    document.body.appendChild(cv);
    const ctx = cv.getContext("2d");
    let dpr = 1;
    function size() {
      dpr = Math.min(devicePixelRatio || 1, 2);
      cv.width = Math.round(innerWidth * dpr);
      cv.height = Math.round(innerHeight * dpr);
      cv.style.width = innerWidth + "px";
      cv.style.height = innerHeight + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    size();

    let from = null, to = null, endPx = 0, startPx = 46, kickPx = 0;
    let s0 = 0, s1 = 1, landed = false, queued = false;

    function measure() {
      const sy = scrollY;
      // The drawing, not the figure: the video is letterboxed inside its frame
      // by `max-height`, so the figure's box is not where the ink is.
      const er = emblem.getBoundingClientRect();
      from = {
        x: er.left + scrollX + er.width * FROM.x,
        y: er.top + sy + er.height * FROM.y,
      };
      // The patch is positioned from the VIDEO, not its frame. `max-height`
      // letterboxes the clip inside the frame, so a percentage of the frame is
      // not a percentage of the picture and the patch would drift off the fruit
      // at some window sizes.
      startPx = er.width * PATCH.w;
      if (patch && frame) {
        const fr = frame.getBoundingClientRect();
        patch.style.left = (er.left - fr.left + er.width * PATCH.x) + "px";
        patch.style.top = (er.top - fr.top + er.height * PATCH.y) + "px";
        patch.style.width = startPx + "px";
        patch.style.height = (er.height * PATCH.h) + "px";
      }

      // Rest size. On desktop it follows the column so the fruit and the copy
      // stay related as the window widens. On a phone there is no column to
      // follow, so it is bounded by both axes — the concept's mobile size, which
      // reads as something you could pick up rather than a boulder.
      const col = slot.getBoundingClientRect();
      endPx = innerWidth >= MIN_W
        ? Math.max(120, Math.min(220, col.width * 0.62))
        : Math.max(110, Math.min(200, Math.min(innerWidth * 0.44, innerHeight * 0.22)));
      // Set the resting box NOW, not on landing: the img is in the layout from
      // the start (just transparent), so growing it at the end would shift the
      // copy under the reader.
      rest.style.width = endPx + "px";

      // Lateral kick — PHONES ONLY. On a narrow screen the tree and the resting
      // place are nearly above one another, so the fruit had ~19% of travel and
      // rotation is distance/radius: a quarter turn, which reads as a drop with
      // a slide rather than a roll. Kicking it out to the right on first contact
      // and letting it roll back adds that distance twice over.
      // Desktop gets none: it already turns 1.2 times, and the room it would
      // kick into is the copy.
      kickPx = innerWidth >= MIN_W ? 0 : Math.min(innerWidth * 0.13, 70);

      // Aim at the RESTING IMAGE, not at its column. On a phone the column is
      // full-width and the fruit is left-biased inside it, so the two are 16% of
      // the viewport apart — the flying fruit was flying to the middle of a box
      // whose contents sit near its left edge, and jumped sideways on landing.
      // The img is in the layout from the start with its final width already
      // set, so its rect IS the destination.
      const c = centreOf(rest, scrollX, sy);
      to = { x: c.x, y: c.y };

      // The journey runs from "the tree is centred" to "the slot is centred".
      // Deriving both from the elements means it scales with the card height and
      // the viewport instead of guessing a pixel distance.
      const mid = (el) => {
        const r = el.getBoundingClientRect();
        return r.top + scrollY + r.height / 2 - innerHeight / 2;
      };
      s0 = mid(emblem);
      s1 = mid(rest);      // must be the same element `to` came from, or the
                           // "ground is mid-viewport at p=1" identity breaks
      if (s1 - s0 < 200) s1 = s0 + 200;    // degenerate layout guard
    }

    function draw() {
      queued = false;
      if (landed) return;
      // Re-measure every frame rather than once up front. The card-03 video is
      // preload="none" and has no intrinsic size until it attaches, so anything
      // measured before that is measuring an empty box — the first version of
      // this cached the geometry at start-up and the fruit never reached its
      // target because the journey it had been given was the pre-layout one.
      // Two getBoundingClientRects per frame, and only while it is in flight.
      measure();
      const p = Math.max(0, Math.min(1, (scrollY - s0) / (s1 - s0)));

      ctx.clearRect(0, 0, innerWidth, innerHeight);

      // ── where along the journey are we ────────────────────────────────────
      let px = 0, height = 1, prevP = 0, prevX = 0;
      for (const ph of PHASES) {
        if (p <= ph.p || ph === PHASES[PHASES.length - 1]) {
          const u = Math.max(0, Math.min(1, (p - prevP) / (ph.p - prevP)));
          px = prevX + (ph.x - prevX) * (ph.id === "roll" ? easeOut(u) : u);
          if (ph.up === null) height = 1;                    // still hanging
          else if (ph.id === "drop") height = 1 - easeIn(u); // falls away
          else if (ph.up) height = ph.up * 4 * u * (1 - u);  // parabola off the floor
          else height = 0;                                   // rolling
          break;
        }
        prevP = ph.p; prevX = ph.x;
      }

      // While it is still on the tree, the fruit in the DRAWING is the fruit.
      // Drawing the sprite here too put a second one directly on top of the
      // first, visible from the moment the reader arrived. Nothing to render:
      // just make sure the patch is off so the drawn one shows through.
      if (p < HANG) {
        if (patch) patch.classList.remove("on");
        return;
      }
      // Past the handover the drawn one is covered and the sprite takes over.
      // They are the same size and in the same place, so the swap is invisible.
      if (patch) patch.classList.add("on");

      // The kick: nothing until it lands, out fast, back slow. `u^0.65` puts the
      // peak at ~1/3 of the way rather than halfway, so it squirts sideways on
      // impact and then spends the rest of the journey rolling back — which is
      // the part worth watching. Zero at both ends, so the landing is still
      // exact and no correction is needed.
      let kick = 0;
      if (kickPx && p > LAND) {
        const u = Math.min(1, (p - LAND) / (SETTLED - LAND));
        kick = kickPx * Math.sin(Math.PI * Math.pow(u, 0.65));
      }
      const x = from.x + (to.x - from.x) * px + kick;

      // The ground is defined in SCREEN space, not document space, and that one
      // choice is what keeps the fruit visible.
      //
      // Anchoring the fall to the slot's document position meant the fruit hit
      // the floor at p=0.44 and then sat there while the viewport spent the
      // other 56% of the journey catching up — on a phone that put it 1220px
      // down an 844px screen, so it vanished mid-flight and reappeared at the
      // end. Falling to mid-viewport instead means it lands where the reader is
      // looking and then rolls along with them.
      //
      // Mid-viewport is not an arbitrary choice: `s1` is defined as the scroll
      // at which the slot is centred, so at p=1 `scrollY + innerHeight/2` IS
      // `to.y`, exactly. The fruit arrives in the column with no correction.
      const ground = scrollY + innerHeight / 2;
      const y = ground - (ground - from.y) * height;
      const w = startPx + (endPx - startPx) * easeOut(Math.min(1, px * 1.2));

      // Rolling: angle = distance travelled / radius. That is what rolling IS.
      // A little free tumble before it touches down, since nothing is driving it.
      const rad = Math.max(1, w * BALL_FRAC);
      // From the ACTUAL displacement, not from `px` times the span — so if the
      // path is ever given a lateral kick, the spin follows it (and reverses)
      // for free instead of having to be kept in step by hand.
      const spin = height > 0.02 && px < 0.12
        ? p * 1.6
        : (x - from.x) / rad;

      const vx = x - scrollX, vy = y - scrollY;
      if (vx > -w && vx < innerWidth + w && vy > -w && vy < innerHeight + w) {
        ctx.save();
        ctx.translate(vx, vy);
        ctx.rotate(spin);
        ctx.drawImage(img, -w / 2, -w / 2, w, w);
        ctx.restore();
      }

      // 0.995, not 1. `s1` is a fractional pixel and scroll positions are
      // integers, so p tops out at 0.999 and an exact `< 1` test never fires —
      // the fruit rolled all the way in and then refused to land.
      if (p < 0.995) return;

      // Hand off to the DOM and drop the canvas. From here CSS owns it — no rAF
      // running behind the rest of the page.
      landed = true;
      rest.classList.add("on");
      cv.remove();
      removeEventListener("scroll", onScroll);
      dispatchEvent(new CustomEvent("fields:fruit-landed"));
    }

    function onScroll() {
      if (landed || queued) return;
      queued = true;
      requestAnimationFrame(draw);
    }

    const go = () => {
      measure();
      addEventListener("scroll", onScroll, { passive: true });
      draw();
    };
    img.complete ? go() : img.addEventListener("load", go, { once: true });

    addEventListener("resize", () => {
      if (!landed) { size(); measure(); onScroll(); }
    });
  }

  if (document.readyState === "loading") {
    addEventListener("DOMContentLoaded", run, { once: true });
  } else run();
})();
