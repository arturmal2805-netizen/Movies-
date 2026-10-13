import test from 'node:test';
import assert from 'node:assert/strict';
import {productionExclusion,styleAffinity,directorFocus} from './production-policy.js';
import {isEligibleForSelection,audienceProductionScore,selectionPriorityScore,selectionScore,buildSelectionProfile,compareSelection} from './audience-priority.js';
import {tasteScore,tasteFeatures} from './taste.js';
test('budget and budget proxy tags cannot hide or reprioritize permitted films',()=>{
 const base={id:1,year:2020,genreIds:[27],popularity:10,vote_count:2000},profile=buildSelectionProfile([],{});
 for(const budget of [undefined,null,0,1,2999999,3000000,1e9,-1,true,'3000000',NaN,Infinity])for(const tag of ['independent film','low budget','microbudget','micro budget']){
  const film={...base,budget,productionBudget:budget,keywords:[tag]};
  assert.equal(productionExclusion(film),null);assert.equal(isEligibleForSelection(film),true);
  assert.equal(audienceProductionScore(film),audienceProductionScore(base));assert.equal(selectionPriorityScore(film),selectionPriorityScore(base));
  assert.equal(selectionScore(film,profile),selectionScore(base,profile));assert.deepEqual(tasteFeatures(film),tasteFeatures(base));
 }
});
test('financial metadata changes do not change a fitted personalized model',()=>{
 const films=Array.from({length:40},(_,i)=>({id:i+1,year:2020,genreIds:[27],companyIds:[1],castIds:[2],productionBudget:i<10?1e9:1})),reactions=Object.fromEntries(films.map((f,i)=>[f.id,{impression:i<10?'like':'dislike'}]));
 const a=buildSelectionProfile(films,reactions),other=films.map(f=>({...f,productionBudget:null,budget:1,keywords:['low budget','microbudget']})),b=buildSelectionProfile(other,reactions);
 assert.equal(tasteScore(films[0],a),tasteScore(other[0],b));
});
test('year genres countries and horror-comedy guards survive removal of the budget gate',()=>{
 const base={year:2020,genreIds:[27]};
 for(const change of [{year:1999},{genreIds:[27,35]},{genreIds:[16]},{genreIds:[99]},{originalLanguage:'ja'}])assert.equal(isEligibleForSelection({...base,...change}),false);
 for(const keywords of [['parody'],['mockbuster'],['campy'],['horror spoof']])assert.equal(productionExclusion({...base,keywords}),'camp_or_parody');
});
test('popularity and breadth dominate weak thematic coincidences without banning candidates',()=>{
 const film={popularity:2,vote_count:100},popular={popularity:30,vote_count:5000};
 assert.ok(selectionPriorityScore(popular,-100)>selectionPriorityScore(film,100));assert.ok(Number.isFinite(selectionPriorityScore({...film,popularity:1e308,vote_count:1e308})));
});
test('favourite identity and multi-concept style remain independent of budget',()=>{
 assert.equal(directorFocus({_liked_directors:['Robert Eggers'],credits:{crew:[{job:'Actor',name:'Robert Eggers'}]}}),false);
 assert.equal(directorFocus({director:'Robert Eggers'}),true);
 assert.equal(styleAffinity({keywords:['vampire','zombie','monster']}),0);assert.ok(styleAffinity({keywords:['gothic horror','period piece','isolation']})>0);
});
test('Zombeavers stays excluded and popular poor reviews do not automatically beat good ones',()=>{
 assert.equal(isEligibleForSelection({year:2014,genreIds:[27,28,35],productionBudget:null}),false);
 const bad={id:1,year:2020,genreIds:[27],popularity:100,vote_count:5000,vote_average:4},good={...bad,id:2,popularity:10,vote_count:2000,vote_average:7};
 assert.deepEqual([bad,good].sort((a,b)=>compareSelection(a,b,buildSelectionProfile([],{}))).map(f=>f.id),[2,1]);
});
