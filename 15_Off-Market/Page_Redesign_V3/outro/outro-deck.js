/**
 * outro-deck.js — the shatter sequence, packaged for the real deck.
 *
 * Everything `crack-demo.html` does, minus the demo's own chrome (the stand-in
 * page, the replay button, the sound toggle, the build stamp). Pressing card
 * 11's neon runs it:
 *
 *   the screen cracks where the finger landed -> the fracture races across the
 *   pane -> 67 pieces fall away -> the code rain is revealed -> the ship's
 *   computer reads the build sequence over Cassini's Saturn recording, counting
 *   down T-3 - 2 - 1 -> the signal cuts on "Construction completed."
 *
 *   FieldsOutro.play(clientX, clientY)
 *
 * Requires glass-audio.js, signal-bed.js and crack.js loaded first, and
 * window.FIELDS_OUTRO_BASE pointing at the outro folder.
 *
 * Four things that are different here from the demo, and why:
 *
 *   THE DOM IS BUILT ON DEMAND. A reader who never presses the button should
 *   carry none of this — no fixed overlays, no canvas, no rain loop. Everything
 *   is created inside play().
 *
 *   THE PRESS IS THE GESTURE. Browsers block audio until real input, and this
 *   press IS that input, so the glass, the voice and the signal are all armed
 *   inside the click handler. It is the one moment in the deck where sound is
 *   guaranteed to work.
 *
 *   SCROLL IS LOCKED for the duration. The reader has committed; letting them
 *   scroll the deck out from under a full-screen shatter would be nonsense.
 *
 *   IT ENDS ON AN EVENT, NOT A DEAD STOP. `fields:strategy-built` fires when the
 *   last line lands, for whatever comes next to hang off.
 */
