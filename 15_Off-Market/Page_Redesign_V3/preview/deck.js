<script>
(() => {
  "use strict";

  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;


  const landing = document.getElementById("card-00");

  // Lock the page while the intro owns the screen. Set from script, not in the
  // markup, so the deck stays scrollable if the intro fails to boot.
  document.documentElement.classList.add("intro-locked");

  // ── hand-off ───────────────────────────────────────────────────────────────
  // Card 00 standalone (Will, 2026-08-03): "We found your home." gets a viewport
  // to itself, unnumbered and off the rail — it is the landing of the intro, not
  // a chapter of the deck.
  addEventListener("fields:intro-done", () => {
    // Scroll first, reveal on arrival. Revealing up front would run the whole
    // .9s transition while card 00 is still below the fold, so the reader
    // arrives at copy that has already finished animating.
    landing.scrollIntoView({ behavior: "smooth", block: "start" });
    setTimeout(() => landing.classList.add("revealIn"), 420);
  }, { once: true });

  // ── the drawing ────────────────────────────────────────────────────────────
  // Set up BEFORE the observer, and default to a no-op. Six of the twelve lead
  // angles are text-only, so those decks have no <video> at all — and when the
  // media block bailed out early with `return`, the observer still fired and
  // called into it, hitting `let fired` in its temporal dead zone:
  // "Cannot access 'fired' before initialization". It only showed on the one
  // text-only example in the set.
  let revealEmblem = () => {};

  const media = document.getElementById("media");
  const video = document.getElementById("emblem");
  const replay = document.getElementById("replay");

  // On mobile the drawing moves directly beneath the headline (Will's call,
  // 2026-08-03). Left at the end of the card it sat most of a screen below the
  // fold, so the reader met the argument and the evidence a screen apart.
  // The figure has to be INSIDE the text column for that, which no amount of
  // CSS can do from a sibling grid cell — so move the node, rather than render
  // a second <video> and download the clip twice.
  // Desktop is unaffected: the two-column grid already puts it beside the copy.
  if (media && matchMedia("(max-width:899px)").matches) {
    const col = document.querySelector("#card-03 .colText");
    const h2 = col && col.querySelector("h2");
    if (h2) h2.insertAdjacentElement("afterend", media);
  }

  if (media && video) {

  // How long after the copy starts arriving before the drawing does. The
  // stagger runs .04s -> .64s with a .9s transition, so the last line has
  // settled by ~1.5s. 1250ms lands the drawing just as the copy finishes,
  // rather than leaving a dead beat between the two.
  const MEDIA_DELAY_MS = 1250;

  // Attach the clip on the reader's first sign of intent, not on load. Hanging
  // it off an IntersectionObserver on card 02 is no deferral at all — card 02 is
  // within the first screens, so it intersects almost immediately. This way
  // someone who opens the page and leaves never downloads ~2MB, and anyone who
  // scrolls gets a full card of lead time, far longer than it needs to buffer.
  function ensureSrc() {
    if (video.src) return;
    video.src = video.dataset.src;
    video.load();
  }
  ["wheel", "touchmove", "keydown", "pointerdown"].forEach((ev) =>
    addEventListener(ev, ensureSrc, { once: true, passive: true }));

  function play() {
    media.classList.add("mediaIn");
    ensureSrc();
    if (reduced) { video.controls = true; return; }
    try { video.currentTime = 0; } catch (_) {}
    // Muted + playsinline satisfies iOS and Android, but Low Power Mode and
    // Data Saver refuse regardless. Fall back to a tappable video rather than
    // leaving a blank rectangle.
    video.play().catch(() => { video.controls = true; media.classList.add("needsTap"); });
  }

  let fired = false;
  revealEmblem = () => {
    if (fired) return;
    fired = true;
    if (reduced) return play();
    setTimeout(play, MEDIA_DELAY_MS);
  };

  if (replay) replay.addEventListener("click", play);

  // Trigger on the DRAWING entering view, not the card. Card 03 runs 1.4-1.8
  // phone screens tall, so on mobile the drawing sits half a screen below the
  // fold — firing on the card meant the 5-6s reveal had usually finished before
  // the reader ever scrolled to it, and they met a static picture. On desktop
  // the drawing is beside the copy and enters with the card anyway, so this is
  // the same moment there.
  new IntersectionObserver((es, obs) => {
    for (const e of es) if (e.isIntersecting) { obs.disconnect(); revealEmblem(); }
  }, { threshold: 0.35 }).observe(media);
  }

  // ── always start at the beginning ─────────────────────────────────────────
  // Browsers restore scroll position on reload. On a scroll NARRATIVE that is
  // simply wrong — the intro plays and then drops the reader into card 9 — and
  // it had a second, invisible cost: a restored position could put the neon on
  // screen at load, so its take ran and burnt itself out before the reader had
  // touched anything, which on a phone means it played in silence and never
  // played again.
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";

  // ── the scroll cues are links ─────────────────────────────────────────────
  // "↓ So what did you find?" reads as an invitation, so it should behave like
  // one.
  //
  // The target comes from DOM ORDER, not from incrementing the card number. The
  // builder drops cards it has no data for, so the ids genuinely have holes — a
  // nine-card deck runs card-05 straight to card-07 — and arithmetic would send
  // that cue to an element that does not exist.
  //
  // Replaced with a real <a> rather than given a click handler on the span: it
  // is then keyboard-operable, announces itself as a link, and inherits the
  // page's smooth scrolling without any script. Swapping the node preserves its
  // position among its siblings, so the stagger's nth-child delays still line up.
  for (const cue of [...document.querySelectorAll(".next")]) {
    const card = cue.closest(".card");
    const next = card && card.nextElementSibling;
    if (!next || !next.id) continue;
    const a = document.createElement("a");
    a.className = cue.className;
    a.href = "#" + next.id;
    while (cue.firstChild) a.appendChild(cue.firstChild);
    cue.replaceWith(a);
  }

  // ── cards reveal on approach ───────────────────────────────────────────────
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      e.target.classList.add("revealIn");
      io.unobserve(e.target);

    }
  }, { threshold: 0.15 });
  document.querySelectorAll(".card").forEach((c) => { if (c !== landing) io.observe(c); });
})();
</script>
