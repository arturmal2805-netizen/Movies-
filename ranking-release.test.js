import test from 'node:test';
import assert from 'node:assert/strict';
import {RankingReleaseMonitor} from './ranking-release.js';
const moduleFor=selection=>({selectionVersion:selection,selectionScore(){},selectionSecondaryScore(){},compareSelection(){},buildSelectionProfile(){}});
const release={version:'quality47',selection:'audience-first47'};
test('new ranking is applied once without a page reload',async()=>{
 let applied=0,loads=0;
 const monitor=new RankingReleaseMonitor({version:'quality46',fetchManifest:async()=>release,loadRanking:async()=>{loads++;return moduleFor(release.selection);},onUpdate:()=>{applied++;}});
 assert.equal(await monitor.check(),true);assert.equal(await monitor.check(),false);
 assert.equal(monitor.version,'quality47');assert.equal(applied,1);assert.equal(loads,1);
});
test('typing or an open review postpones loading and then applies the update',async()=>{
 let ready=false,loads=0;
 const monitor=new RankingReleaseMonitor({version:'quality46',fetchManifest:async()=>release,loadRanking:async()=>{loads++;return moduleFor(release.selection);},canApply:()=>ready,onUpdate:()=>{}});
 assert.equal(await monitor.check(),false);assert.equal(loads,0);
 ready=true;assert.equal(await monitor.check(),true);
});
test('a review opened during the module request cannot be interrupted',async()=>{
 let ready=true,applied=0;
 const monitor=new RankingReleaseMonitor({version:'quality46',fetchManifest:async()=>release,loadRanking:async()=>{ready=false;return moduleFor(release.selection);},canApply:()=>ready,onUpdate:()=>{applied++;}});
 assert.equal(await monitor.check(),false);assert.equal(applied,0);assert.equal(monitor.version,'quality46');
});
test('stale CDN code is rejected and retried without marking the new version applied',async()=>{
 let attempts=0;
 const monitor=new RankingReleaseMonitor({version:'quality46',fetchManifest:async()=>release,loadRanking:async()=>moduleFor(++attempts===1?'audience-first46':'audience-first47'),onUpdate:()=>{}});
 assert.equal(await monitor.check(),false);assert.equal(monitor.version,'quality46');
 assert.equal(await monitor.check(),true);assert.equal(attempts,2);
});
test('network errors, malformed releases, and rollbacks leave the working ranking intact',async()=>{
 for(const manifest of [null,{version:'quality47;anything',selection:'audience-first47'},{version:'quality47'},{version:'quality45',selection:'audience-priority45'}]){
  const monitor=new RankingReleaseMonitor({version:'quality46',fetchManifest:async()=>manifest,loadRanking:()=>{throw new Error('Must not load');},onUpdate:()=>{throw new Error('Must not apply');}});
  assert.equal(await monitor.check(),false);assert.equal(monitor.version,'quality46');
 }
 const monitor=new RankingReleaseMonitor({version:'quality46',fetchManifest:async()=>{throw new Error('offline');},onUpdate:()=>{}});
 assert.equal(await monitor.check(),false);assert.equal(monitor.checking,false);
});
test('simultaneous visibility and timer checks share one update request',async()=>{
 let finish,requests=0;
 const monitor=new RankingReleaseMonitor({version:'quality46',fetchManifest:()=>{requests++;return new Promise(resolve=>finish=resolve);},loadRanking:async()=>moduleFor(release.selection),onUpdate:()=>{}});
 const active=monitor.check();assert.equal(await monitor.check(),false);assert.equal(requests,1);
 finish(release);assert.equal(await active,true);
});
