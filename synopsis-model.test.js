import test from 'node:test';
import assert from 'node:assert/strict';
import {fitSynopsis,synopsisScore,synopsisTokens} from './synopsis-model.js';
import {buildTasteProfile,tasteScore} from './taste.js';

function history(){
 const films=Array.from({length:100},(_,i)=>({id:i+1,genreIds:[27],year:2020,rating:6.5,originalLanguage:'en',description:i<10?'Лес древний ритуал культ призрак':'Телешоу шутка вечеринка смех комедия'}));
 const reactions=Object.fromEntries(films.map((f,i)=>[f.id,{impression:i<10?'like':'dislike'}]));
 return {films,reactions};
}

test('plot evidence separates same-genre films and metadata changes invalidate the profile cache',()=>{
 const {films,reactions}=history();
 const previous=buildTasteProfile(films,reactions,{includeSynopsis:false,includeReach:false});
 assert.equal(tasteScore(films[0],previous),tasteScore(films[99],previous));
 const current=buildTasteProfile(films,reactions);
 assert.ok(tasteScore(films[0],current)>tasteScore(films[99],current));
 films[0].description='Different plot';assert.notEqual(buildTasteProfile(films,reactions),current);
});
test('neutral and watched text cannot train or expand the learned vocabulary',()=>{
 const {films,reactions}=history(),before=fitSynopsis(films,reactions);
 const extra=Array.from({length:100},(_,i)=>({id:1000+i,description:'invented neutral vocabulary'}));
 const after=fitSynopsis([...films,...extra],{...reactions,...Object.fromEntries(extra.map((f,i)=>[f.id,{impression:i%2?'watched':'neutral'}]))});
 assert.deepEqual(before,after);
});
test('unseen invalid and missing plots provide no evidence and title/caption do not substitute for synopsis',()=>{
 const {films,reactions}=history(),model=fitSynopsis(films,reactions);
 for(const description of [null,42,false,{},'', 'unobserved unknown words'])assert.equal(synopsisScore({description},model),0);
 assert.equal(synopsisScore({title:'Лес ритуал культ',recommendationReason:'Лес ритуал культ',plot:10},model),0);
 assert.deepEqual(synopsisTokens({description:'Ритуал ритуалы РИТУАЛ'}),['ритуал','ритуал','ритуал']);
 assert.deepEqual(synopsisTokens({description:'ЁЖИК'}),synopsisTokens({overview:'ежик'}));
 assert.equal(synopsisTokens({description:'forest '.repeat(1000)}).length,160);
 assert.equal(synopsisTokens({description:' '.repeat(4000)+'forest'}).length,0);
});
test('audience reach is learned from personal opinions in both directions and updates its cache',()=>{
 for(const [liked,rejected] of [[2,40],[40,2]]){
  const {films,reactions}=history();for(let i=0;i<films.length;i++){delete films[i].description;films[i].remoteMetrics={popularity:i<10?liked:rejected};}
  const previous=buildTasteProfile(films,reactions,{includeSynopsis:false,includeReach:false});
  assert.equal(tasteScore(films[0],previous),tasteScore(films[99],previous));
  const model=buildTasteProfile(films,reactions);
  assert.ok(tasteScore(films[0],model)>tasteScore(films[99],model));
  films[0].remoteMetrics.popularity+=1;assert.notEqual(buildTasteProfile(films,reactions),model);
 }
});
