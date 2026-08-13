/**
 * sirens — a bank of facility / submarine alarms, synthesised.
 *
 * Each is built on the principle of the real device rather than as a variation
 * on a beep, because that is what makes them recognisable:
 *
 *   AOOGA        a motor-driven REED. Harmonically rich and buzzy, pitch rising
 *                then falling as the motor loads. The US Navy dive alarm.
 *   bell         a STRUCK resonator. Inharmonic partials, sharp attack, long
 *                decay — Soviet "kolokol gromkogo boya" battle bell.
 *   wail         a ROTOR. Slow sinusoidal pitch sweep, sustained. Air-raid.
 *   whoop/yelp   swept tones at different rates; yelp is the same shape faster.
 *   slowWhoop    BS 5839 evacuation. A long rise that resets — deliberately
 *                unlike anything natural, which is why it reads as "get out".
 *   hilo         European two-tone. What the sequence uses today.
 *   scram        fast pulsed high tone. Reactor-trip urgency.
 *   klaxon       an electric HORN — square-ish, two detuned drivers beating
 *                against each other. Harsh on purpose.
 *   t3           the international fire temporal pattern: three pulses, pause.
 *   steady       one sustained tone. The most ominous, the least busy.
 *   descend      falling pitch — reads as failure rather than warning.
 *
 * All return a stop() and all route through a caller-supplied gain so the
 * sequence can duck or mute them.
 *
 * Level discipline: these are alarms, and the temptation is to make them loud.
 * A siren on a property site is the single most likely thing to get muted, so
 * every one here is gain-staged to sit UNDER the voice, and the sequence plays
 * two cycles then stops.
 */

const ctxNow = (ctx) => ctx.currentTime;

/** Shared: a band-limited buzzy oscillator with harmonic bite. */
function reedOsc(ctx, dest, { type = "sawtooth", freq = 300, q = 1.2, cutoff = 2600 }) {
  const o = ctx.createOscillator();
  o.type = type;
  o.frequency.value = freq;
  const bp = ctx.createBiquadFilter();
  bp.type = "bandpass";
  bp.frequency.value = cutoff;
  bp.Q.value = q;
  const g = ctx.createGain();
  g.gain.value = 0;
  o.connect(bp).connect(g).connect(dest);
  o.start();
  return { o, g, bp, stop: (t) => { try { o.stop(t); } catch {} } };
}

/** Inharmonic struck resonator — a bell, not a tone. */
function strike(ctx, dest, f0, gain, decay) {
  const t = ctxNow(ctx);
  // Ratios from a real bell's partials: hum, prime, tierce, quint, nominal.
  for (const [r, a] of [[0.5, 0.5], [1, 1], [1.19, 0.55], [1.5, 0.4], [2, 0.62], [2.66, 0.25]]) {
    const o = ctx.createOscillator();
    o.type = "sine";
    o.frequency.value = f0 * r;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(gain * a, t + 0.004);
    g.gain.exponentialRampToValueAtTime(1e-4, t + decay * (1 / (0.6 + r * 0.5)));
    o.connect(g).connect(dest);
    o.start(t);
    o.stop(t + decay + 0.1);
  }
}

