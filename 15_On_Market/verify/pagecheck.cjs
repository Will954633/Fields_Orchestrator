const puppeteer=require('puppeteer');
(async()=>{
const b=await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-setuid-sandbox']});
const p=await b.newPage();
await p.setUserAgent('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1');
await p.setViewport({width:390,height:844,isMobile:true});
const errs=[];p.on('pageerror',e=>errs.push(String(e).slice(0,200)));
p.on('console',m=>{if(m.type()==='error')errs.push('console: '+m.text().slice(0,160));});
await p.goto('https://fieldsestate.com.au/property/1-dandenong-terrace-robina',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4000));
const info=await p.evaluate(()=>({
  h:document.body.scrollHeight, imgs:document.querySelectorAll('img').length,
  txt:document.body.innerText.slice(0,180).replace(/\n+/g,' | '),
  hasComparables:!!document.querySelector('#comparables'),
  root:(document.querySelector('#root')||document.body).children.length}));
console.log('scrollHeight     :',info.h);
console.log('images           :',info.imgs);
console.log('#comparables     :',info.hasComparables);
console.log('visible text     :',info.txt);
console.log('page errors      :',errs.length?errs.slice(0,4):'none');
await b.close();})();
