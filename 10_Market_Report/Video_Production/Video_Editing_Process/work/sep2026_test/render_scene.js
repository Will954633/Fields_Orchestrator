#!/usr/bin/env node
// Render panel.html?scene=<id> to a transparent 1920x1080 PNG.
// Usage: node render_scene.js <scene_id> [outfile]
const puppeteer = require('/home/fields/Fields_Orchestrator/node_modules/puppeteer-core');
const path = require('path');

const scene = process.argv[2];
const out = process.argv[3] || path.join(__dirname, 'scenes', `${scene}.png`);
const htmlPath = 'file://' + path.join(__dirname, 'panel.html') + '?scene=' + encodeURIComponent(scene);

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: 'new',
    args: ['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage','--force-color-profile=srgb','--hide-scrollbars'],
    defaultViewport: { width: 1080, height: 1920, deviceScaleFactor: 1 },
  });
  const page = await browser.newPage();
  await page.goto(htmlPath, { waitUntil: 'networkidle0' });
  await new Promise(r => setTimeout(r, 400));
  await page.evaluate(() => window.__setT && window.__setT(9999)); // final/settled state
  await new Promise(r => setTimeout(r, 120));
  await page.screenshot({ path: out, omitBackground: true, clip: { x:0, y:0, width:1080, height:1920 } });
  await browser.close();
  console.log('wrote', out);
})().catch(e => { console.error(e); process.exit(1); });
