import {filmCategories,isEligibleForDiscovery} from './categories.js?v=quality43';
import {normalizeRating} from './ratings.js?v=quality43';
import {fitMargin,marginFeatures,tasteModelVersion} from './taste-model.js?v=quality43';
import {fitSynopsis,synopsisScore} from './synopsis-model.js?v=quality43';
import {fitProduction,productionScore} from './production-model.js?v=quality43';
const generic=new Set(['based on novel or book','based on true story','sequel','remake','duringcreditsstinger','aftercreditsstinger','independent film','woman director']);
const normalize=value=>String(value||'').toLocaleLowerCase('ru').replace(/[-_]/g,' ').replace(/\s+/g,' ').trim();
export function tasteFeatures(film,includeDirectorAliases=true){
 const aliases=includeDirectorAliases&&Array.isArray(film.directorAliases)?[...new Set(film.directorAliases.filter(name=>typeof name==='string'&&name.trim()).map(normalize))]:[];
 const groups={genre:[...new Set(film.genreIds||[])],category:filmCategories(film),keyword:[...new Set((Array.isArray(film.keywords)?film.keywords:[]).map(k=>normalize(typeof k==='string'?k:k?.name)))].slice(0,24),director:aliases.length?aliases:[normalize(film.director)]};
 const result=[];
 for(const [kind,raw] of Object.entries(groups)){
  const values=raw.filter(v=>v&&(kind!=='keyword'||!generic.has(v)));
  for(const value of values)result.push([`${kind}:${value}`,1/Math.sqrt(values.length),kind]);
 }
 return result;
}
export function tasteSignal(value){
 const r=normalizeRating(value);if(!r)return 0;
 if(r.feedbackStage==='interest')return ({like:1,dislike:-1})[r.impression]||0;
 const scales=[r.plot,r.cinematography].filter(Number.isFinite);
 const adjustment=scales.length?(scales.reduce((a,b)=>a+b,0)/scales.length-5.5)/4.5:0;
 if(r.impression==='neutral'&&scales.length&&scales.every(v=>v===5))return 0;
 return (({like:1,dislike:-1})[r.impression]||0)*.8+adjustment*.2;
}
const cachedProfiles=new WeakMap();
export function buildTasteProfile(films,reactions,{includeQuality=true,includeDirectorAliases=true,includePublicQuality=true,includeSynopsis=true,includeReach=true,includeRuntime=true,includeProduction=true}={}){
 const signature=JSON.stringify([includeQuality,includeDirectorAliases,includePublicQuality,includeSynopsis,includeReach,includeRuntime,includeProduction,films.filter(f=>reactions[f.id]).map(f=>[f.id,normalizeRating(reactions[f.id]),f.genreIds,f.genre,f.keywords,f.director,f.originalLanguage,f.original_language,f.year,f.release_date,f.tmdbId,f.description||f.overview,f.rating,f.vote_average,f.directorAliases,f.popularity,f.remoteMetrics?.popularity,f.minutes,f.runtime,f.companyIds,f.castIds,f.productionBudget,f.production_companies,f.credits?.cast,f.budget])]);
 const runtimeEnabled=includeRuntime&&includeQuality&&includeDirectorAliases&&includePublicQuality&&(includeSynopsis||includeReach);
 const cached=cachedProfiles.get(reactions);if(cached?.signature===signature)return cached.profile;
 const sums=new Map(),counts=new Map(),shares=new Map(),anchors=[];
 for(const film of films){if(!reactions[film.id])continue;const signal=tasteSignal(reactions[film.id]);if(!signal)continue;const vector=tasteFeatures(film,includeDirectorAliases);anchors.push([signal,new Map(vector.map(([key,share,kind])=>[key,{share,kind}])),Date.parse(reactions[film.id].ratedAt)||0]);
  for(const [key,share] of vector){sums.set(key,(sums.get(key)||0)+signal*share);counts.set(key,(counts.get(key)||0)+1);shares.set(key,(shares.get(key)||0)+share);}
 }
 const baseline=anchors.length?anchors.reduce((sum,[signal])=>sum+signal,0)/anchors.length:0;
 const profile=new Map([...sums].map(([key,value])=>[key,.25*value/(counts.get(key)+2)+.75*(value-baseline*shares.get(key))/(counts.get(key)+4)]));profile.anchors=anchors.map(([signal,vector,at])=>[signal,vector,at,[...vector].reduce((sum,[key,{share,kind}])=>sum+share*featureWeight(key,kind),0)]);profile.neighborIndex=new Map();for(let i=0;i<profile.anchors.length;i++)for(const [key,{kind}] of profile.anchors[i][1])if(kind==='keyword'||kind==='director'||kind==='category'&&key!=='category:horror'){if(!profile.neighborIndex.has(key))profile.neighborIndex.set(key,[]);profile.neighborIndex.get(key).push(i);}profile.contrastWeights=new Map(profile);
 const positive=new Map(),negative=new Map(),examples=[];let positiveCount=0,negativeCount=0;
 for(const film of films){const label=normalizeRating(reactions[film.id])?.impression;if(label!=='like'&&label!=='dislike')continue;const counts=label==='like'?positive:negative;if(label==='like')positiveCount++;else negativeCount++;const vector=predictiveFeatures(film,includeQuality,includeDirectorAliases,includeReach&&includeQuality&&includeDirectorAliases&&includePublicQuality,runtimeEnabled);examples.push([marginFeatures(vector),label==='like']);for(const [key,share] of vector)counts.set(key,(counts.get(key)||0)+share);}
 profile.predictive=positiveCount>=3&&negativeCount>=3&&positiveCount+negativeCount>=20;
 if(profile.predictive){const total=positiveCount+negativeCount,positivePrior=2*positiveCount/total,negativePrior=2*negativeCount/total;profile.balancedWeights=new Map([...new Set([...positive.keys(),...negative.keys()])].map(key=>[key,Math.log(((positive.get(key)||0)+positivePrior)/(positiveCount+positivePrior))-Math.log(((negative.get(key)||0)+negativePrior)/(negativeCount+negativePrior))]));const trained=fitMargin(examples);profile.clear();for(const [key,value] of trained.weights)profile.set(key,value);profile.bias=trained.bias;}
 profile.includeQuality=includeQuality;profile.includeDirectorAliases=includeDirectorAliases;profile.includePublicQuality=includeQuality&&includePublicQuality;
 profile.includeSynopsis=includeSynopsis&&includeQuality&&includeDirectorAliases&&includePublicQuality;profile.includeReach=includeReach&&includeQuality&&includeDirectorAliases&&includePublicQuality;
 profile.includeRuntime=runtimeEnabled;
 profile.synopsisModel=profile.predictive&&profile.includeSynopsis?fitSynopsis(films,reactions):null;
 profile.modelVersion=profile.predictive?(profile.includeRuntime?tasteModelVersion:profile.includeSynopsis||profile.includeReach?'synopsis-aware40':includeQuality?(includeDirectorAliases?(includePublicQuality?'reliability-aware38':'director-aware37'):'quality-aware36'):'empirical-taste32'):'contrast-fallback';

 profile.productionModel=profile.predictive&&includeProduction&&includeQuality&&includeDirectorAliases&&includePublicQuality&&(profile.includeSynopsis||profile.includeReach||profile.includeRuntime)?fitProduction(films.filter(isEligibleForDiscovery),reactions):null;
 if(profile.productionModel?.ready)profile.modelVersion='production-aware43';
 cachedProfiles.set(reactions,{signature,profile});return profile;
}
const importance={genre:1,category:5,keyword:4,director:2,language:.75,period:.75,quality:.75,reach:1.5,runtime:.75};
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
function predictiveFeatures(film,includeQuality=true,includeDirectorAliases=true,includeReach=true,includeRuntime=true){
 const vector=tasteFeatures(film,includeDirectorAliases),language=film.originalLanguage||film.original_language;
 if(language)vector.push([`language:${language}`,1,'language']);
 const year=Number(film.year||String(film.release_date||'').slice(0,4));
 if(Number.isInteger(year)&&year>0)vector.push([`period:${Math.floor(year/5)}`,1,'period']);
 const rating=film.rating??film.vote_average;if(includeQuality&&Number.isFinite(rating)&&rating>0&&rating<=10)vector.push([`quality:${Math.min(9,Math.floor(rating))}`,1,'quality']);
 const popularity=film.popularity??film.remoteMetrics?.popularity;if(includeReach&&Number.isFinite(popularity)&&popularity>=0)vector.push([`reach:${Math.min(8,Math.floor(Math.log2(popularity+1)))}`,1,'reach']);
 const duration=film.minutes??film.runtime;if(includeRuntime&&Number.isFinite(duration)&&duration>0)vector.push([`runtime:${Math.min(12,Math.floor(duration/20))}`,1,'runtime']);
 return vector;
}
export function tasteScore(film,profile){
 const target=filmCategories(film).some(c=>c==='horror'||c==='dystopian');
 if(profile.predictive){const vector=predictiveFeatures(film,profile.includeQuality!==false,profile.includeDirectorAliases!==false,profile.includeReach===true,profile.includeRuntime===true).filter(([key,,kind])=>!['reach','runtime'].includes(kind)||profile.balancedWeights.has(key)),frequency=3*vector.reduce((sum,[key,share,kind])=>sum+(profile.balancedWeights.get(key)||0)*share*featureWeight(key,kind),0)/Math.max(1,vector.reduce((sum,[key,share,kind])=>sum+share*featureWeight(key,kind),0));const rating=film.rating??film.vote_average,quality=profile.includePublicQuality&&Number.isFinite(rating)&&rating>0&&rating<=10?.2*(rating-6.5):0;return (target?1:0)+.25*tasteAcceptanceScore(film,profile)+.75*frequency+quality+.25*synopsisScore(film,profile.synopsisModel)+.5*productionScore(film,profile.productionModel);}
 const vector=tasteFeatures(film);return (target?1:0)+vector.reduce((value,[key,share,kind])=>value+(profile.get(key)||0)*share*featureWeight(key,kind),0)+nearbyScore(vector,profile.neighborIndex?[...new Set(vector.flatMap(([key])=>profile.neighborIndex.get(key)||[]))].sort((a,b)=>a-b).map(i=>profile.anchors[i]):profile.anchors||[])*2;
}

export function tasteAcceptanceScore(film,profile){
 if(profile.predictive)return profile.bias+marginFeatures(predictiveFeatures(film,profile.includeQuality!==false,profile.includeDirectorAliases!==false,profile.includeReach===true,profile.includeRuntime===true)).reduce((sum,[key,share])=>sum+(profile.get(key)||0)*share,0);
 return tasteScore(film,profile)-(filmCategories(film).some(c=>c==='horror'||c==='dystopian')?1:0);
}
