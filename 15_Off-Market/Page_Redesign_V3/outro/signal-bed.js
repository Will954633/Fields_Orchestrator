/**
 * signal-bed.js — the Cassini recording, under the final scene.
 *
 * Saturn's radio emissions, recorded by Cassini's plasma-wave instrument and
 * shifted into hearing range. NASA audio is public domain, so unlike the film's
 * own signal there is nothing to licence. It plays under the code rain while the
 * ship's computer reads the build sequence.
 *
 *   FieldsSignalBed.fetch();                 // at page load — network only
 *   FieldsSignalBed.arm(ctx);                // inside the gesture — decode
 *   FieldsSignalBed.start({ fadeIn: 1.5 });  // 1s after the rain starts
 *   FieldsSignalBed.duck(0.5, 0.25);         // under each spoken line
 *   FieldsSignalBed.stop(0.2);               // on "Construction completed."
 *
 * Two decisions worth knowing about:
 *
 *   WEB AUDIO, NOT <audio>. An <audio> element's `volume` can only be stepped
 *   from a timer, which makes a 1.5s fade audibly steppy. A GainNode ramp is
 *   sample-accurate. It also means the fade-out on the last line is a true
 *   200ms ramp rather than a hard cut, which would click on a bed this loud.
 *
 *   DECODED, NOT STREAMED. The clip loops seamlessly as an AudioBuffer, and the
 *   sequence timing has drifted repeatedly during this build — the clip is 13.2s
 *   and the scene currently needs ~11.9s of it, which is too little headroom to
 *   assume. Looping means a slow device can never run the bed out.
 */
(function (global) {
  "use strict";

  // Same reason as crack.js: this runs from the demo folder and from the deck.
  const URL_ = (window.FIELDS_OUTRO_BASE || "") + "../audio/nasa/saturn-radio.mp3";

  let raw = null;          // ArrayBuffer, fetched at page load
  let buf = null;          // decoded, once there is a context
  let ctx = null, bus = null, src = null;
  let level = 1.0, ducked = false;

  /** Network at load time, so the gesture only has to decode. */
  function fetch_() {
    if (raw || !global.fetch) return;
    global.fetch(URL_)
      .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(r.status))))
      .then((b) => { raw = b; })
      .catch(() => { raw = null; });      // silence is an acceptable failure here
  }

  /** Must be given a context created inside a user gesture. */
  function arm(context) {
    if (!context) return;
    ctx = context;
    if (!bus) {
      bus = ctx.createGain();
      bus.gain.value = 0;
      // Straight to the destination, NOT through the glass master — that bus
      // carries a -6dB shelf above 6kHz tuned for the tinkle, which would take
      // the top off a recording whose whole character is up there.
      bus.connect(ctx.destination);
    }
    if (buf || !raw) return;
    // decodeAudioData is callback-style on older Safari, hence both forms.
    try {
      const p = ctx.decodeAudioData(raw.slice(0), (b) => { buf = b; }, () => {});
      if (p && p.then) p.then((b) => { buf = b; }).catch(() => {});
    } catch (_) {}
  }

  function start(opts) {
    const o = opts || {};
    level = o.level === undefined ? 1.0 : o.level;
    const fade = o.fadeIn === undefined ? 1.5 : o.fadeIn;
    if (!ctx || !bus || !buf || src) return false;
    src = ctx.createBufferSource();
    src.buffer = buf;
    src.loop = true;                      // insurance, see the header note
    src.connect(bus);
    const t = ctx.currentTime;
    // From effectively silent, not from zero: an exponential ramp cannot start
    // at 0, and a linear one from 0 has a duller knee than this.
    bus.gain.cancelScheduledValues(t);
    bus.gain.setValueAtTime(0.0015, t);
    bus.gain.exponentialRampToValueAtTime(level, t + fade);
    src.start();
    return true;
  }

  /** Pull it down under a spoken line, then let it back up. */
  function duck(to, seconds) {
    if (!ctx || !bus || !src) return;
    ducked = true;
    ramp(level * (to === undefined ? 0.5 : to), seconds === undefined ? 0.25 : seconds);
  }
  function unduck(seconds) {
    if (!ctx || !bus || !src || !ducked) return;
    ducked = false;
    ramp(level, seconds === undefined ? 0.4 : seconds);
  }
  function ramp(v, seconds) {
    const t = ctx.currentTime;
    bus.gain.cancelScheduledValues(t);
    bus.gain.setValueAtTime(Math.max(0.0015, bus.gain.value), t);
    bus.gain.exponentialRampToValueAtTime(Math.max(0.0015, v), t + seconds);
  }

  /** Short fade rather than a hard stop — a bed this loud clicks if cut. */
  function stop(seconds) {
    if (!ctx || !bus || !src) return;
    const s = seconds === undefined ? 0.2 : seconds;
    const t = ctx.currentTime, node = src;
    src = null; ducked = false;
    bus.gain.cancelScheduledValues(t);
    bus.gain.setValueAtTime(Math.max(0.0015, bus.gain.value), t);
    bus.gain.exponentialRampToValueAtTime(0.0015, t + s);
    try { node.stop(t + s + 0.02); } catch (_) {}
  }

  global.FieldsSignalBed = {
    fetch: fetch_, arm, start, duck, unduck, stop,
    get playing() { return !!src; },
    get ready() { return !!buf; },
  };
})(window);
