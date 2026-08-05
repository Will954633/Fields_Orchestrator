/* ============================================================================
   fridge.js — decides WHEN the door opens and closes. Nothing else.

   The door, the light, the drawing, the shelves and the options are all CSS +
   HTML and work with this file deleted. That is the point: on the real site the
   sequence has to run before 219 KB of app JavaScript has necessarily landed
   over a kitchen 4G connection.

   Deliberately plain .js, no build step — so this exact file can be served from
   public/fridge/ in production and loaded here at the concepts URL, and
   prototype and production cannot drift. Same reason src/components/BreakGlass
   keeps its 3,000 lines of behaviour in public/ rather than in .tsx.

   Query params: ?art=mono  ?sound=0  ?debug=1
   ========================================================================== */
(function () {
  'use strict';

  var fridge = document.getElementById('fridge');
  var srToggle = document.getElementById('srToggle');
  if (!fridge) { console.warn('[fridge] no #fridge element — nothing to do'); return; }

  var q = new URLSearchParams(location.search);
  var DEBUG = q.has('debug');
  var reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var audio = window.fridgeAudio || null;

  if (q.get('art') === 'mono') document.body.classList.add('art-mono');
  if (audio && q.get('sound') === '0') audio.enable(false);

  /* Decode the three recordings up front. A context created without a gesture
     starts suspended, and decodeAudioData works fine suspended — so this costs
     nothing and means the hum starts the instant the visitor first touches,
     rather than a fetch later. */
  if (audio) { try { audio.preload(); } catch (e) {} }

  var muteBtn = document.getElementById('muteBtn');

  /* Must match the CSS transition durations. Out of sync and the interior
     re-darkens while the door is still visibly swinging. */
  var CLOSE_MS = 1020;

  var isOpen = false;
  var interacted = false;
  var autoTimer = null;
  var closingTimer = null;
  var t0 = performance.now();

  function emit(name, props) {
    if (window.posthog && window.posthog.capture) window.posthog.capture(name, props);
    if (DEBUG) console.log('[fridge]', name, JSON.stringify(props), audio ? JSON.stringify(audio.state()) : '');
  }

  function setOpen(next, method) {
    if (next === isOpen) return;
    isOpen = next;
    clearTimeout(closingTimer);

    if (next) {
      fridge.classList.remove('is-closing');
      fridge.classList.add('is-open');
    } else {
      fridge.classList.remove('is-open');
      fridge.classList.add('is-closing');
      /* is-closing drives the "light stays on until it seats" keyframe. It has
         to be taken off again afterwards or the next open starts from the
         extinguish end-state. */
      closingTimer = setTimeout(function () { fridge.classList.remove('is-closing'); }, CLOSE_MS);
    }

    if (srToggle) {
      srToggle.setAttribute('aria-expanded', String(next));
      srToggle.textContent = next ? 'Close the fridge' : 'Open the fridge';
    }
    var prompt = document.querySelector('.prompt');
    if (prompt) prompt.textContent = next ? 'Close' : 'Open';

    /* Sound and haptics belong to the PULL only.
       The auto-open has no user activation behind it, so on Android the context
       would be created without activation, report running, and emit nothing —
       and we'd have no idea. Better to be deliberately silent than silently
       broken. The hum therefore also begins at the first touch, never on load:
       audible autoplay is blocked everywhere, and that is policy, not a bug. */
    if (method === 'pulled' && audio) {
      if (audio.arm()) {
        if (next) audio.open(); else audio.close();
        if (muteBtn) muteBtn.classList.add('on');
      }
      if (navigator.vibrate) { try { navigator.vibrate(next ? 12 : 18); } catch (e) {} }
    }

    emit(next ? 'fridge_open' : 'fridge_close', {
      method: method,
      ms_since_load: Math.round(performance.now() - t0)
    });
  }

  /* ── Any touch anywhere opens it ────────────────────────────────────────
     Not a handle hitbox. Asking someone to find a 40px handle on a phone in a
     kitchen is a failure mode with no upside.

     Bound on pointerup / click, NEVER pointerdown — see the activation note in
     fridgeAudio.js. Closing has a tighter rule than opening: a tap inside the
     cavity must NOT close the door, or people lose the menu while reaching for
     an option. So the close targets are the door itself and the room around
     it, and the interior is inert. */
  function onTap(e) {
    var t = e.target;
    if (t && t.closest && t.closest('.shelf a')) return;   // let the link work
    if (t && t.closest && t.closest('.srToggle, .muteBtn')) return;  // own handlers

    interacted = true;
    clearTimeout(autoTimer);

    if (!isOpen) { setOpen(true, 'pulled'); return; }
    if (t && t.closest && t.closest('.cavity')) return;    // reading, not closing
    setOpen(false, 'pulled');
  }

  document.addEventListener('pointerup', onTap, { passive: true });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    if (document.activeElement && document.activeElement.closest &&
        document.activeElement.closest('.shelf a, .srToggle')) return;
    interacted = true; clearTimeout(autoTimer);
    setOpen(!isOpen, 'pulled');
  });

  if (muteBtn && audio) {
    muteBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      var m = audio.setMuted(!audio.isMuted(), isOpen);
      muteBtn.setAttribute('aria-pressed', String(m));
      muteBtn.setAttribute('aria-label', m ? 'Unmute the fridge' : 'Mute the fridge');
      muteBtn.innerHTML = m ? '&#9835;\u0338' : '&#9834;';
      emit('fridge_mute', { muted: m });
    });
  }

  if (srToggle) {
    srToggle.addEventListener('click', function () {
      interacted = true; clearTimeout(autoTimer);
      setOpen(!isOpen, 'pulled');
    });
  }

  /* ── Auto-open, so nobody is left staring at a closed fridge ───────────
     Under reduced motion, immediately — the 0.8s beat exists to be watched, and
     if the motion is switched off there is nothing to watch. */
  if (reduce) {
    setOpen(true, 'auto');
  } else {
    autoTimer = setTimeout(function () { if (!interacted) setOpen(true, 'auto'); }, 800);
  }

  /* ── Measurement ──────────────────────────────────────────────────────
     On the site this becomes phCapture() from src/utils/posthog.ts.
     Namespaced fridge_* on purpose — reusing the deck's offmarket_report_view /
     card_viewed / deck_exit would silently corrupt the off-market funnel
     metrics, which are shared between two arms and feed the RL reward ledger. */
  /* The scan itself is only observable as an arrival on this page, so
     fridge_land is the denominator for everything else. Attribution is
     REGISTERED rather than carried in the URL: /fridge is now the landing page
     itself, not a 301 that appends utm_*, which saves a round trip on exactly
     the connection that matters (a kitchen, on 4G). PostHog filters registered
     super properties identically to parsed ones. */
  if (window.posthog && window.posthog.register) {
    window.posthog.register({
      utm_source: 'fridge_magnet',
      utm_medium: 'print',
      utm_campaign: 'fridge_magnet_bizcard',
      fridge_arm: 'v1'
    });
  }
  emit('fridge_land', {
    reduced_motion: reduce,
    referrer: document.referrer || null,
    suburb: (document.querySelector('.eyebrow') || {}).textContent || null
  });

  var idleTimer = null;
  function armIdle() {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(function () {
      if (isOpen) emit('fridge_idle', { seconds: 15 });
    }, 15000);
  }
  armIdle();

  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('.shelf a');
    if (!a) return;
    clearTimeout(idleTimer);
    var all = Array.prototype.slice.call(document.querySelectorAll('.shelf a'));
    emit('fridge_option_click', {
      href: a.getAttribute('href'),
      shelf_index: all.indexOf(a) + 1,
      ms_since_load: Math.round(performance.now() - t0)
    });
  });

  /* Terminal event — sendBeacon so it survives the tab closing, matching the
     deck_exit pattern in DiscoveryDeck.tsx:331-343. Also kill the hum, or it
     keeps running behind a backgrounded tab. */
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') {
      if (audio) audio.suspend(isOpen);     // never leave a fridge humming behind a dead tab
      emit('fridge_exit', { opened: isOpen, interacted: interacted, ms: Math.round(performance.now() - t0) });
    } else if (audio && interacted) {
      audio.wake(isOpen);
    }
  });
})();
