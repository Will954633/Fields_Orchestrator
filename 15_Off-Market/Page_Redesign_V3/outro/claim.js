/**
 * claim.js — the last beat: "your website is ready, come and get it".
 *
 * Runs off `fields:strategy-built`, the event the outro fires when the ship's
 * computer says "Construction completed." The camera pans down off the build log
 * and onto an offer, typed in the same hand as the opening sequence.
 *
 *   Your website is ready.
 *   Now claim your private access.
 *   We'll send a secure link to your mobile.
 *   [ Claim my website ]
 *
 * THE MECHANIC. Pressing the button opens the reader's own SMS app with the
 * message already written — `SEND 27 Protea Court` — addressed to us. They press
 * send; we reply with the link to their mini-site.
 *
 * Why that way round, rather than a form asking for a number:
 *
 *   IT COLLECTS THE ONE THING NOBODY WILL TYPE. Every measurement we have says
 *   the public will not hand over a phone number to a website. They will happily
 *   send a text. The number arrives as a side effect of them asking, which is
 *   the whole trick — see the contact-capture note in memory.
 *
 *   THE CONSENT IS UNAMBIGUOUS. They messaged us, in their own words, asking for
 *   a thing. A reply carrying that thing is a response to a request, not a
 *   marketing message. That is a far cleaner footing than an opt-in checkbox.
 *
 *   THE ADDRESS IS IN THE MESSAGE. No session to keep alive, no cookie to match,
 *   no token to expire. The text itself says which house it is, so the reply can
 *   be built from the message alone even if they send it three days later from a
 *   different phone on a different network.
 *
 * DESKTOP HAS NO SMS APP, so it gets a QR code instead: the same `sms:` URI,
 * rendered at build time, scanned with the phone that is already in their hand.
 * The number and the message are printed underneath as well, because a QR code
 * that fails leaves you with nothing.
 *
 * Config arrives as `window.__FIELDS_CLAIM` from the deck builder — address,
 * number, the prebuilt QR, and the deck's own analytics keys (slug/suburb/arm).
 * No config, no panel: this must never be the thing that breaks the ending.
 */
