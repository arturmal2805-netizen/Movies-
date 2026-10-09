import {filmCategories} from './categories.js?v=private-export29';
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
 if(r.impression==='neutral'&&scales.length&&scales.every(v=>v===5))return 0;
 return (({like:1,dislike:-1})[r.impression]||0)*.8+adjustment*.2;
}
export function buildTasteProfile(films,reactions){
 const sums=new Map(),counts=new Map(),shares=new Map(),anchors=[];
 for(const film of films){if(!reactions[film.id])continue;const signal=tasteSignal(reactions[film.id]);if(!signal)continue;anchors.push([signal,new Map(tasteFeatures(film).map(([key,share,kind])=>[key,{share,kind}])),Date.parse(reactions[film.id].ratedAt)||0]);
  for(const [key,share] of tasteFeatures(film)){sums.set(key,(sums.get(key)||0)+signal*share);counts.set(key,(counts.get(key)||0)+1);shares.set(key,(shares.get(key)||0)+share);}
 }
 const baseline=anchors.length?anchors.reduce((sum,[signal])=>sum+signal,0)/anchors.length:0;
 const profile=new Map([...sums].map(([key,value])=>[key,.25*value/(counts.get(key)+2)+.75*(value-baseline*shares.get(key))/(counts.get(key)+4)]));profile.anchors=anchors.map(([signal,vector,at])=>[signal,vector,at,[...vector].reduce((sum,[key,{share,kind}])=>sum+share*featureWeight(key,kind),0)]);profile.neighborIndex=new Map();for(let i=0;i<profile.anchors.length;i++)for(const [key,{kind}] of profile.anchors[i][1])if(kind==='keyword'||kind==='director'||kind==='category'&&key!=='category:horror'){if(!profile.neighborIndex.has(key))profile.neighborIndex.set(key,[]);profile.neighborIndex.get(key).push(i);}return profile;
}
const importance={genre:1,category:5,keyword:4,director:2};
const featureWeight=(key,kind)=>key==='category:horror'?.5:importance[kind];
function nearbyScore(vector,anchors){
 const candidate=new Map(vector.map(([key,share,kind])=>[key,{share,kind}])),matches=[];
 const candidateTotal=vector.reduce((sum,[key,share,kind])=>sum+share*featureWeight(key,kind),0);
 for(const [signal,anchor,,anchorTotal] of anchors){
  let shared=0;for(const [key,b] of anchor){const a=candidate.get(key);if(a)shared+=Math.min(a.share,b.share)*featureWeight(key,a.kind);}
  const total=candidateTotal+anchorTotal-shared;
  const specific=[...anchor].some(([key,{kind}])=>candidate.has(key)&&(kind==='keyword'||kind==='director'||kind==='category'&&key!=='category:horror'));
  const similarity=total?shared/total:0;if(similarity>=.12&&specific)matches.push([similarity,signal]);
 }
 matches.sort((a,b)=>b[0]-a[0]);const nearest=matches.slice(0,6);
 return nearest.reduce((sum,[sim,signal])=>sum+sim*signal,0)/(1.5+nearest.reduce((sum,[sim])=>sum+sim,0));
}

export function isDocumentary(film){return (film.genreIds||[]).includes(99)||/документ|documentary/i.test(film.genre||'');}
export function tasteScore(film,profile){const vector=tasteFeatures(film),target=filmCategories(film).some(c=>c==='horror'||c==='dystopian');return (target?1:0)+vector.reduce((value,[key,share,kind])=>value+(profile.get(key)||0)*share*featureWeight(key,kind),0)+nearbyScore(vector,profile.neighborIndex?[...new Set(vector.flatMap(([key])=>profile.neighborIndex.get(key)||[]))].sort((a,b)=>a-b).map(i=>profile.anchors[i]):profile.anchors||[])*2;}
