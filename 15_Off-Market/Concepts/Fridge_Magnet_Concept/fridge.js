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

  /* Absolute, so it works identically from the concepts workbench (a different
     host) and from /fridge in production. */
  var HOME = 'https://fieldsestate.com.au/';

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
    if (prompt) prompt.textContent = next ? 'Tap to close' : 'Tap to open';

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
    if (t && t.closest && t.closest('.srToggle, .muteBtn, .secret')) return;  // own handlers

    interacted = true;
    clearTimeout(autoTimer); clearTimeout(nudgeTimer);

    if (!isOpen) { setOpen(true, 'pulled'); return; }
    if (t && t.closest && t.closest('.cavity')) return;    // reading, not closing
    setOpen(false, 'pulled');
  }

  /* Bound to THREE event types, not one.

     A single physical tap delivers pointerup -> touchend -> click within ~10ms
     (measured), so listening to all three costs nothing but means the door
     still opens if any one of them is swallowed — which is what "I closed it
     and then couldn't open it again" looks like from the outside. The dedupe
     window makes the redundancy safe: without it, one tap would toggle three
     times and land back where it started, which is the same symptom. */
  var lastTap = 0;
  function onTapDeduped(e) {
    var now = e.timeStamp || performance.now();
    if (now - lastTap < 450) return;
    lastTap = now;
    onTap(e);
  }
  document.addEventListener('pointerup', onTapDeduped, { passive: true });
  document.addEventListener('touchend',  onTapDeduped, { passive: true });
  document.addEventListener('click',     onTapDeduped);
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    if (document.activeElement && document.activeElement.closest &&
        document.activeElement.closest('.shelf a, .srToggle')) return;
    interacted = true; clearTimeout(autoTimer); clearTimeout(nudgeTimer);
    setOpen(!isOpen, 'pulled');
  });

  if (muteBtn && audio) {
    muteBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      var m = audio.setMuted(!audio.isMuted());
      muteBtn.setAttribute('aria-pressed', String(m));
      muteBtn.setAttribute('aria-label', m ? 'Unmute the fridge' : 'Mute the fridge');
      muteBtn.innerHTML = m ? '&#9835;\u0338' : '&#9834;';
      emit('fridge_mute', { muted: m });
    });
  }

  if (srToggle) {
    srToggle.addEventListener('click', function () {
      interacted = true; clearTimeout(autoTimer); clearTimeout(nudgeTimer);
      setOpen(!isOpen, 'pulled');
    });
  }

  /* ── Whose fridge is this? ────────────────────────────────────────────
     The suburb used to be hardcoded to Burleigh Waters, which was arbitrary and
     wrong for two thirds of the target market. There is no suburb-neutral
     market page either — /market-intelligence 301s to Robina, which is just
     somebody else's arbitrary choice.

     So: ask. /api/v1/my-home is read-only and address-only, and recognises
     anyone who has used Analyse Your Home or landed on their own /off-market
     page from Google. If it resolves we name their suburb; if it doesn't we say
     "your market" and let the site pick. Never guess a suburb at them.

     ?suburb=<slug> overrides both — for testing, and for the per-magnet codes
     in the scoping doc's v2 rung. */
  var SUBURBS = {
    'robina': 'Robina',
    'varsity-lakes': 'Varsity Lakes',
    'burleigh-waters': 'Burleigh Waters',
    'burleigh-heads': 'Burleigh Heads',
    'mermaid-waters': 'Mermaid Waters',
    'miami': 'Miami',
    'palm-beach': 'Palm Beach'
  };

  function setSuburb(slug, source) {
    var name = SUBURBS[slug];
    if (!name) return false;
    var eb = document.getElementById('eyebrow');
    var a  = document.getElementById('optMarket');
    var lb = document.getElementById('optMarketLabel');
    if (eb) eb.textContent = name;
    if (a)  a.href = 'https://fieldsestate.com.au/market-intelligence/' + slug;
    if (lb) lb.childNodes[0].nodeValue = "What's happening in " + name + ' ';
    emit('fridge_suburb', { suburb: slug, source: source });
    return true;
  }

  (function resolveSuburb() {
    var forced = q.get('suburb');
    if (forced && setSuburb(forced.toLowerCase(), 'url')) return;
    if (!window.posthog || !window.posthog.get_distinct_id) return;
    var did;
    try { did = window.posthog.get_distinct_id(); } catch (e) { return; }
    if (!did || did.length < 8) return;
    var tok = '';
    try { tok = localStorage.getItem('fields_device_token') || ''; } catch (e) {}
    fetch('/api/v1/my-home?distinct_id=' + encodeURIComponent(did) +
          (tok ? '&device_token=' + encodeURIComponent(tok) : ''))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || !d.ok || !d.home || !d.home.slug) return;
        /* the resolver returns an ADDRESS slug (14-fern-street-burleigh-waters),
           so take the suburb off the tail rather than inventing a parser */
        var slug = String(d.home.slug);
        for (var k in SUBURBS) {
          if (slug.length > k.length && slug.slice(-(k.length + 1)) === '-' + k) {
            setSuburb(k, d.home.source || 'my_home');
            emit('fridge_recognised', { confidence: d.home.confidence, source: d.home.source });
            return;
          }
        }
      })
      .catch(function () { /* never let recognition break the page */ });
  })();

  /* ── The secret door ──────────────────────────────────────────────────
     A small unlabelled button on the inside of the door. Press it and the
     false back of the fridge hinges down, the Fields homepage is behind it,
     and then we go there.

     The navigation waits for the reveal to finish. Leaving before the panel
     lands would make the whole thing a slow redirect instead of a reveal —
     the point is that they SEE what is behind before they are taken to it. */
  var VAULT_MS = 1500;
  var secret = document.getElementById('secret');
  if (secret) {
    secret.addEventListener('click', function (e) {
      e.stopPropagation();
      if (fridge.classList.contains('is-vault')) return;
      interacted = true;
      clearTimeout(autoTimer); clearTimeout(nudgeTimer); clearTimeout(idleTimer);

      if (audio && audio.arm()) audio.latch();
      if (navigator.vibrate) { try { navigator.vibrate([8, 40, 22]); } catch (err) {} }

      fridge.classList.add('is-vault');
      document.body.classList.add('is-vaulting');
      secret.disabled = true;
      emit('fridge_secret', { ms_since_load: Math.round(performance.now() - t0) });

      setTimeout(function () { window.location.href = HOME; }, VAULT_MS);
    });
  }

  /* ── The door WAITS for a tap. It does not auto-open. ─────────────────
     It used to open itself at 0.8s, and that made the single most important
     moment on the page — the first opening — permanently silent, because no
     gesture had happened and audible autoplay is blocked everywhere. The first
     sound a visitor got was the door CLOSING. Backwards.

     So the open is now always earned by a tap, which means it always has the
     gasket, the hum starting, and the haptic. Two safety nets, both silent,
     because a silent nudge is better than a silent reveal:

       4s   NUDGE  — the door cracks ~11% and settles back. Says "this opens"
                     without spending the reveal.
       12s  OPEN   — give up and show the options anyway. Nobody who waited
                     this long should be left with a closed box.

     Reduced motion still opens immediately: the beat exists to be watched, and
     if motion is off there is nothing to watch. */
  var NUDGE_MS = 4000, GIVE_UP_MS = 12000;
  var nudgeTimer = null;

  function nudge() {
    if (interacted || isOpen) return;
    fridge.classList.add('is-nudging');
    setTimeout(function () { fridge.classList.remove('is-nudging'); }, 1000);
    emit('fridge_nudge', {});
  }

  if (reduce) {
    setOpen(true, 'auto');
  } else {
    nudgeTimer = setTimeout(nudge, NUDGE_MS);
    autoTimer  = setTimeout(function () { if (!interacted) setOpen(true, 'auto'); }, GIVE_UP_MS);
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
      if (audio) audio.suspend();     // never leave a fridge humming behind a dead tab
      emit('fridge_exit', { opened: isOpen, interacted: interacted, ms: Math.round(performance.now() - t0) });
    } else if (audio && interacted) {
      audio.wake();
    }
  });
})();
