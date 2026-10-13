import test from 'node:test';
import assert from 'node:assert/strict';
import {audienceScore,audiencePriorityScore,publicQualityScore,selectionScore,selectionVersion} from './audience-priority.js';
import {buildTasteProfile,tasteScore} from './taste.js';
test('public reach gives a material soft priority and both metadata shapes agree',()=>{
 assert.ok(audienceScore({popularity:30})-audienceScore({popularity:2})>.8);
 assert.ok(audienceScore({vote_count:20000})>audienceScore({vote_count:200}));
 assert.equal(audienceScore({remoteMetrics:{popularity:30,voteCount:2000}}),audienceScore({popularity:30,vote_count:2000}));
 assert.equal(selectionVersion,'audience-priority45');
});
test('unknown public reach is neutral and extreme data cannot drown out personal evidence',()=>{
 for(const value of [undefined,null,0,-1,NaN,Infinity,true,'100'])assert.equal(audienceScore({popularity:value,vote_count:value}),0);
 assert.ok(audiencePriorityScore({popularity:1e300,vote_count:1e300})<=3);
 assert.equal(audienceScore({popularity:null,vote_count:null,remoteMetrics:{popularity:30,voteCount:2000}}),audienceScore({popularity:30,vote_count:2000}));
 assert.ok(Number.isFinite(publicQualityScore({vote_average:10,vote_count:1e308})));
});
test('browser selection uses the same prior without changing the learned taste model',()=>{
 const profile=buildTasteProfile([],{}),a={genreIds:[27],popularity:2},b={...a,popularity:30};
 assert.equal(tasteScore(a,profile),tasteScore(b,profile));
 assert.ok(selectionScore(b,profile)>selectionScore(a,profile));
 assert.equal(selectionScore(a,profile)-tasteScore(a,profile),audienceScore(a));
});
test('audience44 stays frozen for honest before/after comparison',()=>{
 const film={popularity:20,vote_count:5000,vote_average:7};
 const old=.4*Math.log2(21/9)+.1*Math.log2(5500/1500)+.006*.5*5000/5500;
 assert.ok(Math.abs(audiencePriorityScore(film,true,{legacy:true})-old)<1e-12);
 assert.ok(audiencePriorityScore(film,true)>old*3);
 const a={popularity:8,vote_count:400},b={...a,vote_count:4000};
 const difference=audienceScore(b,{legacy:true})-audienceScore(a,{legacy:true});
 assert.ok(Math.abs(audienceScore(b)-audienceScore(a)-difference*7)<1e-12);
});