export const SIRENS = {
  /* ---- submarine dive alarm ------------------------------------------- */
  aooga(ctx, dest, o = {}) {
    const { cycles = 2, dur = 1.15, lo = 165, hi = 300, gain = 0.20 } = o;
    const t0 = ctxNow(ctx);
    const r = reedOsc(ctx, dest, { type: "sawtooth", freq: lo, q: 0.9, cutoff: 900 });
    // A second, slightly detuned reed. Real klaxons have more than one and the
    // beating between them is a big part of the character.
    const r2 = reedOsc(ctx, dest, { type: "sawtooth", freq: lo * 1.008, q: 0.9, cutoff: 1300 });
    for (let i = 0; i < cycles; i++) {
      const s = t0 + i * (dur + 0.16);
      for (const rr of [r, r2]) {
        // the motor loading up, then falling away: AH-OO-GA
        rr.o.frequency.setValueAtTime(lo, s);
        rr.o.frequency.linearRampToValueAtTime(hi, s + dur * 0.34);
        rr.o.frequency.setValueAtTime(hi, s + dur * 0.62);
        rr.o.frequency.linearRampToValueAtTime(lo * 0.92, s + dur);
        rr.g.gain.setValueAtTime(0.0001, s);
        rr.g.gain.linearRampToValueAtTime(gain, s + 0.06);
        rr.g.gain.setValueAtTime(gain, s + dur * 0.8);
        rr.g.gain.exponentialRampToValueAtTime(0.0001, s + dur);
      }
    }
    const end = t0 + cycles * (dur + 0.16) + 0.2;
    r.stop(end); r2.stop(end);
    return () => { r.stop(ctxNow(ctx)); r2.stop(ctxNow(ctx)); };
  },

  /* ---- Soviet battle bell ---------------------------------------------- */
  bell(ctx, dest, o = {}) {
    const { cycles = 2, rate = 0.17, perCycle = 6, f0 = 620, gain = 0.13 } = o;
    const timers = [];
    let n = 0;
    for (let c = 0; c < cycles; c++)
      for (let i = 0; i < perCycle; i++)
        timers.push(setTimeout(() => strike(ctx, dest, f0, gain, 0.5),
                               (n++ * rate + c * 0.35) * 1000));
    return () => timers.forEach(clearTimeout);
  },

  /* ---- air-raid rotor wail ---------------------------------------------- */
  wail(ctx, dest, o = {}) {
    const { cycles = 2, dur = 2.6, lo = 300, hi = 660, gain = 0.15 } = o;
    const t0 = ctxNow(ctx);
    const r = reedOsc(ctx, dest, { type: "sawtooth", freq: lo, q: 0.7, cutoff: 1500 });
    r.g.gain.setValueAtTime(0.0001, t0);
    r.g.gain.linearRampToValueAtTime(gain, t0 + 0.35);
    for (let i = 0; i < cycles; i++) {
      const s = t0 + i * dur;
      r.o.frequency.setValueAtTime(lo, s);
      r.o.frequency.linearRampToValueAtTime(hi, s + dur * 0.45);
      r.o.frequency.linearRampToValueAtTime(lo, s + dur);
    }
    const end = t0 + cycles * dur;
    r.g.gain.setValueAtTime(gain, end - 0.4);
    r.g.gain.exponentialRampToValueAtTime(0.0001, end);
    r.stop(end + 0.1);
    return () => r.stop(ctxNow(ctx));
  },

  /* ---- whoop / yelp ------------------------------------------------------ */
  whoop(ctx, dest, o = {}) { return sweep(ctx, dest, { rise: 0.52, gap: 0.10, cycles: 4, lo: 380, hi: 1050, gain: 0.14, ...o }); },
  yelp(ctx, dest, o = {})  { return sweep(ctx, dest, { rise: 0.16, gap: 0.03, cycles: 10, lo: 480, hi: 1180, gain: 0.12, ...o }); },
  slowWhoop(ctx, dest, o = {}) { return sweep(ctx, dest, { rise: 1.35, gap: 0.12, cycles: 2, lo: 500, hi: 1200, gain: 0.15, ...o }); },

  /* ---- European two-tone (current) --------------------------------------- */
  hilo(ctx, dest, o = {}) {
    const { cycles = 2, hi = 620, lo = 465, seg = 0.42, gain = 0.16 } = o;
    const t0 = ctxNow(ctx);
    for (let i = 0; i < cycles; i++)
      for (const [k, f] of [[0, hi], [1, lo]]) {
        const t = t0 + i * seg * 2 + k * seg;
        const os = ctx.createOscillator(); os.type = "sawtooth"; os.frequency.setValueAtTime(f, t);
        const bp = ctx.createBiquadFilter(); bp.type = "bandpass"; bp.frequency.value = f * 2; bp.Q.value = 1.4;
        const g = ctx.createGain();
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(gain, t + 0.07);
        g.gain.setValueAtTime(gain, t + seg * 0.66);
        g.gain.exponentialRampToValueAtTime(0.0001, t + seg * 0.95);
        os.connect(bp).connect(g).connect(dest); os.start(t); os.stop(t + seg);
      }
    return () => {};
  },

  /* ---- reactor trip ------------------------------------------------------ */
  scram(ctx, dest, o = {}) {
    const { pulses = 14, rate = 0.13, f = 1180, gain = 0.11 } = o;
    const t0 = ctxNow(ctx);
    for (let i = 0; i < pulses; i++) {
      const t = t0 + i * rate;
      const os = ctx.createOscillator(); os.type = "square"; os.frequency.value = f;
      const lp = ctx.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 3200;
      const g = ctx.createGain();
      g.gain.setValueAtTime(0.0001, t);
      g.gain.linearRampToValueAtTime(gain, t + 0.008);
      g.gain.setValueAtTime(gain, t + rate * 0.45);
      g.gain.exponentialRampToValueAtTime(0.0001, t + rate * 0.72);
      os.connect(lp).connect(g).connect(dest); os.start(t); os.stop(t + rate);
    }
    return () => {};
  },

  /* ---- harsh electric horn ----------------------------------------------- */
  klaxon(ctx, dest, o = {}) {
    const { cycles = 3, on = 0.44, off = 0.20, f = 233, gain = 0.13 } = o;
    const t0 = ctxNow(ctx);
    for (let i = 0; i < cycles; i++) {
      const t = t0 + i * (on + off);
      // two detuned square drivers; the beating IS the horn's character
      for (const det of [0, 3.5]) {
        const os = ctx.createOscillator(); os.type = "square"; os.frequency.value = f + det;
        const bp = ctx.createBiquadFilter(); bp.type = "bandpass"; bp.frequency.value = f * 4.2; bp.Q.value = 0.8;
        const g = ctx.createGain();
        g.gain.setValueAtTime(0.0001, t);
        g.gain.linearRampToValueAtTime(gain, t + 0.03);
        g.gain.setValueAtTime(gain, t + on * 0.8);
        g.gain.exponentialRampToValueAtTime(0.0001, t + on);
        os.connect(bp).connect(g).connect(dest); os.start(t); os.stop(t + on + 0.02);
      }
    }
    return () => {};
  },

  /* ---- fire temporal-3 ---------------------------------------------------- */
  t3(ctx, dest, o = {}) {
    const { sets = 2, f = 900, gain = 0.13 } = o;
    const t0 = ctxNow(ctx);
    for (let s = 0; s < sets; s++)
      for (let i = 0; i < 3; i++) {
        const t = t0 + s * 2.4 + i * 1.0;
        const os = ctx.createOscillator(); os.type = "square"; os.frequency.value = f;
        const lp = ctx.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 2600;
        const g = ctx.createGain();
        g.gain.setValueAtTime(0.0001, t);
        g.gain.linearRampToValueAtTime(gain, t + 0.02);
        g.gain.setValueAtTime(gain, t + 0.44);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.5);
        os.connect(lp).connect(g).connect(dest); os.start(t); os.stop(t + 0.52);
      }
    return () => {};
  },

  /* ---- one sustained tone ------------------------------------------------- */
  steady(ctx, dest, o = {}) {
    const { dur = 2.2, f = 440, gain = 0.13 } = o;
    const t = ctxNow(ctx);
    const os = ctx.createOscillator(); os.type = "sawtooth"; os.frequency.value = f;
    // a touch of vibrato so it is not sterile
    const lfo = ctx.createOscillator(); lfo.frequency.value = 4.5;
    const lfoG = ctx.createGain(); lfoG.gain.value = 2.4;
    lfo.connect(lfoG).connect(os.frequency); lfo.start(t);
    const bp = ctx.createBiquadFilter(); bp.type = "bandpass"; bp.frequency.value = f * 2.6; bp.Q.value = 1.1;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(gain, t + 0.25);
    g.gain.setValueAtTime(gain, t + dur - 0.4);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    os.connect(bp).connect(g).connect(dest);
    os.start(t); os.stop(t + dur + 0.05); lfo.stop(t + dur + 0.05);
    return () => { try { os.stop(); lfo.stop(); } catch {} };
  },

  /* ---- falling: reads as failure, not warning ----------------------------- */
  descend(ctx, dest, o = {}) {
    const { cycles = 2, dur = 1.5, hi = 880, lo = 180, gain = 0.15 } = o;
    const t0 = ctxNow(ctx);
    for (let i = 0; i < cycles; i++) {
      const t = t0 + i * (dur + 0.12);
      const os = ctx.createOscillator(); os.type = "sawtooth";
      os.frequency.setValueAtTime(hi, t);
      os.frequency.exponentialRampToValueAtTime(lo, t + dur);
      const lp = ctx.createBiquadFilter(); lp.type = "lowpass";
      lp.frequency.setValueAtTime(3000, t);
      lp.frequency.exponentialRampToValueAtTime(500, t + dur);
      const g = ctx.createGain();
      g.gain.setValueAtTime(0.0001, t);
      g.gain.linearRampToValueAtTime(gain, t + 0.05);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      os.connect(lp).connect(g).connect(dest); os.start(t); os.stop(t + dur + 0.02);
    }
    return () => {};
  },
};

