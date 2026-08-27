const puppeteer = require('/home/fields/Fields_Orchestrator/node_modules/puppeteer-core');
const path = require('path');
const fs = require('fs');

const DIR = __dirname;
const FRAMES = path.join(DIR, 'frames');
const FPS = 30;
const DUR = 12000;               // ms
const N = Math.round(DUR / 1000 * FPS);   // 360

const ARGS = ['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage','--disable-gpu',
  '--hide-scrollbars','--force-color-profile=srgb','--disable-features=MediaRouter','--mute-audio'];

(async () => {
  fs.rmSync(FRAMES, { recursive: true, force: true });
  fs.mkdirSync(FRAMES, { recursive: true });

  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: 'new',
    args: ARGS,
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1080, height: 1920, deviceScaleFactor: 1 });
  await page.goto('file://' + path.join(DIR, 'reel_scene.html'), { waitUntil: 'networkidle0' });
  await page.waitForFunction('window.__READY__===true', { timeout: 15000 });
  await page.evaluate(() => document.fonts && document.fonts.ready);

  const t0 = Date.now();
  for (let f = 0; f < N; f++) {
    const t = f * 1000 / FPS;
    await page.evaluate((tt) => window.seek(tt), t);
    await page.screenshot({
      path: path.join(FRAMES, String(f).padStart(4, '0') + '.png'),
      clip: { x: 0, y: 0, width: 1080, height: 1920 },
      optimizeForSpeed: true,
    });
    if (f % 60 === 0) console.log(`frame ${f}/${N}  (${Math.round((Date.now()-t0)/1000)}s)`);
  }
  console.log(`done ${N} frames in ${Math.round((Date.now()-t0)/1000)}s`);
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
