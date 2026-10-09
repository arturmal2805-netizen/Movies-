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
