#!/usr/bin/env python3
"""
deploy.py — stage this concept into the website repo's public/ tree.

The prototype and production must not drift, so nothing is hand-copied and
nothing is rewritten by hand. This is the only way files move.

What it produces in /home/fields/Feilds_Website/01_Website/:

    public/fridge.html          <- generated from index.html
    public/fridge/fridge.css        }
    public/fridge/fridge.js         }  byte-identical copies
    public/fridge/fridgeAudio.js    }
    public/fridge/assets/*          }

Served by a `[[redirects]] from="/fridge" to="/fridge.html" status=200` entry,
exactly like /privacy and /seller-guide already are. NOT a React route: the app
ships 219KB of JS before it can animate anything, and the whole point of this
page is that the door paints and swings from HTML + CSS alone.

The one transformation: the concept is served from a FOLDER
(/concepts/off-market/Fridge_Magnet_Concept/) where relative paths resolve
correctly, but production serves it at the bare path /fridge, where
`assets/x.png` would resolve to `/assets/x.png` — which is the Vite hashed
bundle directory. A single <base href="/fridge/"> fixes every relative URL at
once: stylesheet, scripts, <img>, CSS url(), and fetch() in fridgeAudio.js all
resolve against the document base.

Run:  python3 deploy.py           (writes files, prints the push command)
      python3 deploy.py --check   (dry run, diff only)
"""
import argparse, hashlib, os, re, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
WEB  = "/home/fields/Feilds_Website/01_Website"

# What ships. Deliberately NOT: assets/source/ (Will's raw recordings),
# build_*.py|sh, verify/, README.md.
ASSETS = ["grain.png", "magnet.webp", "artwork.svg", "fields-icon-mask.png", "home.webp",
          "fridge-open.m4a", "fridge-close.m4a", "fridge-latch.m4a", "fridge-hum.m4a"]
CODE   = ["fridge.css", "fridge.js", "fridgeAudio.js"]

POSTHOG = """
    <!-- PostHog. Copied from src/root.tsx:216-256 — this page is static and
         never mounts the React app, so it cannot inherit the app's analytics.
         Includes the same internal-tester opt-out, so testing from the VM or
         with ?fields_internal=1 does not pollute the funnel. -->
    <script>
      !function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="init capture register register_once unregister getFeatureFlag isFeatureEnabled reloadFeatureFlags onFeatureFlags identify setPersonProperties reset get_distinct_id get_session_id opt_in_capturing opt_out_capturing has_opted_out_capturing debug".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);
      try {
        var __p = new URLSearchParams(window.location.search);
        if (__p.get('fields_internal') === '1') localStorage.setItem('fields_internal', '1');
        var __internal = localStorage.getItem('fields_internal') === '1'
          || window.location.hostname === 'vm.fieldsestate.com.au'
          || (document.referrer || '').indexOf('vm.fieldsestate.com.au') !== -1;
      } catch (e) { var __internal = false; }
      posthog.init('phc_RQ68rG9adv6NYtoZS4JzmJVzVyOWUfprV9ceHb0nLEs', {
        api_host: 'https://us.i.posthog.com',
        person_profiles: 'always',
        capture_pageview: true,
        capture_pageleave: true,
        autocapture: true,
        persistence: 'localStorage+cookie',
        opt_out_capturing_by_default: __internal,
        disable_session_recording: __internal
      });
    </script>
"""

HEAD_EXTRA = """<base href="/fridge/">
<meta name="description" content="Scanned the magnet on your fridge? Everything happening in your street, in one place.">
<meta name="theme-color" content="#070908">
<meta property="og:title" content="Fields — open the fridge">
<meta property="og:description" content="Scanned the magnet on your fridge? Everything happening in your street, in one place.">
<link rel="preload" as="image" href="/fridge/assets/artwork.svg">
"""


def build_html():
    src = open(os.path.join(HERE, "index.html")).read()

    # <base> must come FIRST in <head> — it only governs elements after it.
    src = src.replace('<meta charset="utf-8">',
                      '<meta charset="utf-8">\n' + HEAD_EXTRA.rstrip(), 1)

    # PostHog immediately before our own scripts so window.posthog exists by the
    # time fridge.js fires fridge_land.
    src = src.replace('<script src="fridgeAudio.js"></script>',
                      POSTHOG.rstrip() + '\n\n<script src="fridgeAudio.js"></script>', 1)

    src = src.replace("<title>Fields — the fridge</title>",
                      "<title>Fields — open the fridge</title>", 1)

    banner = ("<!-- GENERATED by 15_Off-Market/Concepts/Fridge_Magnet_Concept/deploy.py — "
              "DO NOT EDIT HERE. Edit the concept and re-run deploy.py. -->\n")
    return banner + src


def md5(b):
    return hashlib.md5(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="dry run")
    a = ap.parse_args()

    out_html = os.path.join(WEB, "public", "fridge.html")
    out_dir  = os.path.join(WEB, "public", "fridge")
    html = build_html().encode()

    plan = [(out_html, html)]
    for f in CODE:
        plan.append((os.path.join(out_dir, f), open(os.path.join(HERE, f), "rb").read()))
    for f in ASSETS:
        plan.append((os.path.join(out_dir, "assets", f),
                     open(os.path.join(HERE, "assets", f), "rb").read()))

    changed = []
    for path, data in plan:
        old = open(path, "rb").read() if os.path.exists(path) else None
        if old is None or md5(old) != md5(data):
            changed.append(path)
            if not a.check:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "wb").write(data)

    total = sum(len(d) for _, d in plan)
    for path, data in plan:
        mark = "*" if path in changed else " "
        print(f" {mark} {len(data):>8,}  {os.path.relpath(path, WEB)}")
    print(f"\n   {total:,} bytes total, {len(changed)} changed"
          + ("  (dry run)" if a.check else ""))

    if changed and not a.check:
        rel = " ".join(sorted(os.path.relpath(p, WEB) for p, _ in plan))
        print("\nPush as ONE commit (one Netlify build):\n")
        print(f"  cd {WEB} && python3 scripts/push_website_files.py \\\n"
              f"    -m 'feat(fridge): QR landing page' \\\n    {rel} netlify.toml")


if __name__ == "__main__":
    main()
