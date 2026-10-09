import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ManualRecommendations} from './manual-recommendations.js';
const id='00000000-0000-4000-8000-000000000001';
function fixture(){
 const storage=new Map();globalThis.localStorage={getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
 let starts=0,callbacks=[],states=[],completed=0;
 const server={session:{user:{id:'owner'}},startRecommendations:async()=>{starts++;return{id,status:'queued'}},recommendationStatus:async()=>({id,status:'running'}),activeRecommendation:async()=>null};
 const controller=new ManualRecommendations(server,{schedule:fn=>{callbacks.push(fn);return callbacks.length},cancel:()=>{},onState:job=>states.push(job),onComplete:async()=>{completed++}});
 return {controller,server,storage,states,get starts(){return starts},get completed(){return completed},callbacks};
}
test('double clicks reuse the active request; completed requests allow a fresh search',async()=>{
 const f=fixture();await Promise.all([f.controller.start(),f.controller.start()]);assert.equal(f.starts,1);
 await f.controller.start();assert.equal(f.starts,1);
 f.server.recommendationStatus=async()=>({id,status:'completed',added_count:3});await f.controller.poll();assert.equal(f.completed,1);assert.equal(f.storage.size,0);
 await f.controller.start();assert.equal(f.starts,2);
});
test('network failures keep a long-running job active until its real result',async()=>{
 const f=fixture();await f.controller.start();f.server.recommendationStatus=async()=>{throw Error('offline')};await f.controller.poll();assert.equal(f.states.at(-1).connectionLost,true);
 f.server.recommendationStatus=async()=>({id,status:'running'});for(let n=0;n<25;n++)await f.controller.poll();assert.equal(f.controller.job.status,'running');assert.equal(f.completed,0);
 f.server.recommendationStatus=async()=>({id,status:'completed',added_count:0});await f.controller.poll();assert.equal(f.states.at(-1).added_count,0);
});
test('page reload resumes saved job without dispatching again',async()=>{
 const f=fixture();f.storage.set(f.controller.key(),JSON.stringify({id}));await f.controller.resume();assert.equal(f.starts,0);assert.equal(f.controller.job.status,'running');
});
test('GitHub rejection is a failed request, never a successful completion',async()=>{
 const f=fixture();await f.controller.start();f.server.recommendationStatus=async()=>({id,status:'failed',error_code:'github_rejected'});await f.controller.poll();assert.equal(f.completed,0);assert.equal(f.states.at(-1).status,'failed');assert.equal(f.storage.size,0);
});
test('logout ignores a late response from the previous account',async()=>{
 const f=fixture();let resolve;f.server.startRecommendations=()=>new Promise(r=>resolve=r);const pending=f.controller.start();f.controller.stop();resolve({id,status:'queued'});await pending;assert.equal(f.controller.job,null);assert.equal(f.storage.size,0);
});
test('missing server setup reports an error and releases the button',async()=>{
 const f=fixture();f.server.startRecommendations=async()=>{throw Error('not configured')};await assert.rejects(f.controller.start());assert.equal(f.controller.starting,false);assert.equal(f.states.at(-1).status,'error');
});
