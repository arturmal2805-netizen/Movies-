export function swipeDirection(distance,duration){
 if(Math.abs(distance)<12)return 0;
 return Math.round(Math.abs(distance))>=18||Math.abs(distance)/Math.max(1,duration)>=.12?Math.sign(distance):0;
}
export function installMobileFeed(feed){
 const root=document.documentElement,mobile=()=>matchMedia('(max-width:600px)').matches;
 let gesture=null,frame=0,motion=null,pendingRender=null,suppressUntil=0;
 root.classList.add('mobile-feed');
 const cards=()=>[...feed.querySelectorAll('.film')];
 const id=card=>card?.querySelector('[data-detail]')?.dataset.detail;
 const find=key=>cards().find(card=>id(card)===key);
 const nearest=()=>cards().reduce((best,card)=>!best||Math.abs(card.getBoundingClientRect().top-10)<Math.abs(best.getBoundingClientRect().top-10)?card:best,null);
 const top=card=>card?Math.max(0,Math.min(root.scrollHeight-innerHeight,scrollY+card.getBoundingClientRect().top-10)):scrollY;
 const scroll=y=>window.scrollTo({top:y,left:0,behavior:'instant'});
 function flush(){if(gesture||motion)return;const render=pendingRender;pendingRender=null;render?.();}
 function finish(flushRender=true){
  cancelAnimationFrame(frame);frame=0;
  if(motion)scroll(motion.key?top(find(motion.key)):motion.y);
  motion=null;if(flushRender)flush();
 }
 function animate(card,y){
  cancelAnimationFrame(frame);
  motion={key:id(card),y:y??top(card)};
  const from=scrollY,start=performance.now(),duration=matchMedia('(prefers-reduced-motion:reduce)').matches?0:380;
  function step(now){
   const t=duration?Math.min(1,(now-start)/duration):1;
   const destination=motion.key?top(find(motion.key)):motion.y;
   scroll(from+(destination-from)*(1-Math.pow(1-t,4)));
   if(t<1)frame=requestAnimationFrame(step);else finish();
  }
  frame=requestAnimationFrame(step);
 }
 // Install non-passive handlers before the first touch, not while a touch is in progress.
 // CSS gives vertical scrolling of this feed exclusively to this controller.
 feed.addEventListener('touchstart',event=>{
  if(!mobile()||event.touches.length!==1||document.querySelector('dialog[open]'))return;
  finish(false);const card=nearest();if(!card)return;
  const touch=event.touches[0];
  gesture={key:id(card),x:touch.clientX,y:touch.clientY,at:performance.now(),origin:scrollY,entryTop:card.getBoundingClientRect().top,dragging:false};
 },{passive:true});
 feed.addEventListener('touchmove',event=>{
  if(!gesture)return;
  if(event.touches.length!==1){cancel();return;}
  const touch=event.touches[0],dy=gesture.y-touch.clientY,dx=gesture.x-touch.clientX;
  if(!gesture.dragging&&Math.abs(dy)>6&&Math.abs(dy)>Math.abs(dx)*1.2)gesture.dragging=true;
  if(!gesture.dragging)return;
  if(event.cancelable)event.preventDefault();
  scroll(gesture.origin+Math.max(-innerHeight*.35,Math.min(innerHeight*.35,dy*.55)));
 },{passive:false});
 feed.addEventListener('touchend',event=>{
  if(!gesture)return;
  const g=gesture;gesture=null;const touch=event.changedTouches[0];
  const dy=touch?g.y-touch.clientY:0,dx=touch?g.x-touch.clientX:0;
  if(Math.abs(dy)>6&&Math.abs(dy)>Math.abs(dx)*1.2)g.dragging=true;
  if(!g.dragging){requestAnimationFrame(flush);return;}
  if(event.cancelable)event.preventDefault();suppressUntil=performance.now()+400;
  const direction=swipeDirection(dy,performance.now()-g.at),list=cards(),index=list.findIndex(card=>id(card)===g.key);
  if(index<0){flush();return;}
  if(direction<0&&index===0){animate(null,Math.max(0,top(list[0])-innerHeight));return;}
  const entering=g.entryTop>innerHeight*.25;
  const next=entering&&direction>0?index:Math.max(0,Math.min(list.length-1,index+direction));
  animate(list[next]);
 },{passive:false});
 function cancel(){const g=gesture;gesture=null;if(g?.dragging)animate(find(g.key));else flush();}
 feed.addEventListener('touchcancel',cancel,{passive:true});
 feed.addEventListener('click',event=>{if(performance.now()<suppressUntil){event.preventDefault();event.stopImmediatePropagation();}},true);
 let viewportWidth=innerWidth;
 window.addEventListener('resize',()=>{if(innerWidth!==viewportWidth){gesture=null;finish();viewportWidth=innerWidth;}update();});
 const button=document.createElement('button');button.className='feed-top';button.type='button';button.textContent='↑';button.setAttribute('aria-label','Вернуться наверх');button.title='Вернуться наверх';document.body.append(button);
 button.onclick=()=>{gesture=null;finish();animate(null,0);};
 let ticking=false;function update(){ticking=false;button.hidden=!mobile()||scrollY<feed.offsetTop-100;}
 window.addEventListener('scroll',()=>{if(!ticking){ticking=true;requestAnimationFrame(update);}},{passive:true});update();
 return {
  deferRender(render){if(mobile()&&(gesture||motion)){pendingRender=render;return true;}return false;},
  captureAnchor(){if(!mobile()||scrollY<feed.offsetTop-30)return null;const card=nearest();return card?{key:id(card),offset:card.getBoundingClientRect().top}:null;},
  restoreAnchor(anchor){if(!anchor)return;const card=find(anchor.key);if(card)scroll(scrollY+card.getBoundingClientRect().top-anchor.offset);}
 };
}
