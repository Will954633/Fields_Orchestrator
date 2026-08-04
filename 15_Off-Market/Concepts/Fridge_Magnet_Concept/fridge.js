/* ============================================================================
   fridge.js — decides WHEN the door opens. Nothing else.

   The door, the light, the shelves and the options are all CSS + HTML and work
   with this file deleted. That is the point: on the real site the sequence has
   to run before 219 KB of app JavaScript has necessarily landed over a kitchen
   4G connection.

   Deliberately plain .js, no build step — so this exact file can be served
   from public/fridge/ in production and loaded here at the concepts URL, and
   prototype and production cannot drift. Same reason src/components/BreakGlass
   keeps its 3,000 lines of behaviour in public/ rather than in .tsx.
   ========================================================================== */
(function () {
  'use strict';

  var fridge = document.getElementById('fridge');
  if (!fridge) { console.warn('[fridge] no #fridge element — nothing to do'); return; }

  var reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) return;               // CSS already renders it open

  var opened = false;
  var t0 = performance.now();
  var timer = null;

  function open(method) {
    if (opened) return;
    opened = true;
    clearTimeout(timer);
    fridge.classList.add('is-open');
    teardown();

    // Haptic on a real pull. Android only; iOS ignores it silently.
    if (method === 'pulled' && navigator.vibrate) { try { navigator.vibrate(12); } catch (e) {} }

    emit('fridge_open', {
      method: method,                                  // 'pulled' | 'auto'
      ms_to_open: Math.round(performance.now() - t0)   // 0 for auto
    });
  }

  /* ── Any touch anywhere opens it ────────────────────────────────────────
     Not a handle hitbox. Asking someone to find a 40px handle on a phone in a
     kitchen is a failure mode with no upside.

     Bound on pointerup / touchend / click, NEVER pointerdown: on Android
     Chrome a finger going down may be the start of a scroll, so the browser
     withholds user activation until the gesture resolves as a tap. Anything
     that later wants to make a sound needs that activation, and latching off
     pointerdown is exactly the bug still open on the V3 neon sign.
     See memory web_audio_user_activation_touch.                            */
  function onPointerUp() { open('pulled'); }
  function onKey(e) { if (e.key === 'Enter' || e.key === ' ') open('pulled'); }

  function teardown() {
    document.removeEventListener('pointerup', onPointerUp);
    document.removeEventListener('touchend', onPointerUp);
    document.removeEventListener('keydown', onKey);
  }

  document.addEventListener('pointerup', onPointerUp, { passive: true });
  document.addEventListener('touchend', onPointerUp, { passive: true });
  document.addEventListener('keydown', onKey);

  /* ── Auto-open, so nobody is left staring at a closed fridge ─────────── */
  timer = setTimeout(function () { t0 = performance.now(); open('auto'); }, 800);

  /* ── Measurement ──────────────────────────────────────────────────────
     On the site this becomes phCapture() from src/utils/posthog.ts.
     Names are namespaced fridge_* on purpose — reusing the deck's
     offmarket_report_view / card_viewed / deck_exit would silently corrupt
     the off-market funnel metrics, which are shared between two arms and feed
     the RL reward ledger.                                                  */
  function emit(name, props) {
    if (window.posthog && window.posthog.capture) window.posthog.capture(name, props);
    if (location.search.indexOf('debug') > -1) console.log('[fridge]', name, props);
  }

  var idle = null;

  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('.shelf a');
    if (!a) return;
    clearTimeout(idle);
    var shelves = Array.prototype.slice.call(document.querySelectorAll('.shelf a'));
    emit('fridge_option_click', {
      href: a.getAttribute('href'),
      shelf_index: shelves.indexOf(a) + 1,
      ms_since_open: Math.round(performance.now() - t0)
    });
  });

  // The failure mode to design against: door open, nothing tapped.
  setTimeout(function () {
    idle = setTimeout(function () { emit('fridge_idle', { seconds: 15 }); }, 15000);
  }, 800);

  // Terminal event — sendBeacon so it survives the tab closing, matching the
  // deck_exit pattern in DiscoveryDeck.tsx:331-343.
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState !== 'hidden') return;
    emit('fridge_exit', { opened: opened, ms: Math.round(performance.now() - t0) });
  });
})();
