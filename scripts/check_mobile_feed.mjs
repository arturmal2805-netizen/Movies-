// Start npm run start, then run this script with Playwright installed.
// BASE_URL, PLAYWRIGHT_MODULE and CHROMIUM_PATH can point to an existing test environment.
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
const base=process.env.BASE_URL||'http://127.0.0.1:3000';let landings=0;
try{
 for(const [width,height] of [[320,568],[390,844],[430,932]]){
  const context=await browser.newContext({viewport:{width,height},hasTouch:true,isMobile:true});
  await context.route('**/server-config.js',r=>r.fulfill({contentType:'text/javascript',body:'export const serverConfig={};'}));
  await context.route('**/data/catalog.json*',async r=>{
   await new Promise(resolve=>setTimeout(resolve,120));
   await r.fulfill({json:{schemaVersion:1,sources:{},films:Object.fromEntries(Array.from({length:12},(_,i)=>[i+1,{poster:base+'/broken-poster.jpg'}]))}});
  });
  await context.route('**/broken-poster.jpg',async r=>{
   await new Promise(resolve=>setTimeout(resolve,150));await r.abort();
  });
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const cdp=await context.newCDPSession(page);
  async function swipe(distance,mode='none',settle=450){
   const y=height*.65;await page.evaluate(()=>{window.feedTrace=[];window.traceFeed=true;function sample(){if(!window.traceFeed)return;window.feedTrace.push(scrollY);requestAnimationFrame(sample);}requestAnimationFrame(sample);});
   await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:width/2,y}]});
   for(let i=1;i<=6;i++){
    await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:width/2,y:y-distance*i/6}]});
    if(mode==='finger'&&i===3)await page.locator('#sort').dispatchEvent('change');
    await page.waitForTimeout(12);
   }
   await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
   if(mode==='animation'){await page.waitForTimeout(70);await page.locator('#sort').dispatchEvent('change');}
   await page.waitForTimeout(settle);const trace=await page.evaluate(()=>{window.traceFeed=false;return window.feedTrace;});if(Math.abs(distance)>=18)for(let i=1;i<trace.length;i++)assert.ok((trace[i]-trace[i-1])*Math.sign(distance)>=-1,'Unexpected backward frame: '+trace[i-1]+' -> '+trace[i]);
  }
  async function check(index){
   const card=page.locator('.film').nth(index),box=await card.boundingBox();
   assert.ok(Math.abs(box.y-10)<2,`${width}: card ${index}, actual top ${box.y}`);
   assert.ok(await card.evaluate(e=>e.scrollHeight<=e.clientHeight+1),'Card content fits');
   assert.equal(await card.locator('.poster').evaluate(e=>getComputedStyle(e).opacity),'1','Poster must not fade on a refresh');
   assert.equal(await page.locator('#details').evaluate(e=>e.open),false);
   landings++;
  }
  for(let reload=0;reload<3;reload++){
   if(reload)await page.reload();else await page.goto(base);
   await page.locator('.film').first().waitFor();
   await page.locator('.film').first().evaluate(e=>e.scrollIntoView({block:'start',behavior:'instant'}));
   assert.equal(await page.evaluate(()=>getComputedStyle(document.documentElement).scrollSnapType),'none');
   // Start during initial snapshot/poster loading, then refresh at both gesture phases.
   await swipe(32,'finger');await check(1);
   await swipe(32,'animation');await check(2);
   await swipe(-32,'animation');await check(1);
   await swipe(-32,'finger');await check(0);
   await swipe(18,'finger',20);await swipe(18,'finger');await check(2);
   await swipe(-32,'animation',20);await swipe(-32,'finger');await check(0);
   await swipe(9);await check(0);
   // Reload from inside the feed, not just from the menu.
   await swipe(32);await page.reload();await page.locator('.film').first().waitFor();await page.waitForTimeout(350);
   if(await page.evaluate(()=>scrollY<document.querySelector('#films').offsetTop-30))await page.locator('.film').first().evaluate(e=>e.scrollIntoView({block:'start',behavior:'instant'}));
   const restored=await page.locator('.film').evaluateAll(cards=>cards.reduce((best,card,i)=>Math.abs(card.getBoundingClientRect().top-10)<Math.abs(cards[best].getBoundingClientRect().top-10)?i:best,0));
   await swipe(32,'animation');await check(restored+1);await page.locator('.film').first().evaluate(e=>e.scrollIntoView({block:'start',behavior:'instant'}));
   // Changing the catalog order must preserve the visible film, not the old index.
   await swipe(32);const filmId=await page.locator('.film').nth(1).locator('[data-detail]').getAttribute('data-detail');
   await page.evaluate(async()=>{const {films}=await import(document.querySelector('script[type=module]').src);films.push({...films[0],id:9999,title:'Refresh fixture',genreIds:[27],genre:'Horror',year:2020,rating:100,remoteMetrics:{poster:location.origin+'/later-broken.jpg'}});document.querySelector('#sort').dispatchEvent(new Event('change'));});
   assert.ok(Math.abs((await page.locator(`[data-detail="${filmId}"]`).locator('..').boundingBox()).y-10)<2,'Reorder preserves film identity');
   // A failed image must update only its own poster, never replace all the cards.
   assert.ok(await page.evaluate(()=>{const image=document.querySelector('[data-poster="9999"]');if(!image)throw new Error('Missing poster error fixture');const card=image.closest('.film'),before=card.getBoundingClientRect().top;image.dispatchEvent(new Event('error'));return card.isConnected&&image.style.display==='none'&&card.getBoundingClientRect().top===before;}),'Image error does not rebuild the feed');
   await page.locator('.feed-top').tap();await page.waitForTimeout(450);assert.equal(await page.evaluate(()=>scrollY),0);
  }
  assert.deepEqual(errors,[]);console.log(`${width}: reloads, interrupted gestures, rapid swipes, reorder and posters passed`);
  await context.close();
 }
 console.log(`PASS ${landings} exact landings across 18 page loads`);
}finally{await browser.close();}
