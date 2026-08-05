#!/usr/bin/env python3
"""Mobile app-bar + chapter-menu MOCKUP for the V3 off-market deck.

Takes the deck preview that build_deck_preview.py already produced and injects
one stylesheet and one script, writing a SECOND file beside it. The mockup is
therefore the real deck — real intro, real cards, real outro — with the bar
added, rather than an approximation of it, and `deck.html` is left untouched so
the two can be compared side by side.

    python3 build_mobile_menu_mockup.py                 # from preview/deck.html
    python3 build_mobile_menu_mockup.py --src examples/<slug>.html

Then: https://vm.fieldsestate.com.au/concepts/off-market-v3/preview/deck_mobile_menu.html
(open it in a phone-sized window — the bar is built mobile-first).
"""
import argparse
import base64
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGO = Path("/home/fields/Fields_Orchestrator/00_Run_Commands/Logo_Files/"
            "logo_pack/2-Birch/• PNG/1-Fields-Hero-Grass.png")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(HERE / "deck.html"))
    ap.add_argument("--out", default=str(HERE / "deck_mobile_menu.html"))
    a = ap.parse_args()

    src, out = Path(a.src), Path(a.out)
    html = src.read_text()
    assert "</head>" in html and "</body>" in html, "deck markup changed shape"

    # The logo is copied rather than inlined as a data URI: the deck already
    # carries ~160KB of markup and the browser caches a file, not a URI.
    shutil.copyfile(LOGO, out.parent / "mobile_menu_logo.png")

    css = (HERE / "mobile_menu.css").read_text()
    js = (HERE / "mobile_menu.js").read_text()

    # The script runs at the END of body, after the deck sections exist — it
    # reads them to build the menu. Registering the `fields:intro-done` listener
    # here is still in time: the intro dispatches it seconds later.
    html = html.replace("</head>", f"<style>\n{css}\n</style>\n</head>", 1)
    html = html.replace("</body>", f"<script>\n{js}\n</script>\n</body>", 1)

    out.write_text(html)
    print(f"{out}  ({round(out.stat().st_size / 1024)} KB)")
    print("https://vm.fieldsestate.com.au/concepts/off-market-v3/preview/"
          + out.name)


if __name__ == "__main__":
    main()