(function (global) {
  "use strict";

  const CFG = global.__FIELDS_CLAIM || null;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  // A phone, meaning a device whose SMS app a `sms:` link will actually open.
  // Feature-shaped rather than name-shaped: a touchscreen laptop is not a phone,
  // and a browser we have never heard of still deserves the right answer.
  const isPhone = matchMedia("(hover: none) and (pointer: coarse)").matches;
  // iOS wants `sms:NUMBER&body=`; everything else wants `?body=`. Getting this
  // wrong does not error — it silently opens SMS with an empty message, which
  // is the worst possible failure because it looks like it worked.
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) ||
                (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

  function smsHref(number, body) {
    return "sms:" + number + (isIOS ? "&" : "?") + "body=" + encodeURIComponent(body);
  }

  /** THE LAST STEP HAS TO BE MEASURED LIKE EVERY OTHER ONE.
   *
   *  This file shipped with no analytics at all, so the single most important
   *  moment in the deck — whether the reader actually opened their SMS app —
   *  was invisible. The first real press (6 Aug 2026, 11 Highgate Lane) could
   *  only be reconstructed by pulling a session replay apart mutation by
   *  mutation, and even then we could not have told a press from a non-press.
   *
   *  Same props as the deck's own `base` (slug/suburb/arm), so these join
   *  straight onto card_viewed and deck_exit without a lookup.
   *
   *  `sendBeacon` on the press: the click navigates to `sms:`, which on Android
   *  backgrounds the browser immediately. An ordinary XHR loses the race. */
  function track(event, cfg, extra) {
    try {
      if (!global.posthog || !global.posthog.capture) return;
      global.posthog.capture(event, Object.assign({
        slug: cfg.slug || null,
        suburb: cfg.suburb || null,
        arm: cfg.arm || "v3",
        surface: isPhone ? "phone" : "desktop",
      }, extra || {}), { transport: "sendBeacon" });
    } catch (_) {
      /* analytics must never break the ending */
    }
  }

  async function typeInto(node, text, per) {
    for (let i = 1; i <= text.length; i++) {
      node.textContent = text.slice(0, i);
      await wait(text[i - 1] === "." ? per * 3 : per);
    }
  }

  function build(cfg) {
    const el = document.createElement("div");
    el.id = "fx-claim";
    el.innerHTML =
      '<h2 class="c-h"></h2>' +
      '<p class="c-l1"></p>' +
      '<p class="c-l2"></p>' +
      '<div class="c-act"></div>';
    const act = el.querySelector(".c-act");

    const body = "SEND " + cfg.address;
    const href = smsHref(cfg.number, body);

    if (isPhone) {
      const a = document.createElement("a");
      a.className = "c-btn";
      a.href = href;
      a.textContent = "Claim my website";
      // Not preventDefault'ed — the href IS the action. The class change is only
      // so the panel can say something true afterwards: their SMS app is now
      // open with the message written, and they still have to press send.
      a.addEventListener("click", () => {
        el.classList.add("sent");
        const note = el.querySelector(".c-note");
        if (note) note.textContent = "Your message is ready — press send, and the link comes straight back.";
        // Fired here rather than on the SMS arriving, because those are two
        // different questions. This one is "did the mechanic work"; the reply
        // rate against it is "were they willing to send it".
        track("claim_sms_pressed", cfg, { address: cfg.address });
      });
      act.appendChild(a);
      const note = document.createElement("p");
      note.className = "c-note";
      note.textContent = "Opens your messages with the text already written.";
      act.appendChild(note);
    } else {
      // Desktop. The QR is the primary path and the printed text is the backup;
      // both encode exactly the same thing.
      // Only when there IS one. The React deck has no QR generator yet, and an
      // empty white plate reads as a broken image rather than as an absent
      // feature — the printed number below is a complete fallback on its own.
      if (cfg.qr) {
        const wrap = document.createElement("div");
        wrap.className = "c-qr";
        wrap.innerHTML = cfg.qr;
        act.appendChild(wrap);
      }
      const note = document.createElement("p");
      note.className = "c-note";
      note.innerHTML = "Scan with your phone to open the message.<br>" +
        "Or text <b>" + body.replace(/[<&]/g, "") + "</b> to <b>" +
        cfg.numberDisplay + "</b>";
      act.appendChild(note);
    }
    return el;
  }

  async function run(cfg) {
    const world = document.getElementById("fx-world");
    const msg = document.getElementById("fx-msg");
    if (!world) return;

    const panel = build(cfg);
    world.appendChild(panel);

    // The camera moves, not the content: the build log rises out of frame while
    // the offer comes up from below. One motion, so it reads as a pan down the
    // same wall rather than two things crossfading.
    await wait(reduced ? 0 : 1400);
    if (msg) msg.classList.add("gone");
    panel.classList.add("in");
    track("claim_panel_shown", cfg, { address: cfg.address });
    await wait(reduced ? 0 : 900);

    const h = panel.querySelector(".c-h");
    const l1 = panel.querySelector(".c-l1");
    const l2 = panel.querySelector(".c-l2");
    /** THE ACTION COMES UP ON THE HEADLINE, NOT AFTER ALL THREE LINES.
     *
     *  It used to fade up last, on the reasoning that a button sitting there
     *  through the type-in invites a press before the offer has been made. That
     *  reasoning was half right and wholly expensive.
     *
     *  Expensive: it put the button 32.9s behind the CTA press, of which the
     *  last 6.5s were this panel alone. On 6 Aug 2026 the first real reader in
     *  the deck's history sat through every one of them and the page stopped
     *  0.4s before that line ran — so the only person who has ever pressed
     *  "Start building" never saw a pressable button.
     *
     *  Half right: revealing it with the panel was tried and looks wrong — a
     *  lone button with three empty lines above it for 1.5s, the payoff of the
     *  whole 27-second sequence still unwritten. "Your website is ready." IS
     *  the offer; the two lines below it are elaboration, and they type in
     *  under a button that is already live. Coherent at every frame, and 3.1s
     *  earlier than before.
     *
     *  Do not move this back down. If it needs to move at all, it moves UP. */
    const reveal = () => { panel.classList.add("ready"); };

    if (reduced) {
      h.textContent = "Your website is ready.";
      reveal();
      l1.textContent = "Now claim your private access.";
      l2.textContent = "We'll send a secure link to your mobile.";
    } else {
      await typeInto(h, "Your website is ready.", 46);
      reveal();
      await wait(420);
      await typeInto(l1, "Now claim your private access.", 30);
      await wait(240);
      await typeInto(l2, "We'll send a secure link to your mobile.", 26);
    }
  }

  if (CFG && CFG.address && CFG.number) {
    addEventListener("fields:strategy-built", () => run(CFG), { once: true });
  }
})(window);
