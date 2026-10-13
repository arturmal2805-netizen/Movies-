// Canonical production evidence; all fitted parameters remain private in memory.
import {normalizeRating} from './ratings.js?v=quality43';
import {fitMargin} from './taste-model.js?v=quality43';
export function productionFeatures(movie){
 const vector=[];
 const companies=Array.isArray(movie.companyIds)?movie.companyIds:(Array.isArray(movie.production_companies)?movie.production_companies:[]).map(c=>c?.id);
 const cast=Array.isArray(movie.castIds)?movie.castIds:(Array.isArray(movie.credits?.cast)?movie.credits.cast:[]).map(c=>c?.id);
 for(const [kind,raw,limit] of [['company',companies,8],['cast',cast,6]]){
  const ids=[...new Set(raw.filter(v=>Number.isInteger(v)&&v>0))].slice(0,limit);
  for(const id of ids)vector.push([`${kind}:${id}`,1/Math.sqrt(ids.length),kind]);
 }
 return vector;
}
export function fitProduction(films,reactions){
 const documents=[];
 for(const film of films){const label=normalizeRating(reactions[film.id])?.impression;if(label!=='like'&&label!=='dislike')continue;const vector=productionFeatures(film);if(vector.length)documents.push([vector,label==='like']);}
 const positive=documents.filter(([,y])=>y).length,negative=documents.length-positive;
 const empty={weights:new Map(),bias:0,frequency:new Map(),positiveSupport:new Map(),positiveCount:positive,negativeCount:negative,ready:false};
 if(positive<3||negative<10)return empty;
 const counts=[new Map(),new Map()],coverage=[new Map(),new Map()],support=new Map();
 for(const [vector,label] of documents){const cls=Number(label);for(const kind of new Set(vector.map(([,,kind])=>kind)))coverage[cls].set(kind,(coverage[cls].get(kind)||0)+1);for(const [key,value] of vector){counts[cls].set(key,(counts[cls].get(key)||0)+value);if(label)support.set(key,(support.get(key)||0)+1);}}
 const frequency=new Map();
 for(const key of new Set([...counts[0].keys(),...counts[1].keys()])){const kind=key.split(':')[0],p=coverage[1].get(kind)||0,n=coverage[0].get(kind)||0;if(!p||!n)continue;const pp=2*p/(p+n),np=2*n/(p+n);frequency.set(key,Math.log(((counts[1].get(key)||0)+pp)/(p+pp))-Math.log(((counts[0].get(key)||0)+np)/(n+np)));}
 const examples=documents.map(([v,y])=>[v.filter(([key])=>frequency.has(key)).map(([key,value,kind])=>[key,value*.5,kind]),y]).filter(([v])=>v.length);
 if(examples.filter(([,y])=>y).length<3||examples.filter(([,y])=>!y).length<10)return empty;
 return {...empty,...fitMargin(examples,240,.5),frequency,positiveSupport:support,ready:true};
}
export function productionScore(movie,model){
 if(!model?.ready)return 0;
 const vector=productionFeatures(movie).filter(([key])=>model.frequency.has(key));if(!vector.length)return 0;
 const margin=model.bias+vector.reduce((sum,[key,value])=>sum+(model.weights.get(key)||0)*value*.5,0),frequency=3*vector.reduce((sum,[key,value])=>sum+model.frequency.get(key)*value,0)/Math.max(1,vector.reduce((sum,[,value])=>sum+value,0));
 return Math.max(-2,Math.min(2,.5*margin+.5*frequency));
}
