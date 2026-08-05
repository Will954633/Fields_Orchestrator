/* ============================================================================
   fridgeAudio.js — Will's own fridge, recorded.

   Three real recordings (assets/source/, processed by assets/build_audio.sh):
     fridge-open.m4a    0.72s  the gasket peeling off the frame
     fridge-close.m4a   0.72s  the door landing and the seal snatching shut
     fridge-hum.m4a     4.00s  the compressor, as a SEAMLESS loop

   ── Timing: the sounds are scheduled, not fired ──────────────────────────
   Both clips have their transient somewhere in the middle, and the door takes
   over a second to move. Playing either one on the tap would desynchronise it
   from the picture. Measured, then aligned:

     open   peel peaks 0.130s into the clip; the door breaks its seal at
            0.224s (solved from cubic-bezier(.42,.03,.28,1) over 1.70s)
            -> start the clip at 0.094s

     close  impact peaks 0.060s into the clip; the door SEATS at 1.015s
            (cubic-bezier(.42,.02,.86,.62) over 1.02s)
            -> start the clip at 0.955s

   Fire the close sound on the tap instead and you hear the slam a full second
   before the door arrives. That is the whole reason these are numbers and not
   guesses — change either CSS easing and these must be recomputed.

   ── The hum ───────────────────────────────────────────────────────────────
   Runs continuously and at a CONSTANT level once audio is available, open or
   shut — a fridge does not stop when you close the door, and it does not get
   louder either. An earlier version ducked 0.10 -> 0.28 with the door on the
   theory that you hear into the cabinet; at these levels that read as the
   sound fading in and out. A room tone that moves stops being a room tone.

   ⚠ It CANNOT start before the visitor touches the screen. That is browser
   autoplay policy, not a bug and not something to work around: audible sound
   without user activation is blocked everywhere. We create and decode up front
   so the context is warm, then resume on the first real gesture — so the hum
   begins the instant they touch, with no load delay.

   ⚠ USER ACTIVATION — the rest of the rule.
   On Android Chrome `touchstart`/`pointerdown` grant NO activation: a finger
   going down may be the start of a scroll, so the browser withholds it until
   the gesture resolves as a tap. It lands on pointerup / touchend / click. A
   context armed without activation reports state:"running" and emits SILENCE —
   the bug still open on the V3 neon sign after five rounds. Hence: arm() only
   from pointerup, and ask navigator.userActivation rather than trusting
   ourselves. This is also why the door no longer opens by itself: the first
   opening is the moment that matters, and on a timer it was guaranteed silent.
   Headless Chrome grants activation cold and has no speaker, so none of this
   is verifiable without a real handset.
   ========================================================================== */
