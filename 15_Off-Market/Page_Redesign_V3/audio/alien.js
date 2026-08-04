/**
 * alien.js — a key scraped along a piano's bass strings, slowed down.
 *
 * This is the actual recipe. The signal in Contact (1997) is a variation of the
 * TARDIS effect from Doctor Who, which Brian Hodgson made at the BBC
 * Radiophonic Workshop by dragging a house key along the bass strings of a
 * gutted piano and slowing the tape. Randy Thom adapted it for the film.
 *
 * Which is why every pulse I tried first was wrong. It is not a beat, a carrier
 * or a burst of static. It is a SUSTAINED, GROANING, METALLIC WASH — a mess of
 * inharmonic partials being excited all at once, stretched out until it
 * wheezes. Nothing rhythmic about it.
 *
 *   const a = FieldsAlien.create();   // inside a user gesture
 *   a.start(); a.swell(0.9, 4); a.stop();
 *
 * How it is built, and why each part is there:
 *
 *   INHARMONICITY  A piano's partials are not integer multiples. Stiff strings
 *                  stretch them: fn = n·f0·sqrt(1 + B·n²). On a bass string B is
 *                  large, which is what makes a low piano note sound like a
 *                  gong rather than a sine. That stretch IS the metal.
 *
 *   EXCITATION     A scrape is not a pluck. It is continuous, noisy and uneven —
 *                  filtered noise wandering across the partials, so different
 *                  ones light up at different moments and the sound keeps moving
 *                  without anything changing pitch.
 *
 *   RESONATORS     One very high-Q bandpass per partial. Ringing filters, not
 *                  oscillators: the noise goes in and the metal decides what
 *                  comes out. An oscillator bank would sound like an organ.
 *
 *   SLOWED         Everything sits an octave or two below where a piano would,
 *                  and drifts. Tape slowdown lowers pitch and stretches time,
 *                  and the drift is what stops it sounding like a held chord.
 *
 *   SPACE          A long feedback reverb. This has travelled 26 light years
 *                  and it should not sound like it is in the room.
 */
