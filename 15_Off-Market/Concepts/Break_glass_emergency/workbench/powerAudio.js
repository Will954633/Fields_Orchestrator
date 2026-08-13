/**
 * powerAudio — the sound of mains supply failing. Synthesised, no assets.
 *
 * Pairs with powerFailure.js. The two are locked together by construction: the
 * audio gain is driven from the SAME `brightnessAt()` envelope that drives the
 * light, so the hum sags exactly when the lamps sag. They cannot drift.
 *
 * ── The physics, and where the cinematic version departs from it ───────────
 *
 * MAINS HUM IS 100Hz, NOT 50Hz. A transformer or ballast core is squeezed by
 * magnetostriction twice per cycle — once per polarity peak — so the acoustic
 * fundamental is DOUBLE mains, exactly like the luminous ripple. The 50Hz
 * component you do hear is mechanical looseness and harmonic leakage, and it
 * sits below the 100Hz. This is the same doubling that makes lamps ripple at
 * 100Hz, which is a pleasing coherence: you are hearing and seeing the same
 * physical effect.
 *
 * ⚠ GRID FREQUENCY DOES NOT SLIDE DOWN. The descending "power dying" whine
 * everyone expects is NOT the mains. Grid frequency is held at 50Hz by inertia
 * across the whole network — during a brownout the VOLTAGE sags while the
 * frequency stays put, so a real mains failure gets quieter and dirtier, not
 * lower in pitch. The falling pitch belongs to rotating machinery spinning down
 * or a CRT flyback losing drive. It is included below as `spindown` because it
 * is what an audience reads as "power dying", but it is labelled cinematic, not
 * literal, and it can be switched off.
 *
 * ── The trick that makes it land ──────────────────────────────────────────
 *
 * You cannot hear power go OFF unless you first heard it ON. The `hum` and
 * `roomTone` layers fade in when the glass breaks, so by the time the lever is
 * pulled the ear has habituated to them — and their removal is the event.
 * Silence is the payload. Without that setup the cut is just a thud.
 *
 * All layers are individually switchable so they can be auditioned in the
 * workbench. AudioContext is only ever created inside a user gesture.
 */
import { brightnessAt, totalDurationMs, POWER_DEFAULTS, MAINS_HZ } from "./powerFailure.js";

export const HUM_HZ = MAINS_HZ * 2;   // magnetostriction: twice mains

export const AUDIO_DEFAULTS = {
  master: 0.5,
  hum: true,        // 100Hz core hum + harmonics — the bed
  roomTone: true,   // broadband HVAC/fridge bed; its REMOVAL is the moment
  ballast: true,    // fluorescent buzz + restrike stutter
  arc: true,        // contactor crackle as contacts part
  clunk: true,      // breaker/contactor drop — the mechanical event
  spindown: true,   // ⚠ cinematic, not literal — see note above
};

/**
 * Start the "power is on" bed. Call when the glass breaks.
 * @returns {{ stop:(f?:number)=>void, ctx:AudioContext, bus:GainNode }}
 */
export function startMainsBed(opts = {}) {
  const o = { ...AUDIO_DEFAULTS, ...opts };
  const ctx = opts.ctx ?? new (window.AudioContext || window.webkitAudioContext)();
  const now = ctx.currentTime;

  const bus = ctx.createGain();
  bus.gain.setValueAtTime(0, now);
  bus.gain.linearRampToValueAtTime(o.master, now + 1.4);   // habituate slowly
  bus.connect(ctx.destination);

  const nodes = [];

  if (o.hum) {
    // 100Hz fundamental with 50Hz leakage and odd harmonics. Relative gains
    // chosen so the 100Hz dominates, as it does in a real core.
    const hum = ctx.createGain();
    hum.gain.value = 0.16;
    hum.connect(bus);
    for (const [f, g] of [[MAINS_HZ, 0.35], [HUM_HZ, 1.0], [HUM_HZ * 2, 0.28], [HUM_HZ * 3, 0.12]]) {
      const osc = ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.value = f;
      const gn = ctx.createGain();
      gn.gain.value = g;
      osc.connect(gn).connect(hum);
      osc.start();
      nodes.push(osc);
    }
  }

  if (o.roomTone) {
    // Broadband bed. Barely audible on its own; you notice it when it stops.
    const n = ctx.createBufferSource();
    const len = ctx.sampleRate * 2;
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * 0.5;
    n.buffer = buf; n.loop = true;
    const lp = ctx.createBiquadFilter();
    lp.type = "lowpass"; lp.frequency.value = 420;
    const g = ctx.createGain(); g.gain.value = 0.05;
    n.connect(lp).connect(g).connect(bus);
    n.start();
    nodes.push(n);
  }

  return {
    ctx, bus,
    stop(fade = 0.25) {
      const t = ctx.currentTime;
      bus.gain.cancelScheduledValues(t);
      bus.gain.setValueAtTime(bus.gain.value, t);
      bus.gain.exponentialRampToValueAtTime(1e-4, t + fade);
      setTimeout(() => nodes.forEach((n) => { try { n.stop(); } catch {} }), (fade + 0.1) * 1000);
    },
  };
}

