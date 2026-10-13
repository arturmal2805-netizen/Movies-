import test from 'node:test';
import assert from 'node:assert/strict';
import {productionBudget,productionExclusion,budgetPriorityScore} from './production-policy.js';
import {isEligibleForSelection,audienceProductionScore,selectionScore,buildSelectionProfile} from './audience-priority.js';
test('known low budgets are excluded, missing and invalid budgets are excluded after verification',()=>{
 for(const v of [undefined,null,0,-1,true,false,'3000000',NaN,Infinity]){assert.equal(productionBudget({budget:v}),null);assert.equal(productionExclusion({budget:v}),'unverified_budget');}
 assert.equal(productionExclusion({productionBudget:2999999}),'known_low_budget');assert.equal(productionExclusion({productionBudget:3000000}),null);
 assert.equal(productionBudget({productionBudget:null,budget:5000000}),5000000);
});
test('indie policy uses exact provider tags and never guesses from company or plot',()=>{
 for(const keywords of [['independent film'],{keywords:[{name:'Low-Budget'}]},['microbudget']])assert.equal(productionExclusion({keywords,budget:50000000}),'independent_or_low_budget');
 for(const movie of [{keywords:['independent woman']},{description:'An independent film critic'},{companyIds:[1]},{keywords:34},{keywords:null}])assert.equal(productionExclusion({...movie,budget:15000000}),null);
});
test('production policy hides indie and unverified targets without altering stored films',()=>{
 const film={year:2020,genreIds:[27],popularity:10000};
 assert.equal(isEligibleForSelection({...film,productionBudget:100000}),false);
 assert.equal(isEligibleForSelection({...film,keywords:['independent film'],productionBudget:30000000}),false);
 assert.equal(isEligibleForSelection(film),false);assert.equal(isEligibleForSelection({...film,year:1999,budget:30000000}),false);
});
test('larger budgets boost public ranking while huge popularity retains priority',()=>{
 const film={popularity:5,vote_count:200,budget:10000000},large={...film,budget:50000000};
 assert.ok(audienceProductionScore(large)-audienceProductionScore(film)>3);
 assert.ok(audienceProductionScore({...film,popularity:100})>audienceProductionScore(large));
 assert.equal(selectionScore(large,buildSelectionProfile([],{})),audienceProductionScore(large));
 assert.ok(Number.isFinite(budgetPriorityScore({budget:1e308})));
});

test('canonical favourite director exception does not admit missing budgets or route aliases',async()=>{
 const {directorFocus,styleAffinity}=await import('./production-policy.js');
 const fake={budget:2000000,_liked_directors:['Robert Eggers'],credits:{crew:[{job:'Actor',name:'Robert Eggers'},{job:'Director',name:'Other'}]}};
 assert.equal(directorFocus(fake),false);assert.equal(productionExclusion(fake),'known_low_budget');
 const real={...fake,credits:{crew:[{job:'Director',name:'Robert Eggers'}]},keywords:['independent film']};
 assert.equal(productionExclusion(real),null);assert.equal(productionExclusion({...real,budget:null}),'unverified_budget');
 assert.equal(styleAffinity({keywords:['vampire','zombie','monster']}),0);
 assert.ok(styleAffinity({keywords:['gothic horror','period piece','isolation']})>0);
});
test('Zombeavers cannot pass budget or horror-comedy admission and bad reviews cannot win by budget',async()=>{
 const {compareSelection}=await import('./audience-priority.js');
 assert.equal(isEligibleForSelection({year:2014,genreIds:[27,28,35],productionBudget:null}),false);
 const bad={id:1,year:2020,genreIds:[27],budget:100000000,popularity:100,vote_count:5000,vote_average:4};
 const good={...bad,id:2,budget:5000000,popularity:10,vote_count:2000,vote_average:7};
 assert.deepEqual([bad,good].sort((a,b)=>compareSelection(a,b,buildSelectionProfile([],{}))).map(f=>f.id),[2,1]);
});
