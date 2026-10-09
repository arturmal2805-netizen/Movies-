import {filmCategories} from './categories.js';
import {normalizeRating} from './ratings.js';
const generic=new Set(['based on novel or book','based on true story','sequel','remake','duringcreditsstinger','aftercreditsstinger','independent film','woman director']);
const normalize=value=>String(value||'').toLocaleLowerCase('ru').replace(/[-_]/g,' ').replace(/\s+/g,' ').trim();
export function tasteFeatures(film){
 const groups={genre:[...new Set(film.genreIds||[])],category:filmCategories(film),keyword:[...new Set((Array.isArray(film.keywords)?film.keywords:[]).map(k=>normalize(typeof k==='string'?k:k?.name)))].slice(0,24),director:[normalize(film.director)]};
 const result=[];
 for(const [kind,raw] of Object.entries(groups)){
  const values=raw.filter(v=>v&&(kind!=='keyword'||!generic.has(v)));
  for(const value of values)result.push([`${kind}:${value}`,1/Math.sqrt(values.length),kind]);
 }
 return result;
}
export function tasteSignal(value){
 const r=normalizeRating(value);if(!r)return 0;
 const scales=[r.plot,r.cinematography].filter(Number.isFinite);
 const adjustment=scales.length?(scales.reduce((a,b)=>a+b,0)/scales.length-5.5)/4.5:0;
 return (({like:1,dislike:-1})[r.impression]||0)*.8+adjustment*.2;
}
export function buildTasteProfile(films,reactions){
 const sums=new Map(),counts=new Map();
 for(const film of films){if(!reactions[film.id])continue;const signal=tasteSignal(reactions[film.id]);
  for(const [key,share] of tasteFeatures(film)){sums.set(key,(sums.get(key)||0)+signal*share);counts.set(key,(counts.get(key)||0)+1);}
 }
 return new Map([...sums].map(([key,value])=>[key,value/(counts.get(key)+2)]));
}
const importance={genre:3,category:4,keyword:4,director:2};
export function tasteScore(film,profile){return tasteFeatures(film).reduce((value,[key,share,kind])=>value+(profile.get(key)||0)*share*importance[kind],0);}
