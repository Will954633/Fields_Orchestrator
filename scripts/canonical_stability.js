/**
 * canonical_stability.js — does hydration change the canonical?
 *
 * Invariant C of scripts/sitemap_robots_invariant.py. Fetches each URL in a real
 * browser, captures the canonical from the SSR response body, then reads the DOM
 * canonical after JS has run. Googlebot renders JavaScript, so the post-hydration
 * value is what it actually indexes — and on 2026-08-08 a component rewrote it,
 * making /market-intelligence/Varsity-Lakes declare itself a duplicate of its own
 * child tab. Nothing compared the two values, so nothing noticed.
 *
 * Emits JSON on stdout: [{path, ssr, post, count, error}]
 *   usage: node canonical_stability.js <url> [<url> ...]
 */
const PUPPETEER = "/home/fields/Feilds_Website/01_Website/node_modules/puppeteer";
const SITE = "https://fieldsestate.com.au";

(async () => {
  let puppeteer;
  try {
    puppeteer = require(PUPPETEER);
  } catch (e) {
    // No harness available — emit nothing rather than a false pass. The caller
    // treats an empty result as "not checked", never as "checked and clean".
    process.stdout.write("[]");
    return;
  }
  const urls = process.argv.slice(2);
  const out = [];
  const browser = await puppeteer.launch({ args: ["--no-sandbox", "--disable-dev-shm-usage"] });
  for (const url of urls) {
    const path = url.replace(SITE, "");
    const page = await browser.newPage();
    let ssr = null;
    page.on("response", async (r) => {
      if (r.url() === url && ssr === null) {
        try {
          const m = (await r.text()).match(/<link rel="canonical" href="([^"]*)"/);
          ssr = m ? m[1] : "NONE";
        } catch (_) { /* body already consumed / redirect */ }
      }
    });
    try {
      await page.goto(url, { waitUntil: "networkidle2", timeout: 60000 });
      // The mutation that caused the incident happened in a useEffect, so give the
      // effects a beat to run — reading immediately would report a false pass.
      await new Promise((r) => setTimeout(r, 2500));
      const dom = await page.evaluate(() => {
        const els = document.querySelectorAll('link[rel="canonical"]');
        return { count: els.length, href: els.length ? els[0].href : null };
      });
      out.push({ path, ssr, post: dom.href, count: dom.count, error: null });
    } catch (e) {
      out.push({ path, ssr, post: null, count: 0, error: String(e.message).slice(0, 80) });
    }
    await page.close();
  }
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})();
