/* lab_harness.js — instrumentation for the Home Owner Funnel-Discovery lab.
 *
 * Emits the CANONICAL EVENT SPINE (contract with the reward ledger, build 6A:
 * see 03_Facebook/Home_Owner_Lead_Funnel_Search/ledger/funnel_ledger.py). Every
 * lab_* event carries `variant` (= ad_name / template variant) and `lab_cid`
 * (per-click id threaded from the ad URL) as PostHog super-properties, so the
 * FB-ad -> landing-page seam joins on the PostHog distinct_id.
 *
 * PRIVACY RULE (hard): no raw PII ever goes to PostHog. Field completions send
 * only { field, valid } and, for email, { email_domain } for junk detection.
 * The one real capture (newsletter waitlist email) goes to a server endpoint,
 * NOT analytics — and is DISABLED until the Brisbane newsletter exists.
 *
 * Usage in a template:
 *   <script>window.LAB_POSTHOG_TOKEN='phc_...';</script>
 *   <script src="/lab/lab_harness.js"></script>
 *   ...then either call the Lab.* API, or use declarative data-attributes:
 *     <div data-lab-step="1" data-lab-step-name="ask-name"> ... </div>
 *     <input data-lab-field="address">
 *     <button data-lab-micro="address">Continue</button>
 *     <a data-lab-call href="tel:...">Call us</a>
 *     <div data-lab-terminal="deadend"> ... </div>   (or "waitlist_optin")
 */
(function () {
  "use strict";

  var TOKEN = window.LAB_POSTHOG_TOKEN || "phc_RQ68rG9adv6NYtoZS4JzmJVzVyOWUfprV9ceHb0nLEs";
  var HOST = "https://us.i.posthog.com";

  // ---- URL attribution params -------------------------------------------
  function qp(name) {
    var m = new RegExp("[?&]" + name + "=([^&]*)").exec(window.location.search);
    return m ? decodeURIComponent(m[1].replace(/\+/g, " ")) : "";
  }
  // variant defaults to a body data-attr so a template can hardcode its name.
  var VARIANT = qp("variant") || (document.body && document.body.getAttribute("data-lab-variant")) || "unknown";
  var LAB_CID = qp("lab_cid") || qp("fbclid") || "";

  // ---- standard PostHog snippet -----------------------------------------
  !function (t, e) { var o, n, p, r; e.__SV || (window.posthog = e, e._i = [], e.init = function (i, s, a) { function g(t, e) { var o = e.split("."); 2 == o.length && (t = t[o[0]], e = o[1]), t[e] = function () { t.push([e].concat(Array.prototype.slice.call(arguments, 0))) } } (p = t.createElement("script")).type = "text/javascript", p.async = !0, p.src = s.api_host.replace(".i.posthog.com", "-assets.i.posthog.com") + "/static/array.js", (r = t.getElementsByTagName("script")[0]).parentNode.insertBefore(p, r); var u = e; for (void 0 !== a ? u = e[a] = [] : a = "posthog", u.people = u.people || [], u.toString = function (t) { var e = "posthog"; return "posthog" !== a && (e += "." + a), t || (e += " (stub)"), e }, u.people.toString = function () { return u.toString(1) + ".people (stub)" }, o = "capture identify alias people.set people.set_once set_config register register_once unregister opt_out_capturing has_opted_out_capturing opt_in_capturing reset isFeatureEnabled onFeatureFlags getFeatureFlag getFeatureFlagPayload reloadFeatureFlags group updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures getActiveMatchingSurveys getSurveys onSessionId".split(" "), n = 0; n < o.length; n++)g(u, o[n]); e._i.push([i, s, a]) }, e.__SV = 1) }(document, window.posthog || []);

  posthog.init(TOKEN, {
    api_host: HOST,
    persistence: "localStorage+cookie",
    autocapture: false,          // we emit an explicit, named spine
    capture_pageview: false,     // lab_lp_view is our pageview
  });
  posthog.register({ variant: VARIANT, lab_cid: LAB_CID, lab: true });

  // ---- the spine emitters -----------------------------------------------
  function emit(event, props) {
    // optional test seam — no-op in production (only set by the headless validator)
    if (window.__labSpy) { try { window.__labSpy(event, props || {}); } catch (e) {} }
    try { posthog.capture(event, props || {}); } catch (e) {}
  }

  var Lab = {
    variant: VARIANT,
    lab_cid: LAB_CID,
    lpView: function () { emit("lab_lp_view", { variant: VARIANT, step: 0 }); },
    step: function (i, name) { emit("lab_step_view", { variant: VARIANT, step: i, step_name: name || "" }); },
    fieldFocus: function (field) { emit("lab_field_focus", { variant: VARIANT, field: field }); },
    fieldComplete: function (field, value) {
      var p = { variant: VARIANT, field: field, valid: true };
      if (field === "email" && value && value.indexOf("@") > -1) {
        p.email_domain = value.split("@")[1].toLowerCase();   // domain only — never the address
      }
      emit("lab_field_complete", p);
    },
    micro: function (goal) { emit("lab_micro_conversion", { variant: VARIANT, goal: goal }); },
    callCta: function () { emit("lab_call_cta_click", { variant: VARIANT }); },
    terminal: function (type) { emit("lab_terminal", { variant: VARIANT, terminal_type: type || "deadend" }); },
  };
  window.Lab = Lab;

  // ---- declarative auto-wiring (data-attributes) ------------------------
  function wire() {
    Lab.lpView();

    // steps: fire when a [data-lab-step] element becomes visible
    var steps = document.querySelectorAll("[data-lab-step]");
    if (steps.length && "IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (en.isIntersecting) {
            var el = en.target;
            Lab.step(parseInt(el.getAttribute("data-lab-step"), 10),
                     el.getAttribute("data-lab-step-name"));
            io.unobserve(el);
          }
        });
      }, { threshold: 0.5 });
      steps.forEach(function (el) { io.observe(el); });
    }

    // fields: focus -> fieldFocus; valid blur -> fieldComplete (domain-only for email)
    document.querySelectorAll("[data-lab-field]").forEach(function (inp) {
      var field = inp.getAttribute("data-lab-field");
      inp.addEventListener("focus", function () { Lab.fieldFocus(field); }, { once: true });
      inp.addEventListener("blur", function () {
        var v = (inp.value || "").trim();
        if (!v) return;                         // empty blur = still resisted
        if (field === "email" && v.indexOf("@") < 1) return;   // invalid email
        Lab.fieldComplete(field, v);
      });
    });

    // micro-conversions, call CTA, terminal
    document.querySelectorAll("[data-lab-micro]").forEach(function (b) {
      b.addEventListener("click", function () { Lab.micro(b.getAttribute("data-lab-micro")); });
    });
    document.querySelectorAll("[data-lab-call]").forEach(function (b) {
      b.addEventListener("click", function () { Lab.callCta(); });
    });
    document.querySelectorAll("[data-lab-terminal]").forEach(function (t) {
      if ("IntersectionObserver" in window) {
        var io2 = new IntersectionObserver(function (es) {
          es.forEach(function (e) { if (e.isIntersecting) { Lab.terminal(t.getAttribute("data-lab-terminal")); io2.unobserve(t); } });
        }, { threshold: 0.5 });
        io2.observe(t);
      }
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire);
  else wire();
})();
