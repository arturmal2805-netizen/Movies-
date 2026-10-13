import test from 'node:test';
import assert from 'node:assert/strict';
import {productionBudget,productionExclusion,budgetPriorityScore} from './production-policy.js';
import {isEligibleForSelection,audienceProductionScore,selectionScore,buildSelectionProfile} from './audience-priority.js';
test('known low budgets are excluded, missing and invalid budgets remain unknown',()=>{
 for(const v of [undefined,null,0,-1,true,false,'3000000',NaN,Infinity]){assert.equal(productionBudget({budget:v}),null);assert.equal(productionExclusion({budget:v}),null);}
 assert.equal(productionExclusion({productionBudget:9999999}),'known_low_budget');assert.equal(productionExclusion({productionBudget:10000000}),null);
 assert.equal(productionBudget({productionBudget:null,budget:5000000}),5000000);
});
test('indie policy uses exact provider tags and never guesses from company or plot',()=>{
 for(const keywords of [['independent film'],{keywords:[{name:'Low-Budget'}]},['microbudget']])assert.equal(productionExclusion({keywords,budget:50000000}),'independent_or_low_budget');
 for(const movie of [{keywords:['independent woman']},{description:'An independent film critic'},{companyIds:[1]},{keywords:34},{keywords:null}])assert.equal(productionExclusion(movie),null);
});
test('production policy removes indie from discovery but preserves unknown-budget targets',()=>{
 const film={year:2020,genreIds:[27],popularity:10000};
 assert.equal(isEligibleForSelection({...film,productionBudget:100000}),false);
 assert.equal(isEligibleForSelection({...film,keywords:['independent film'],productionBudget:30000000}),false);
 assert.equal(isEligibleForSelection(film),true);assert.equal(isEligibleForSelection({...film,year:1999,budget:30000000}),false);
});
test('larger budgets boost public ranking while huge popularity retains priority',()=>{
 const film={popularity:5,vote_count:200,budget:10000000},large={...film,budget:50000000};
 assert.ok(audienceProductionScore(large)-audienceProductionScore(film)>3);
 assert.ok(audienceProductionScore({...film,popularity:100})>audienceProductionScore(large));
 assert.equal(selectionScore(large,buildSelectionProfile([],{})),audienceProductionScore(large));
 assert.ok(Number.isFinite(budgetPriorityScore({budget:1e308})));
});
