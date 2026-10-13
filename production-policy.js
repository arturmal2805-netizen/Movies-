// Shared explicit preferences. Unknown TMDB budgets are missing evidence.
import {categoryRules} from './category-rules.js?v=quality47';
export const productionPolicy=categoryRules.selection.production;
export function productionBudget(movie){const value=movie.productionBudget??movie.budget;return Number.isFinite(value)&&value>0?value:null;}
export function productionExclusion(movie){
 let raw=movie.keywords||[];if(!Array.isArray(raw))raw=raw?.keywords||[];if(!Array.isArray(raw))raw=[];
 const words=raw.filter(k=>typeof k==='string'||k&&typeof k==='object').map(k=>String(typeof k==='string'?k:k.name||'').toLowerCase().replace(/[-_]/g,' ').replace(/\s+/g,' ').trim());
 if(words.some(k=>productionPolicy.excluded_keywords.includes(k)))return 'independent_or_low_budget';
 const budget=productionBudget(movie);return budget!==null&&budget<productionPolicy.minimum_known_budget_usd?'known_low_budget':null;
}
export function budgetPriorityScore(movie){const budget=productionBudget(movie);return budget===null?0:productionPolicy.budget_weight*Math.log2(1+budget/productionPolicy.budget_scale_usd);}
