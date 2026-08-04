/**
 * BreakGlass verification. The 24/26-capture visual-check suite does NOT cover
 * this component: it measures page-level properties and never scrolls to the
 * footer or exercises an interaction, so it reports "no measurable differences"
 * whether the break-glass works or is completely broken. Run this too.
 *
 *   node break-glass-check.mjs      # SSR gating, lazy loading, break + pull
 *   node break-glass-a11y.mjs       # CLS, keyboard path, prefers-reduced-motion
 *
 * Pass the branch/prod URL by editing B below.
 */
import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');
const B = 'https://august-2026-rebuild--lambent-tapioca-86ef75.netlify.app';
const OUT = '/tmp/claude-1001/-home-fields-Fields-Orchestrator/054cebcf-18cc-499b-8cf2-1ec7d233cecd/scratchpad';

const b = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox', '--disable-dev-shm-usage'] });

// ---- 1. SSR must not crash, and must not reference /break-glass/ in server HTML
const html = await (await fetch(B + '/')).text();
console.log(`SSR: page renders (${html.length} bytes), footer present=${html.includes('194 Varsity Parade')}`);
console.log(`SSR: /break-glass/ in server HTML = ${html.includes('/break-glass/')}  (expect false — gated on inView)`);

// ---- 2. Not on other routes
const other = await (await fetch(B + '/why-fields')).text();
console.log(`SSR: /why-fields contains break-glass markup = ${other.includes('break-glass')}  (expect false)`);

for (const [label, w, h] of [['desktop', 1440, 950], ['mobile', 390, 844]]) {
  const p = await b.newPage();
  const errs = [], reqs = [];
  p.on('pageerror', e => errs.push(e.message.match(/#\d+/)?.[0] ?? e.message.slice(0, 40)));
  p.on('request', r => { if (r.url().includes('/break-glass/')) reqs.push(r.url().split('/').pop()); });
  await p.setViewport({ width: w, height: h });
  await p.goto(B + '/', { waitUntil: 'networkidle2', timeout: 90000 });
  await new Promise(r => setTimeout(r, 2000));

  // 3. no eager fetch before the footer is approached
  const eagerCount = reqs.length;

  // 4. CLS-safe: does the stage reserve space?
  await p.evaluate(() => document.querySelector('footer')?.scrollIntoView({ block: 'end' }));
  await new Promise(r => setTimeout(r, 2500));

  const geo = await p.evaluate(() => {
    const st = document.querySelector('[class*=stage]');
    if (!st) return { found: false };
    const r = st.getBoundingClientRect();
    const loc = [...document.querySelectorAll('span')].find(s => s.textContent.includes('194 Varsity Parade'));
    const lr = loc ? loc.getBoundingClientRect() : null;
    return {
      found: true,
      stage: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
      addr: lr ? { x: Math.round(lr.x), cx: Math.round(lr.x + lr.width / 2), bottom: Math.round(lr.bottom) } : null,
      stageCx: Math.round(r.x + r.width / 2),
      imgs: st.querySelectorAll('img').length,
      hScroll: document.documentElement.scrollWidth > innerWidth + 1,
    };
  });
  console.log(`\n${label}: stage ${JSON.stringify(geo.stage)} imgs=${geo.imgs}`);
  console.log(`${label}: assets before footer approach = ${eagerCount} (expect 0), after = ${reqs.length}`);
  console.log(`${label}: stage centre x=${geo.stageCx} vs address centre x=${geo.addr?.cx} (want them close)`);
  console.log(`${label}: below address? stage.y=${geo.stage?.y} > addr.bottom=${geo.addr?.bottom} => ${geo.stage?.y > geo.addr?.bottom}`);
  console.log(`${label}: hScroll=${geo.hScroll ? 'YES ✗' : 'no ✓'}  errs=[${[...new Set(errs)].join(',') || 'none ✓'}]`);

  await p.screenshot({ path: `${OUT}/glass-${label}.png` });

  // 5. break it, then pull it — real mouse events (synthetic click never reaches React/DOM handlers reliably)
  const hit = await p.evaluate(() => {
    const el = document.querySelector('[data-x="hit-glass"]');
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  });
  if (hit) {
    await p.mouse.click(hit.x, hit.y);
    await new Promise(r => setTimeout(r, 2400));
    const after = await p.evaluate(() => {
      const st = document.querySelector('[class*=stage]');
      const hh = st.querySelector('[data-x="hit-handle"]');
      const prompt = st.querySelector('[data-x="prompt"]');
      return { handleArmed: hh && !hh.hidden, prompt: (prompt?.textContent || '').trim(),
               assets: [...st.querySelectorAll('img')].length };
    });
    console.log(`${label}: after break -> handleArmed=${after.handleArmed} prompt="${after.prompt}" (expect "Pull down")`);
    await p.screenshot({ path: `${OUT}/glass-${label}-broken.png` });

    const hb = await p.evaluate(() => {
      const el = document.querySelector('[data-x="hit-handle"]');
      if (!el || el.hidden) return null;
      const r = el.getBoundingClientRect();
      return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    });
    if (hb) {
      await p.mouse.click(hb.x, hb.y);
      await new Promise(r => setTimeout(r, 1600));
      const pulled = await p.evaluate(() => {
        const st = document.querySelector('[class*=stage]');
        const down = st.querySelector('[data-x="l-down"]');
        return { downVisible: down && getComputedStyle(down).opacity === '1' };
      });
      console.log(`${label}: after pull  -> latch frame visible=${pulled.downVisible} (expect true)`);
      await p.screenshot({ path: `${OUT}/glass-${label}-pulled.png` });
    } else console.log(`${label}: handle hit target not available ✗`);
  } else console.log(`${label}: glass hit target NOT FOUND ✗`);
  await p.close();
}
await b.close();