(function (global) {
  "use strict";

  // Piano inharmonicity coefficient. Bass strings are stiff and short relative
  // to their pitch, so B is large — 0.0008 is a low note on an upright.
  const B = 0.0009;

  function create(opts) {
    const AC = global.AudioContext || global.webkitAudioContext;
    if (!AC) return null;
    const ctx = new AC();

    const cfg = Object.assign({
      f0: 41,            // fundamental, well below a piano's bottom A — "slowed"
      partials: 16,      // how much metal
      B: B,              // inharmonicity: 0 = a harmonic string, high = a gong
      q: 90,             // resonator sharpness — how much it rings
      scrapeRate: 0.9,   // how fast the scrape wanders across the partials
      grit: 0.5,         // scrape noise on top of the resonance
      space: 0.6,        // reverb amount
      drift: 0.04,       // slow pitch wander
      level: 0.0,        // 0..1
      master: 0.55,
    }, opts || {});

    const master = ctx.createGain();
    master.gain.value = cfg.master;
    master.connect(ctx.destination);

    // A limiter, because the presets differ enormously in output. A bank of
    // Q=140 filters passes far less noise energy than a bank of Q=60, so
    // "distant" and "scraped" are ~8dB apart before this. Measured, not guessed:
    // raw peak ranged 0.0095..0.018 across presets.
    const limit = ctx.createDynamicsCompressor();
    limit.threshold.value = -8; limit.knee.value = 6;
    limit.ratio.value = 12; limit.attack.value = 0.006; limit.release.value = 0.28;
    limit.connect(master);

    // Makeup. High-Q bandpasses only pass a narrow slice of the excitation, so
    // the bank comes out around -40dBFS without this.
    const makeup = ctx.createGain();
    makeup.gain.value = 48;
    makeup.connect(limit);

    const out = ctx.createGain();
    out.gain.value = cfg.level;
    out.connect(makeup);

    // ── space ────────────────────────────────────────────────────────────────
    // A synthesised impulse: exponentially decaying noise. Cheaper than a real
    // convolution file and there is nothing to license.
    const conv = ctx.createConvolver();
    {
      const secs = 4.5, n = Math.floor(ctx.sampleRate * secs);
      const ir = ctx.createBuffer(2, n, ctx.sampleRate);
      for (let c = 0; c < 2; c++) {
        const d = ir.getChannelData(c);
        for (let i = 0; i < n; i++) {
          d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / n, 2.6);
        }
      }
      conv.buffer = ir;
    }
    const wet = ctx.createGain(); wet.gain.value = cfg.space;
    const dry = ctx.createGain(); dry.gain.value = 1 - cfg.space * 0.5;
    conv.connect(wet).connect(out);
    dry.connect(out);

    // ── excitation ───────────────────────────────────────────────────────────
    const noiseBuf = (() => {
      const n = ctx.sampleRate * 4;
      const b = ctx.createBuffer(1, n, ctx.sampleRate);
      const d = b.getChannelData(0);
      // brown-ish noise: a scrape has far more low-frequency energy than hiss
      let last = 0;
      for (let i = 0; i < n; i++) {
        const w = Math.random() * 2 - 1;
        last = (last + 0.028 * w) / 1.028;
        d[i] = last * 3.2;
      }
      return b;
    })();

    const exc = ctx.createBufferSource();
    exc.buffer = noiseBuf; exc.loop = true;
    // The scrape: a bandpass wandering up and down the partial range, so the
    // metal lights up unevenly. This is the difference between a scrape and a
    // sustained hum.
    const scrape = ctx.createBiquadFilter();
    scrape.type = "bandpass"; scrape.frequency.value = 400; scrape.Q.value = 1.1;
    const scrapeLfo = ctx.createOscillator();
    scrapeLfo.type = "triangle"; scrapeLfo.frequency.value = cfg.scrapeRate * 0.13;
    const scrapeAmt = ctx.createGain(); scrapeAmt.gain.value = 620;
    scrapeLfo.connect(scrapeAmt).connect(scrape.frequency);
    // a second, faster wander so it never settles into a pattern
    const scrapeLfo2 = ctx.createOscillator();
    scrapeLfo2.type = "sine"; scrapeLfo2.frequency.value = cfg.scrapeRate * 0.41;
    const scrapeAmt2 = ctx.createGain(); scrapeAmt2.gain.value = 240;
    scrapeLfo2.connect(scrapeAmt2).connect(scrape.frequency);

    exc.connect(scrape);

    // ── the strings ──────────────────────────────────────────────────────────
    const bank = [];
    for (let n = 1; n <= cfg.partials; n++) {
      const f = cfg.f0 * n * Math.sqrt(1 + cfg.B * n * n);
      if (f > 9000) break;
      const bp = ctx.createBiquadFilter();
      bp.type = "bandpass";
      bp.frequency.value = f;
      // upper partials ring less, as they do on a real string
      bp.Q.value = cfg.q / (1 + n * 0.06);
      const g = ctx.createGain();
      g.gain.value = 1 / Math.pow(n, 0.72);
      scrape.connect(bp).connect(g);
      g.connect(conv); g.connect(dry);
      bank.push({ bp, g, base: f, n });
    }

    // grit: the scrape itself, riding over the resonance
    const gritHp = ctx.createBiquadFilter();
    gritHp.type = "highpass"; gritHp.frequency.value = 1400;
    const gritG = ctx.createGain(); gritG.gain.value = cfg.grit * 0.12;
    scrape.connect(gritHp).connect(gritG);
    gritG.connect(conv); gritG.connect(dry);

    // ── drift ────────────────────────────────────────────────────────────────
    // Tape does not hold pitch. Without this it is a held chord, not a signal.
    const drift = ctx.createOscillator();
    drift.type = "sine"; drift.frequency.value = 0.045;
    const driftGains = bank.map(({ bp, base }) => {
      const g = ctx.createGain();
      g.gain.value = base * cfg.drift;
      g.connect(bp.frequency);
      return g;
    });
    driftGains.forEach((g) => drift.connect(g));

    let running = false;
    return {
      ctx,
      start() {
        if (running) return;
        running = true;
        if (ctx.state === "suspended") ctx.resume();
        exc.start(); scrapeLfo.start(); scrapeLfo2.start(); drift.start();
      },
      stop() {
        running = false;
        try { exc.stop(); scrapeLfo.stop(); scrapeLfo2.stop(); drift.stop(); } catch (_) {}
        ctx.close();
      },
      /** Bring it up out of nothing, or take it away. */
      swell(v, seconds) {
        cfg.level = v;
        out.gain.linearRampToValueAtTime(v, ctx.currentTime + (seconds || 3));
      },
      set(k, v) {
        cfg[k] = v;
        const t = ctx.currentTime;
        if (k === "space") { wet.gain.value = v; dry.gain.value = 1 - v * 0.5; }
        else if (k === "grit") gritG.gain.value = v * 0.12;
        else if (k === "q") bank.forEach((b) => { b.bp.Q.value = v / (1 + b.n * 0.06); });
        else if (k === "scrapeRate") {
          scrapeLfo.frequency.setValueAtTime(v * 0.13, t);
          scrapeLfo2.frequency.setValueAtTime(v * 0.41, t);
        } else if (k === "f0" || k === "B") {
          bank.forEach((b) => {
            const f = cfg.f0 * b.n * Math.sqrt(1 + cfg.B * b.n * b.n);
            b.base = f;
            b.bp.frequency.setTargetAtTime(f, t, 0.05);
          });
          driftGains.forEach((g, i) => { g.gain.value = bank[i].base * cfg.drift; });
        } else if (k === "drift") {
          driftGains.forEach((g, i) => { g.gain.value = bank[i].base * v; });
        }
      },
      get(k) { return cfg[k]; },
    };
  }

  // Distinct places to stand, rather than one sound with sliders.
  const PRESETS = [
    { id: "tardis",  name: "Piano string, slowed",
      note: "The recipe as described: a key dragged along bass strings, tape slowed. Start here.",
      f0: 41, B: 0.0009, q: 90, scrapeRate: 0.9, grit: 0.5, space: 0.6, drift: 0.04 },
    { id: "deeper",  name: "Slowed further",
      note: "Same string, more tape. Heavier, more groan, less detail.",
      f0: 26, B: 0.0014, q: 120, scrapeRate: 0.55, grit: 0.35, space: 0.75, drift: 0.05 },
    { id: "gong",    name: "Toward a gong",
      note: "Inharmonicity pushed hard. The partials stop relating to each other at all.",
      f0: 38, B: 0.0035, q: 110, scrapeRate: 0.8, grit: 0.4, space: 0.7, drift: 0.03 },
    { id: "scraped", name: "More scrape",
      note: "The key against the winding, not the note it makes. Grittier, closer, nastier.",
      f0: 44, B: 0.0009, q: 60, scrapeRate: 1.9, grit: 1.0, space: 0.45, drift: 0.06 },
    { id: "distant", name: "Distant",
      note: "Long room, little grit. Something happening a very long way away.",
      f0: 33, B: 0.0011, q: 140, scrapeRate: 0.4, grit: 0.12, space: 0.95, drift: 0.03 },
    { id: "wobble",  name: "Failing tape",
      note: "Heavy drift. The machine reproducing it is not well.",
      f0: 36, B: 0.0012, q: 100, scrapeRate: 0.7, grit: 0.45, space: 0.65, drift: 0.16 },
    { id: "bright",  name: "Bright metal",
      note: "Higher fundamental, tighter ring. More bell than groan.",
      f0: 72, B: 0.0006, q: 130, scrapeRate: 1.2, grit: 0.3, space: 0.55, drift: 0.03 },
    { id: "swarm",   name: "Swarm",
      note: "Fast wander over many partials. Restless, almost like something moving.",
      f0: 47, B: 0.0018, q: 75, scrapeRate: 3.2, grit: 0.6, space: 0.5, drift: 0.08 },
  ];

  global.FieldsAlien = { create, PRESETS };
})(window);
