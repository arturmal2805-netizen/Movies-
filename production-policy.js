// Explicit content preferences. Financial metadata has no role in admission or ranking.
import {directorSelected,patternAffinity} from './interests.js?v=quality53';
import {categoryRules} from './category-rules.js?v=quality53';
export const productionPolicy=categoryRules.selection.production;
const normalize=value=>String(value||'').toLowerCase().replace(/[-_]/g,' ').replace(/\s+/g,' ').trim();
function providerWords(movie){let raw=movie.keywords||[];if(!Array.isArray(raw))raw=raw?.keywords||[];if(!Array.isArray(raw))return [];return raw.filter(k=>typeof k==='string'||k&&typeof k==='object').map(k=>normalize(typeof k==='string'?k:k.name));}
export function directorFocus(movie,interests){return directorSelected(movie,interests);}
export function styleAffinity(movie,model=null){if(model)return patternAffinity(movie,model);const words=providerWords(movie),count=productionPolicy.style_groups.filter(group=>group.some(w=>words.includes(w))).length;return count>=2?count*.5:0;}
export function productionExclusion(movie,options={}){
 const ids=Array.isArray(movie.genreIds)?movie.genreIds:Array.isArray(movie.genres)?movie.genres.map(g=>g?.id):Array.isArray(movie.genre_ids)?movie.genre_ids:[];
 if(productionPolicy.excluded_genre_combinations.some(pair=>pair.every(id=>ids.includes(id))))return 'horror_comedy';
 if(providerWords(movie).some(k=>productionPolicy.excluded_keywords.includes(k)))return 'camp_or_parody';
 return null;
}
