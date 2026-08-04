import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');
const b=await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-dev-shm-usage']});
const p=await b.newPage(); await p.setViewport({width:390,height:844,deviceScaleFactor:2});
await p.goto('https://august-2026-rebuild--lambent-tapioca-86ef75.netlify.app/',{waitUntil:'networkidle2',timeout:90000});
await new Promise(r=>setTimeout(r,2000));
const bb=await p.evaluate(()=>{const e=document.querySelector('[data-site-header] button[aria-controls]');const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2};});
await p.mouse.click(bb.x,bb.y);
await new Promise(r=>setTimeout(r,700));
// elementFromPoint is the authoritative "what is actually on top" test —
// numeric checks all passed while the drawer painted behind the page.
console.log(await p.evaluate(()=>{
  const d=document.querySelector('[role="dialog"]');
  const r=d.getBoundingClientRect();
  const probes=[[r.x+40,r.y+200],[r.x+40,r.y+400],[r.x+40,r.y+600]];
  return {
    drawerBox:{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
    viewportH: innerHeight,
    portalledToBody: d.parentElement === document.body,
    topmostAtProbes: probes.map(([x,y])=>{
      const el=document.elementFromPoint(x,y);
      return el ? (el.closest('[role="dialog"]') ? 'DRAWER ✓' : 'PAGE ✗ ('+el.tagName+')') : 'none';
    }),
  };
}));
await p.screenshot({path:'./burger-open2.png'});
await b.close();
