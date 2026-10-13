import test from 'node:test';
import assert from 'node:assert/strict';
import {audienceScore,publicQualityScore,selectionScore,selectionVersion} from './audience-priority.js';
import {buildTasteProfile,tasteScore} from './taste.js';
test('public reach gives a material soft priority and both metadata shapes agree',()=>{
 assert.ok(audienceScore({popularity:30})-audienceScore({popularity:2})>.8);
 assert.ok(audienceScore({vote_count:20000})>audienceScore({vote_count:200}));
 assert.equal(audienceScore({remoteMetrics:{popularity:30,voteCount:2000}}),audienceScore({popularity:30,vote_count:2000}));
 assert.equal(selectionVersion,'audience-priority44');
});
test('unknown public reach is neutral and extreme data cannot drown out personal evidence',()=>{
 for(const value of [undefined,null,0,-1,NaN,Infinity,true,'100'])assert.equal(audienceScore({popularity:value,vote_count:value}),0);
 assert.ok(audienceScore({popularity:1e300,vote_count:1e300})<=1.1);
 assert.equal(audienceScore({popularity:null,vote_count:null,remoteMetrics:{popularity:30,voteCount:2000}}),audienceScore({popularity:30,vote_count:2000}));
 assert.ok(Number.isFinite(publicQualityScore({vote_average:10,vote_count:1e308})));
});
test('browser selection uses the same prior without changing the learned taste model',()=>{
 const profile=buildTasteProfile([],{}),a={genreIds:[27],popularity:2},b={...a,popularity:30};
 assert.equal(tasteScore(a,profile),tasteScore(b,profile));
 assert.ok(selectionScore(b,profile)>selectionScore(a,profile));
 assert.equal(selectionScore(a,profile)-tasteScore(a,profile),audienceScore(a));
});
