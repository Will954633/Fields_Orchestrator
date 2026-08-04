/**
 * neon_cta.js — card 11's "Start building" as a neon tube.
 *
 * Port of `Concepts/illuminus_sign_concept/button.html`, which Will chose over
 * the three scene variants on 2026-08-04. It won on affordance rather than
 * looks: the more photographic the sign versions got, the less they read as
 * something you can press. This one is flat, axis-aligned and CTA-sized, and
 * keeps the tube and lighting work the scene versions paid for.
 *
 * THE DISCHARGE PHYSICS IS UNCHANGED FROM THE CONCEPT. Do not "simplify" it —
 * every constant is there for a reason and the reasons are measured. The short
 * version, with the full argument in that folder's README:
 *
 *   Striking is BINARY. Ionisation completes in microseconds and neon has no
 *   afterglow, so the tube edge is a hard step. There is no easing on it. What
 *   reads as softness is the halo, not the tube.
 *
 *   The halo LAGS. Bounce light plus retinal integration, modelled as an
 *   asymmetric one-pole filter — 12ms attack, 55ms release — run at 1kHz.
 *
 *   Mains is 50Hz, so a tube ripples at 100Hz. THIS IS THE TRAP: you cannot see
 *   100Hz and neither can a 60fps screen, so sampling it naively aliases it
 *   into a 20Hz strobe. Every frame is therefore the time-INTEGRAL of emission
 *   across that frame's exposure window, supersampled at 1kHz — which is what
 *   an eye and a shutter actually do.
 *
 *   Flicker has a grammar: drop out, hesitate at partial ionisation (dimmer and
 *   pinker, because a cold discharge runs pink), strike with streamer
 *   instability, hold, drop again.
 *
 * Four deliberate differences from the concept page:
 *
 *   PLAYS ONCE. The take runs when the card scrolls into view and then parks
 *   lit. A sign flickering forever under a CTA is obnoxious, and this deck's
 *   traffic is mostly phones.
 *
 *   THE rAF STOPS. On reaching steady, and whenever the card is off-screen.
 *   Nothing runs behind the rest of the page.
 *
 *   VARS ARE SCOPED TO THE BUTTON, not to `:root`. The concept owns its whole
 *   document; this one is a component on a page with ten other cards.
 *
 *   THE LINK STILL WORKS. The concept swallows its own click to replay. Here it
 *   stays a real anchor — focusable, keyboard-operable, and it does not
 *   preventDefault.
 *
 * Flash safety: WCAG 2.3.1 forbids more than three flashes in any one second.
 * Raw physics peaks at 8. SAFE pads only the LIT holds to a 340ms minimum
 * between strike onsets — it never softens an edge, it just makes the sign fail
 * less frantically. On by default and it should stay on: this page takes paid
 * traffic.
 */
