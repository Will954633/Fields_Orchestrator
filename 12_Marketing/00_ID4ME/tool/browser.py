"""Persistent-profile browser lifecycle for the ID4ME automation.

Chrome 136+ refuses --remote-debugging-port against the default user profile, so
attaching to an already-running everyday Chrome is not an option. Instead we run
a dedicated persistent profile: log in once interactively, and every later run
reuses the cookies stored on disk.
"""

from contextlib import contextmanager

from playwright.sync_api import sync_playwright

import config


@contextmanager
def browser_context(headless: bool = False, slow_mo: int = 0):
    """Yield a Playwright BrowserContext backed by the persistent ID4ME profile."""
    config.PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(config.PROFILE_DIR),
            channel=config.CHROME_CHANNEL,
            headless=headless,
            slow_mo=slow_mo,
            viewport={"width": 1500, "height": 950},
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx.set_default_timeout(config.DEFAULT_TIMEOUT_MS)
        try:
            yield ctx
        finally:
            ctx.close()


def first_page(ctx):
    """Return the context's initial page, creating one if Chrome opened none."""
    return ctx.pages[0] if ctx.pages else ctx.new_page()
