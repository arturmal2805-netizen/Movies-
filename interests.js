import {categoryRules} from './category-rules.js?v=quality52';
import {normalizeRating} from './ratings.js?v=quality43';
export const defaultInterests=categoryRules.selection.production.default_interests;
const clean=value=>typeof value==='string'?value.replace(/\s+/g,' ').trim().slice(0,120):'';
export const normalizeInterestName=value=>clean(value).toLowerCase().replace(/[-_]/g,' ');
export function normalizeInterests(value=defaultInterests){
 if(!value||typeof value!=='object'||Array.isArray(value))value=defaultInterests;
 const priority=[...new Set((Array.isArray(value.genrePriority)?value.genrePriority:defaultInterests.genrePriority).filter(g=>['horror','dystopian'].includes(g)))];
 for(const g of ['horror','dystopian'])if(!priority.includes(g))priority.push(g);
 const raw=Array.isArray(value.directors)?value.directors:defaultInterests.directors,seen=new Set(),directors=[];
 for(const item of raw.slice(0,20)){const name=clean(typeof item==='string'?item:item&&typeof item==='object'?item.name:'');if(!name)continue;
  const known=defaultInterests.directors.find(d=>[d.name,...d.aliases].some(n=>normalizeInterestName(n)===normalizeInterestName(name)))?.aliases||[];
  const aliases=Array.isArray(item?.aliases)?item.aliases.slice(0,6).filter(a=>typeof a==='string'&&clean(a)).map(clean):[];
  const names=[...new Set([name,...aliases,...known])].slice(0,8);if(names.some(n=>seen.has(normalizeInterestName(n))))continue;
  names.forEach(n=>seen.add(normalizeInterestName(n)));directors.push({name,aliases:names});
 }
 return {version:1,genrePriority:priority,directors};
}
export function directorSelected(movie,interests){
 const names=movie.credits&&typeof movie.credits==='object'?(Array.isArray(movie.credits.crew)?movie.credits.crew:[]).filter(p=>p?.job==='Director').map(p=>p.name||''):[movie.director||'',...(Array.isArray(movie.directorAliases)?movie.directorAliases:[])];
 const targets=new Set(normalizeInterests(interests).directors.flatMap(d=>[d.name,...d.aliases]).map(normalizeInterestName));
 return names.filter(n=>typeof n==='string').flatMap(n=>n.split(',')).some(n=>targets.has(normalizeInterestName(n)));
}
const generic=new Set(['vampire','zombie','monster','witch','ghost','murder','death','demon','violence','blood','sequel','remake','based on novel or book','based on true story','duringcreditsstinger','aftercreditsstinger','independent film','woman director']);
export function styleKey(name){const key=normalizeInterestName(name);const concept=Object.entries(categoryRules.selection.production.style_concepts).find(([,aliases])=>aliases.includes(key))?.[0];return concept?'@'+concept:'';}
function rawWords(movie){let raw=movie.keywords||[];if(!Array.isArray(raw))raw=raw?.keywords||[];return Array.isArray(raw)?[...new Set(raw.filter(k=>typeof k==='string'||k&&typeof k==='object').map(k=>normalizeInterestName(typeof k==='string'?k:k.name)))]:[];}
function words(movie){return [...new Set(rawWords(movie).map(styleKey))];}
export function buildStyleModel(films,reactions,interests,{legacy=false}={}){
 const extract=legacy?rawWords:words;
 const references=films.filter(f=>normalizeRating(reactions[f.id])?.impression==='like'&&directorSelected(f,interests));
 const rejected=films.filter(f=>normalizeRating(reactions[f.id])?.impression==='dislike');
 const count=list=>{const c=new Map();for(const m of list)for(const k of extract(m))if(k&&!generic.has(k))c.set(k,(c.get(k)||0)+1);return c;};
 const p=count(references),n=count(rejected),weights=new Map();for(const [k,v] of p)weights.set(k,Math.min(3,Math.max(0,rejected.length?Math.log((v+1)/(references.length+2))-Math.log(((n.get(k)||0)+1)/(rejected.length+2)):Math.log1p(v))));
 return {weights,referenceCount:references.length,legacy,patterns:references.map(m=>extract(m).filter(k=>(weights.get(k)||0)>0))};
}
export function patternAffinity(movie,model){
 const candidates=new Set(model.legacy?rawWords(movie):words(movie));let strongest=0;
 for(const pattern of model.patterns){const hits=pattern.filter(k=>candidates.has(k)).map(k=>model.weights.get(k)||0);if(hits.length>=2)strongest=Math.max(strongest,hits.reduce((a,b)=>a+b,0));}
 return Math.min(2,strongest/4);
}
