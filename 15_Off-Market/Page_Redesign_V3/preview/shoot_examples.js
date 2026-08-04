#!/usr/bin/env node
/**
 * shoot_examples.js — desktop and mobile stills of every example deck.
 *
 * For each built example: skip the intro, walk card by card, and shoot. The
 * emblem video is seeked to its last frame rather than being waited out, so a
 * still always shows the finished drawing instead of whatever moment the
 * screenshot happened to land on.
 *
 * Writes shots/<slug>/<device>-<nn>-<id>.png and an index.json, then
 * examples.html is generated from those by build_examples_index.py.
 *
 * Usage:
 *   node shoot_examples.js                 # all examples, both devices
 *   node shoot_examples.js --only 8-corina-close-robina
 *   node shoot_examples.js --device mobile
 */

const fs = require("fs");
const path = require("path");
const puppeteer = require("/home/fields/Fields_Orchestrator/node_modules/puppeteer-core");

const HERE = __dirname;
const BASE = "https://vm.fieldsestate.com.au/concepts/off-market-v3/preview/examples";
const SHOTS = path.join(HERE, "shots");
const CHROME = process.env.SITE_INSPECTOR_CHROME_PATH || "/usr/bin/google-chrome";

const DEVICES = {
  desktop: { width: 1440, height: 900, deviceScaleFactor: 1, isMobile: false },
  // iPhone 14 logical viewport. deviceScaleFactor 2 so the hatch in the emblem
  // survives — at 1 the fine strokes alias into mush and the still misrepresents
  // what the reader actually sees on the device.
  mobile:  { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true,
             hasTouch: true },
};

function args() {
  const a = process.argv.slice(2);
  const o = { only: null, device: null };
  for (let i = 0; i < a.length; i++) {
    if (a[i] === "--only") o.only = a[++i];
    else if (a[i] === "--device") o.device = a[++i];
  }
  return o;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function shoot(browser, slug, device, spec) {
  const page = await browser.newPage();
  await page.setViewport(spec);
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("requestfailed", (r) => {
    // favicon and other incidentals are not worth failing a run over
    if (!/favicon/.test(r.url())) errors.push("404 " + r.url().split("/").pop());
  });

  await page.goto(`${BASE}/${slug}.html`, { waitUntil: "load", timeout: 60000 });

  // Skip the intro rather than sitting through 11s per shot. Escape is the
  // documented skip; fall back to removing the lock if the intro failed to boot.
  await page.keyboard.press("Escape");
  await page.waitForFunction(
    '!document.documentElement.classList.contains("intro-locked")',
    { timeout: 20000 }
  ).catch(() => page.evaluate(() =>
    document.documentElement.classList.remove("intro-locked")));

  // Reveal everything up front: the IntersectionObserver only fires for cards
  // that pass through the viewport, and scroll-jumping can skip one entirely.
  await page.evaluate(() => {
    document.querySelectorAll(".card").forEach((c) => c.classList.add("revealIn"));
  });

  // Park the emblem on its finished frame.
  await page.evaluate(async () => {
    const v = document.getElementById("emblem");
    if (!v) return;
    if (!v.src) { v.src = v.dataset.src; v.load(); }
    document.getElementById("media")?.classList.add("mediaIn");
    await new Promise((res) => {
      const done = () => res();
      if (v.readyState >= 2) return done();
      v.addEventListener("loadeddata", done, { once: true });
      setTimeout(done, 8000);
    });
    try { v.pause(); v.currentTime = Math.max(0, (v.duration || 6) - 0.05); } catch (_) {}
    await new Promise((res) => {
      v.addEventListener("seeked", res, { once: true });
      setTimeout(res, 2500);
    });
  });

  const cards = await page.evaluate(() =>
    [...document.querySelectorAll(".card")].map((c, i) => ({
      id: c.id || `card-${i}`, n: c.dataset.n || "",
    })));

  const dir = path.join(SHOTS, slug);
  fs.mkdirSync(dir, { recursive: true });
  const shots = [];
  for (let i = 0; i < cards.length; i++) {
    const { id } = cards[i];
    // By index, not by id. An id that does not resolve makes scrollIntoView a
    // silent no-op, and the pass shoots the previous card again without failing.
    const ok = await page.evaluate((idx) => {
      const el = document.querySelectorAll(".card")[idx];
      if (!el) return false;
      el.scrollIntoView({ behavior: "instant", block: "start" });
      return true;
    }, i);
    if (!ok) { errors.push(`card ${i} not found`); continue; }
    await sleep(450);
    // Clip to the card, not the viewport. Cards are min-height:100svh but grow
    // past it when the copy is long — card 03 on a phone carries the lead, the
    // ticks, the rarity callout, the doorstep list AND the drawing, so a
    // viewport shot would silently crop the drawing out of the review.
    const box = await page.evaluate((idx) => {
      const el = document.querySelectorAll(".card")[idx];
      const r = el.getBoundingClientRect();
      return { x: 0, y: Math.max(0, r.top + scrollY), width: innerWidth,
               height: Math.ceil(r.height) };
    }, i);
    const file = `${device}-${String(i).padStart(2, "0")}-${id}.png`;
    await page.screenshot({ path: path.join(dir, file), clip: box,
                            captureBeyondViewport: true });
    shots.push({ file, h: box.height, overflows: box.height > spec.height + 4 });
  }
  await page.close();
  const over = shots.filter((s) => s.overflows).length;
  return { slug, device, shots: shots.map((s) => s.file), over,
           errors: [...new Set(errors)] };
}

async function main() {
  const o = args();
  const slugs = fs.readdirSync(path.join(HERE, "examples"))
    .filter((f) => f.endsWith(".html"))
    .map((f) => f.replace(/\.html$/, ""))
    .filter((s) => !o.only || s === o.only)
    .sort();
  const devices = Object.keys(DEVICES).filter((d) => !o.device || d === o.device);
  if (!slugs.length) { console.error("no examples built — run build_deck_preview.py --all"); process.exit(1); }

  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: "new",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
           "--disable-gpu", "--mute-audio", "--autoplay-policy=no-user-gesture-required"],
  });

  const index = {};
  try {
    for (const slug of slugs) {
      index[slug] = {};
      for (const device of devices) {
        const r = await shoot(browser, slug, device, DEVICES[device]);
        index[slug][device] = r.shots;
        const bad = r.errors.length ? `  ⚠ ${r.errors.join("; ")}` : "";
        const ov = r.over ? `  (${r.over} card(s) taller than one screen)` : "";
        console.log(`  ${slug.padEnd(36)} ${device.padEnd(8)} `
                    + `${String(r.shots.length).padStart(2)} shots${ov}${bad}`);
      }
    }
  } finally {
    await browser.close();
  }
  fs.mkdirSync(SHOTS, { recursive: true });
  fs.writeFileSync(path.join(SHOTS, "index.json"), JSON.stringify(index, null, 2));
  console.log(`\nwrote ${Object.keys(index).length} example(s) to preview/shots/`);
}

main().catch((e) => { console.error(e); process.exit(1); });
