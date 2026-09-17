#!/usr/bin/env node
// Render panel_fs.html (1920x1080, opaque) either as a single settled PNG or an
// animated frame sequence driven by window.__setT(t).
//   node render_fs.js still <outfile>
//   node render_fs.js anim <active_dur_seconds> <total_dur_seconds> [fps]
const puppeteer = require('/home/fields/Fields_Orchestrator/node_modules/puppeteer-core');
const path = require('path'), fs = require('fs');

const mode = process.argv[2] || 'still';
const htmlPath = 'file://' + path.join(__dirname, 'panel_fs.html');
const W = 1920, H = 1080;

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome', headless: 'new',
    args: ['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage','--force-color-profile=srgb','--hide-scrollbars'],
    defaultViewport: { width: W, height: H, deviceScaleFactor: 1 },
  });
  const page = await browser.newPage();
  await page.goto(htmlPath, { waitUntil: 'networkidle0' });
  await page.waitForFunction(() => window.__ready === true, { timeout: 15000 });

  if (mode === 'still') {
    const out = process.argv[3] || path.join(__dirname, 'fs_still.png');
    await page.evaluate(() => window.__setT(9999));
    await new Promise(r => setTimeout(r, 120));
    await page.screenshot({ path: out, clip: { x:0, y:0, width:W, height:H } });
    console.log('wrote', out);
  } else {
    const active = parseFloat(process.argv[3]);   // animation completes by here
    const total  = parseFloat(process.argv[4]);   // render this many seconds of frames
    const fps    = parseInt(process.argv[5] || '25', 10);
    const dir = path.join(__dirname, 'scenes', 'fs_frames');
    fs.rmSync(dir, { recursive: true, force: true });
    fs.mkdirSync(dir, { recursive: true });
    const N = Math.round(total * fps);
    for (let f = 0; f <= N; f++) {
      const t = f / fps;
      await page.evaluate(tt => window.__setT(tt), t);
      await page.screenshot({ path: path.join(dir, `f${String(f).padStart(4,'0')}.png`), clip: { x:0, y:0, width:W, height:H } });
    }
    console.log(`wrote ${N+1} frames -> ${dir}`);
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
