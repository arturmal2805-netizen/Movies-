// Match the server's audience prior; missing values are neutral, never a veto.
import {normalizeInterests,buildStyleModel} from './interests.js?v=quality53';
import {tasteScore,buildTasteProfile} from './taste.js?v=quality53';
import {filmCategories,isEligibleForDiscovery} from './categories.js?v=quality53';
import {productionPolicy,productionExclusion,styleAffinity} from './production-policy.js?v=quality53';
export function buildSelectionProfile(films,reactions,interests){
 const profile=buildTasteProfile(films,reactions),preferences=normalizeInterests(interests),key=JSON.stringify(preferences);
 if(profile.styleKey!==key){profile.interests=preferences;profile.styleModel=buildStyleModel(films,reactions,preferences);profile.styleKey=key;}
 return profile;
}
export const selectionVersion='audience-first53';
export function isEligibleForSelection(film,interests){return isEligibleForDiscovery(film)&&!productionExclusion(film,{interests});}
export function publicQualityTier(film){
 const rating=film.rating??film.vote_average,votes=film.vote_count??film.remoteMetrics?.voteCount;
 if(!Number.isFinite(rating)||rating<=0||rating>10||!Number.isFinite(votes)||votes<=0)return 0;
 const estimate=6+(rating-6)*(votes/(votes+500));return estimate>=6.25?2:estimate>=5.5?1:0;
}
export function audienceProductionScore(film,{legacy=false,styleModel=null}={}){
 const popularity=film.popularity??film.remoteMetrics?.popularity,votes=film.vote_count??film.remoteMetrics?.voteCount;
 return (Number.isFinite(popularity)&&popularity>0?productionPolicy.popularity_weight*Math.log2(1+popularity):0)+(Number.isFinite(votes)&&votes>0?productionPolicy.votes_weight*Math.log2(1+votes):0)+imdbAudienceBonus(film)+(legacy?0:6*styleAffinity(film,styleModel));
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
export function validatedImdbMetrics(film){
 const r=film.remoteMetrics;if(!r||r.imdbVerified!==true||typeof r.imdbId!=='string'||!/^tt[0-9]{7,12}$/.test(r.imdbId))return null;
 const canonical=film.imdb_id??film.imdbId;if(canonical&&canonical!==r.imdbId)return null;
 return Number.isFinite(r.imdb)&&r.imdb>0&&r.imdb<=10&&Number.isSafeInteger(r.imdbVoteCount)&&r.imdbVoteCount>0&&r.imdbVoteCount<=1e10?{rating:r.imdb,votes:r.imdbVoteCount}:null;
}
export function confidenceQuality(film){
 const rating=film.rating??film.vote_average,votes=film.vote_count??film.remoteMetrics?.voteCount;
 const valid=Number.isFinite(rating)&&rating>0&&rating<=10&&Number.isFinite(votes)&&votes>0;
 const tmdb=valid?5+(rating-5)*(votes/(votes+300)):5,imdb=validatedImdbMetrics(film);
 if(!imdb)return tmdb;
 const estimate=5+(imdb.rating-5)*(imdb.votes/(imdb.votes+1000));return valid?(tmdb+estimate)/2:estimate;
}
export function selectionPriorityScore(film,personal=0,styleModel=null){
 return audienceProductionScore(film,{legacy:true})+10*(confidenceQuality(film)-6)+(Number.isFinite(personal)?7*Math.tanh(personal/3):0)+6*styleAffinity(film,styleModel);
}
export function selectionScore(film,profile,options={}){
 return options.legacy||options.legacyVersion==='45'?tasteScore(film,profile)+audiencePriorityScore(film,profile.predictive,options):options.legacyVersion==='46'?audienceFirstScore(film):options.legacyVersion==='48'?audienceProductionScore(film,{styleModel:profile.styleModel}):selectionPriorityScore(film,personalFitScore(film,profile),profile.styleModel);
}
export function personalFitScore(film,profile){return tasteScore(film,profile)-(filmCategories(film).some(c=>c==='horror'||c==='dystopian')?1:0);}
export function selectionSecondaryScore(film,profile){return personalFitScore(film,profile)+publicQualityScore(film,profile.predictive);}
export function compareSelection(a,b,profile,scores=null,secondary=null){
 const primary=film=>scores?.get(film.id)??selectionScore(film,profile);
 const tie=film=>secondary?.get(film.id)??selectionSecondaryScore(film,profile);
 return primary(b)-primary(a)||tie(b)-tie(a)||(a.tmdbId??a.id)-(b.tmdbId??b.id);
}

export function imdbAudienceBonus(film){
 const evidence=validatedImdbMetrics(film),floor=productionPolicy.imdb_audience_floor;
 if(!evidence)return 0;
 const quality=Math.max(0,Math.min(1,(evidence.rating-6)*2)),support=Math.min(1,evidence.votes/floor);
 return quality*support*(productionPolicy.imdb_audience_weight+6*Math.log2(1+evidence.votes/floor));
}
