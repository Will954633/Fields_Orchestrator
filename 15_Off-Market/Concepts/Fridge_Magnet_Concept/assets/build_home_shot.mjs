/* Captures the homepage as a still for the secret-door reveal.
   A live <iframe> was rejected: it fires the homepage's own PostHog (phantom
   sessions with odd referrers), costs a full page load on every fridge visit,
   and — decisive — can reveal a BLANK box if it hasn't painted, which ruins the
   one moment it exists for. A still always paints.
   ⚠ It goes stale when the homepage changes. Re-run this. */
import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');
const b = await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-dev-shm-usage']});
const p = await b.newPage();
await p.setViewport({width:390,height:844,deviceScaleFactor:2});
await p.goto('https://fieldsestate.com.au/?fields_internal=1',{waitUntil:'networkidle0'});
await new Promise(r=>setTimeout(r,2500));
await p.evaluate(()=>{ // no cookie banners / overlays in the reveal
  document.querySelectorAll('[class*="cookie" i],[class*="consent" i],[id*="cookie" i]').forEach(e=>e.remove());
  window.scrollTo(0,0);
});
await p.screenshot({path:'assets/home_raw.png'});
await b.close();
console.log('captured assets/home_raw.png');
