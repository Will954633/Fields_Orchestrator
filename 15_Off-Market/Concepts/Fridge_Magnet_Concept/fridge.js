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

  /* Durable device id. Every fridge_* event is logged against it server-side so
     Will has a complete ledger of who scanned the magnet and what they did —
     independent of PostHog's distinct_id, which rotates (FB in-app browser resets
     storage). Shared key with the rest of the site (analyse-your-home, off-market
     ownership), so a fridge scan and a later AYH submit resolve to one device. */
  var DEVICE_KEY = 'fields_device_token';
  var deviceToken = '';
  try {
    deviceToken = localStorage.getItem(DEVICE_KEY) || '';
    if (!deviceToken) {
      deviceToken = (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
                    : 'fd_' + Math.abs((Date.now() ^ (performance.now() * 1000)) | 0).toString(36);
      localStorage.setItem(DEVICE_KEY, deviceToken);
    }
  } catch (e) { /* private mode: no durable token, events still land keyed by a per-load id */ }

  /* Absolute so it works from the concepts workbench (a different host, CORS *)
     and from /fridge in production alike. */
  var EVENT_API = 'https://fieldsestate.com.au/api/v1/fridge-event';

  /* Mirror the fridge PostHog event to the durable MongoDB ledger. sendBeacon so
     it survives the tab closing / the navigation away on an option tap — the same
     reason the deck uses it for deck_exit. Fire-and-forget: a logging failure must
     never affect the page. */
  function logEvent(name, props) {
    if (!deviceToken) return;
    var body = {
      device_token: deviceToken,
      distinct_id: (window.posthog && window.posthog.get_distinct_id) ? (function () {
        try { return window.posthog.get_distinct_id(); } catch (e) { return null; }
      })() : null,
      event: name,
      props: props || {},
      referrer: document.referrer || null,
      utm_source: 'fridge_magnet', utm_medium: 'print', utm_campaign: 'fridge_magnet_bizcard'
    };
    try {
      var blob = new Blob([JSON.stringify(body)], { type: 'application/json' });
      if (navigator.sendBeacon && navigator.sendBeacon(EVENT_API, blob)) return;
    } catch (e) { /* fall through to fetch */ }
    try {
      fetch(EVENT_API, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body), keepalive: true }).catch(function () {});
    } catch (e) { /* nothing more we can do; never throw from logging */ }
  }

  function emit(name, props) {
    if (window.posthog && window.posthog.capture) window.posthog.capture(name, props);
    logEvent(name, props);
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
    if (t && t.closest && t.closest('.srToggle, .muteBtn, .secret, .who, .addrSheet')) return;  // own handlers

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
        document.activeElement.closest('.shelf a, .srToggle, .addrSheet')) return;
    if (addrSheet && !addrSheet.hidden) return;   // sheet owns the keyboard while open
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
  /* Only three suburbs have market pages, plus a Gold Coast aggregate for
     everyone else. The URL slug is Title-Case ON PURPOSE: the page echoes the
     slug straight into its own <title>, so /market-intelligence/robina renders
     "robina Market Intelligence". Lowercase renders, it just looks broken. */
  var SUBURBS = [
    { key: 'robina',          slug: 'Robina',          name: 'Robina' },
    { key: 'varsity-lakes',   slug: 'Varsity-Lakes',   name: 'Varsity Lakes' },
    { key: 'burleigh-waters', slug: 'Burleigh-Waters', name: 'Burleigh Waters' },
    { key: 'gold-coast',      slug: 'Gold-Coast',      name: 'the Gold Coast' }
  ];
  var PICK_KEY = 'fields_fridge_suburb';
  var picker = document.getElementById('suburbPick');
  var optMarket = document.getElementById('optMarket');

  /* True once we know the visitor's suburb (they chose it, chose it last time, or
     my-home recognised them). Until then the market option must ASK — never fall
     through to /market-intelligence, which 301s to Robina, i.e. somebody else's
     suburb. */
  var suburbResolved = false;
  /* Set when the market option was tapped with no suburb yet: picking one then
     navigates straight away, instead of making them tap the shelf a second time. */
  var pendingMarketNav = false;

  function findSuburb(key) {
    for (var i = 0; i < SUBURBS.length; i++) if (SUBURBS[i].key === key) return SUBURBS[i];
    return null;
  }

  function marketUrl(sub) { return 'https://fieldsestate.com.au/market-intelligence/' + sub.slug; }

  function setSuburb(key, source) {
    var sub = findSuburb(key);
    if (!sub) return false;
    var lb = document.getElementById('optMarketLabel');
    if (optMarket) optMarket.href = marketUrl(sub);
    if (lb) lb.childNodes[0].nodeValue = "What's happening in " + sub.name + ' ';
    if (picker && picker.value !== key) picker.value = key;
    suburbResolved = true;
    if (picker) picker.classList.remove('is-asking');
    emit('fridge_suburb', { suburb: key, source: source });
    if (pendingMarketNav) { pendingMarketNav = false; location.href = marketUrl(sub); }
    return true;
  }

  /* An explicit choice outranks everything and is remembered. */
  if (picker) {
    picker.addEventListener('change', function (e) {
      e.stopPropagation();
      var v = picker.value;
      if (!v) return;
      try { localStorage.setItem(PICK_KEY, v); } catch (err) {}
      setSuburb(v, 'chosen');
    });
    /* the picker sits inside the cavity, where taps are inert by design —
       but a <select> must still receive its own events */
    picker.addEventListener('pointerup', function (e) { e.stopPropagation(); });
  }

  /* Precedence: ?suburb= (testing / future per-magnet codes) > what they chose
     last time > who my-home thinks they are > nothing, and we say "your
     market". Never guess a suburb at somebody. */
  (function resolveSuburb() {
    var forced = q.get('suburb');
    if (forced && setSuburb(forced.toLowerCase(), 'url')) return;

    var saved = null;
    try { saved = localStorage.getItem(PICK_KEY); } catch (e) {}
    if (saved && setSuburb(saved, 'remembered')) return;

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
        for (var i = 0; i < SUBURBS.length; i++) {
          var k = SUBURBS[i].key;
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

  /* ── The four options ─────────────────────────────────────────────────
     Every shelf link is a real <a> with a working fallback href, so with this
     file deleted the page still goes somewhere sensible. Here we UPGRADE them:

       market   — needs a suburb. If we already know it (chosen / remembered /
                  recognised) the link is live and we let it through. If we do
                  NOT, we intercept and open the picker rather than let the href
                  fall through to /market-intelligence, which 301s to Robina.

       address  — sold / for-sale / worth all live on ONE page: the visitor's own
                  /off-market/<slug>. We intercept, ask for the address, and send
                  them there jumped to the rail named by data-anchor. The generic
                  fallback href only fires with JS off. */
  var OFFMARKET = 'https://fieldsestate.com.au/off-market/';
  var ADDR_API  = 'https://fieldsestate.com.au/api/v1/address-search';

  /* Mirror of slugifyAddress() in netlify/functions/analyse-your-home-submit.mjs
     and components/PropertyBridgeV2. Keep the three in step — the server keys the
     /off-market page off the same transform.
       "14 Fern Street, Burleigh Waters QLD 4226" -> "14-fern-street-burleigh-waters" */
  function slugifyAddress(address) {
    if (!address || typeof address !== 'string') return null;
    var cleaned = address
      .replace(/\s+QLD\s+\d{4}.*$/i, '')
      .replace(/\s+\d{4}\s*$/, '')
      .replace(/,/g, ' ')
      .replace(/[^a-zA-Z0-9\s\/-]/g, '')
      .replace(/[\s\/]+/g, '-')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '')
      .toLowerCase();
    return cleaned || null;
  }

  var addrSheet   = document.getElementById('addrSheet');
  var addrScrim   = document.getElementById('addrScrim');
  var addrClose   = document.getElementById('addrClose');
  var addrInput   = document.getElementById('addrInput');
  var addrList    = document.getElementById('addrList');
  var addrForm    = document.getElementById('addrForm');
  var addrTitle   = document.getElementById('addrTitle');
  var addrEyebrow = document.getElementById('addrEyebrow');
  var addrHint    = document.getElementById('addrHint');
  var addrAnchor  = '';     // #v5-near | #v5-new | #v5-valuation for the current flow
  var addrContext = '';     // the shelf's data-context, for events
  var addrTimer   = null;
  var addrSeq     = 0;      // discards out-of-order autocomplete responses

  function openAddrSheet(anchor, context) {
    if (!addrSheet) return;
    addrAnchor = anchor || '';
    addrContext = context || '';
    if (addrEyebrow) addrEyebrow.textContent = 'Your home';
    if (addrTitle)   addrTitle.textContent = 'Which home is yours?';
    if (addrHint)    addrHint.textContent = context
      ? 'We’ll show you ' + context + ', on your own page.'
      : 'Robina, Varsity Lakes and Burleigh Waters — one page for every home.';
    addrInput.value = '';
    addrList.innerHTML = '';
    addrList.classList.remove('has');
    addrSheet.hidden = false;
    /* let layout settle before the open class so the transition actually runs */
    requestAnimationFrame(function () { addrSheet.classList.add('is-open'); });
    setTimeout(function () { try { addrInput.focus({ preventScroll: true }); } catch (e) { addrInput.focus(); } }, 60);
    emit('fridge_address_open', { anchor: addrAnchor, context: addrContext });
  }

  function closeAddrSheet() {
    if (!addrSheet || addrSheet.hidden) return;
    addrSheet.classList.remove('is-open');
    clearTimeout(addrTimer); addrSeq++;
    setTimeout(function () { addrSheet.hidden = true; }, 220);
  }

  function goToHome(address, via) {
    var slug = slugifyAddress(address);
    if (!slug) return;
    /* address is included ON PURPOSE — the server recomputes the slug from it and
       find-or-creates the CRM record for this household, back-attributing this
       device's whole fridge history to the address. */
    emit('fridge_address_go', { slug: slug, address: address, anchor: addrAnchor, context: addrContext, via: via });
    /* give the beacon a beat to leave before we navigate away */
    setTimeout(function () { location.href = OFFMARKET + slug + addrAnchor; }, 60);
  }

  function renderSuggest(items) {
    addrList.innerHTML = '';
    if (!items || !items.length) { addrList.classList.remove('has'); return; }
    items.forEach(function (it) {
      var full = it.address || it.address_raw || '';
      if (!full) return;
      var li = document.createElement('li');
      var b  = document.createElement('button');
      b.type = 'button';
      b.className = 'addrOpt';
      b.textContent = full;
      b.addEventListener('click', function (e) { e.stopPropagation(); goToHome(full, 'suggestion'); });
      li.appendChild(b);
      addrList.appendChild(li);
    });
    addrList.classList.add('has');
  }

  function fetchSuggest(q) {
    var seq = ++addrSeq;
    fetch(ADDR_API + '?q=' + encodeURIComponent(q) + '&limit=6')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (seq !== addrSeq) return;                 // a newer keystroke superseded this
        renderSuggest((d && d.results) || []);
        emit('fridge_address_suggest', { q_len: q.length, n: ((d && d.results) || []).length });
      })
      .catch(function () { if (seq === addrSeq) renderSuggest([]); });
  }

  if (addrInput) {
    addrInput.addEventListener('input', function () {
      var v = addrInput.value.trim();
      clearTimeout(addrTimer);
      if (v.length < 3) { addrSeq++; renderSuggest([]); return; }
      addrTimer = setTimeout(function () { fetchSuggest(v); }, 220);
    });
  }
  if (addrForm) {
    /* Enter with no pick: take the top suggestion if there is one, else slugify
       what they typed. A slightly-off address still lands on a self-healing
       /off-market page rather than nothing. */
    addrForm.addEventListener('submit', function (e) {
      e.preventDefault();
      var first = addrList.querySelector('.addrOpt');
      if (first) { goToHome(first.textContent, 'typed_enter_top'); return; }
      var v = addrInput.value.trim();
      if (v.length >= 4) goToHome(v, 'typed_raw');
    });
  }
  if (addrScrim) addrScrim.addEventListener('click', function (e) { e.stopPropagation(); closeAddrSheet(); });
  if (addrClose) addrClose.addEventListener('click', function (e) { e.stopPropagation(); closeAddrSheet(); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && addrSheet && !addrSheet.hidden) closeAddrSheet();
  });

  /* Intercept the shelf links. Bound on each <a> so preventDefault reliably
     stops navigation before the fallback href fires. */
  Array.prototype.forEach.call(document.querySelectorAll('.shelf a'), function (a) {
    a.addEventListener('click', function (e) {
      var flow = a.getAttribute('data-flow');
      if (flow === 'address') {
        e.preventDefault();
        openAddrSheet(a.getAttribute('data-anchor') || '', a.getAttribute('data-context') || '');
        return;
      }
      if (flow === 'market') {
        if (suburbResolved) return;               // href is already the right suburb — let it go
        e.preventDefault();
        pendingMarketNav = true;                  // picking a suburb now navigates
        if (picker) {
          picker.classList.add('is-asking');
          try { picker.focus({ preventScroll: true }); } catch (err) { picker.focus(); }
          if (typeof picker.showPicker === 'function') { try { picker.showPicker(); } catch (err) {} }
        }
        emit('fridge_market_needs_suburb', {});
      }
    });
  });

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
