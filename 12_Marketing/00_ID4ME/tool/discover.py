"""Discovery tooling: learn how the ID4ME dashboard is actually built.

Two modes, both writing artefacts into ./discovery for inspection:

  dom    Navigate to the dashboard and dump the rendered HTML, a screenshot and
         an inventory of every input / button / form / link on the page.

  watch  Open the dashboard and record every network request for N seconds while
         a human performs one search by hand. This reveals the underlying search
         API, which is far faster and more stable to call than driving the UI.
"""

import json
import time
from datetime import datetime, timezone

import config
from browser import browser_context, first_page

ELEMENT_INVENTORY_JS = """
() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const describe = (el) => ({
    tag: el.tagName.toLowerCase(),
    type: el.getAttribute('type'),
    id: el.id || null,
    name: el.getAttribute('name'),
    placeholder: el.getAttribute('placeholder'),
    ariaLabel: el.getAttribute('aria-label'),
    role: el.getAttribute('role'),
    className: (el.getAttribute('class') || '').slice(0, 200),
    dataTestId: el.getAttribute('data-testid') || el.getAttribute('data-test') || null,
    text: (el.innerText || el.value || '').trim().slice(0, 120),
    visible: visible(el),
  });
  const grab = (sel) => Array.from(document.querySelectorAll(sel)).map(describe);
  return {
    url: location.href,
    title: document.title,
    inputs: grab('input, textarea, select'),
    buttons: grab('button, [role=button], input[type=submit]'),
    forms: Array.from(document.querySelectorAll('form')).map((f) => ({
      id: f.id || null,
      action: f.getAttribute('action'),
      method: f.getAttribute('method'),
      fields: Array.from(f.elements).map((e) => e.getAttribute('name')).filter(Boolean),
    })),
    links: grab('a[href]').filter((l) => l.visible).slice(0, 60),
    iframes: Array.from(document.querySelectorAll('iframe')).map((f) => ({
      src: f.getAttribute('src'), id: f.id || null, name: f.getAttribute('name'),
    })),
  };
}
"""


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _write(name: str, text: str) -> None:
    path = config.DISCOVERY_DIR / name
    path.write_text(text, encoding="utf-8")
    print(f"  wrote {path}")


def dump_dom(headless: bool = False, url: str | None = None) -> None:
    """Capture the dashboard's structure so selectors can be written from fact."""
    target = url or config.DASHBOARD_URL
    stamp = _stamp()
    with browser_context(headless=headless) as ctx:
        page = first_page(ctx)
        page.goto(target, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)  # let client-side rendering settle

        inventory = page.evaluate(ELEMENT_INVENTORY_JS)
        _write(f"dom_{stamp}.html", page.content())
        _write(f"inventory_{stamp}.json", json.dumps(inventory, indent=2))
        page.screenshot(path=str(config.DISCOVERY_DIR / f"screen_{stamp}.png"),
                        full_page=True)
        print(f"  wrote {config.DISCOVERY_DIR / f'screen_{stamp}.png'}")

        print(f"\nURL after load: {inventory['url']}")
        print(f"Title: {inventory['title']}")
        print(f"\nVisible inputs ({sum(1 for i in inventory['inputs'] if i['visible'])}):")
        for el in inventory["inputs"]:
            if el["visible"]:
                print(f"  {el}")
        print(f"\nVisible buttons:")
        for el in inventory["buttons"]:
            if el["visible"]:
                print(f"  {el['tag']} text={el['text']!r} id={el['id']} "
                      f"class={el['className'][:80]!r}")


def watch_network(seconds: int = 120, headless: bool = False) -> None:
    """Record network traffic while a human performs one search by hand."""
    stamp = _stamp()
    captured: list[dict] = []
    skip_types = {"image", "font", "stylesheet", "media"}

    with browser_context(headless=headless) as ctx:
        page = first_page(ctx)

        def on_response(response):
            req = response.request
            if req.resource_type in skip_types:
                return
            entry = {
                "method": req.method,
                "url": req.url,
                "resource_type": req.resource_type,
                "status": response.status,
                "post_data": (req.post_data or "")[:4000],
                "request_headers": {
                    k: v for k, v in req.headers.items()
                    if k.lower() in {"content-type", "accept", "x-requested-with",
                                     "authorization", "x-csrf-token", "referer"}
                },
            }
            ctype = (response.headers.get("content-type") or "")
            if "json" in ctype or req.resource_type in {"xhr", "fetch"}:
                try:
                    entry["response_body"] = response.text()[:20000]
                except Exception as exc:  # body may already be consumed/streamed
                    entry["response_body"] = f"<unavailable: {exc}>"
            captured.append(entry)

        ctx.on("response", on_response)
        page.goto(config.DASHBOARD_URL, wait_until="domcontentloaded")

        print("\n" + "=" * 72)
        print("  RECORDING NETWORK TRAFFIC")
        print(f"  In the Chrome window that just opened, search ONE address by hand.")
        print(f"  Recording for {seconds}s, then the browser closes automatically.")
        print("=" * 72 + "\n")

        deadline = time.time() + seconds
        while time.time() < deadline:
            page.wait_for_timeout(1000)
            remaining = int(deadline - time.time())
            if remaining % 15 == 0 and remaining > 0:
                print(f"  ...{remaining}s left, {len(captured)} requests captured")

        # Snapshot the results page too, so result selectors can be written.
        try:
            _write(f"results_dom_{stamp}.html", page.content())
            _write(f"results_inventory_{stamp}.json",
                   json.dumps(page.evaluate(ELEMENT_INVENTORY_JS), indent=2))
            page.screenshot(
                path=str(config.DISCOVERY_DIR / f"results_screen_{stamp}.png"),
                full_page=True)
        except Exception as exc:
            print(f"  (could not snapshot results page: {exc})")

    _write(f"network_{stamp}.json", json.dumps(captured, indent=2))

    interesting = [c for c in captured if c["resource_type"] in {"xhr", "fetch"}]
    print(f"\nCaptured {len(captured)} requests, {len(interesting)} XHR/fetch:")
    for c in interesting:
        print(f"  {c['status']} {c['method']} {c['url'][:130]}")
