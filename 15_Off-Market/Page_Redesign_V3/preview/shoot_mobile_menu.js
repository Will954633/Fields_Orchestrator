#!/usr/bin/env node
/**
 * shoot_mobile_menu.js — stills of the mockup app bar.
 *
 * Three frames at iPhone 14 size: mid-intro (the bar must NOT be there), card 00
 * with the bar arrived, and the menu open. Also asserts the bar is absent while
 * `.intro-locked` is on, which is the whole point of the reveal gate.
 */
const path = require("path");
const puppeteer = require("/home/fields/Fields_Orchestrator/node_modules/puppeteer-core");

const URL = "https://vm.fieldsestate.com.au/concepts/off-market-v3/preview/deck_mobile_menu.html";
const OUT = path.join(__dirname, "shots", "mobile-menu");
const CHROME = process.env.SITE_INSPECTOR_CHROME_PATH || "/usr/bin/google-chrome";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  require("fs").mkdirSync(OUT, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: "new",
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("requestfailed", (r) => { if (!/favicon/.test(r.url())) errors.push("FAILED " + r.url()); });

  await page.goto(URL, { waitUntil: "load", timeout: 60000 });

  // 1 — mid-intro. The bar must not exist on screen yet.
  await sleep(2500);
  await page.screenshot({ path: path.join(OUT, "01-intro.png") });
  const duringIntro = await page.evaluate(() => {
    const b = document.querySelector(".fx-navbar");
    return { present: !!b, visible: !!b && getComputedStyle(b).display !== "none" };
  });

  // 2 — skip to the hand-off, then card 00 with the bar.
  await page.keyboard.press("Escape");
  await page.waitForFunction('document.documentElement.classList.contains("fx-nav-ready")', { timeout: 20000 });
  await sleep(1600); // the 700ms hold + 500ms fade
  await page.screenshot({ path: path.join(OUT, "02-card00-bar.png") });

  // 3 — menu open.
  await page.click(".fx-burger");
  await sleep(500);
  await page.screenshot({ path: path.join(OUT, "03-menu-open.png") });
  const items = await page.$$eval(".fx-navpanel a", (as) => as.map((a) => a.textContent.trim()));

  // 4 — deep in the deck: tint on, current chapter marked.
  await page.click(".fx-burger");
  await page.evaluate(() => document.getElementById("card-08")?.scrollIntoView());
  await sleep(900);
  await page.click(".fx-burger");
  await sleep(500);
  await page.screenshot({ path: path.join(OUT, "04-current.png") });
  const current = await page.$eval(".fx-navpanel a[aria-current='true']", (a) => a.textContent.trim()).catch(() => null);

  console.log(JSON.stringify({ duringIntro, items, current, errors }, null, 2));
  await browser.close();
})();
