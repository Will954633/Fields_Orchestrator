/* MOBILE APP BAR + CHAPTER MENU — mockup behaviour for the V3 deck.
 *
 * Reads the deck that is already in the document (`main#deck > section.card`)
 * and builds the menu from the cards THAT HOME ACTUALLY HAS. This matters:
 * `comparable` and `value_drivers` are dropped by the builder when the data
 * isn't there, so a hardcoded eleven-line menu would point at cards that don't
 * exist on roughly a third of homes.
 *
 * Labels are keyed off the section id (card-01 … card-11), which the builder
 * derives from the card TYPE, not its render order — so the label always
 * matches the card even on a deck that renders nine.
 */
(function () {
  "use strict";

  var LABELS = {
    "card-00": "Your home",
    "card-01": "What we analysed",
    "card-02": "What stood out",
    "card-03": "What makes it different",
    "card-04": "Why that matters",
    "card-05": "Who you're competing with",
    "card-06": "The obvious comparison",
    "card-07": "What carries the price",
    "card-08": "Your likely buyer",
    "card-09": "What it's worth",
    "card-10": "How we'd sell it",
    "card-11": "Your full analysis",
  };

  // Site links under the divider. Suburb is filled in from the deck config when
  // it's there, matching the live deck's deep-link into Market Intelligence.
  var SITE = "https://fieldsestate.com.au";

  var deck = document.getElementById("deck");
  if (!deck) return;

  var sections = [].slice.call(deck.querySelectorAll("section.card"));
  if (!sections.length) return;

  // ---- bar ----
  var bar = document.createElement("header");
  bar.className = "fx-navbar";
  bar.innerHTML =
    '<a href="' + SITE + '" aria-label="Fields"><img src="mobile_menu_logo.png" alt="Fields"></a>' +
    '<button class="fx-burger" type="button" aria-expanded="false" aria-controls="fx-navpanel" ' +
    'aria-label="Chapters"><span></span><span></span><span></span></button>';

  var panel = document.createElement("nav");
  panel.className = "fx-navpanel";
  panel.id = "fx-navpanel";
  panel.setAttribute("aria-label", "Chapters");

  var html = ['<div class="fx-eyebrow">On this page</div>'];
  var n = 0;
  sections.forEach(function (s) {
    var id = s.id;
    var label = LABELS[id];
    if (!label) return;
    var offer = s.hasAttribute("data-offer") || id === "card-11";
    var num = offer || id === "card-00" ? "" : String(++n).padStart(2, "0");
    html.push(
      '<a href="#' + id + '" data-target="' + id + '"' + (offer ? ' class="fx-offer"' : "") + '>' +
        '<span class="fx-n">' + num + "</span><span>" + label + "</span></a>"
    );
  });

  var suburb = (window.__FIELDS_INTRO && window.__FIELDS_INTRO.locality) || "";
  var slug = suburb.trim().replace(/\s+/g, "-");
  html.push("<hr>", '<div class="fx-eyebrow">fieldsestate.com.au</div>');
  html.push(
    '<a href="' + SITE + '/market-intelligence/' + (slug || "Robina") + '/sell-now"><span class="fx-n"></span><span>Market Intelligence</span></a>',
    '<a href="' + SITE + '/news"><span class="fx-n"></span><span>News &amp; Research</span></a>',
    '<a href="' + SITE + '/analyse-your-home"><span class="fx-n"></span><span>Analyse your home</span></a>'
  );
  panel.innerHTML = html.join("");

  document.body.appendChild(bar);
  document.body.appendChild(panel);

  // ---- open / close ----
  var burger = bar.querySelector(".fx-burger");
  function setOpen(open) {
    burger.setAttribute("aria-expanded", String(open));
    panel.classList.toggle("fx-open", open);
  }
  burger.addEventListener("click", function (e) {
    e.stopPropagation();
    setOpen(burger.getAttribute("aria-expanded") !== "true");
  });
  // Close on any chapter tap. The href does the scrolling — `scroll-behavior:
  // smooth` is already on <html> — so nothing here calls scrollIntoView.
  panel.addEventListener("click", function (e) {
    if (e.target.closest("a")) setOpen(false);
  });
  document.addEventListener("click", function (e) {
    if (!panel.contains(e.target) && !bar.contains(e.target)) setOpen(false);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") setOpen(false);
  });

  // ---- tint once past the hero ----
  var hero = document.getElementById("card-00") || sections[0];
  new IntersectionObserver(
    function (rs) { bar.classList.toggle("fx-scrolled", !rs[0].isIntersecting); },
    { threshold: 0 }
  ).observe(hero);

  // ---- current chapter ----
  var links = {};
  [].slice.call(panel.querySelectorAll("a[data-target]")).forEach(function (a) {
    links[a.dataset.target] = a;
  });
  // Mid-viewport band: a card counts as "current" when it owns the middle of
  // the screen, not when its first pixel appears.
  var spy = new IntersectionObserver(
    function (rs) {
      rs.forEach(function (r) {
        var a = links[r.target.id];
        if (!a || !r.isIntersecting) return;
        for (var k in links) links[k].removeAttribute("aria-current");
        a.setAttribute("aria-current", "true");
      });
    },
    { rootMargin: "-45% 0px -45% 0px" }
  );
  sections.forEach(function (s) { if (links[s.id]) spy.observe(s); });

  // ---- REVEAL: with card 00, never during the matrix ----
  function reveal() { document.documentElement.classList.add("fx-nav-ready"); }
  // The intro releases `.intro-locked` and then dispatches this; the React deck
  // flips `introDone` on the same event.
  window.addEventListener("fields:intro-done", reveal, { once: true });
  // No intro on this document (skipped, or a home with no `intro_tokens`) —
  // the bar must not be withheld forever waiting for an event nothing fires.
  if (!document.getElementById("stage") && !document.querySelector(".intro-stage")) reveal();
})();
