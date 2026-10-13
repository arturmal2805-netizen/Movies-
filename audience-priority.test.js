import test from 'node:test';
import assert from 'node:assert/strict';
import {audienceScore,audiencePriorityScore,publicQualityScore,audienceFirstScore,audienceProductionScore,selectionPriorityScore,personalFitScore,compareSelection,selectionScore,selectionVersion,imdbAudienceBonus} from './audience-priority.js';
import {buildTasteProfile,tasteScore} from './taste.js';
test('public reach gives a material soft priority and both metadata shapes agree',()=>{
 assert.ok(audienceScore({popularity:30})-audienceScore({popularity:2})>.8);
 assert.ok(audienceScore({vote_count:20000})>audienceScore({vote_count:200}));
 assert.equal(audienceScore({remoteMetrics:{popularity:30,voteCount:2000}}),audienceScore({popularity:30,vote_count:2000}));
 assert.equal(selectionVersion,'audience-first52');
});
test('unknown public reach is neutral and extreme data cannot drown out personal evidence',()=>{
 for(const value of [undefined,null,0,-1,NaN,Infinity,true,'100'])assert.equal(audienceScore({popularity:value,vote_count:value}),0);
 assert.ok(audiencePriorityScore({popularity:1e300,vote_count:1e300})<=3);
 assert.equal(audienceScore({popularity:null,vote_count:null,remoteMetrics:{popularity:30,voteCount:2000}}),audienceScore({popularity:30,vote_count:2000}));
 assert.ok(Number.isFinite(publicQualityScore({vote_average:10,vote_count:1e308})));
});
test('browser joint selection keeps audience reach and learned taste separate',()=>{
 const profile=buildTasteProfile([],{}),a={genreIds:[27],popularity:2},b={...a,popularity:30};
 assert.equal(tasteScore(a,profile),tasteScore(b,profile));
 assert.ok(selectionScore(b,profile)>selectionScore(a,profile));
 assert.equal(selectionScore(a,profile),selectionPriorityScore(a,personalFitScore(a,profile)));
 assert.equal(selectionScore(a,profile,{legacyVersion:'46'}),audienceFirstScore(a));
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
test('strict public order precedes thematic interest and still uses personal evidence for ties',()=>{
 const films=Array.from({length:40},(_,i)=>({id:i+1,genreIds:[27],year:2020,keywords:[i<10?'body horror':'ghost']}));
 const reactions=Object.fromEntries(films.map((f,i)=>[f.id,{impression:i<10?'like':'dislike'}]));
 const profile=buildTasteProfile(films,reactions);
 const personal={id:1000,tmdbId:2000,genreIds:[27],year:2020,keywords:['body horror'],popularity:2,vote_count:100};
 const known={...personal,id:1001,tmdbId:2001,keywords:['ghost'],popularity:30,vote_count:5000};
 assert.ok(tasteScore(personal,profile)>tasteScore(known,profile));
 assert.deepEqual([personal,known].sort((a,b)=>compareSelection(a,b,profile)).map(f=>f.id),[known.id,personal.id]);
 const tie={...known,popularity:2,vote_count:100};
 assert.ok(compareSelection(personal,tie,profile)<0);
});
test('public audience continues to separate well-known films and never rejects unknown data',()=>{
 assert.ok(audienceFirstScore({popularity:400,vote_count:200000})>audienceFirstScore({popularity:40,vote_count:20000}));
 assert.ok(Number.isFinite(audienceFirstScore({popularity:1e308,vote_count:1e308})));
 for(const value of [undefined,null,0,-1,true,'100',NaN,Infinity])assert.equal(audienceFirstScore({popularity:value,vote_count:value}),0);
});


test('personal evidence changes every comparison without removing negative candidates',()=>{
 const movie={popularity:10,vote_count:1000,vote_average:7,budget:5000000};
 assert.ok(selectionPriorityScore(movie,2)>selectionPriorityScore(movie,-2));
 assert.ok(Number.isFinite(selectionPriorityScore(movie,-10000)));
 assert.ok(Number.isFinite(selectionPriorityScore({...movie,vote_count:1e308})));
});


test('only verified canonical IMDb audience evidence affects public recognition',()=>{
 const film={popularity:3,vote_count:300,vote_average:6},remoteMetrics={imdbId:'tt1234567',imdbVerified:true,imdb:6.8,imdbVoteCount:25000};
 assert.ok(selectionPriorityScore({...film,remoteMetrics})>selectionPriorityScore(film));
 assert.ok(imdbAudienceBonus({...film,remoteMetrics})>0);
 for(const changes of [{imdbVerified:false},{imdbVoteCount:null},{imdbId:'bad'},{imdb:NaN}])assert.equal(selectionPriorityScore({...film,remoteMetrics:{...remoteMetrics,...changes}}),selectionPriorityScore(film));
 assert.equal(selectionPriorityScore({...film,imdb_id:'tt9999999',remoteMetrics}),selectionPriorityScore(film));
});