/**
 * Play the failure. Drives the bed's gain from the light envelope, then layers
 * the mechanical events on top.
 * @param bed  return value of startMainsBed()
 * @returns {() => void} cancel
 */
export function playPowerFailure(bed, opts = {}) {
  const o = { ...AUDIO_DEFAULTS, ...POWER_DEFAULTS, ...opts };
  const { ctx, bus } = bed;
  const t0 = ctx.currentTime;
  const dur = totalDurationMs(o);

  // ---- the bed follows the LIGHT, sample-for-sample ------------------------
  // Scheduled rather than rAF-driven so it stays accurate if the main thread
  // stalls — audio glitches are far more noticeable than a dropped frame.
  bus.gain.cancelScheduledValues(t0);
  const STEP = 16;
  for (let t = 0; t <= dur; t += STEP) {
    const b = brightnessAt(t, o);
    bus.gain.linearRampToValueAtTime(Math.max(1e-4, o.master * b), t0 + t / 1000);
  }

  const timers = [];
  const at = (ms, fn) => timers.push(setTimeout(fn, ms));

  const noiseBurst = (dur_, type, freq, q, g0, g1, dest = ctx.destination) => {
    const n = Math.floor(ctx.sampleRate * dur_);
    const buf = ctx.createBuffer(1, n, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
    const s = ctx.createBufferSource(); s.buffer = buf;
    const f = ctx.createBiquadFilter(); f.type = type; f.frequency.value = freq; f.Q.value = q;
    const g = ctx.createGain();
    g.gain.setValueAtTime(g0, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(Math.max(g1, 1e-4), ctx.currentTime + dur_);
    s.connect(f).connect(g).connect(dest); s.start();
  };

  // ---- restrike: the ballast tries to reignite ----------------------------
  if (o.ballast) {
    at(o.sagMs, () => {
      for (let i = 0; i < 3; i++)
        setTimeout(() => noiseBurst(0.05, "bandpass", 1800 + Math.random() * 900, 6, 0.16, 0.001), i * 42);
    });
  }

  // ---- arc: contacts parting under load ----------------------------------
  if (o.arc) {
    const start = o.sagMs + o.restrikeMs + o.brownoutMs * 0.6;
    at(start, () => {
      for (let i = 0; i < 7; i++)
        setTimeout(() => noiseBurst(0.02 + Math.random() * 0.03, "highpass", 3200, 1, 0.1, 0.001), Math.random() * 260);
    });
  }

  // ---- spindown: the cinematic falling whine ------------------------------
  // ⚠ Grid frequency does NOT do this. Rotating machinery and CRT flybacks do.
  if (o.spindown) {
    at(o.sagMs + o.restrikeMs + o.brownoutMs, () => {
      const osc = ctx.createOscillator(), g = ctx.createGain();
      const t = ctx.currentTime, len = (o.collapseMs + o.filamentMs) / 1000;
      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(HUM_HZ * 1.5, t);
      osc.frequency.exponentialRampToValueAtTime(28, t + len);
      const lp = ctx.createBiquadFilter();
      lp.type = "lowpass";
      lp.frequency.setValueAtTime(2200, t);
      lp.frequency.exponentialRampToValueAtTime(220, t + len);
      g.gain.setValueAtTime(0.12, t);
      g.gain.exponentialRampToValueAtTime(1e-4, t + len);
      osc.connect(lp).connect(g).connect(ctx.destination);
      osc.start(); osc.stop(t + len + 0.05);
    });
  }

  // ---- clunk: the breaker drops. The mechanical full-stop. ----------------
  if (o.clunk) {
    at(o.sagMs + o.restrikeMs + o.brownoutMs + o.collapseMs, () => {
      noiseBurst(0.14, "lowpass", 380, 1, 0.4, 0.001);
      const osc = ctx.createOscillator(), g = ctx.createGain();
      const t = ctx.currentTime;
      osc.type = "sine";
      osc.frequency.setValueAtTime(72, t);
      osc.frequency.exponentialRampToValueAtTime(40, t + 0.3);
      g.gain.setValueAtTime(0.34, t);
      g.gain.exponentialRampToValueAtTime(1e-4, t + 0.3);
      osc.connect(g).connect(ctx.destination);
      osc.start(); osc.stop(t + 0.32);
    });
  }

  return () => timers.forEach(clearTimeout);
}
