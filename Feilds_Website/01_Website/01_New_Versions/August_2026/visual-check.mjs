/* ==========================================================================
   Visual regression harness for the August 2026 rebuild.

     node visual-check.mjs baseline          -> capture production (main)
     node visual-check.mjs after  <base-url> -> capture the branch preview
     node visual-check.mjs diff              -> compare and report

   Phase 1 and 2 of the build plan claim to be visually neutral. That claim is
   only worth anything if it is measured, so this exists before any refactor.

   Note: screenshots are taken WITHOUT a `clip` — Puppeteer's clip uses page
   coordinates, not viewport, which silently produced misleading captures
   earlier in this project.
   ========================================================================== */
import { createRequire } from 'module';
import fs from 'node:fs';
import path from 'node:path';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');

const ROOT = '/home/fields/Fields_Orchestrator/Feilds_Website/01_Website/01_New_Versions/August_2026';
const PROD = 'https://fieldsestate.com.au';

export const ROUTES = [
  ['home',            '/'],
  // Added 2026-08-04. MarketIntelligencePage USED to be "/" and was covered by
  // the 'home' row. The cutover moved it to /news and made "/" the browse
  // surface — so this page silently lost regression coverage at the exact
  // moment it was most likely to break. Its two known faults (React #418 from
  // the Data Insights Strip's SSR placeholder, and mobile horizontal overflow)
  // went unseen in two full suite runs because of it.
  // Rule: when a route moves, the harness must follow it in the SAME change.
  ['news',            '/news'],
  ['for-sale-v3',     '/for-sale-v3'],
  ['property',        '/property/17-springvale-street-robina'],
  ['article',         '/articles/is-1-200-000-the-new-entry-price-for-a-house-in-robina'],
  ['market-sell-now', '/market-intelligence/Robina'],
  ['market-crash',    '/market-intelligence/Robina/crash-risk'],
  ['market-overview', '/market-intelligence/Robina/overview'],
  ['analyse-home',    '/analyse-your-home'],
  ['your-home',       '/your-home/13-terrace-court-merrimac'],
  ['why-fields',      '/why-fields'],
  ['contact',         '/contact'],
  ['discover',        '/discover'],
];

const WIDTHS = [['desktop', 1440, 1000], ['mobile', 390, 844]];

async function capture(dir, base) {
  fs.mkdirSync(dir, { recursive: true });
  const browser = await puppeteer.launch({
    headless: 'new', args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const report = [];

  for (const [name, route] of ROUTES) {
    for (const [label, w, h] of WIDTHS) {
      const page = await browser.newPage();
      const errors = [];
      page.on('pageerror', (e) => errors.push(e.message.slice(0, 120)));
      page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text().slice(0, 120)); });
      await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
      let status = 0;
      try {
        const res = await page.goto(base + route, { waitUntil: 'networkidle2', timeout: 90000 });
        status = res ? res.status() : 0;
        // settle lazy images, then return to top so captures are comparable
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await new Promise((r) => setTimeout(r, 2500));
        await page.evaluate(() => window.scrollTo(0, 0));
        await new Promise((r) => setTimeout(r, 1200));
        await page.screenshot({ path: path.join(dir, `${name}-${label}.png`) });
      } catch (e) {
        errors.push('NAV ' + e.message.slice(0, 100));
      }
      const probe = await page.evaluate(() => ({
        bodyBg: getComputedStyle(document.body).backgroundColor,
        bodyColor: getComputedStyle(document.body).color,
        font: getComputedStyle(document.body).fontFamily.split(',')[0].replace(/"/g, ''),
        headers: document.querySelectorAll('header').length,
        footers: document.querySelectorAll('footer').length,
        overflow: document.documentElement.scrollWidth > window.innerWidth,
        theme: document.documentElement.dataset.theme || null,
        h1: (document.querySelector('h1') || {}).textContent?.trim().slice(0, 60) || null,
      })).catch(() => ({}));
      report.push({ name, label, route, status, ...probe, errors: [...new Set(errors)] });
      await page.close();
    }
  }
  await browser.close();
  fs.writeFileSync(path.join(dir, '_report.json'), JSON.stringify(report, null, 1));
  return report;
}

function summarise(report, title) {
  console.log(`\n=== ${title} ===`);
  console.log('route'.padEnd(18) + 'vp'.padEnd(9) + 'st'.padEnd(5) + 'hdr/ftr'.padEnd(9)
              + 'ovf'.padEnd(5) + 'font'.padEnd(8) + 'errors');
  for (const r of report) {
    console.log(
      r.name.padEnd(18) + r.label.padEnd(9) + String(r.status).padEnd(5) +
      `${r.headers ?? '?'}/${r.footers ?? '?'}`.padEnd(9) +
      (r.overflow ? 'YES' : '-').padEnd(5) +
      String(r.font ?? '?').slice(0, 7).padEnd(8) +
      (r.errors?.length ? r.errors.length + ' ' + r.errors[0].slice(0, 50) : '-'));
  }
  const bad = report.filter((r) => r.status !== 200 || r.overflow || r.errors?.length);
  console.log(`\n${report.length} captures · ${bad.length} with issues`);
}

const mode = process.argv[2] || 'baseline';
if (mode === 'baseline') {
  summarise(await capture(path.join(ROOT, 'baseline'), PROD), 'BASELINE (production / main)');
} else if (mode === 'after') {
  const base = process.argv[3];
  if (!base) { console.error('usage: node visual-check.mjs after <base-url>'); process.exit(1); }
  summarise(await capture(path.join(ROOT, 'after'), base), `AFTER (${base})`);
} else if (mode === 'diff') {
  const a = JSON.parse(fs.readFileSync(path.join(ROOT, 'baseline/_report.json')));
  const b = JSON.parse(fs.readFileSync(path.join(ROOT, 'after/_report.json')));
  console.log('\n=== DIFF (baseline -> after) ===');
  let n = 0;
  for (const x of a) {
    const y = b.find((z) => z.name === x.name && z.label === x.label);
    if (!y) { console.log(`${x.name}/${x.label}: MISSING in after`); n++; continue; }
    for (const k of ['status', 'bodyBg', 'bodyColor', 'font', 'headers', 'footers', 'overflow']) {
      if (JSON.stringify(x[k]) !== JSON.stringify(y[k])) {
        console.log(`${x.name}/${x.label}  ${k}: ${JSON.stringify(x[k])} -> ${JSON.stringify(y[k])}`);
        n++;
      }
    }
    if ((y.errors || []).length > (x.errors || []).length) {
      console.log(`${x.name}/${x.label}  NEW ERRORS: ${y.errors.slice(0, 2).join(' | ')}`);
      n++;
    }
  }
  console.log(n ? `\n${n} differences — each must be intended.` : '\nNo measurable differences.');
}
