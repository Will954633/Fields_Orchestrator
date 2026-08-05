/* ============================================================================
   fridgeAudio.js — the door sounds, synthesised. No audio files.

   Why synthesised rather than a sample: zero bytes over the wire, no licensing,
   tunable without a re-export, and it matches how the rest of this site does
   sound (public/off-market-v3/glass-audio.js, components/WhaleMoment/
   whaleAudio.ts, BreakGlass/powerAudio.js all synthesise).

   A fridge door is three distinct events, and getting the ORDER right matters
   more than the timbre:

     opening  the magnetic gasket peels off the frame (a filtered noise "shhk"
              that starts broad and closes down), then the door mass releases
              (a soft low thump). Peel first, thump second.
     closing  the reverse and heavier: the door swings in and lands (a hard
              low-frequency impact + a click transient where the plastic meets
              the frame), and THEN the gasket snatches shut behind it.
     resting  a compressor hum, very quiet, only while the door is open.

   ⚠ USER ACTIVATION — read before touching this.
   On Android Chrome, `touchstart`/`pointerdown` grant NO user activation: a
   finger going down may be the start of a scroll, so the browser withholds
   activation until the gesture resolves as a tap. Activation lands on
   `pointerup` / `touchend` / `click`. A context armed without activation
   reports state:"running" and emits SILENCE — which is the bug still open on
   the V3 neon sign after five rounds of fixes (see
   Page_Redesign_V3/NEON_SOUND_UNSOLVED.md).

   Consequences enforced below:
     - arm() is only ever called from a real pointerup/click handler
     - we ask navigator.userActivation.isActive rather than trusting the caller
     - THE AUTO-OPEN AT 0.8s IS SILENT, and must stay silent: no gesture has
       happened, so there is no activation to honour. Sound belongs to the pull.
     - headless Chrome grants activation cold and has no speaker, so none of
       this is verifiable without a real handset.
   ========================================================================== */
(function (global) {
  'use strict';

  var ctx = null;
  var master = null;
  var hum = null;
  var enabled = true;

  function hasActivation() {
    try {
      if (navigator.userActivation) return !!navigator.userActivation.isActive;
    } catch (e) {}
    return true;                        // older engines: trust the caller
  }

  /* Create or revive the context. MUST be called synchronously inside a
     gesture handler. Also rebuilds anything we believed in that is not
     actually running. */
  function arm() {
    if (!enabled) return false;
    try {
      var AC = global.AudioContext || global.webkitAudioContext;
      if (!AC) return false;
      if (!ctx || ctx.state === 'closed') {
        ctx = new AC();
        master = ctx.createGain();
        master.gain.value = 0.9;
        master.connect(ctx.destination);
      }
      if (ctx.state !== 'running') ctx.resume();
      return ctx.state === 'running' || hasActivation();
    } catch (e) { return false; }
  }

  function noiseBuffer(seconds) {
    var n = Math.floor(ctx.sampleRate * seconds);
    var b = ctx.createBuffer(1, n, ctx.sampleRate);
    var d = b.getChannelData(0);
    for (var i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
    return b;
  }

  /* A band-passed noise burst — the gasket. sweep moves the filter over the
     life of the burst, which is what makes it read as rubber peeling off metal
     rather than as static. */
  function peel(t0, dur, f0, f1, q, gain) {
    var src = ctx.createBufferSource();
    src.buffer = noiseBuffer(dur + 0.05);
    var bp = ctx.createBiquadFilter();
    bp.type = 'bandpass';
    bp.Q.value = q;
    bp.frequency.setValueAtTime(f0, t0);
    bp.frequency.exponentialRampToValueAtTime(Math.max(40, f1), t0 + dur);
    var g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(gain, t0 + dur * 0.16);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    src.connect(bp); bp.connect(g); g.connect(master);
    src.start(t0); src.stop(t0 + dur + 0.05);
  }

  /* Low-frequency body thump. A door is heavy and mostly inaudible above
     200Hz — the pitch drop is the mass settling. */
  function thump(t0, f0, f1, dur, gain) {
    var o = ctx.createOscillator();
    o.type = 'sine';
    o.frequency.setValueAtTime(f0, t0);
    o.frequency.exponentialRampToValueAtTime(f1, t0 + dur * 0.8);
    var g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(gain, t0 + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(g); g.connect(master);
    o.start(t0); o.stop(t0 + dur + 0.02);
  }

  /* The hard contact transient — plastic on plastic. Very short, high-passed. */
  function click(t0, gain) {
    var src = ctx.createBufferSource();
    src.buffer = noiseBuffer(0.05);
    var hp = ctx.createBiquadFilter();
    hp.type = 'highpass';
    hp.frequency.value = 1400;
    var g = ctx.createGain();
    g.gain.setValueAtTime(gain, t0);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.045);
    src.connect(hp); hp.connect(g); g.connect(master);
    src.start(t0); src.stop(t0 + 0.06);
  }

  var A = {
    /* Call from a gesture handler. Returns false if audio is genuinely
       unavailable, so the caller can stop pretending it worked. */
    arm: arm,

    available: function () { return !!ctx && ctx.state === 'running'; },

    enable: function (on) { enabled = !!on; if (!on) A.hum(false); },

    /* gasket peels, then the door lets go */
    open: function () {
      if (!ctx || !enabled) return;
      var t = ctx.currentTime + 0.01;
      peel(t, 0.20, 1500, 320, 3.2, 0.16);   // the shhk of the seal releasing
      peel(t + 0.05, 0.13, 520, 190, 5.5, 0.11);
      thump(t + 0.07, 92, 46, 0.20, 0.20);   // mass releasing
    },

    /* the door lands, then the gasket snatches it shut */
    close: function () {
      if (!ctx || !enabled) return;
      var t = ctx.currentTime + 0.01;
      thump(t, 130, 42, 0.30, 0.42);         // impact — the heaviest sound here
      click(t + 0.004, 0.09);                // frame contact
      peel(t + 0.02, 0.17, 900, 150, 4.0, 0.13);  // seal sucking in behind it
      thump(t + 0.10, 58, 34, 0.24, 0.14);   // the low settle
    },

    /* compressor drone while the door is open. Deliberately near-inaudible —
       it should register as "the room is not silent", never as a tone. */
    hum: function (on) {
      if (!ctx || !enabled) { return; }
      if (on && !hum) {
        var o = ctx.createOscillator();
        o.type = 'sawtooth';
        o.frequency.value = 99.5;
        var lp = ctx.createBiquadFilter();
        lp.type = 'lowpass';
        lp.frequency.value = 220;
        var g = ctx.createGain();
        g.gain.setValueAtTime(0.0001, ctx.currentTime);
        g.gain.linearRampToValueAtTime(0.014, ctx.currentTime + 1.2);
        o.connect(lp); lp.connect(g); g.connect(master);
        o.start();
        hum = { o: o, g: g };
      } else if (!on && hum) {
        var h = hum; hum = null;
        h.g.gain.cancelScheduledValues(ctx.currentTime);
        h.g.gain.setValueAtTime(h.g.gain.value, ctx.currentTime);
        h.g.gain.linearRampToValueAtTime(0.0001, ctx.currentTime + 0.5);
        setTimeout(function () { try { h.o.stop(); } catch (e) {} }, 700);
      }
    },

    state: function () {
      return {
        ctx: ctx ? ctx.state : 'none',
        activation: hasActivation(),
        enabled: enabled,
        humming: !!hum
      };
    }
  };

  global.fridgeAudio = A;
})(window);
