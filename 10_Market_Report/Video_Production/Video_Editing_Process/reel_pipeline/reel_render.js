#!/usr/bin/env node
// Render any reel panel (text_reel.html / chart_reel.html) to a 1080x1920 frame
// sequence, injecting a scene JSON and driving window.__setT(t).
//
//   node reel_render.js <panel.html> <scene.json> <outFramesDir> <durationS> <fps> <transparent:0|1>
//
// transparent=1 -> omitBackground (text overlay). transparent=0 -> opaque (chart bg).
const puppeteer = require('/home/fields/Fields_Orchestrator/node_modules/puppeteer-core');
const path = require('path'), fs = require('fs');

const [,, panel, sceneJson, outDir, durS, fpsS, transS] = process.argv;
const dur = parseFloat(durS), fps = parseInt(fpsS||'25',10), transparent = transS==='1';
const W = 1080, H = 1920;
const scene = JSON.parse(fs.readFileSync(sceneJson, 'utf8'));
const htmlPath = 'file://' + path.resolve(panel);

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome', headless: 'new',
    args: ['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage','--force-color-profile=srgb','--hide-scrollbars'],
    defaultViewport: { width: W, height: H, deviceScaleFactor: 1 },
  });
  const page = await browser.newPage();
  await page.goto(htmlPath, { waitUntil: 'networkidle0' });
  await page.waitForFunction(() => window.__panelReady === true, { timeout: 15000 });
  await page.evaluate(s => window.__build(s), scene);
  await new Promise(r => setTimeout(r, 120));
  fs.rmSync(outDir, { recursive: true, force: true });
  fs.mkdirSync(outDir, { recursive: true });
  const N = Math.round(dur * fps);
  for (let f = 0; f <= N; f++) {
    await page.evaluate(tt => window.__setT(tt), f / fps);
    await page.screenshot({ path: path.join(outDir, `f${String(f).padStart(4,'0')}.png`),
      omitBackground: transparent, clip: { x:0, y:0, width:W, height:H } });
  }
  await browser.close();
  console.log(`wrote ${N+1} frames -> ${outDir}`);
})().catch(e => { console.error(e); process.exit(1); });
