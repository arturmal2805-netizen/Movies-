import test from 'node:test';
import assert from 'node:assert/strict';
import {buildTasteProfile,tasteScore,tasteSignal} from './taste.js';
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
