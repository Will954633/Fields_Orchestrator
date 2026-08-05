#!/usr/bin/env bash
# Every destination must RENDER, not merely return 200.
#
# /sold returned HTTP 200 and was signed off as working. It renders the Not
# Found page: the React Router catch-all ($.tsx) has no loader, so a soft 404
# is indistinguishable from a real page by status code alone. The correct route
# was /recently-sold. Check the rendered text, never the status.
set -e
cd "$(dirname "$0")/.."
node - <<'JS'
import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');
const fs = require('fs');
const html = fs.readFileSync('index.html','utf8');
const hrefs = [...html.matchAll(/<a href="(https:\/\/fieldsestate\.com\.au[^"]+)"/g)].map(m=>m[1]);
const b = await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-dev-shm-usage']});
let bad = 0;
for (const u of hrefs) {
  const p = await b.newPage(); await p.setViewport({width:390,height:844});
  await p.goto(u,{waitUntil:'domcontentloaded'});
  await new Promise(r=>setTimeout(r,4000));
  const d = await p.evaluate(()=>({t:document.title,len:document.body.innerText.length,
    nf:/not found/i.test(document.title)||/not found/i.test(document.body.innerText.slice(0,400))}));
  const ok = !d.nf && d.len > 300;
  if (!ok) bad++;
  console.log(`  ${ok?'OK  ':'FAIL'}  ${u.replace('https://fieldsestate.com.au','').padEnd(26)} ${String(d.len).padStart(6)}ch  ${d.t.slice(0,44)}`);
  await p.close();
}
await b.close();
if (bad) { console.log(`\n  ${bad} destination(s) do not render — soft 404s return 200`); process.exit(1); }
console.log('\n  all destinations render');
JS
