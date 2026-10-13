// Shared explicit preferences. Unknown TMDB budgets are missing evidence.
import {directorSelected,patternAffinity} from './interests.js?v=quality48';
import {categoryRules} from './category-rules.js?v=quality48';
export const productionPolicy=categoryRules.selection.production;
export function productionBudget(movie){const value=movie.productionBudget??movie.budget;return Number.isFinite(value)&&value>0?value:null;}
const normalize=value=>String(value||'').toLowerCase().replace(/[-_]/g,' ').replace(/\s+/g,' ').trim();
function providerWords(movie){let raw=movie.keywords||[];if(!Array.isArray(raw))raw=raw?.keywords||[];if(!Array.isArray(raw))return [];return raw.filter(k=>typeof k==='string'||k&&typeof k==='object').map(k=>normalize(typeof k==='string'?k:k.name));}
export function directorFocus(movie,interests){return directorSelected(movie,interests);}
export function styleAffinity(movie,model=null){if(model)return patternAffinity(movie,model);const words=providerWords(movie),count=productionPolicy.style_groups.filter(group=>group.some(w=>words.includes(w))).length;return count>=2?count*.5:0;}
export function productionExclusion(movie,{requireBudget=true,legacy=false,interests}={}){
 const ids=Array.isArray(movie.genreIds)?movie.genreIds:Array.isArray(movie.genres)?movie.genres.map(g=>g?.id):Array.isArray(movie.genre_ids)?movie.genre_ids:[];
 if(!legacy&&productionPolicy.excluded_genre_combinations.some(pair=>pair.every(id=>ids.includes(id))))return 'horror_comedy';
 const old=['independent film','low budget','microbudget','micro budget'];
 const banned=legacy?old:productionPolicy.excluded_keywords.filter(k=>!directorFocus(movie,interests)||!old.includes(k));
 if(providerWords(movie).some(k=>banned.includes(k)))return 'independent_or_low_budget';
 const budget=productionBudget(movie);if(budget!==null&&budget<(legacy?10000000:productionPolicy.minimum_known_budget_usd)&&(legacy||!directorFocus(movie,interests)))return 'known_low_budget';
 return budget===null&&requireBudget&&!legacy&&productionPolicy.require_known_budget?'unverified_budget':null;
}
export function budgetPriorityScore(movie){const budget=productionBudget(movie);return budget===null?0:productionPolicy.budget_weight*Math.log2(1+budget/productionPolicy.budget_scale_usd);}
