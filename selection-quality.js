import {audienceFirstScore,audienceProductionScore,publicQualityScore} from './audience-priority.js?v=quality47';
import {productionExclusion} from './production-policy.js?v=quality47';
import {buildTasteProfile,tasteScore} from './taste.js?v=quality43';
import {filmCategories,isEligibleForDiscovery} from './categories.js?v=quality43';

export function ratingSummary(rows){
 const unique=new Map();
 for(const row of rows){
  if(!Number.isInteger(row?.tmdb_id)||row.tmdb_id<=0)continue;
  const previous=unique.get(row.tmdb_id);
  if(!previous||String(row.updated_at||'')>=String(previous.updated_at||''))unique.set(row.tmdb_id,row);
 }
 const count=list=>{
  const result={like:0,dislike:0,neutral:0,watched:0,unknown:0};
  for(const row of list)result[Object.hasOwn(result,row.impression)?row.impression:'unknown']++;
  result.decisive=result.like+result.dislike;
  result.precision=result.decisive?result.like/result.decisive:null;
  result.total=list.length;return result;
 };
 const all=[...unique.values()];
 const recommendations=all.filter(r=>['manual','scheduled'].includes(r.metadata?.recommendationMode));
 const latest=recommendations.filter(r=>r.updated_at).sort((a,b)=>String(b.updated_at).localeCompare(String(a.updated_at))||b.tmdb_id-a.tmdb_id).slice(0,30);
 return {all:count(all),recommended:count(recommendations),latest:count(latest)};
}

function chronological(rows){return rows.filter(r=>['like','dislike'].includes(r.impression)).sort((a,b)=>String(a.updated_at||'').localeCompare(String(b.updated_at||''))||a.tmdb_id-b.tmdb_id);}
function modelFor(rows,includeQuality=true,includeDirectorAliases=true,includePublicQuality=true,includeSynopsis=true,includeReach=true,includeRuntime=true,includeProduction=true){
 const films=rows.map(r=>({...r.metadata,id:r.tmdb_id,tmdbId:r.tmdb_id}));
 const reactions=Object.fromEntries(rows.map(r=>[r.tmdb_id,{impression:r.impression,plot:r.plot,cinematography:r.cinematography,ratedAt:r.updated_at,feedbackStage:r.metadata?.ratingFeedbackStage||'unknown',interestLevel:r.metadata?.ratingInterestLevel}]));
 return buildTasteProfile(films,reactions,{includeQuality,includeDirectorAliases,includePublicQuality,includeSynopsis,includeReach,includeRuntime,includeProduction});
}
function score(film,model){return tasteScore(film,model)-(filmCategories(film).some(c=>c==='horror'||c==='dystopian')?1:0);}
export function selectionFloor(rows,includeQuality=true){
 const decisive=chronological(rows);
 if(decisive.length<100||decisive.some(r=>!r.updated_at))return null;
 const split=Math.floor(decisive.length*.8),model=modelFor(decisive.slice(0,split),includeQuality);
 const validation=decisive.slice(split).filter(r=>isEligibleForDiscovery(r.metadata||{}));
 const positives=validation.filter(r=>r.impression==='like').map(r=>score(r.metadata,model)).sort((a,b)=>a-b);
 if(!model.predictive||validation.length<20||positives.length<2)return null;
 const scores=validation.map(r=>score(r.metadata,model)).sort((a,b)=>a-b),middle=Math.floor(positives.length/2);
 const median=positives.length%2?positives[middle]:(positives[middle-1]+positives[middle])/2;
 return Math.min(scores[Math.floor((scores.length-1)*.85)],median);
}
export function evaluateSelection(rows){
 const decisive=chronological(rows);
 if(decisive.length<100||decisive.some(r=>!r.updated_at))return {status:'insufficient'};
 const split=Math.floor(decisive.length*.8),train=decisive.slice(0,split);
 const test=decisive.slice(split).filter(r=>isEligibleForDiscovery(r.metadata||{})),model=modelFor(train);
 const previous=model,previousFloor=null;
 const measure=(selectedModel,cutoff,legacyGate,legacyAudience=false)=>{
  const predictions=test.filter(r=>legacyAudience||!productionExclusion(r.metadata)).map(r=>{const personal=score(r.metadata,selectedModel);return [legacyAudience?audienceFirstScore(r.metadata):audienceProductionScore(r.metadata),personal+publicQualityScore(r.metadata,selectedModel.predictive),r.impression==='like',r.tmdb_id];});
  const ordered=[...predictions].sort((a,b)=>b[0]-a[0]||b[1]-a[1]||a[3]-b[3]);
  const pool=ordered.filter(([value,margin])=>!legacyGate||margin>=-.8&&(cutoff===null||value>=cutoff)),kept=pool.slice(0,30);
  const liked=kept.filter(([, ,label])=>label).length;
  return {accepted:kept.length,liked,precision:kept.length?liked/kept.length:null,eligible_pool:pool.length,likes_at_10:kept.slice(0,10).filter(([, ,y])=>y).length};
 };
 return {status:'evaluated',training:train.length,tested:test.length,positives:test.filter(r=>r.impression==='like').length,floor:previousFloor,metric:'top_30',before:measure(previous,previousFloor,false,true),after:measure(model,null,false)};
}
