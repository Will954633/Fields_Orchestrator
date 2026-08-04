/**
 * signal.js — a signal arriving out of the noise.
 *
 * The VLA scene in Contact: a wide band of static, and then something
 * underneath it that is unmistakably deliberate. Synthesised, not sampled —
 * the film's audio is copyrighted, and a pulse over static is not.
 *
 *   const s = FieldsSignal.create();      // inside a user gesture
 *   s.start();                            // static only
 *   s.setSignal(0.8);                     // bring the pulse up
 *   s.stop();
 *
 * Three parts, and each is doing a specific job:
 *
 *   STATIC   Wide filtered noise, slowly breathing. This is the sky. It has to
 *            be genuinely unstructured or the arrival of structure means
 *            nothing — the whole effect is contrast.
 *
 *   PULSE    A low resonant hit: fundamental plus one harmonic, hard attack,
 *            short exponential tail, with a click of noise at the onset. Hollow
 *            rather than musical. A tone would read as music; this has to read
 *            as a machine.
 *
 *   COUNTING The part people remember without knowing why. The pulses arrive in
 *            GROUPS, and the group sizes are the primes: 2, 3, 5, 7, 11, 13...
 *            Nothing in nature counts. That is the entire dramatic point of the
 *            scene, and it costs almost nothing to reproduce.
 */
