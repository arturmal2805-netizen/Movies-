// Match the server's audience prior; missing values are neutral, never a veto.
import {tasteScore,buildTasteProfile} from './taste.js?v=quality43';
import {filmCategories,isEligibleForDiscovery} from './categories.js?v=quality43';
import {productionPolicy,productionExclusion,budgetPriorityScore} from './production-policy.js?v=quality47';
export {buildTasteProfile as buildSelectionProfile};
export const selectionVersion='audience-first47';
export function isEligibleForSelection(film){return isEligibleForDiscovery(film)&&!productionExclusion(film);}
export function audienceProductionScore(film){
 const popularity=film.popularity??film.remoteMetrics?.popularity,votes=film.vote_count??film.remoteMetrics?.voteCount;
 return (Number.isFinite(popularity)&&popularity>0?productionPolicy.popularity_weight*Math.log2(1+popularity):0)+(Number.isFinite(votes)&&votes>0?productionPolicy.votes_weight*Math.log2(1+votes):0)+budgetPriorityScore(film);
}
export function audienceFirstScore(film){
 const popularity=film.popularity??film.remoteMetrics?.popularity,votes=film.vote_count??film.remoteMetrics?.voteCount;
 return (Number.isFinite(popularity)&&popularity>0?3*Math.log2(1+popularity):0)+(Number.isFinite(votes)&&votes>0?Math.log2(1+votes):0);
}
export function audienceScore(film,{legacy=false}={}){
 const popularity=film.popularity??film.remoteMetrics?.popularity;
 const votes=film.vote_count??film.remoteMetrics?.voteCount;
 let score=0;
 if(Number.isFinite(popularity)&&popularity>0)score=(legacy?.4:1.6)*Math.max(-2,Math.min(2,Math.log2((popularity+1)/9)));
 if(Number.isFinite(votes)&&votes>0)score+=(legacy?.1:.7)*Math.max(-1,Math.min(3,Math.log2((votes+500)/1500)));
 return score;
}
export function publicQualityScore(film,predictive=false,{legacy=false}={}){
 const rating=film.rating??film.vote_average,votes=film.vote_count??film.remoteMetrics?.voteCount;
 if(!Number.isFinite(rating)||rating<=0||rating>10||!Number.isFinite(votes)||votes<=0)return 0;
 const quality=6.5+(rating-6.5)*(votes/(votes+500));
 return (quality-6.5)*(predictive?(legacy?.006:.2):.08);
}
export function audiencePriorityScore(film,predictive=false,{legacy=false}={}){
 const value=audienceScore(film,{legacy})+publicQualityScore(film,predictive,{legacy});
 return legacy?value:Math.max(-3,Math.min(3,value));
}
export function selectionScore(film,profile,options={}){
 return options.legacy||options.legacyVersion==='45'?tasteScore(film,profile)+audiencePriorityScore(film,profile.predictive,options):options.legacyVersion==='46'?audienceFirstScore(film):audienceProductionScore(film);
}
export function selectionSecondaryScore(film,profile){return tasteScore(film,profile)-(filmCategories(film).some(c=>c==='horror'||c==='dystopian')?1:0)+publicQualityScore(film,profile.predictive);}
export function compareSelection(a,b,profile,scores=null,secondary=null){
 const primary=film=>scores?.get(film.id)??selectionScore(film,profile);
 const tie=film=>secondary?.get(film.id)??selectionSecondaryScore(film,profile);
 return primary(b)-primary(a)||tie(b)-tie(a)||(a.tmdbId??a.id)-(b.tmdbId??b.id);
}