(function (global) {
  "use strict";

  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  // Bump alongside build_voice.py — the filenames never change, so a cached clip
  // would leave her saying the old line under the new caption.
  const VOICE_V = "?v=20260803b";

  const GLYPHS = ("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ$%.,:/-+=<>#*" +
                  "0123456789").split("");
  const WORDS = ["ANALYSING", "COMPARABLE", "ADJUSTING", "POSITION", "STRATEGY",
                 "BUILDING", "SEQUENCE", "INDEXING", "VALUATION", "COMPILING",
                 "SORTING", "MATCHING", "BUYER POOL", "PRICE BAND", "TIMING"];

  const SCRIPT = [
    { t: "Analysing selling strategy...", v: "01", after: () => quake(1) },
    { t: "Construction sequence initiated..", v: "02", after: () => quake(1) },
    { t: "Approaching completion in T-3 seconds...", v: "03", after: () => quake(2),
      countdown: true },
    { t: "Construction completed.", v: "04", after: () => quake(0), ok: true },
  ];
  const COUNT = ["c3", "c2", "c1"];

  let world, behind, cv, ctx, msg, running = false;
  const VOICE = {};

  function el(tag, id) {
    const n = document.createElement(tag);
    if (id) n.id = id;
    return n;
  }

  function quake(level) {
    if (!world) return;
    world.classList.remove("quake-1", "quake-2");
    if (level && !reduced) world.classList.add("quake-" + level);
  }

  // ── the rain field ─────────────────────────────────────────────────────────
  // Same look as the intro, but this one only has to fall and then switch off
  // right to left — it carries no recognition tiers, because by this point the
  // reader has already been shown their own street.
  let W, H, cw, ch, cols, rowsN, colLife, streams = [], last = 0, rainOn = false, shutdown = -1;

  function size() {
    const dpr = Math.min(2, devicePixelRatio || 1);
    W = innerWidth; H = innerHeight;
    cv.width = W * dpr; cv.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.font = "16px ui-monospace, Menlo, Consolas, monospace";
    cw = 13; ch = 19;
    cols = Math.ceil(W / cw); rowsN = Math.ceil(H / ch);
    colLife = new Float32Array(cols).fill(1);
    streams = [];
    for (let i = 0; i < cols; i++) {
      const n = 1 + (Math.random() < 0.4 ? 1 : 0);
      for (let k = 0; k < n; k++) streams.push(newStream(i, true));
    }
  }
  function newStream(col, spread) {
    return { col, y: spread ? -Math.random() * rowsN : -2,
             speed: 5 + Math.random() * 11, len: 8 + Math.random() * 18,
             word: Math.random() < 0.34 ? WORDS[(Math.random() * WORDS.length) | 0] : null,
             seed: Math.random() * 1e6 };
  }
  function rainFrame(now) {
    if (!rainOn) return;
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    ctx.fillStyle = "rgba(0,0,0,0.22)";
    ctx.fillRect(0, 0, W, H);
    if (shutdown >= 0) {
      shutdown += dt / 3.0;
      for (let i = 0; i < cols; i++) {
        const edge = 1 - shutdown;
        colLife[i] = i / cols > edge ? Math.max(0, colLife[i] - dt * 3.2) : colLife[i];
      }
    }
    for (const s of streams) {
      s.y += s.speed * dt;
      const life = colLife[s.col] || 0;
      if (life <= 0) continue;
      for (let k = 0; k < s.len; k++) {
        const y = Math.floor(s.y - k);
        if (y < 0 || y > rowsN) continue;
        const head = k === 0;
        const a = (1 - k / s.len) * life;
        let chr;
        if (s.word && k < s.word.length) chr = s.word[s.word.length - 1 - k];
        else chr = GLYPHS[(Math.floor(s.seed + y * 7 + k * 13 + now / 90) % GLYPHS.length + GLYPHS.length) % GLYPHS.length];
        ctx.fillStyle = head ? `rgba(210,255,225,${a})` : `rgba(60,235,120,${a * 0.8})`;
        ctx.fillText(chr, s.col * cw, y * ch);
      }
      if (s.y - s.len > rowsN) Object.assign(s, newStream(s.col, false));
    }
    requestAnimationFrame(rainFrame);
  }

  // ── the printed sequence ───────────────────────────────────────────────────
  async function type(line) {
    const row = document.createElement("div");
    if (line.ok) row.className = "ok";
    msg.appendChild(row);

    // Pace the typing to the speech, not the other way round. A fixed
    // characters-per-second either finishes early and leaves the voice talking
    // to a static line, or lags behind it — and the mismatch is the thing that
    // makes captioned voice look cheap.
    const v = VOICE[line.v];
    let per = 52, dot = 180, spoke = 0;
    if (v) {
      if (line.ok) FieldsSignalBed.stop(0.2);
      else FieldsSignalBed.duck(0.5, 0.25);
      try { v.audio.currentTime = 0; v.audio.play(); spoke = performance.now(); } catch (_) {}
      const visible = line.t.replace(/\./g, "").length;
      const dots = line.t.length - visible;
      per = Math.max(24, (v.seconds * 1000 * 0.82 - dots * 120) / Math.max(1, visible));
      dot = 120;
    }
    for (let i = 1; i <= line.t.length; i++) {
      row.textContent = line.t.slice(0, i);
      await wait(line.t[i - 1] === "." ? dot : per);
    }

    if (line.countdown) {
      // The typing is paced to 82% of the clip, so the last character lands
      // while she is still finishing the sentence. Every other line has a gap
      // after it that absorbs this; the countdown chains straight on, so
      // without an explicit hold "Three" starts on top of "...seconds".
      if (v && spoke) {
        await wait(Math.max(0, v.seconds * 1000 - (performance.now() - spoke) + 200));
      }
      line.after();                 // shake escalates THROUGH the count
      await countdown(row, line.t);
      return;
    }
    if (v && !line.ok) FieldsSignalBed.unduck(0.4);
    line.after();
  }

  // Swap the "3" in "...T-3 seconds..." for a live digit and count it down. A
  // flat 1s beat, so the countdown genuinely takes the three seconds she just
  // promised — the clips are 0.5-0.65s, so each number lands and then hangs.
  async function countdown(row, text) {
    const at = text.indexOf("3");
    row.textContent = "";
    const n = document.createElement("span");
    n.className = "n";
    row.append(text.slice(0, at), n, text.slice(at + 1));
    for (let i = 0; i < COUNT.length; i++) {
      n.textContent = String(3 - i);
      const c = VOICE[COUNT[i]];
      if (c) { try { c.audio.currentTime = 0; c.audio.play(); } catch (_) {} }
      row.classList.remove("beat"); void row.offsetWidth; row.classList.add("beat");
      await wait(1000);
    }
    row.classList.remove("beat");
  }

  function loadVoice() {
    const base = (global.FIELDS_OUTRO_BASE || "") + "voice/";
    return fetch(base + "index.json" + VOICE_V)
      .then((r) => r.json())
      .then((m) => {
        for (const l of m.lines) {
          const a = new Audio(base + l.file + VOICE_V);
          a.preload = "auto"; a.volume = 0.85;
          VOICE[l.id] = { audio: a, seconds: l.seconds };
        }
      })
      .catch(() => {});           // silence is survivable; a broken page is not
  }

  // ── the whole thing ────────────────────────────────────────────────────────
  function build() {
    world = el("div", "fx-world");
    behind = el("div", "fx-behind");
    cv = el("canvas", "fx-rain");
    msg = el("div", "fx-msg");
    behind.appendChild(cv);
    world.append(behind, msg);
    document.body.appendChild(world);
    ctx = cv.getContext("2d", { alpha: false });
    // Sized and filled black from the start: that black is what shows through
    // the impact hole and through every gap the falling glass leaves.
    size();
    ctx.fillStyle = "#000"; ctx.fillRect(0, 0, W, H);
    addEventListener("resize", () => { if (rainOn) size(); });
  }

  async function play(x, y) {
    if (running) return;
    running = true;

    // The press is a real user gesture, which is what makes any of this audible.
    const actx = FieldsGlassAudio.arm();
    FieldsSignalBed.arm(actx);
    FieldsSignalBed.fetch();
    loadVoice();

    build();
    document.documentElement.style.overflow = "hidden";
    document.body.style.overflow = "hidden";

    const deck = document.getElementById("deck");

    FieldsCrack.strike(x, y, {
      reveal: cv,
      skipGash: true,
      onImpact: () => {
        if (reduced) return;
        FieldsGlassAudio.impact();
        world.classList.remove("jolt"); void world.offsetWidth;
        world.classList.add("jolt");
      },
      // The deck stays readable THROUGH the cracked glass — that is the whole
      // idea — and only goes when the pane starts falling.
      onNetwork: () => { if (!reduced) FieldsGlassAudio.crackle(900); },
      onFall: () => {
        if (deck) deck.classList.add("fx-gone");
        if (!reduced) FieldsGlassAudio.shatter(3800);
      },
      onDone: async () => {
        // Now, and not before: the glass has completely gone, so the code starts
        // on an empty screen rather than being glimpsed through it.
        behind.classList.add("on");
        rainOn = true; last = performance.now();
        requestAnimationFrame(rainFrame);

        // The signal comes up one second behind the code, over 1.5s. Arriving
        // second, out of nothing, reads as something being picked up; arriving
        // together reads as a cue.
        if (!reduced) setTimeout(() => FieldsSignalBed.start({ fadeIn: 1.5 }), 1000);

        await wait(2200);
        shutdown = 0;                     // code switches off right to left
        await wait(3000);
        for (const line of SCRIPT) { await type(line); await wait(500); }
        await wait(1600);
        quake(0);
        dispatchEvent(new CustomEvent("fields:strategy-built"));
      },
    });
  }

  global.FieldsOutro = { play, get running() { return running; } };
})(window);
