import {buildTasteProfile,tasteScore,tasteAcceptanceScore} from './taste.js?v=quality35';
import {filmCategories,isEligibleForDiscovery} from './categories.js?v=quality35';

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
 return {all:count(all),recommended:count(all.filter(r=>['manual','scheduled'].includes(r.metadata?.recommendationMode)))};
}

function chronological(rows){return rows.filter(r=>['like','dislike'].includes(r.impression)).sort((a,b)=>String(a.updated_at||'').localeCompare(String(b.updated_at||''))||a.tmdb_id-b.tmdb_id);}
function modelFor(rows){
 const films=rows.map(r=>({...r.metadata,id:r.tmdb_id,tmdbId:r.tmdb_id}));
 const reactions=Object.fromEntries(rows.map(r=>[r.tmdb_id,{impression:r.impression,plot:r.plot,cinematography:r.cinematography,ratedAt:r.updated_at}]));
 return buildTasteProfile(films,reactions);
}
function score(film,model){return tasteScore(film,model)-(filmCategories(film).some(c=>c==='horror'||c==='dystopian')?1:0);}
export function selectionFloor(rows){
 const decisive=chronological(rows);
 if(decisive.length<100||decisive.some(r=>!r.updated_at))return null;
 const split=Math.floor(decisive.length*.8),model=modelFor(decisive.slice(0,split));
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
 const test=decisive.slice(split).filter(r=>isEligibleForDiscovery(r.metadata||{})),model=modelFor(train),floor=selectionFloor(train);
 const predictions=test.map(r=>[score(r.metadata,model),tasteAcceptanceScore(r.metadata,model),r.impression==='like']);
 const measure=calibrated=>{
  const kept=predictions.filter(([value,margin])=>margin>=-.8&&(!calibrated||floor===null||value>=floor));
  const liked=kept.filter(([, ,label])=>label).length;
  return {accepted:kept.length,liked,precision:kept.length?liked/kept.length:null};
 };
 return {status:'evaluated',training:train.length,tested:test.length,positives:predictions.filter(([, ,y])=>y).length,floor,before:measure(false),after:measure(true)};
}
