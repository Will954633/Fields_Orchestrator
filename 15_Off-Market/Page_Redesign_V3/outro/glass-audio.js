/**
 * glass-audio.js — breaking glass, synthesised. No sample, no licence, no bytes.
 *
 *   FieldsGlassAudio.arm();           // inside the click handler, always
 *   FieldsGlassAudio.impact();
 *   FieldsGlassAudio.crackle(900);
 *   FieldsGlassAudio.shatter(3800);
 *
 * Why synthesised rather than a recording:
 *   - Licensing. A commercial site cannot use a stock sample without checking
 *     its terms, and "we found it on a free sounds site" is not a licence.
 *   - Weight. This effect already ships ~2MB of artwork; a decent glass sample
 *     is another 200-400KB.
 *   - Timing. A recording is one fixed shape. This has to land on OUR beats —
 *     impact, a crackle that runs as long as the fracture takes, and a tinkle
 *     that lasts exactly as long as the pieces fall — and those change every
 *     time we retune the animation.
 *
 * What breaking glass actually is, acoustically, and what this reproduces:
 *   - the IMPACT is a broadband noise transient with a very fast decay, plus a
 *     brief low thump as the pane flexes
 *   - a CRACK running is a sparse train of tiny clicks, not a continuous sound
 *   - the TINKLE is the giveaway: dozens of small shards, each a poorly damped
 *     resonator ringing at 1.5-8kHz for 30-250ms, arriving in a dense scatter.
 *     Get the scatter and the decay right and the ear accepts it as glass.
 */
(function (global) {
  "use strict";

  let ctx = null, master = null, muted = false;

  /** Must be called from inside a user gesture — every browser blocks audio
   *  until one. The CTA click is that gesture, which is the ideal case: the
   *  sound is a response to something the reader deliberately did. */
  function arm() {
    if (ctx) { if (ctx.state === "suspended") ctx.resume(); return ctx; }
    const AC = global.AudioContext || global.webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
    master = ctx.createGain();
    master.gain.value = 0.55;
    // A gentle high shelf: glass lives up top, and without a lid the tinkle is
    // fatiguing on laptop speakers, which is where most of this will be heard.
    const shelf = ctx.createBiquadFilter();
    shelf.type = "highshelf"; shelf.frequency.value = 6000; shelf.gain.value = -6;
    master.connect(shelf).connect(ctx.destination);
    return ctx;
  }

  function noiseBuffer(seconds) {
    const n = Math.max(1, Math.floor(ctx.sampleRate * seconds));
    const b = ctx.createBuffer(1, n, ctx.sampleRate);
    const d = b.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
    return b;
  }

  /** A burst of filtered noise: the fracture itself, not the shards. */
  function burst(at, dur, freq, q, gain, type) {
    const src = ctx.createBufferSource();
    src.buffer = noiseBuffer(dur + 0.02);
    const f = ctx.createBiquadFilter();
    f.type = type || "bandpass"; f.frequency.value = freq; f.Q.value = q;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0, at);
    g.gain.linearRampToValueAtTime(gain, at + 0.0015);          // near-instant
    g.gain.exponentialRampToValueAtTime(0.0001, at + dur);
    src.connect(f).connect(g).connect(master);
    src.start(at); src.stop(at + dur + 0.02);
  }

  /** One shard ringing. The pitch drops slightly as it decays, which is what
   *  separates glass from a synthesised bell. */
  function shard(at, freq, dur, gain) {
    const o = ctx.createOscillator();
    o.type = Math.random() < 0.35 ? "triangle" : "sine";
    o.frequency.setValueAtTime(freq, at);
    o.frequency.exponentialRampToValueAtTime(freq * 0.86, at + dur);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0, at);
    g.gain.linearRampToValueAtTime(gain, at + 0.002);
    g.gain.exponentialRampToValueAtTime(0.0001, at + dur);
    // a touch of stereo spread so the cloud has width rather than sitting in
    // the middle of your head
    const pan = ctx.createStereoPanner ? ctx.createStereoPanner() : null;
    if (pan) { pan.pan.value = (Math.random() * 2 - 1) * 0.7; o.connect(g).connect(pan).connect(master); }
    else o.connect(g).connect(master);
    o.start(at); o.stop(at + dur + 0.02);
  }

  function impact() {
    if (!ctx || muted) return;
    const t = ctx.currentTime;
    // the strike: broadband, gone in 90ms
    burst(t, 0.09, 3200, 0.7, 0.9, "highpass");
    burst(t + 0.004, 0.05, 6500, 1.2, 0.55);
    // the pane flexing — felt more than heard, but its absence is felt too
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = "sine";
    o.frequency.setValueAtTime(180, t);
    o.frequency.exponentialRampToValueAtTime(70, t + 0.18);
    g.gain.setValueAtTime(0.55, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.2);
    o.connect(g).connect(master); o.start(t); o.stop(t + 0.22);
    // first few shards thrown at the point of contact
    for (let i = 0; i < 9; i++) {
      shard(t + Math.random() * 0.14, 2200 + Math.random() * 4500,
            0.05 + Math.random() * 0.12, 0.10 + Math.random() * 0.10);
    }
  }

  /** A crack running is a sparse train of clicks, and it accelerates. */
  function crackle(ms) {
    if (!ctx || muted) return;
    const t = ctx.currentTime, dur = ms / 1000;
    const n = Math.round(26 * (dur / 0.9));
    for (let i = 0; i < n; i++) {
      // biased toward the end: the fracture front speeds up as it goes
      const at = t + Math.pow(Math.random(), 0.65) * dur;
      burst(at, 0.012 + Math.random() * 0.02, 1800 + Math.random() * 5200,
            2 + Math.random() * 6, 0.10 + Math.random() * 0.16);
    }
  }

  /** The tinkle. Dense at first, thinning as the last pieces land. */
  function shatter(ms) {
    if (!ctx || muted) return;
    const t = ctx.currentTime, dur = ms / 1000;
    // the pane letting go
    burst(t, 0.22, 2600, 0.6, 0.6, "highpass");
    const n = Math.round(150 * Math.min(2, dur / 3.8));
    for (let i = 0; i < n; i++) {
      // front-loaded: most of the glass goes early, then stragglers
      const k = Math.pow(Math.random(), 1.9);
      const at = t + k * dur;
      const life = 1 - k;
      shard(at, 1500 + Math.random() * 6500,
            0.03 + Math.random() * 0.22,
            (0.05 + Math.random() * 0.12) * (0.45 + life * 0.55));
      // the odd larger piece landing
      if (Math.random() < 0.09) {
        burst(at, 0.05 + Math.random() * 0.08, 700 + Math.random() * 900,
              1.5, 0.10 + Math.random() * 0.10);
      }
    }
  }

  function setMuted(v) {
    muted = !!v;
    if (master) master.gain.value = muted ? 0 : 0.55;
  }

  global.FieldsGlassAudio = {
    arm, impact, crackle, shatter, setMuted,
    get muted() { return muted; },
    get available() { return !!(global.AudioContext || global.webkitAudioContext); },
  };
})(window);
