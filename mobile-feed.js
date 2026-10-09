export function swipeDirection(distance,duration){
 if(Math.abs(distance)<12)return 0;
 return Math.abs(distance)>=18||Math.abs(distance)/Math.max(1,duration)>=.12?Math.sign(distance):0;
}
export function installMobileFeed(feed){
 const root=document.documentElement,mobile=()=>matchMedia('(max-width:600px)').matches;
 let gesture=null,frame=0,destination=null,suppressUntil=0,cleanup=()=>{};
 // A metadata refresh rebuilds card elements; resolve the same film by its stable ID.
 function liveCard(card){if(card?.isConnected)return card;const id=card?.querySelector('[data-detail]')?.dataset.detail;return id?feed.querySelector(`[data-detail="${id}"]`)?.closest('.film'):null;}
 const top=card=>{card=liveCard(card);return card?Math.max(0,Math.min(document.documentElement.scrollHeight-innerHeight,scrollY+card.getBoundingClientRect().top-10)):null;};
 function finish(){cancelAnimationFrame(frame);frame=0;if(destination!==null)scrollTo(0,destination);destination=null;root.classList.remove('feed-gesture');}
 function animate(y){
  if(y===null){finish();return;}
  cancelAnimationFrame(frame);root.classList.add('feed-gesture');destination=y;
  const from=scrollY,start=performance.now(),duration=matchMedia('(prefers-reduced-motion:reduce)').matches?0:380;
  function step(now){const t=duration?Math.min(1,(now-start)/duration):1;scrollTo(0,from+(y-from)*(1-Math.pow(1-t,4)));if(t<1)frame=requestAnimationFrame(step);else finish();}
  frame=requestAnimationFrame(step);
 }
 feed.addEventListener('touchstart',event=>{
  if(!mobile()||event.touches.length!==1)return;
  cleanup();finish();const cards=[...feed.querySelectorAll('.film')];if(!cards.length)return;
  const card=cards.reduce((best,c)=>Math.abs(c.getBoundingClientRect().top-10)<Math.abs(best.getBoundingClientRect().top-10)?c:best,event.target.closest('.film')||cards[0]);
  if(!card)return;const touch=event.touches[0];
  gesture={card,cards,index:cards.indexOf(card),x:touch.clientX,y:touch.clientY,at:performance.now(),origin:scrollY,entryTop:card.getBoundingClientRect().top,distance:0,dragging:false};
  // Keep receiving this touch even if a background render detaches its original element.
  const target=event.target;
  target.addEventListener('touchmove',move,{passive:false});target.addEventListener('touchend',end,{passive:false});target.addEventListener('touchcancel',cancel,{passive:true});
  cleanup=()=>{target.removeEventListener('touchmove',move);target.removeEventListener('touchend',end);target.removeEventListener('touchcancel',cancel);};
 },{passive:true});
 function move(event){
  if(!gesture)return;if(event.touches.length!==1){cleanup();gesture=null;finish();return;}
  const touch=event.touches[0],dy=gesture.y-touch.clientY,dx=gesture.x-touch.clientX;
  if(!gesture.dragging&&Math.abs(dy)>6&&Math.abs(dy)>Math.abs(dx)*1.2){gesture.dragging=true;root.classList.add('feed-gesture');}
  if(!gesture.dragging)return;event.preventDefault();gesture.distance=dy;
  scrollTo(0,gesture.origin+Math.max(-innerHeight*.35,Math.min(innerHeight*.35,dy*.55)));
 }
 function end(event){
  if(!gesture)return;cleanup();const g=gesture;gesture=null;const touch=event.changedTouches[0];
  if(touch){g.distance=g.y-touch.clientY;if(Math.abs(g.distance)>6&&Math.abs(g.distance)>Math.abs(g.x-touch.clientX)*1.2)g.dragging=true;}
  if(!g.dragging)return;event.preventDefault();
  suppressUntil=performance.now()+400;
  const direction=swipeDirection(g.distance,performance.now()-g.at);
  // At the entrance, reveal the first full card rather than skip it.
  const entering=g.entryTop>innerHeight*.25;
  const index=entering&&direction>0?g.index:Math.max(0,Math.min(g.cards.length-1,g.index+direction));
  if(direction<0&&g.index===0){animate(Math.max(0,top(g.card)-innerHeight));return;}
  const target=liveCard(g.cards[index])||feed.querySelectorAll('.film')[Math.min(index,feed.querySelectorAll('.film').length-1)];
  animate(top(target));
 }
 function cancel(){cleanup();const g=gesture;gesture=null;if(g?.dragging)animate(top(g.card));}
 feed.addEventListener('click',event=>{if(performance.now()<suppressUntil){event.preventDefault();event.stopImmediatePropagation();}},true);
 // Safari's address bar changes viewport height during scrolling; keep that gesture alive.
 let viewportWidth=innerWidth;
 window.addEventListener('resize',()=>{if(innerWidth!==viewportWidth){cleanup();gesture=null;finish();viewportWidth=innerWidth;}update();});
 const button=document.createElement('button');button.className='feed-top';button.type='button';button.textContent='↑';button.setAttribute('aria-label','Вернуться наверх');button.title='Вернуться наверх';document.body.append(button);
 button.onclick=()=>{cleanup();gesture=null;animate(0);};
 let ticking=false;function update(){ticking=false;button.hidden=!mobile()||scrollY<feed.offsetTop-100;}
 window.addEventListener('scroll',()=>{if(!ticking){ticking=true;requestAnimationFrame(update);}},{passive:true});update();
}
