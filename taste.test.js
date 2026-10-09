import test from 'node:test';
import assert from 'node:assert/strict';
import {buildTasteProfile,tasteScore,tasteSignal,tasteAcceptanceScore} from './taste.js';
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

test('optimistic rare-tag frequency cannot override the separate rejection score',()=>{
 const films=Array.from({length:100},(_,i)=>({id:i+1,genreIds:[27],year:2020,originalLanguage:i<10?'en':'es',keywords:i<10?['alien lifeform']:i<34?['haunted house',`rare label ${i-10}`]:['haunted house']}));
 const reactions=Object.fromEntries(films.map((f,i)=>[f.id,{impression:i<10?'like':'dislike'}]));
 const p=buildTasteProfile(films,reactions),candidate={genreIds:[27],year:2020,originalLanguage:'es',keywords:['haunted house',...Array.from({length:24},(_,i)=>`rare label ${i}`)]};
 assert.ok(tasteScore(candidate,p)>1);assert.ok(tasteAcceptanceScore(candidate,p)<-.8);
});
