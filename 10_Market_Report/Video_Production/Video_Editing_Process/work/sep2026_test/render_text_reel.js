#!/usr/bin/env node
// Render panel_text_reel.html to a TRANSPARENT 1080x1920 frame sequence (word reveal).
//   node render_text_reel.js <total_dur_seconds> [fps]
const puppeteer = require('/home/fields/Fields_Orchestrator/node_modules/puppeteer-core');
const path = require('path'), fs = require('fs');

const total = parseFloat(process.argv[2] || '6');
const fps   = parseInt(process.argv[3] || '25', 10);
const W = 1080, H = 1920;
const htmlPath = 'file://' + path.join(__dirname, 'panel_text_reel.html');
const dir = path.join(__dirname, 'scenes', 'text_reel_frames');

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome', headless: 'new',
    args: ['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage','--force-color-profile=srgb','--hide-scrollbars'],
    defaultViewport: { width: W, height: H, deviceScaleFactor: 1 },
  });
  const page = await browser.newPage();
  await page.goto(htmlPath, { waitUntil: 'networkidle0' });
  await page.waitForFunction(() => window.__ready === true, { timeout: 15000 });
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  const N = Math.round(total * fps);
  for (let f = 0; f <= N; f++) {
    await page.evaluate(tt => window.__setT(tt), f / fps);
    await page.screenshot({ path: path.join(dir, `f${String(f).padStart(4,'0')}.png`), omitBackground: true,
      clip: { x:0, y:0, width:W, height:H } });
  }
  await browser.close();
  console.log(`wrote ${N+1} transparent frames -> ${dir}`);
})().catch(e => { console.error(e); process.exit(1); });
