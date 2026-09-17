#!/usr/bin/env node
// Render an ANIMATED scene to a PNG frame sequence by driving window.__setT(t).
// Reuses one page (no reload per frame) so it's fast.
// Usage: node render_anim.js <scene_id> <active_dur_seconds> [fps]
const puppeteer = require('/home/fields/Fields_Orchestrator/node_modules/puppeteer-core');
const path = require('path'), fs = require('fs');

const scene = process.argv[2];
const dur = parseFloat(process.argv[3]);
const fps = parseInt(process.argv[4] || '25', 10);
const dir = path.join(__dirname, 'scenes', `${scene}_frames`);
fs.rmSync(dir, { recursive: true, force: true });
fs.mkdirSync(dir, { recursive: true });
const htmlPath = 'file://' + path.join(__dirname, 'panel.html') + '?scene=' + encodeURIComponent(scene);

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome', headless: 'new',
    args: ['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage','--force-color-profile=srgb','--hide-scrollbars'],
    defaultViewport: { width: 1080, height: 1920, deviceScaleFactor: 1 },
  });
  const page = await browser.newPage();
  await page.goto(htmlPath, { waitUntil: 'networkidle0' });
  await page.waitForFunction(() => window.__ready === true, { timeout: 15000 });
  const N = Math.round(dur * fps);
  for (let f = 0; f <= N; f++) {
    const t = f / fps;
    await page.evaluate(tt => window.__setT(tt), t);
    await page.screenshot({ path: path.join(dir, `f${String(f).padStart(4,'0')}.png`), omitBackground: true,
      clip: { x:0, y:0, width:1080, height:1920 } });
  }
  // freeze frame = last one, for holding after the animation completes
  fs.copyFileSync(path.join(dir, `f${String(N).padStart(4,'0')}.png`), path.join(__dirname, 'scenes', `${scene}_last.png`));
  await browser.close();
  console.log(`wrote ${N+1} frames -> ${dir}  (+ ${scene}_last.png)`);
})().catch(e => { console.error(e); process.exit(1); });
