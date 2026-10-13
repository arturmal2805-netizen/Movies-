import test from 'node:test';
import assert from 'node:assert/strict';
import {buildTasteProfile,tasteScore,tasteSignal,tasteAcceptanceScore} from './taste.js';
test('continuous public quality is secondary, cache-aware and does not change acceptance margin',()=>{
 const films=Array.from({length:40},(_,i)=>({id:i+1,year:2020,genreIds:[27],keywords:[i<8?'monster':'ghost']}));
 const reactions=Object.fromEntries(films.map((f,i)=>[f.id,{impression:i<8?'like':'dislike'}]));
 const model=buildTasteProfile(films,reactions),previous=buildTasteProfile(films,reactions,{includePublicQuality:false});
 assert.notEqual(model,previous);assert.equal(model.modelVersion,'duration-aware42');assert.equal(previous.modelVersion,'director-aware37');
 for(const rating of [2,6.5,9]){
  const film={year:2020,genreIds:[27],rating};
  assert.ok(Math.abs(tasteScore(film,model)-tasteScore(film,previous)-.2*(rating-6.5))<1e-12);
  assert.equal(tasteAcceptanceScore(film,model),tasteAcceptanceScore(film,previous));
 }
});
test('verified director translations influence taste and invalidate its cache',()=>{
 const films=Array.from({length:40},(_,i)=>({id:i+1,year:2020,genreIds:[27],director:i<8?'Зак Креггер':'Other',keywords:['monster']}));
 const reactions=Object.fromEntries(films.map((f,i)=>[f.id,{impression:i<8?'like':'dislike'}]));
 const before=buildTasteProfile(films,reactions);
 const plain={year:2020,genreIds:[27],director:'Zach Cregger',keywords:['monster']};
 assert.ok(tasteScore({...plain,directorAliases:['Зак Креггер']},before)>tasteScore(plain,before));
 films[0].directorAliases=['Different alias'];assert.notEqual(buildTasteProfile(films,reactions),before);
});
test('public rating preference is learned in both directions independently of user technical scores',()=>{
 for(const [liked,rejected] of [[8,3],[3,8]]){
  const films=Array.from({length:100},(_,i)=>({id:i+1,genreIds:[27],year:2020,rating:i<10?liked:rejected}));
  const reactions=Object.fromEntries(films.map((f,i)=>[f.id,{impression:i<10?'like':'dislike',plot:i<10?1:10}]));
  const current=buildTasteProfile(films,reactions),previous=buildTasteProfile(films,reactions,{includeQuality:false});
  assert.ok(tasteScore(films[0],current)>tasteScore(films[99],current));
  assert.ok(Math.abs(tasteScore(films[0],previous)-tasteScore(films[99],previous))<1e-12);
 }
});
test('updating public ratings invalidates the browser taste cache',()=>{
 const films=Array.from({length:100},(_,i)=>({id:i+1,genreIds:[27],year:2020,rating:6}));
 const reactions=Object.fromEntries(films.map((f,i)=>[f.id,{impression:i<10?'like':'dislike'}]));
 const previous=buildTasteProfile(films,reactions);films[0].rating=8;
 assert.notEqual(buildTasteProfile(films,reactions),previous);
});
test('specific horror themes separate two films in the same genre',()=>{
 const rated={id:1,genreIds:[27],keywords:['body horror']};
 const profile=buildTasteProfile([rated],{1:{impression:'like',plot:9,cinematography:8}});
 assert.ok(tasteScore({genreIds:[27],keywords:['body horror']},profile)>tasteScore({genreIds:[27],keywords:['ghost']},profile));
});
test('dislike stays negative even with beautiful cinematography',()=>assert.ok(tasteSignal({impression:'dislike',plot:10,cinematography:10})<0));
test('generic sequel tag cannot overrule taste or cause unrelated matches',()=>{
 const profile=buildTasteProfile([{id:1,genreIds:[27],keywords:['sequel']}],{1:{impression:'like'}});
 assert.equal(tasteScore({genreIds:[35],keywords:['sequel']},profile),0);
});
test('explicit horror preference ranks horror first before ratings exist',()=>{
 const horror={genreIds:[27]},comedy={genreIds:[35]};assert.ok(tasteScore(horror,new Map())>tasteScore(comedy,new Map()));
});

test('rejecting unrelated horror does not erase a strong body horror preference',()=>{
 const liked={id:1,genreIds:[27],keywords:['body horror','mutation'],director:'Body Director'};
 const rejected=Array.from({length:8},(_,i)=>({id:i+2,genreIds:[27],keywords:['ghost','haunted house'],director:'Ghost Director'}));
 const reactions={1:{impression:'like',plot:10,cinematography:10},...Object.fromEntries(rejected.map(f=>[f.id,{impression:'dislike',plot:1,cinematography:1}]))};
 const profile=buildTasteProfile([liked,...rejected],reactions);
 assert.ok(tasteScore(liked,profile)>1);assert.ok(tasteScore(liked,profile)>tasteScore(rejected[0],profile));
});
test('unscored neutral ratings do not dilute preferences and neighbor search uses the full history',()=>{
 const films=Array.from({length:100},(_,i)=>({id:i+1,genreIds:[27],keywords:['body horror']}));
 const positive={1:{impression:'like'}};
 const neutral={...positive,...Object.fromEntries(films.slice(1).map(f=>[f.id,{impression:'neutral'}]))};
 assert.equal(tasteScore(films[0],buildTasteProfile(films,positive)),tasteScore(films[0],buildTasteProfile(films,neutral)));
 const all=Object.fromEntries(films.map(f=>[f.id,{impression:'like',ratedAt:new Date(2026,0,f.id).toISOString()}]));
 assert.equal(buildTasteProfile(films,all).anchors.length,100);
});
test('525 ratings retain an early favorite after 524 rejections of a different theme',()=>{
 const favorite={id:1,genreIds:[27],keywords:['body horror','mutation'],director:'Old favorite'};
 const films=[favorite,...Array.from({length:524},(_,i)=>({id:i+2,genreIds:[27],keywords:['ghost','haunted house'],director:'Rejected director'}))];
 const reactions=Object.fromEntries(films.map(f=>[f.id,{impression:f.id===1?'like':'dislike',plot:f.id===1?10:1,cinematography:f.id===1?10:1}]));
 const model=buildTasteProfile(films,reactions);assert.equal(model.anchors.length,525);
 assert.ok(tasteScore(favorite,model)>1);assert.ok(tasteScore(favorite,model)>tasteScore(films[1],model));
});
test('normal five-five is a neutral signal',()=>assert.equal(tasteSignal({impression:'neutral',plot:5,cinematography:5}),0));