function sweep(ctx, dest, { rise, gap, cycles, lo, hi, gain }) {
  const t0 = ctxNow(ctx);
  for (let i = 0; i < cycles; i++) {
    const t = t0 + i * (rise + gap);
    const os = ctx.createOscillator(); os.type = "sawtooth";
    os.frequency.setValueAtTime(lo, t);
    os.frequency.exponentialRampToValueAtTime(hi, t + rise);
    const bp = ctx.createBiquadFilter(); bp.type = "bandpass";
    bp.frequency.setValueAtTime(lo * 2, t);
    bp.frequency.exponentialRampToValueAtTime(hi * 1.6, t + rise);
    bp.Q.value = 1.0;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(gain, t + 0.05);
    g.gain.setValueAtTime(gain, t + rise * 0.8);
    g.gain.exponentialRampToValueAtTime(0.0001, t + rise);
    os.connect(bp).connect(g).connect(dest); os.start(t); os.stop(t + rise + 0.02);
  }
  return () => {};
}

export const SIREN_INFO = [
  ["aooga",     "Dive klaxon (AOOGA)",     "US Navy dive alarm. Motor-driven reed — pitch rises then falls as the motor loads. The most 'submarine' of the set."],
  ["klaxon",    "Electric horn",           "Two detuned square drivers beating against each other. Harsh, industrial, unmistakably a machine."],
  ["bell",      "Battle bell",             "Struck resonator with inharmonic partials. Soviet 'kolokol gromkogo boya'. Urgent without being electronic."],
  ["wail",      "Air-raid wail",           "Rotor siren. Slow sustained sweep. The most cinematic; also the longest."],
  ["slowWhoop", "Slow whoop (BS 5839)",    "UK evacuation standard. A long rise that resets — deliberately unlike any natural sound."],
  ["whoop",     "Whoop",                   "Faster repeated sweep. Reads as active emergency rather than warning."],
  ["yelp",      "Yelp",                    "Whoop at speed. Panic register — probably too much here."],
  ["scram",     "Reactor trip",            "Fast pulsed high tone. Clinical urgency; the most 'control room'."],
  ["hilo",      "Two-tone (current)",      "European hi-lo. What the sequence uses now."],
  ["t3",        "Fire temporal-3",         "Three pulses then pause — the international fire pattern. Very recognisable, maybe too domestic."],
  ["steady",    "Steady tone",             "One sustained note with slight vibrato. The most ominous and least busy."],
  ["descend",   "Descending",              "Falling pitch. Reads as something failing rather than warning — pairs oddly well with the power dying."],
];