(function () {
  "use strict";

  const MAINS_HZ = 50, RIPPLE_HZ = MAINS_HZ * 2, RIPPLE_DEPTH = 0.14;
  const RIPPLE_NORM = 1 / (1 - RIPPLE_DEPTH / 2);
  const SUB_MS = 1, TAU_ATTACK = 12, TAU_RELEASE = 55;
  const PULSES = 3, PULSE_MS = 1150, PULSE_FLOOR = 0.30;
  const DARK_MS = 420;
  const SAFE_MIN_STRIKE_GAP = 340;
  const SAFE = true;
  const TUBE_GAP = 14;      // px of tube missing at bottom centre — it has ends

  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

  function mulberry32(a) {
    return function () {
      a |= 0; a = a + 0x6D2B79F5 | 0;
      let t = Math.imul(a ^ a >>> 15, 1 | a);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  /** One failure, authored end to end. Ends AT steady — there is no loop. */
  function buildTake(seed) {
    const rnd = mulberry32(seed), seg = [];
    let t = 0;
    const push = (d, o) => { seg.push(Object.assign({ t0: t, t1: t + d }, o)); t += d; };
    push(DARK_MS, { kind: "dark", phase: "dark" });
    for (let i = 0; i < PULSES; i++) push(PULSE_MS, { kind: "pulse", phase: "pulse" });
    const n = 7 + Math.floor(rnd() * 4);
    for (let i = 0; i < n; i++) {
      const last = i === n - 1;
      push(rnd() < 0.22 ? 180 + rnd() * 260 : 14 + rnd() * 95, { kind: "off", phase: "flicker" });
      if (rnd() < 0.55) push(5 + rnd() * 16, { kind: "partial", a: 0.18 + rnd() * 0.28, phase: "flicker" });
      let on = last ? 240 + rnd() * 120 : 28 + rnd() * 190;
      if (SAFE) on = Math.max(on, SAFE_MIN_STRIKE_GAP);
      push(on, { kind: "on", a: 0.86 + rnd() * 0.14, ph: rnd() * 6.283, phase: "flicker" });
    }
    return { seg, total: t, seed };
  }

  function ripple(t) {
    const ph = 2 * Math.PI * RIPPLE_HZ * (t / 1000);
    return (1 - RIPPLE_DEPTH * (0.5 - 0.5 * Math.cos(ph))) * RIPPLE_NORM;
  }

  function emit(take, t) {
    if (t >= take.total) return { a: 1, warm: 0, done: true };
    let s = take.seg[take.seg.length - 1];
    for (let i = 0; i < take.seg.length; i++) {
      if (t < take.seg[i].t1) { s = take.seg[i]; break; }
    }
    const u = (t - s.t0) / (s.t1 - s.t0);
    switch (s.kind) {
      case "dark": return { a: 0, warm: 0 };
      case "off": return { a: 0, warm: 1 };
      case "partial": return { a: s.a, warm: 1 };
      case "pulse": {
        const a = PULSE_FLOOR + (1 - PULSE_FLOOR) * Math.sin(Math.PI * u) ** 2;
        return { a: Math.min(1, a * ripple(t)), warm: (1 - a) * 0.35 };
      }
      case "on": {
        const age = t - s.t0;
        const wob = 1 + 0.13 * Math.sin(2 * Math.PI * 62 * (age / 1000) + s.ph) * Math.exp(-age / 22);
        return { a: Math.min(1, s.a * wob * ripple(t)), warm: 0.25 * Math.exp(-age / 60) };
      }
    }
    return { a: 0, warm: 0 };
  }

  /* ---- sound -----------------------------------------------------------
     A magnetic ballast hums at TWICE mains — 100Hz — because the core
     magnetostricts once per half-cycle. Sawtooth through a lowpass, because the
     real thing is rich in odd harmonics. Every strike ticks.

     Two things about running it on a real page rather than a concept demo:

     AUTHORISE EARLY, PLAY ON THE SCROLL CUE. The graph is built the moment the
     page loads and we ask to resume it three times: at load, on the first real
     input (whenever that happens), and again the instant the sign scrolls into
     view. Wherever the browser permits audio — desktop Chrome with media
     engagement, anything with a relaxed policy, or any reader who has tapped so
     much as the intro's "skip" — the context is already running by the time the
     sign strikes and the sound just plays.

     Where it does NOT permit it, nothing can help. User activation is defined as
     only being triggerable by events with `isTrusted === true` — events the
     browser itself generated from real input. A synthetic click fired from an
     IntersectionObserver is `isTrusted: false` and is excluded by definition;
     that exclusion IS the autoplay policy. Scroll can trigger any amount of
     GRAPHICS (the fruit on card 04 is proof of that) because drawing pixels
     needs no permission. Audio is the one thing on the page behind a gate, and
     the gate does not care what triggered the sequence — only whether real
     input authorised playback. On iOS in particular, a reader who scrolls the
     whole deck without touching anything will hear nothing, and no amount of
     code changes that.

     IT FADES OUT AFTER THE SIGN SETTLES. A real transformer hums forever; a web
     page doing that is intrusive and burns battery. You hear it strike and
     settle, then it goes quiet. FADE_OUT is the one number to change if it
     should hold.

     Everything is wrapped: a machine with no audio device must never break a
     page that is mainly visual. */
  const FADE_OUT = 1.8;
  // Overall ballast level. Will confirmed the recipe at x1 is audible on his
  // phone as a sustained tone and x8 is loud, so x3 sits between "present on a
  // handset" and "obtrusive on a laptop". One number to retune.
  const LEVEL = 3;

  const audio = (() => {
    let ctx = null, master = null, ready = false, wasLit = false;
    let humG = null, h3G = null, h5G = null, h7G = null;
    let bornInGesture = false;
    // Counters for the on-page readout (?audiodebug=1). Cheap, and this took
    // four wrong guesses to diagnose without them.
    const stat = { arms: 0, rebuilds: 0, frames: 0, lastGain: 0, settled: false };

    /**
     * IS THERE A LIVE USER ACTIVATION RIGHT NOW — not "did an input event fire".
     *
     * These are not the same thing and the difference is the entire bug. Chrome
     * on Android does NOT grant activation on `touchstart` or `pointerdown` from
     * a finger: a touch that goes down might be the start of a scroll, so the
     * browser withholds activation until the gesture resolves as a tap. Desktop
     * pointerdown activates immediately; touch does not.
     *
     * So on a phone, the very first scroll fired `touchstart` -> arm(true) ->
     * a context was rebuilt with no activation to honour it, and `bornInGesture`
     * latched TRUE on a lie. From that moment the rebuild path was dead: every
     * later gesture, including real taps on the chapter cues, found
     * `bornInGesture === true` and rebuilt nothing. The context sat suspended (or
     * "running" and mute) for the rest of the session and could never recover.
     *
     * `navigator.userActivation.isActive` is the browser's own answer, so ask it
     * instead of inferring from the event type. Where it does not exist
     * (Safari < 16.4) fall back to trusting the caller, which is today's
     * behaviour and no worse.
     */
    function activationLive(inGesture) {
      if (!inGesture) return false;
      const ua = navigator.userActivation;
      return ua ? !!ua.isActive : true;
    }
    function teardown() {
      try { if (ctx) ctx.close(); } catch (e) {}
      ctx = master = humG = h3G = h5G = h7G = null;
      ready = false;
    }
    /** The mobile unlock. `resume()` alone is not enough — a context created
     *  outside a gesture will happily report state "running" and produce NO
     *  OUTPUT on a handset. Playing a buffer inside the gesture is what actually
     *  opens the audio path. */
    function unlock() {
      if (!ctx) return;
      try {
        const b = ctx.createBuffer(1, 1, ctx.sampleRate);
        const s = ctx.createBufferSource();
        s.buffer = b; s.connect(ctx.destination); s.start(0);
      } catch (e) {}
    }
    function build() {
      try {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return false;
        ctx = new AC();
        master = ctx.createGain(); master.gain.value = 1;
        master.connect(ctx.destination);
        const lp = ctx.createBiquadFilter();
        lp.type = "lowpass"; lp.frequency.value = 2600; lp.Q.value = 0.7;
        lp.connect(master);
        const mk = (f) => {
          const o = ctx.createOscillator(), v = ctx.createGain();
          o.type = "sawtooth"; o.frequency.value = f; v.gain.value = 0;
          o.connect(v).connect(lp); o.start(); return v;
        };
        // ODD HARMONICS, AND ENOUGH OF THEM TO BE HEARD ON A PHONE.
        // A magnetic ballast is rich in odd harmonics and the first version only
        // had two of them — 100Hz and 300Hz. A phone speaker rolls off hard
        // below ~500Hz and physically cannot reproduce 100Hz at any useful
        // level, so on a handset the hum was inaudible and only the 2400Hz
        // strike ticks came through. It read as "no sound" while measuring
        // perfectly healthy. The 5th and 7th put real energy in the band a small
        // speaker can actually move, and they are MORE faithful to a ballast,
        // not less — the low end is still there for headphones and laptops.
        humG = mk(RIPPLE_HZ);          // 100Hz  — body, on decent speakers
        h3G = mk(RIPPLE_HZ * 3);       // 300Hz
        h5G = mk(RIPPLE_HZ * 5);       // 500Hz  — the lowest a phone really gives
        h7G = mk(RIPPLE_HZ * 7);       // 700Hz  — where the buzz lives on a handset
        return true;
      } catch (e) { ctx = null; return false; }
    }
    function tick(freq, gain, decay) {
      if (!ctx) return;
      try {
        const len = Math.min(2048, decay * 10);
        const buf = ctx.createBuffer(1, len, ctx.sampleRate), d = buf.getChannelData(0);
        for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.exp(-i / decay);
        const src = ctx.createBufferSource(); src.buffer = buf;
        const bp = ctx.createBiquadFilter();
        bp.type = "bandpass"; bp.frequency.value = freq; bp.Q.value = 1.1;
        const g = ctx.createGain(); g.gain.value = gain;
        src.connect(bp).connect(g).connect(master); src.start();
      } catch (e) {}
    }
    return {
      get ready() { return ready; },
      /** Live means the context exists AND the browser is letting it run. */
      get live() { return ready && ctx && ctx.state === "running"; },
      get born() { return bornInGesture; },
      /**
       * Safe to call as often as you like. Pass true when this is running inside
       * a REAL user-input handler.
       *
       * The rebuild is the whole point. Building at load gets sound on desktop
       * with no tap, which is what we want — but a context born outside a
       * gesture is dead on a phone: it reports "running" after a later resume()
       * and emits nothing. That is exactly what happened here — the glass and
       * the voice worked on Android because their context is created inside the
       * press, and only the neon, built at load, was silent. So the first time a
       * real gesture arrives, if this context was not born in one, throw it away
       * and build a fresh one right here where the browser will honour it.
       */
      stat,
      snapshot() {
        return {
          ctx: ctx ? ctx.state : "none",
          born: bornInGesture,
          master: ctx && master ? +master.gain.value.toFixed(4) : null,
          hum: ctx && humG ? +humG.gain.value.toFixed(4) : null,
          arms: stat.arms, rebuilds: stat.rebuilds, frames: stat.frames,
          lastGain: +stat.lastGain.toFixed(4), settled: stat.settled,
          // The browser's own view of activation, which is the thing that was
          // being inferred wrongly. `ever` false at the sign means the reader
          // has genuinely not tapped anything and no code can produce sound.
          act: navigator.userActivation
            ? (navigator.userActivation.isActive ? "live" : "-") +
              "/" + (navigator.userActivation.hasBeenActive ? "ever" : "never")
            : "unsupported",
        };
      },
      arm(inGesture) {
        stat.arms++;
        const real = activationLive(inGesture);

        // Rebuild on the first REAL activation if this context was not born in
        // one — and also if it was, but is not actually running. The second
        // clause is the safety net: a context that never got permission stays
        // suspended forever, and there is no reason to keep a dead one just
        // because we once believed in it.
        if (ready && real && (!bornInGesture || !ctx || ctx.state !== "running")) {
          teardown(); stat.rebuilds++;
        }
        if (!ready) {
          if (!build()) return;
          ready = true;
          bornInGesture = real;
        }
        if (ctx && ctx.state === "suspended") {
          try { const r = ctx.resume(); if (r && r.catch) r.catch(() => {}); } catch (e) {}
        }
        if (real) unlock();
      },
      frame(lvl) {
        if (!ready || !ctx || ctx.state !== "running") return;
        // THE BALLAST DOES NOT FLICKER — THE TUBE DOES.
        //
        // This was gated straight off emission, so the hum vanished through
        // every dropout and only ever reached full gain on the brightest
        // frames. Averaged over a take that is mostly dark and flicker, it sat
        // far below the level of the isolated tone Will could hear perfectly
        // well on the same handset — audible in a test, inaudible in place.
        //
        // A real transformer is energised the whole time the sign is powered.
        // It hums continuously and the discharge stutters on top of it. So:
        // a constant floor with the emission riding over it, which is both more
        // faithful and the thing that makes it survive a phone speaker.
        const g = 0.55 + 0.45 * Math.max(0, Math.min(1, lvl));
        const t = ctx.currentTime;
        stat.frames++; stat.lastGain = LEVEL * 0.030 * g;
        humG.gain.setTargetAtTime(LEVEL * 0.030 * g, t, 0.02);
        h3G.gain.setTargetAtTime(LEVEL * 0.014 * g, t, 0.02);
        h5G.gain.setTargetAtTime(LEVEL * 0.013 * g, t, 0.02);
        h7G.gain.setTargetAtTime(LEVEL * 0.009 * g, t, 0.02);
        const lit = lvl > 0.12;
        if (lit && !wasLit) tick(2400, 0.16, 140);
        wasLit = lit;
      },
      /** A plain beep through THIS graph — same context, same master, same
       *  destination as the hum. If the isolated test page is audible and this
       *  is not, the difference is the graph, not the recipe. */
      beep() {
        if (!ctx || !master) return "no context";
        try {
          const o = ctx.createOscillator(), g = ctx.createGain();
          o.frequency.value = 440; g.gain.value = 0.25;
          o.connect(g).connect(master);
          o.start(); o.stop(ctx.currentTime + 0.8);
          return "played 440Hz @0.25 · ctx " + ctx.state + " · master " + master.gain.value;
        } catch (e) { return "FAILED " + e.message; }
      },
      settle() {
        if (!ready || !ctx) return;
        stat.settled = true;
        const t = ctx.currentTime;
        master.gain.cancelScheduledValues(t);
        master.gain.setValueAtTime(master.gain.value, t);
        master.gain.linearRampToValueAtTime(0, t + FADE_OUT);
      },
      mute() {
        if (!ready || !ctx) return;
        for (const g of [humG, h3G, h5G, h7G]) if (g) g.gain.value = 0;
        wasLit = false;
      },
    };
  })();

  function init() {
    const wrap = document.querySelector(".neonWrap");
    const btn = wrap && wrap.querySelector(".neon");
    const frame = btn && btn.querySelector(".neonFrame");
    if (!wrap || !btn || !frame) return;

    const set = (k, v) => wrap.style.setProperty(k, v);
    const park = () => { set("--lvl", "1"); set("--bloom", "1"); set("--warm", "0"); };

    // The tube path is generated from the button's OWN layout box, so the
    // corner radii cannot distort at any width. offsetWidth/offsetHeight, not
    // getBoundingClientRect — the rect includes the hover lift transform, which
    // would make the tube twitch under the pointer.
    function drawFrame() {
      const w = btn.offsetWidth, h = btn.offsetHeight;
      if (!w || !h) return;
      const rad = h / 2, gap = TUBE_GAP;
      const d = [`M ${w / 2 - gap / 2} ${h}`, `H ${rad}`,
                 `A ${rad} ${rad} 0 0 1 0 ${h - rad}`, `V ${rad}`,
                 `A ${rad} ${rad} 0 0 1 ${rad} 0`, `H ${w - rad}`,
                 `A ${rad} ${rad} 0 0 1 ${w} ${rad}`, `V ${h - rad}`,
                 `A ${rad} ${rad} 0 0 1 ${w - rad} ${h}`, `H ${w / 2 + gap / 2}`].join(" ");
      frame.setAttribute("viewBox", `0 0 ${w} ${h}`);
      frame.innerHTML =
        `<path class="t-glass" d="${d}"/>` +
        `<path class="t-bloom" d="${d}"/><path class="t-halo" d="${d}"/>` +
        `<path class="t-body"  d="${d}"/>` +
        `<path class="t-inner" d="${d}"/><path class="t-core" d="${d}"/>`;
    }

    new ResizeObserver(drawFrame).observe(btn);
    addEventListener("resize", drawFrame);
    drawFrame();

    if (reduced) {
      // Not a shortened sequence — none of it, and no sound either. A CTA
      // strobing and buzzing at someone who asked the OS for less motion is
      // exactly what that setting is for.
      park();
      return;
    }

    // 1. At load. Builds the graph and asks to run. On a permissive browser this
    //    alone is enough and the sign will have sound with no tap at all.
    audio.arm();

    // 2. On the first real input, whenever it comes — including the intro's
    //    "tap to skip" and the chapter cues, which are in this same document.
    //    Passive so it can never delay a scroll. Left attached rather than
    //    once-only: if the first ask was refused, every later gesture is
    //    another chance, and arm() now checks with the browser each time rather
    //    than latching on the first one.
    //
    //    THE LIST MATTERS. `touchstart` grants no activation on Android — a
    //    finger going down may be the start of a scroll, so Chrome waits to see
    //    whether the gesture resolves as a tap. `touchend`, `pointerup` and
    //    `click` are where activation actually lands on a phone, and they were
    //    all missing. Listening to the down-events alone meant that on a
    //    handset we asked at the one moment the answer is always no.
    for (const t of ["pointerdown", "pointerup", "touchstart", "touchend",
                     "click", "keydown", "keyup"]) {
      addEventListener(t, () => audio.arm(true), { passive: true });
    }

    const take = buildTake(20260804);
    let elapsed = 0, last = 0, bloom = 0, warmS = 0, raf = 0, running = false, done = false;

    function step(now) {
      if (!running) return;
      const dtWall = Math.min(now - last, 120);   // cap, so a tab switch cannot
      last = now;                                  // fast-forward the whole take
      const prev = elapsed;
      elapsed += dtWall;

      // Integrate emission across THIS frame's exposure window at 1kHz. This is
      // the line that stops the 100Hz ripple aliasing into a 20Hz strobe.
      const steps = Math.max(1, Math.round(dtWall / SUB_MS)), dt = dtWall / steps;
      let sum = 0, warmSum = 0, finished = false;
      for (let i = 0; i < steps; i++) {
        const e = emit(take, prev + dt * (i + 0.5));
        sum += e.a; warmSum += e.warm;
        if (e.done) finished = true;
        const tau = e.a > bloom ? TAU_ATTACK : TAU_RELEASE;
        bloom += (e.a - bloom) * (1 - Math.exp(-dt / tau));
      }
      const lvl = sum / steps;
      warmS += (warmSum / steps - warmS) * 0.25;
      set("--lvl", lvl.toFixed(4));
      set("--bloom", bloom.toFixed(4));
      set("--warm", warmS.toFixed(4));

      audio.frame(lvl);

      if (finished) {
        done = true; running = false; park();
        window.__neonTake = "finished";
        audio.settle();          // heard it strike; now let it go quiet
        return;
      }
      raf = requestAnimationFrame(step);
    }

    function start() {
      if (done || running) return;
      // 3. The scroll cue itself. If activation happened anywhere earlier in the
      //    deck, this is where it gets used.
      audio.arm();
      // THE SIGN NEVER WAITS FOR SOUND. An earlier version held the take until
      // the audio was provably usable, so that a take could not be spent in
      // silence — and the cost was a sign that sat dark on arrival, which is far
      // worse than a sign that strikes quietly. The visual runs on schedule and
      // the audio joins the moment it can; `frame()` simply no-ops until then.
      //
      // What made the hold unnecessary is `history.scrollRestoration = "manual"`
      // in deck.js: the reader now always starts at the top, so on a phone they
      // MUST scroll to reach the sign, and that scroll is the gesture that makes
      // the audio real. The hold was guarding against a case that no longer
      // happens.
      window.__neonTake = "running";
      running = true;
      last = performance.now();
      raf = requestAnimationFrame(step);
    }
    function stop() {
      running = false;
      cancelAnimationFrame(raf);
      audio.mute();              // scrolled away mid-take — do not hum offscreen
    }

    // Runs when the card arrives, pauses if the reader scrolls away mid-take and
    // picks up where it left off — `elapsed` is the clock, not wall time.
    window.FieldsNeon = { audio: () => audio.snapshot(), beep: () => audio.beep() };

    const io = new IntersectionObserver((es) => {
      for (const e of es) {
        if (e.isIntersecting) { window.__neonTake = "running"; start(); }
        else { window.__neonTake = "paused (offscreen)"; stop(); }
      }
      if (done) io.disconnect();
      // Fire only when the sign is properly ON SCREEN, not when it clips the
      // edge. `threshold: 0.35` alone triggered the moment a third of the button
      // crossed the bottom of the viewport — measured on a phone, the take
      // STARTED with the button's centre at 90% of screen height and FINISHED at
      // 87%, so the whole seven seconds played out in a sliver at the bottom
      // edge while the reader was still scrolling toward it. They then arrived
      // at a sign that was already parked lit with its audio faded out, which
      // reads exactly as "it lights up but makes no sound".
      //
      // Shrinking the root to the middle half of the viewport means the take
      // cannot start until the sign is somewhere the reader is actually looking.
    // Only the BOTTOM edge is pulled in. Shrinking both sides to the middle half
    // stopped it firing at all. The problem was only ever the bottom: the take
    // began with the button's centre at 90% of screen height and ended at 87%,
    // so it ran out in a sliver at the edge while the reader scrolled toward it.
    }, { threshold: 0.5, rootMargin: "0px 0px -18% 0px" });
    io.observe(btn);

    // A backgrounded tab still fires rAF on some platforms; stop rather than
    // burn a phone battery on a sign nobody is looking at.
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) stop();
      else if (!done && btn.getBoundingClientRect().top < innerHeight) start();
    });
  }

  if (document.readyState === "loading") {
    addEventListener("DOMContentLoaded", init, { once: true });
  } else init();

  // ── on-page readout ────────────────────────────────────────────────────────
  // ?audiodebug=1 only. The neon's audio failed on a handset while every local
  // measurement said it was healthy, and it cost four wrong fixes to find out
  // why. This is how the next one gets answered in a single message.
  if (/audiodebug/.test(location.search)) {
    const box = document.createElement("div");
    box.style.cssText = "position:fixed;left:0;right:0;top:0;z-index:999;background:#000e;" +
      "color:#8FE9A8;font:11px/1.6 ui-monospace,Menlo,Consolas,monospace;padding:.5rem .6rem;" +
      "border-bottom:1px solid #8FE9A855;white-space:pre-wrap";
    const btn2 = document.createElement("button");
    btn2.textContent = "TAP FOR TEST TONE (neon's own graph)";
    btn2.style.cssText = "display:block;width:100%;margin-top:.4rem;padding:.7rem;" +
      "background:#132;border:1px solid #8FE9A8;color:#8FE9A8;border-radius:8px;" +
      "font:inherit;font-size:12px";
    const out = document.createElement("div");
    out.style.cssText = "color:#CFF6DA;margin-top:.3rem";
    btn2.onclick = () => { out.textContent = window.FieldsNeon
      ? window.FieldsNeon.beep() : "module not ready"; };
    // Attach NOW if the document is already parsed. This script is injected at
    // the end of <body>, so DOMContentLoaded has usually fired before it runs
    // and a listener for it never gets called — the panel's button silently
    // never appeared.
    // The readout goes in its OWN node. Writing box.textContent replaces every
    // child, so the button and its output were being deleted 8 times a second.
    const lines = document.createElement("div");
    const attach = () => { document.body.append(box); box.append(lines, btn2, out); };
    if (document.readyState === "loading") {
      addEventListener("DOMContentLoaded", attach, { once: true });
    } else attach();
    setInterval(() => {
      const a = (window.FieldsNeon && window.FieldsNeon.audio()) || {};
      const w = document.querySelector(".neonWrap");
      lines.textContent =
        `ctx ${a.ctx}  born-in-gesture ${a.born}  rebuilds ${a.rebuilds}
` +
        `activation ${a.act}
` +
        `master ${a.master}  humGain ${a.hum}  lastWrite ${a.lastGain}
` +
        `arms ${a.arms}  frames ${a.frames}  settled ${a.settled}
` +
        `--lvl ${w ? w.style.getPropertyValue("--lvl") || "0" : "?"}  ` +
        `take ${window.__neonTake || "waiting"}`;
    }, 120);
  }
})();