(function (global) {
  'use strict';

  var BASE = 'assets/';
  var CLIPS = { open: 'fridge-open.m4a', close: 'fridge-close.m4a',
                latch: 'fridge-latch.m4a', hum: 'fridge-hum.m4a' };

  /* Measured alignment — see header. Seconds after the tap. */
  var OPEN_AT  = 0.094;
  var CLOSE_AT = 0.955;

  /* ONE constant level. It used to duck between 0.10 shut and 0.28 open —
     "hearing into the cabinet" — which was a 2.8x swing over ~1s and read, at
     these low levels, as the sound fading in and out rather than as a room
     tone. A fridge in a kitchen is a steady presence; anything that moves draws
     attention to itself. Only the initial fade-in, mute and tab-hide ever
     change it now. */
  var HUM      = 0.17;
  var ONESHOT  = 0.85;

  var ctx = null, master = null, humGain = null, oneGain = null;
  var buf = {}, humSrc = null, pending = null;
  var enabled = true, muted = false, loading = null;

  function hasActivation() {
    try {
      if (navigator.userActivation) return !!navigator.userActivation.isActive;
    } catch (e) {}
    return true;                            // older engines: trust the caller
  }

  /* Build the graph and decode. Safe to call on page load — a context created
     without a gesture simply starts suspended, and decodeAudioData works fine
     while suspended. Doing it early is what makes the hum instant on first
     touch instead of a fetch away. */
  function preload() {
    if (loading) return loading;
    var AC = global.AudioContext || global.webkitAudioContext;
    if (!AC) return (loading = Promise.reject(new Error('no WebAudio')));
    try { ctx = new AC(); } catch (e) { return (loading = Promise.reject(e)); }

    master  = ctx.createGain(); master.gain.value = 1;
    humGain = ctx.createGain(); humGain.gain.value = 0;
    oneGain = ctx.createGain(); oneGain.gain.value = ONESHOT;
    humGain.connect(master); oneGain.connect(master); master.connect(ctx.destination);

    loading = Promise.all(Object.keys(CLIPS).map(function (k) {
      return fetch(BASE + CLIPS[k])
        .then(function (r) { if (!r.ok) throw new Error(CLIPS[k] + ' ' + r.status); return r.arrayBuffer(); })
        .then(function (ab) {
          return new Promise(function (res, rej) {
            // callback form: Safari still doesn't reliably return a promise here
            ctx.decodeAudioData(ab, function (b) { buf[k] = b; res(); }, rej);
          });
        });
    }));
    return loading;
  }

  function startHum() {
    if (humSrc || !buf.hum || !ctx) return;
    humSrc = ctx.createBufferSource();
    humSrc.buffer = buf.hum;
    humSrc.loop = true;              // buffer is crossfade-joined; no click
    humSrc.connect(humGain);
    humSrc.start(0);
  }

  function ramp(g, to, secs) {
    if (!ctx) return;
    var t = ctx.currentTime;
    g.gain.cancelScheduledValues(t);
    g.gain.setValueAtTime(g.gain.value, t);
    g.gain.linearRampToValueAtTime(to, t + secs);
  }

  function fire(name, at) {
    if (!ctx || !buf[name] || !enabled || muted) return null;
    var s = ctx.createBufferSource();
    s.buffer = buf[name];
    s.connect(oneGain);
    s.start(ctx.currentTime + at);
    return s;
  }

  var A = {
    preload: preload,

    /* Call ONLY from a real pointerup/click handler. */
    arm: function () {
      if (!enabled) return false;
      if (!ctx) preload();
      if (!ctx) return false;
      if (ctx.state !== 'running') ctx.resume();
      startHum();
      /* only ever ramped once, on arming — after this the bed is constant */
      if (!muted && humGain.gain.value < HUM * 0.9) ramp(humGain, HUM, 1.2);
      return ctx.state === 'running' || hasActivation();
    },

    available: function () { return !!ctx && ctx.state === 'running'; },

    /* door opened: peel. The bed is NOT touched — it just keeps running. */
    open: function () {
      if (pending) { try { pending.stop(); } catch (e) {} pending = null; }
      fire('open', OPEN_AT);
    },

    /* the secret button. Fires immediately — a button click has no travel to
       wait for, unlike the door. */
    latch: function () { fire('latch', 0); },

    /* door closed: the impact is scheduled to land as the door seats */
    close: function () {
      if (pending) { try { pending.stop(); } catch (e) {} }
      pending = fire('close', CLOSE_AT);
    },

    /* the hum never stops on its own — a fridge doesn't. Only mute or a
       backgrounded tab silences it. */
    setMuted: function (on) {
      muted = !!on;
      ramp(humGain, muted ? 0 : HUM, 0.25);
      return muted;
    },
    isMuted: function () { return muted; },

    /* tab hidden: drop the bed to zero but leave the source running, so coming
       back is instant and we never leave a fridge humming behind a dead tab */
    suspend: function () {
      if (!ctx) return;
      ramp(humGain, 0, 0.2);
      setTimeout(function () { if (ctx && ctx.state === 'running') ctx.suspend(); }, 250);
    },
    wake: function () {
      if (!ctx || muted) return;
      if (ctx.state !== 'running') ctx.resume();
      ramp(humGain, HUM, 0.6);
    },

    enable: function (on) { enabled = !!on; if (!on) ramp(humGain, 0, 0.1); },

    state: function () {
      return {
        ctx: ctx ? ctx.state : 'none',
        decoded: Object.keys(buf),
        humming: !!humSrc,
        humGain: humGain ? +humGain.gain.value.toFixed(3) : null,
        activation: hasActivation(),
        muted: muted, enabled: enabled
      };
    }
  };

  global.fridgeAudio = A;
})(window);
