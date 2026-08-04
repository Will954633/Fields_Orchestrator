/**
 * MobileNav verification. visual-check.mjs does NOT cover this — it measures
 * page-level properties (status, landmarks, overflow, fonts) and never opens
 * the drawer, so it reports "no measurable differences" whether the burger
 * works or is entirely broken.
 *
 *   node mobile-nav-check.mjs        # burger, 7 groups, 33 destinations,
 *                                    # Escape, focus return, scroll lock, desktop
 *   node mobile-nav-paint-check.mjs  # elementFromPoint: is it ACTUALLY on top?
 *
 * The paint check exists because every numeric assertion above passed while the
 * drawer was painting behind the page (clipped by SiteHeader's overflow-x:clip).
 * Behaviour checks do not prove appearance. See [MOBILE-BURGER-MISSING].
 */
import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');
const B='https://august-2026-rebuild--lambent-tapioca-86ef75.netlify.app';
const b=await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-dev-shm-usage']});

// --- mobile: burger present, strip gone, drawer works
const p=await b.newPage(); const errs=[];
p.on('pageerror',e=>errs.push(e.message.match(/#\d+/)?.[0]??e.message.slice(0,40)));
await p.setViewport({width:390,height:844,deviceScaleFactor:2});
await p.goto(B+'/',{waitUntil:'networkidle2',timeout:90000});
await new Promise(r=>setTimeout(r,2000));

const before=await p.evaluate(()=>{
  const h=document.querySelector('[data-site-header]');
  const burger=h.querySelector('button[aria-controls]');
  const nav=h.querySelector('nav[aria-label="Primary navigation"]');
  const br=burger?burger.getBoundingClientRect():null;
  return { burger:!!burger, burgerSize:br?`${Math.round(br.width)}x${Math.round(br.height)}`:null,
           stripHidden: nav? getComputedStyle(nav).display==='none' : 'no-nav',
           expanded: burger?.getAttribute('aria-expanded'),
           hScroll: document.documentElement.scrollWidth>innerWidth+1 };
});
console.log('mobile before open:', before);

const bb=await p.evaluate(()=>{const e=document.querySelector('[data-site-header] button[aria-controls]');const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2};});
await p.mouse.click(bb.x,bb.y);
await new Promise(r=>setTimeout(r,600));
const open=await p.evaluate(()=>{
  const d=document.querySelector('[role="dialog"]');
  const heads=[...d.querySelectorAll('button[aria-expanded]')].map(x=>x.textContent.replace(/›/g,'').trim());
  const links=[...d.querySelectorAll('a')];
  const small=links.filter(a=>a.getBoundingClientRect().height<44).length;
  return { drawerVisible:d.getBoundingClientRect().x>=0, groups:heads.length, groupTitles:heads,
           visibleLinks:links.length, linksUnder44px:small,
           bodyLocked:getComputedStyle(document.body).overflow==='hidden',
           expanded:document.querySelector('[data-site-header] button[aria-controls]').getAttribute('aria-expanded') };
});
console.log('after opening    :', open);

// expand every group and count total destinations
const total=await p.evaluate(async()=>{
  const d=document.querySelector('[role="dialog"]');
  const heads=[...d.querySelectorAll('button[aria-expanded]')];
  const seen=new Set();
  // collect BEFORE clicking too — group 0 starts open, and clicking its head
  // closes it, which is why an earlier run under-counted by exactly 4.
  d.querySelectorAll('a').forEach(a=>seen.add(a.getAttribute('href')));
  for(const h of heads){
    if(h.getAttribute('aria-expanded')==='false') h.click();
    await new Promise(r=>setTimeout(r,120));
    d.querySelectorAll('a').forEach(a=>seen.add(a.getAttribute('href'))); }
  return {destinations:seen.size, sample:[...seen].slice(0,4)};
});
console.log('all groups opened:', total);

await p.screenshot({path:'./burger-open.png'});
await p.keyboard.press('Escape');
await new Promise(r=>setTimeout(r,500));
console.log('after Escape     :', await p.evaluate(()=>({
  expanded:document.querySelector('[data-site-header] button[aria-controls]').getAttribute('aria-expanded'),
  bodyRestored:getComputedStyle(document.body).overflow!=='hidden',
  focusBackOnBurger:document.activeElement?.getAttribute('aria-controls')!=null })));
console.log('errors:', errs.length?[...new Set(errs)]:'none ✓');
await p.close();

// --- desktop must be untouched
const q=await b.newPage(); await q.setViewport({width:1440,height:900});
await q.goto(B+'/',{waitUntil:'networkidle2',timeout:90000});
await new Promise(r=>setTimeout(r,1500));
console.log('desktop          :', await q.evaluate(()=>{
  const h=document.querySelector('[data-site-header]');
  return { burgerVisible: getComputedStyle(h.querySelector('button[aria-controls]')).display!=='none',
           navLinks:[...h.querySelectorAll('nav a')].map(a=>a.textContent.trim()) };
}));
await b.close();
