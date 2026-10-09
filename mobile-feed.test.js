import test from 'node:test';import assert from 'node:assert/strict';import {swipeDirection} from './mobile-feed.js';
test('short intentional and slow swipes advance, taps and tiny drift stay put',()=>{assert.equal(swipeDirection(30,700),1);assert.equal(swipeDirection(17.999,700),1);assert.equal(swipeDirection(-30,700),-1);assert.equal(swipeDirection(15,45),1);assert.equal(swipeDirection(10,10),0);assert.equal(swipeDirection(15,700),0);assert.equal(swipeDirection(400,250),1);});

// Exercise touch lifecycle and background refreshes with a deterministic viewport.
function viewport(t){
 const listeners=new Map(),frames=new Map();let nextFrame=0;
 const root={scrollHeight:9000,classList:{add(){}}};
 const feed={offsetTop:1000,cards:[],querySelectorAll:()=>feed.cards,addEventListener(type,fn,options){listeners.set(type,{fn,options});}};
 const card=key=>({querySelector:()=>({dataset:{detail:key}}),getBoundingClientRect(){return {top:1000+feed.cards.indexOf(this)*800-globalThis.scrollY};}});
 feed.cards=['a','b','c','d'].map(card);
 const button={setAttribute(){}};
 for(const [key,value] of Object.entries({document:{documentElement:root,querySelector:()=>null,createElement:()=>button,body:{append(){}}},window:{scrollTo(options){assert.equal(options.behavior,'instant');globalThis.scrollY=options.top;},addEventListener(){}},matchMedia:()=>({matches:true}),innerWidth:390,innerHeight:800,scrollY:990,requestAnimationFrame:fn=>{frames.set(++nextFrame,fn);return nextFrame;},cancelAnimationFrame:id=>frames.delete(id)})){
  const descriptor=Object.getOwnPropertyDescriptor(globalThis,key);Object.defineProperty(globalThis,key,{value,writable:true,configurable:true});
  t.after(()=>{if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key];});
 }
 const controller=installMobileFeed(feed);
 function event(type,y){const e={touches:type==='touchend'?[]:[{clientX:100,clientY:y}],changedTouches:[{clientX:100,clientY:y}],cancelable:true,preventDefault(){}};listeners.get(type).fn(e);}
 function settle(){for(const [key,fn] of [...frames]){frames.delete(key);fn(performance.now()+1000);}}
 const render=()=>{const anchor=controller.captureAnchor();feed.cards=feed.cards.map(c=>card(c.querySelector().dataset.detail));controller.restoreAnchor(anchor);};
 return {feed,controller,listeners,event,settle,render,card};
}
import {installMobileFeed} from './mobile-feed.js';
test('background render waits for finger release and animation, then preserves the target film',t=>{
 const v=viewport(t);let renders=0;const refresh=()=>{renders++;v.render();};
 assert.equal(v.listeners.get('touchmove').options.passive,false);
 v.event('touchstart',500);v.event('touchmove',460);
 assert.equal(v.controller.deferRender(refresh),true);assert.equal(renders,0);
 v.event('touchend',460);assert.equal(v.controller.deferRender(refresh),true);
 v.settle();assert.equal(renders,1);assert.equal(scrollY,1790);assert.equal(v.feed.cards[1].getBoundingClientRect().top,10);
});
test('second swipe during animation keeps its touch target connected until both gestures finish',t=>{
 const v=viewport(t);const original=v.feed.cards[0];
 v.event('touchstart',500);v.event('touchmove',460);v.controller.deferRender(v.render);v.event('touchend',460);
 v.event('touchstart',500);assert.equal(v.feed.cards[0],original);
 v.event('touchmove',460);v.event('touchend',460);v.settle();
 assert.equal(scrollY,2590);assert.notEqual(v.feed.cards[0],original);
});
test('idle catalog reorder preserves the visible film and its exact screen position',t=>{
 const v=viewport(t);globalThis.scrollY=1790;const anchor=v.controller.captureAnchor();
 v.feed.cards.unshift(v.card('new'));v.controller.restoreAnchor(anchor);
 assert.equal(v.feed.cards[2].querySelector().dataset.detail,'b');assert.equal(v.feed.cards[2].getBoundingClientRect().top,10);
});
test('cancelled touch settles on the same film and releases a pending refresh',t=>{
 const v=viewport(t);v.event('touchstart',500);v.event('touchmove',440);v.controller.deferRender(v.render);
 v.listeners.get('touchcancel').fn();v.settle();assert.equal(scrollY,990);
 assert.equal(v.controller.deferRender(v.render),false);
});