test('regularized classifier separates preferences despite class imbalance',()=>{
 const films=Array.from({length:100},(_,i)=>({id:i+1,genreIds:[27],keywords:[i<10?'alien lifeform':'haunted house'],originalLanguage:i<10?'en':'es',year:2020}));
 const reactions=Object.fromEntries(films.map((f,i)=>[f.id,{impression:i<10?'like':'dislike'}]));
 const model=buildTasteProfile(films,reactions);
 assert.equal(model.predictive,true);
 assert.ok(model.get('keyword:alien lifeform')>0);assert.ok(model.get('keyword:haunted house')<0);
 assert.ok(tasteScore(films[0],model)>tasteScore(films[99],model));
 assert.ok(Math.abs(model.get('genre:27'))<.1);
 assert.ok(Math.abs(tasteScore({keywords:['unobserved theme']},model)-model.bias)<1e-12);
 const neutralFilms=Array.from({length:500},(_,i)=>({...films[0],id:101+i}));
 const neutralReactions={...reactions,...Object.fromEntries(neutralFilms.map(f=>[f.id,{impression:'neutral',plot:10,cinematography:10}]))};
 assert.equal(tasteScore(films[0],model),tasteScore(films[0],buildTasteProfile([...films,...neutralFilms],neutralReactions)));
});

test('cached taste retrains after in-place rating and metadata changes',()=>{
 const films=Array.from({length:30},(_,i)=>({id:i+1,genreIds:[27],keywords:[i<10?'alien lifeform':'haunted house']}));
 const reactions=Object.fromEntries(films.map((f,i)=>[f.id,{impression:i<10?'like':'dislike'}]));
 const first=buildTasteProfile(films,reactions);assert.equal(buildTasteProfile(films,reactions),first);
 reactions[1].impression='dislike';const updated=buildTasteProfile(films,reactions);assert.notEqual(updated,first);
 films[1].keywords=['mutation'];assert.notEqual(buildTasteProfile(films,reactions),updated);
});

test('negative-only rare tags are penalized and cannot override rejection',()=>{
 const films=Array.from({length:100},(_,i)=>({id:i+1,genreIds:[27],year:2020,originalLanguage:i<10?'en':'es',keywords:i<10?['alien lifeform']:i<34?['haunted house',`rare label ${i-10}`]:['haunted house']}));
 const reactions=Object.fromEntries(films.map((f,i)=>[f.id,{impression:i<10?'like':'dislike'}]));
 const p=buildTasteProfile(films,reactions),candidate={genreIds:[27],year:2020,originalLanguage:'es',keywords:['haunted house',...Array.from({length:24},(_,i)=>`rare label ${i}`)]};
 assert.ok(tasteScore(candidate,p)<1);for(let i=0;i<24;i++)assert.ok(p.balancedWeights.get(`keyword:rare label ${i}`)<0);assert.ok(tasteAcceptanceScore(candidate,p)<-.8);
});

test('length preferences learn either direction while old model and unknown length stay neutral',()=>{
 for(const [liked,rejected] of [[90,130],[130,90]]){
  const films=Array.from({length:100},(_,i)=>({id:i+1,year:2020,genreIds:[27],minutes:i<10?liked:rejected}));
  const reactions=Object.fromEntries(films.map((f,i)=>[f.id,{impression:i<10?'like':'dislike'}]));
  const current=buildTasteProfile(films,reactions),previous=buildTasteProfile(films,reactions,{includeRuntime:false});
  assert.ok(tasteScore(films[0],current)>tasteScore(films[99],current));
  assert.ok(Math.abs(tasteScore(films[0],previous)-tasteScore(films[99],previous))<1e-10);
  assert.equal(current.modelVersion,'duration-aware42');assert.equal(previous.modelVersion,'synopsis-aware40');
 }
 const films=Array.from({length:100},(_,i)=>({id:i+1,genreIds:[27],keywords:[i<10?'ritual':'ghost']}));
 const reactions=Object.fromEntries(films.map((f,i)=>[f.id,{impression:i<10?'like':'dislike'}]));
 const current=buildTasteProfile(films,reactions);
 for(const duration of [100,null,false,0,-1,'100',NaN,Infinity])assert.ok(Math.abs(tasteScore({...films[99],minutes:duration},current)-tasteScore(films[99],current))<1e-10);
});

test('profile cache invalidates when a rated film length changes',()=>{
 const films=Array.from({length:100},(_,i)=>({id:i+1,genreIds:[27],minutes:100}));
 const reactions=Object.fromEntries(films.map((f,i)=>[f.id,{impression:i<10?'like':'dislike'}]));
 const before=buildTasteProfile(films,reactions);films[0].minutes=140;
 assert.notEqual(buildTasteProfile(films,reactions),before);
});
