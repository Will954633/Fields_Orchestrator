#!/usr/bin/env node
const puppeteer = require('/home/fields/Fields_Orchestrator/node_modules/puppeteer-core');
const path = require('path');
const OUT = path.join(__dirname, 'charts');
const URL = 'https://fieldsestate.com.au/news/gold-coast';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function sectionByH3(page, needle) {
  const handle = await page.evaluateHandle((needle) => {
    const h = [...document.querySelectorAll('h3')].find(e => e.textContent.includes(needle));
    return h ? h.closest('section') : null;
  }, needle);
  const el = handle.asElement();
  if (!el) throw new Error('no section for: ' + needle);
  return el;
}
async function scrollWait(page, el, waitSel) {
  await el.evaluate(e => e.scrollIntoView({block:'center'}));
  await sleep(1200);
  await page.waitForFunction((e,s) => !!e.querySelector(s), {timeout:30000}, el, waitSel);
  await sleep(800);
}

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome', headless: 'new',
    args: ['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage','--force-color-profile=srgb','--hide-scrollbars'],
    defaultViewport: { width: 1500, height: 1600, deviceScaleFactor: 2 },
  });
  const page = await browser.newPage();
  await page.goto(URL, { waitUntil: 'networkidle0', timeout: 90000 });
  await sleep(2000);
  // slow-scroll whole page to trigger any lazy renders
  await page.evaluate(async () => {
    for (let y=0; y<document.body.scrollHeight; y+=600){ window.scrollTo(0,y); await new Promise(r=>setTimeout(r,200)); }
    window.scrollTo(0,0);
  });
  await sleep(1500);

  // Chart 1
  const sec1 = await sectionByH3(page, 'Trading At');
  await scrollWait(page, sec1, 'svg');
  await sec1.evaluate(el => {
    const btn = [...el.querySelectorAll('button')].find(b => b.textContent.trim() === '3 years');
    if (btn) btn.click();
  });
  await sleep(1200);
  await sec1.screenshot({ path: path.join(OUT,'median_section.png') });
  // plot-only: nearest div ancestor of svg
  const svg1 = await sec1.$('svg');
  const wrap1 = await svg1.evaluateHandle(s => s.parentElement);
  await wrap1.asElement().screenshot({ path: path.join(OUT,'median.png') });
  console.log('chart1 done, structure:', await sec1.evaluate(el => el.className));

  // Chart 2
  const sec2 = await sectionByH3(page, 'Taking to Sell');
  await scrollWait(page, sec2, 'svg');
  const pressed = await sec2.evaluate(el => [...el.querySelectorAll('button[aria-pressed="true"]')].map(b=>b.textContent.trim()));
  console.log('DOM pressed:', pressed.join(' | '));
  await sec2.screenshot({ path: path.join(OUT,'dom_section.png') });
  const svg2 = await sec2.$('svg');
  const wrap2 = await svg2.evaluateHandle(s => s.parentElement);
  await wrap2.asElement().screenshot({ path: path.join(OUT,'dom.png') });
  console.log('chart2 done');

  // Chart 3
  const sec3 = await sectionByH3(page, 'Which Signals Actually Lead');
  await scrollWait(page, sec3, '.liexp #chart svg');
  await sec3.evaluate(el => { const b = el.querySelector('#rangeseg [data-range="3y"]'); if (b) b.click(); });
  await sleep(1500);
  await sec3.screenshot({ path: path.join(OUT,'signals_section.png') });
  const chart3 = await sec3.$('.liexp #chart');
  await chart3.screenshot({ path: path.join(OUT,'signals.png') });
  console.log('chart3 done');

  await browser.close();
  console.log('ALL DONE');
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
