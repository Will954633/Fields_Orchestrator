const puppeteer=require('puppeteer');
(async()=>{
const b=await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-setuid-sandbox']});
const p=await b.newPage();
await p.setUserAgent('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1');
await p.setViewport({width:390,height:844,isMobile:true,deviceScaleFactor:2});
const imgs=[];
p.on('response',async r=>{const u=r.url();
  if(/blobs\.fieldsestate\.com\.au.*\.(jpg|webp)$/.test(u)){
    let len=0; try{len=(await r.buffer()).length;}catch(e){len=parseInt(r.headers()['content-length']||'0',10);}
    imgs.push({u,len,type:r.headers()['content-type']});}});
await p.goto(process.argv[2],{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,2500));
const hero=await p.evaluate(()=>{const i=document.querySelector('img');return i?{src:i.currentSrc||i.src,srcset:(i.srcset||'').slice(0,90),w:i.naturalWidth,h:i.naturalHeight}:null;});
console.log('hero currentSrc:',hero&&hero.src.split('/').pop());
console.log('hero natural   :',hero&&hero.w+'x'+hero.h);
console.log('hero srcset set:',hero&&hero.srcset?'yes':'NO');
const webp=imgs.filter(i=>i.u.endsWith('.webp')), jpg=imgs.filter(i=>i.u.endsWith('.jpg'));
const kb=a=>Math.round(a.reduce((s,i)=>s+i.len,0)/1024);
console.log(`webp fetched: ${webp.length} files, ${kb(webp)} KB`);
console.log(`jpg  fetched: ${jpg.length} files, ${kb(jpg)} KB`);
if(webp[0])console.log('example webp:',webp[0].u.split('/').pop(),webp[0].type,Math.round(webp[0].len/1024)+'KB');
await b.close();})();