(function (global) {
  "use strict";

  const PRIMES = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47];

  function create(opts) {
    const AC = global.AudioContext || global.webkitAudioContext;
    if (!AC) return null;
    const ctx = new AC();

    const cfg = Object.assign({
      pulseHz: 92,        // fundamental of the hit
      decay: 0.19,        // how long each pulse rings
      rate: 3.6,          // pulses per second inside a group
      gap: 1.1,           // seconds of silence between groups
      staticLevel: 0.5,   // 0..1
      signalLevel: 0.0,   // 0..1 — raise this to bring the signal in
      counting: true,     // prime groups, or a steady unbroken pulse
      character: "noise", // see PULSES below
      master: 0.5,
    }, opts || {});

    const master = ctx.createGain();
    master.gain.value = cfg.master;
    master.connect(ctx.destination);

    // ── the sky ─────────────────────────────────────────────────────────────
    const noiseBuf = (() => {
      const n = ctx.sampleRate * 3;
      const b = ctx.createBuffer(1, n, ctx.sampleRate);
      const d = b.getChannelData(0);
      for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
      return b;
    })();

    const noise = ctx.createBufferSource();
    noise.buffer = noiseBuf; noise.loop = true;
    const nBand = ctx.createBiquadFilter();
    nBand.type = "bandpass"; nBand.frequency.value = 1500; nBand.Q.value = 0.4;
    const nHi = ctx.createBiquadFilter();
    nHi.type = "highpass"; nHi.frequency.value = 320;
    const nGain = ctx.createGain();
    nGain.gain.value = cfg.staticLevel * 0.16;

    // A very slow wander on the filter, so the static breathes instead of
    // sitting there as a flat hiss. Nothing in the sky is perfectly steady.
    const lfo = ctx.createOscillator();
    lfo.type = "sine"; lfo.frequency.value = 0.07;
    const lfoAmt = ctx.createGain(); lfoAmt.gain.value = 420;
    lfo.connect(lfoAmt).connect(nBand.frequency);

    noise.connect(nBand).connect(nHi).connect(nGain).connect(master);

    // ── the signal ──────────────────────────────────────────────────────────
    const sigGain = ctx.createGain();
    sigGain.gain.value = cfg.signalLevel;
    // Band-limited: it has travelled 26 light years and come out of a radio
    // receiver, not a speaker in the room.
    const sigLo = ctx.createBiquadFilter();
    // 2600 was right for a bass thump and strangles everything else. The
    // noise and carrier characters live well above it.
    sigLo.type = "lowpass"; sigLo.frequency.value = 7000;
    sigGain.connect(sigLo).connect(master);

    /**
     * The pulse itself. Five characters, because I got this wrong first time:
     * my instinct was a low resonant thump, which is a DRUM. What arrives out
     * of a radio telescope is the noise floor itself being modulated — the
     * static pulsing — or a carrier being keyed. Those sound nothing like a
     * kick and everything like a transmission.
     */
    const PULSES = {
      /** The static itself, gated. Bright, hissy, "vvt vvt vvt". */
      noise(at) {
        const nb = ctx.createBufferSource();
        nb.buffer = noiseBuf;
        const bp = ctx.createBiquadFilter();
        bp.type = "bandpass"; bp.frequency.value = cfg.pulseHz * 13; bp.Q.value = 2.2;
        const g = ctx.createGain();
        g.gain.setValueAtTime(0, at);
        g.gain.linearRampToValueAtTime(1.0, at + 0.004);
        g.gain.exponentialRampToValueAtTime(0.0001, at + cfg.decay);
        nb.connect(bp).connect(g).connect(sigGain);
        nb.start(at, Math.random() * 2); nb.stop(at + cfg.decay + 0.02);
      },

      /** Noise through a filter that sweeps up — the classic "whoop". */
      sweep(at) {
        const nb = ctx.createBufferSource();
        nb.buffer = noiseBuf;
        const bp = ctx.createBiquadFilter();
        bp.type = "bandpass"; bp.Q.value = 9;
        bp.frequency.setValueAtTime(cfg.pulseHz * 4, at);
        bp.frequency.exponentialRampToValueAtTime(cfg.pulseHz * 26, at + cfg.decay * 0.85);
        const g = ctx.createGain();
        g.gain.setValueAtTime(0, at);
        g.gain.linearRampToValueAtTime(1.5, at + 0.006);
        g.gain.exponentialRampToValueAtTime(0.0001, at + cfg.decay);
        nb.connect(bp).connect(g).connect(sigGain);
        nb.start(at, Math.random() * 2); nb.stop(at + cfg.decay + 0.02);
      },

      /** A carrier being keyed on and off. Buzzy, electronic, unmistakably
       *  artificial — the sound of something being TRANSMITTED. */
      carrier(at) {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.type = "sawtooth";
        o.frequency.value = cfg.pulseHz * 4.5;
        // ring-modulated by a second oscillator: metallic, inharmonic, wrong
        // in the way electronics are wrong
        const ring = ctx.createOscillator(), rg = ctx.createGain();
        ring.type = "sine"; ring.frequency.value = cfg.pulseHz * 1.7;
        rg.gain.value = 0;
        ring.connect(rg.gain);
        const lp = ctx.createBiquadFilter();
        lp.type = "lowpass"; lp.frequency.value = 2200;
        g.gain.setValueAtTime(0, at);
        g.gain.linearRampToValueAtTime(0.5, at + 0.005);
        g.gain.setValueAtTime(0.5, at + cfg.decay * 0.6);
        g.gain.exponentialRampToValueAtTime(0.0001, at + cfg.decay);
        o.connect(rg).connect(lp).connect(g).connect(sigGain);
        o.start(at); ring.start(at);
        o.stop(at + cfg.decay + 0.02); ring.stop(at + cfg.decay + 0.02);
      },

      /** A carrier with the pitch wobbling fast. The "alien transmission"
       *  warble — a signal that has been through something on the way. */
      warble(at) {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.type = "square";
        o.frequency.value = cfg.pulseHz * 5;
        const fm = ctx.createOscillator(), fmg = ctx.createGain();
        fm.type = "sine"; fm.frequency.value = 34;
        fmg.gain.value = cfg.pulseHz * 2.4;
        fm.connect(fmg).connect(o.frequency);
        const lp = ctx.createBiquadFilter();
        lp.type = "lowpass"; lp.frequency.value = 1800;
        g.gain.setValueAtTime(0, at);
        g.gain.linearRampToValueAtTime(0.32, at + 0.008);
        g.gain.exponentialRampToValueAtTime(0.0001, at + cfg.decay);
        o.connect(lp).connect(g).connect(sigGain);
        o.start(at); fm.start(at);
        o.stop(at + cfg.decay + 0.02); fm.stop(at + cfg.decay + 0.02);
      },

      /** Sparse hard clicks, wide open. A counter, not a rhythm. */
      geiger(at) {
        const nb = ctx.createBufferSource();
        nb.buffer = noiseBuf;
        const hp = ctx.createBiquadFilter();
        hp.type = "highpass"; hp.frequency.value = cfg.pulseHz * 22;
        const g = ctx.createGain();
        g.gain.setValueAtTime(1.4, at);
        g.gain.exponentialRampToValueAtTime(0.0001, at + Math.min(0.05, cfg.decay));
        nb.connect(hp).connect(g).connect(sigGain);
        nb.start(at, Math.random() * 2); nb.stop(at + 0.08);
      },

      /** A radar chirp — a tone sweeping up fast. Narrowband and searching. */
      chirp(at) {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.type = "sine";
        o.frequency.setValueAtTime(cfg.pulseHz * 3, at);
        o.frequency.exponentialRampToValueAtTime(cfg.pulseHz * 16, at + cfg.decay);
        g.gain.setValueAtTime(0, at);
        g.gain.linearRampToValueAtTime(0.45, at + 0.01);
        g.gain.exponentialRampToValueAtTime(0.0001, at + cfg.decay);
        o.connect(g).connect(sigGain);
        o.start(at); o.stop(at + cfg.decay + 0.02);
      },

      /** A whistler: a tone falling away. What lightning sounds like on a
       *  radio receiver, and the most "space" of the lot. */
      whistler(at) {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.type = "sine";
        o.frequency.setValueAtTime(cfg.pulseHz * 20, at);
        o.frequency.exponentialRampToValueAtTime(cfg.pulseHz * 2.2, at + cfg.decay * 1.6);
        g.gain.setValueAtTime(0, at);
        g.gain.linearRampToValueAtTime(0.4, at + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, at + cfg.decay * 1.6);
        o.connect(g).connect(sigGain);
        o.start(at); o.stop(at + cfg.decay * 1.7);
      },

      /** Broadband whoosh — a pulsar sweeping past. Noise, but shaped, so it
       *  reads as rotation rather than as a burst. */
      pulsar(at) {
        const nb = ctx.createBufferSource();
        nb.buffer = noiseBuf;
        const lp = ctx.createBiquadFilter();
        lp.type = "lowpass"; lp.Q.value = 4;
        lp.frequency.setValueAtTime(cfg.pulseHz * 3, at);
        lp.frequency.exponentialRampToValueAtTime(cfg.pulseHz * 18, at + cfg.decay * 0.5);
        lp.frequency.exponentialRampToValueAtTime(cfg.pulseHz * 3, at + cfg.decay);
        const g = ctx.createGain();
        g.gain.setValueAtTime(0, at);
        g.gain.linearRampToValueAtTime(1.7, at + cfg.decay * 0.35);
        g.gain.exponentialRampToValueAtTime(0.0001, at + cfg.decay * 1.1);
        nb.connect(lp).connect(g).connect(sigGain);
        nb.start(at, Math.random() * 2); nb.stop(at + cfg.decay * 1.2);
      },

      /** Harsh amplitude-modulated buzz. Data, not a message. */
      buzz(at) {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.type = "square";
        o.frequency.value = cfg.pulseHz * 2.2;
        const am = ctx.createOscillator(), amg = ctx.createGain();
        am.type = "square"; am.frequency.value = 62; amg.gain.value = 0.5;
        const dep = ctx.createGain(); dep.gain.value = 0.5;
        am.connect(amg).connect(dep.gain);
        const lp = ctx.createBiquadFilter();
        lp.type = "lowpass"; lp.frequency.value = 3000;
        g.gain.setValueAtTime(0, at);
        g.gain.linearRampToValueAtTime(0.3, at + 0.006);
        g.gain.setValueAtTime(0.3, at + cfg.decay * 0.7);
        g.gain.exponentialRampToValueAtTime(0.0001, at + cfg.decay);
        o.connect(dep).connect(lp).connect(g).connect(sigGain);
        o.start(at); am.start(at);
        o.stop(at + cfg.decay + 0.02); am.stop(at + cfg.decay + 0.02);
      },

      /** The first attempt, kept for comparison. It is a drum. */
      thump(at) {
        for (const [mult, gain, det] of [[1, 0.9, 0], [2, 0.28, 3]]) {
          const o = ctx.createOscillator(), g = ctx.createGain();
          o.type = "sine";
          o.frequency.setValueAtTime(cfg.pulseHz * mult + det, at);
          o.frequency.exponentialRampToValueAtTime(cfg.pulseHz * mult * 0.93, at + cfg.decay);
          g.gain.setValueAtTime(0, at);
          g.gain.linearRampToValueAtTime(gain, at + 0.003);
          g.gain.exponentialRampToValueAtTime(0.0001, at + cfg.decay);
          o.connect(g).connect(sigGain);
          o.start(at); o.stop(at + cfg.decay + 0.02);
        }
      },
    };

    function pulse(at) {
      (PULSES[cfg.character] || PULSES.noise)(at);
    }

    // ── the counting ────────────────────────────────────────────────────────
    let timer = null, primeIdx = 0, running = false;
    let onGroup = null;

    function scheduleGroup() {
      if (!running) return;
      const count = cfg.counting ? PRIMES[primeIdx % PRIMES.length] : 8;
      const t0 = ctx.currentTime + 0.05;
      for (let i = 0; i < count; i++) pulse(t0 + i / cfg.rate);
      const span = count / cfg.rate + cfg.gap;
      if (onGroup) onGroup(count, primeIdx);
      primeIdx++;
      timer = setTimeout(scheduleGroup, span * 1000);
    }

    return {
      ctx,
      start() {
        if (running) return;
        running = true;
        if (ctx.state === "suspended") ctx.resume();
        noise.start(); lfo.start();
        scheduleGroup();
      },
      stop() {
        running = false;
        clearTimeout(timer);
        try { noise.stop(); lfo.stop(); } catch (_) {}
        ctx.close();
      },
      /** Bring the signal out of the noise, or bury it again. */
      setSignal(v, seconds) {
        cfg.signalLevel = v;
        sigGain.gain.linearRampToValueAtTime(v, ctx.currentTime + (seconds || 0.3));
      },
      setStatic(v) {
        cfg.staticLevel = v;
        nGain.gain.linearRampToValueAtTime(v * 0.16, ctx.currentTime + 0.2);
      },
      set(k, v) { cfg[k] = v; },
      get(k) { return cfg[k]; },
      onGroup(fn) { onGroup = fn; },
      reset() { primeIdx = 0; },
    };
  }

  // Ready-made combinations. A character on its own is only half of it — the
  // rate and the ring change what it reads as far more than the waveform does.
  const PRESETS = [
    { id: "hiss",     name: "Gated static",      character: "noise",    pulseHz: 92,  decay: 0.14, rate: 3.6, gap: 1.1,
      note: "The sky itself, switching on and off. Closest to a receiver." },
    { id: "hiss-fast",name: "Gated static, fast",character: "noise",    pulseHz: 120, decay: 0.06, rate: 8,   gap: 0.8,
      note: "Same, but urgent. Reads as data rather than a message." },
    { id: "whoop",    name: "Whoop",             character: "sweep",    pulseHz: 70,  decay: 0.22, rate: 2.6, gap: 1.2,
      note: "Noise through a rising filter. Big and analogue." },
    { id: "carrier",  name: "Keyed carrier",     character: "carrier",  pulseHz: 90,  decay: 0.18, rate: 3.2, gap: 1.1,
      note: "A transmitter being switched. Buzzy and deliberate." },
    { id: "warble",   name: "Warble",            character: "warble",   pulseHz: 80,  decay: 0.20, rate: 3.0, gap: 1.2,
      note: "A carrier that has been through something on the way." },
    { id: "chirp",    name: "Radar chirp",       character: "chirp",    pulseHz: 90,  decay: 0.12, rate: 4.0, gap: 1.0,
      note: "Narrowband, rising. Searching rather than speaking." },
    { id: "whistler", name: "Whistler",          character: "whistler", pulseHz: 60,  decay: 0.30, rate: 1.6, gap: 1.4,
      note: "A tone falling away. The most 'space' of the lot." },
    { id: "pulsar",   name: "Pulsar",            character: "pulsar",   pulseHz: 55,  decay: 0.34, rate: 1.8, gap: 1.3,
      note: "A broadband sweep. Rotation, not transmission." },
    { id: "geiger",   name: "Counter",           character: "geiger",   pulseHz: 90,  decay: 0.04, rate: 9,   gap: 0.7,
      note: "Hard sparse clicks. Counting, unmistakably." },
    { id: "buzz",     name: "Data buzz",         character: "buzz",     pulseHz: 110, decay: 0.16, rate: 4.5, gap: 0.9,
      note: "Harsh and modulated. Machine talking to machine." },
    { id: "slow",     name: "Deep and slow",     character: "carrier",  pulseHz: 48,  decay: 0.42, rate: 1.2, gap: 1.8,
      note: "Same carrier, half the speed. Ominous rather than busy." },
    { id: "thump",    name: "Thump (first try)", character: "thump",    pulseHz: 92,  decay: 0.19, rate: 3.6, gap: 1.1,
      note: "What I built first. Included so you can hear why it is wrong." },
  ];

  global.FieldsSignal = { create, PRIMES, PRESETS,
    CHARACTERS: ["noise", "sweep", "carrier", "warble", "chirp",
                 "whistler", "pulsar", "geiger", "buzz", "thump"] };
})(window);
