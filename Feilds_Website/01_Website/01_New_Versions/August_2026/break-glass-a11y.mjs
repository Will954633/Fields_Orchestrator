import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');
const B='https://august-2026-rebuild--lambent-tapioca-86ef75.netlify.app';
const b = await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-dev-shm-usage']});

// ---- CLS: does the stage reserve its space? (aspect-ratio should mean yes)
{
  const p=await b.newPage(); await p.setViewport({width:1440,height:900});
  await p.evaluateOnNewDocument(()=>{ window.__cls=0;
    new PerformanceObserver(l=>{for(const e of l.getEntries()) if(!e.hadRecentInput) window.__cls+=e.value;})
      .observe({type:'layout-shift',buffered:true}); });
  await p.goto(B+'/',{waitUntil:'networkidle2',timeout:90000});
  await p.evaluate(()=>document.querySelector('footer')?.scrollIntoView({block:'end'}));
  await new Promise(r=>setTimeout(r,3500));
  console.log('CLS after footer + assets load:', await p.evaluate(()=>+window.__cls.toFixed(4)), '(want < 0.1)');
  await p.close();
}

// ---- keyboard: Tab to the glass, Enter breaks; then Enter pulls
{
  const p=await b.newPage(); await p.setViewport({width:1440,height:900});
  await p.goto(B+'/',{waitUntil:'networkidle2',timeout:90000});
  await p.evaluate(()=>document.querySelector('footer')?.scrollIntoView({block:'end'}));
  await new Promise(r=>setTimeout(r,2500));
  await p.evaluate(()=>document.querySelector('[data-x="hit-glass"]')?.focus());
  const focused = await p.evaluate(()=>document.activeElement?.getAttribute('data-x'));
  await p.keyboard.press('Enter');
  await new Promise(r=>setTimeout(r,2400));
  const armed = await p.evaluate(()=>{const h=document.querySelector('[data-x="hit-handle"]');return h&&!h.hidden;});
  await p.evaluate(()=>document.querySelector('[data-x="hit-handle"]')?.focus());
  await p.keyboard.press('Enter');
  await new Promise(r=>setTimeout(r,1500));
  const pulled = await p.evaluate(()=>{const d=document.querySelector('[data-x="l-down"]');return d&&getComputedStyle(d).opacity==='1';});
  console.log(`keyboard: focus=${focused} -> Enter breaks=${armed} -> Enter pulls=${pulled}`);
  await p.close();
}

// ---- prefers-reduced-motion: no shake, short swing
{
  const p=await b.newPage(); await p.setViewport({width:1440,height:900});
  await p.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);
  await p.goto(B+'/',{waitUntil:'networkidle2',timeout:90000});
  await p.evaluate(()=>document.querySelector('footer')?.scrollIntoView({block:'end'}));
  await new Promise(r=>setTimeout(r,2500));
  const hit=await p.evaluate(()=>{const e=document.querySelector('[data-x="hit-glass"]');const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};});
  await p.mouse.click(hit.x,hit.y);
  await new Promise(r=>setTimeout(r,300));
  const shaking = await p.evaluate(()=>{
    const st=document.querySelector('[class*=stage]');
    return getComputedStyle(st).animationName;
  });
  console.log(`reduced-motion: stage animation-name="${shaking}" (want "none")`);
  await p.close();
}
await b.close();
