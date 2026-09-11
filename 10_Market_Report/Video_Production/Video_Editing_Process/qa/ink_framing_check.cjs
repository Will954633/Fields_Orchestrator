/* ask_zoom_check.cjs — verify two walkthrough ink states on a /news suburb page:
 *   1. asking-chart zoom (t~320 Robina v2): every red ink circle inside the visible chart box
 *   2. withdrawn zoom (t~386 Robina v2): "23"/"53" notes must not overlap the caption (#wkChip),
 *      and each note sits ABOVE the topmost red circle's bottom edge region it belongs to.
 * Usage: NODE_PATH=... node ask_zoom_check.cjs <baseUrl> <outPrefix> <tAsking> <tWithdrawn>
 */
'use strict';
const puppeteer = require('puppeteer');

const baseUrl = process.argv[2] || 'https://fieldsestate.com.au/news/robina';
const outPrefix = process.argv[3] || '/tmp/ask_zoom';
const T_ASK = parseFloat(process.argv[4] || '320');
const T_DS = parseFloat(process.argv[5] || '386');

const VIEWPORTS = [
  { name: 'desktop', width: 1280, height: 1024, deviceScaleFactor: 1, isMobile: false, hasTouch: false },
  { name: 'mobile', width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
];

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function seekTo(page, t) {
  await page.evaluate((T) => { const v = document.getElementById('wkVid'); if (v) { v.pause(); v.currentTime = T; } }, t);
  await sleep(2200);
  await page.evaluate((T) => { const v = document.getElementById('wkVid'); if (v) { v.pause(); v.currentTime = T; } }, t);
  await sleep(400);
}

function collect(chartSel) {
  const svg = document.querySelector(chartSel);
  if (!svg) return { err: 'no svg ' + chartSel };
  const sr = svg.getBoundingClientRect();
  const box = { left: sr.left, top: sr.top, right: sr.right, bottom: sr.bottom };
  const circles = [];
  document.querySelectorAll('#wkInk path[stroke="#dc3545"], #wkInkWrap path[stroke="#dc3545"]').forEach(p => {
    const r = p.getBoundingClientRect();
    if (r.width < 10 || r.height < 10) return;
    circles.push({ left: r.left, top: r.top, right: r.right, bottom: r.bottom,
      cx: (r.left + r.right) / 2, cy: (r.top + r.bottom) / 2 });
  });
  const notes = [];
  document.querySelectorAll('.wk-note').forEach(n => {
    const r = n.getBoundingClientRect();
    if (!r.width) return;
    notes.push({ text: (n.textContent || '').trim(), left: r.left, top: r.top, right: r.right, bottom: r.bottom });
  });
  let cap = null;
  const chip = document.getElementById('wkChip');
  const capEl = document.getElementById('wkCap');
  if (chip && capEl && !capEl.classList.contains('hide')) {
    const r = chip.getBoundingClientRect();
    if (r.width) cap = { left: r.left, top: r.top, right: r.right, bottom: r.bottom, text: (chip.textContent || '').slice(0, 40) };
  }
  return { box, viewBox: svg.getAttribute('viewBox'), circles, notes, cap };
}

function overlaps(a, b) {
  return Math.min(a.right, b.right) - Math.max(a.left, b.left) > 2 &&
         Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 2;
}

(async () => {
  const browser = await puppeteer.launch({
    headless: 'new', executablePath: '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  });
  let bad = 0;
  for (const vp of VIEWPORTS) {
    const page = await browser.newPage();
    await page.setViewport(vp);
    page.setDefaultNavigationTimeout(60000);
    try { await page.goto(baseUrl, { waitUntil: 'networkidle2', timeout: 60000 }); } catch (e) { console.error(`[${vp.name}] nav: ${e.message}`); }
    await sleep(2000);
    try { await page.waitForSelector('[data-tour="play"]', { timeout: 15000 }); await page.click('[data-tour="play"]'); }
    catch (e) { console.error(`[${vp.name}] play: ${e.message}`); }
    await sleep(2500);

    // --- check 1: asking zoom ---
    await seekTo(page, T_ASK);
    let info = await page.evaluate(collect, '#askingChartHost svg.chart-svg');
    if (info.err) { console.error(`[${vp.name}] ASK: ${info.err}`); bad++; }
    else {
      console.log(`[${vp.name}] ASK t=${T_ASK} viewBox=${info.viewBox}`);
      if (!info.circles.length) { console.log('  ASK: NO CIRCLES FOUND'); bad++; }
      info.circles.forEach((c, i) => {
        const inside = c.cx >= info.box.left && c.cx <= info.box.right && c.cy >= info.box.top && c.cy <= info.box.bottom;
        console.log(`  ASK circle ${i}: centre (${c.cx.toFixed(0)},${c.cy.toFixed(0)}) → ${inside ? 'INSIDE' : 'OFF-CHART'}`);
        if (!inside) bad++;
      });
    }
    await page.screenshot({ path: `${outPrefix}_${vp.name}_ask_t${T_ASK}.png`, fullPage: false });

    // --- check 2: withdrawn zoom, "23"/"53" vs caption ---
    await seekTo(page, T_DS);
    info = await page.evaluate(collect, '#dsChartHost svg.chart-svg');
    if (info.err) { console.error(`[${vp.name}] DS: ${info.err}`); bad++; }
    else {
      console.log(`[${vp.name}] DS t=${T_DS} viewBox=${info.viewBox} cap=${info.cap ? JSON.stringify(info.cap.text) : 'none'}`);
      const nums = info.notes.filter(n => n.text === '23' || n.text === '53');
      if (!nums.length) { console.log('  DS: no 23/53 notes found'); bad++; }
      nums.forEach(n => {
        const onCap = info.cap && overlaps(n, info.cap);
        console.log(`  DS note "${n.text}": top=${n.top.toFixed(0)} bottom=${n.bottom.toFixed(0)} → ${onCap ? 'OVERLAPS CAPTION' : 'clear of caption'}`);
        if (onCap) bad++;
        // note should sit above the centre of its nearest circle
        let nearest = null, nd = 1e9;
        info.circles.forEach(c => { const d = Math.hypot((n.left + n.right) / 2 - c.cx, (n.top + n.bottom) / 2 - c.cy); if (d < nd) { nd = d; nearest = c; } });
        if (nearest) {
          const above = n.bottom <= nearest.cy;
          console.log(`    vs nearest circle centre (${nearest.cx.toFixed(0)},${nearest.cy.toFixed(0)}): ${above ? 'ABOVE' : 'NOT ABOVE'}`);
          if (n.text === '23' && !above) bad++;
        }
      });
    }
    await page.screenshot({ path: `${outPrefix}_${vp.name}_ds_t${T_DS}.png`, fullPage: false });
    await page.close();
  }
  await browser.close();
  console.log(bad ? `RESULT: ${bad} problem(s)` : 'RESULT: clean');
})();
