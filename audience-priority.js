// Match the server's audience prior; missing values are neutral, never a veto.
import {tasteScore} from './taste.js?v=quality43';
export const selectionVersion='audience-priority44';
export function audienceScore(film){
 const popularity=film.popularity??film.remoteMetrics?.popularity;
 const votes=film.vote_count??film.remoteMetrics?.voteCount;
 let score=0;
 if(Number.isFinite(popularity)&&popularity>0)score=.4*Math.max(-2,Math.min(2,Math.log2((popularity+1)/9)));
 if(Number.isFinite(votes)&&votes>0)score+=.1*Math.max(-1,Math.min(3,Math.log2((votes+500)/1500)));
 return score;
}
export function publicQualityScore(film,predictive=false){
 const rating=film.rating??film.vote_average,votes=film.vote_count??film.remoteMetrics?.voteCount;
 if(!Number.isFinite(rating)||rating<=0||rating>10||!Number.isFinite(votes)||votes<=0)return 0;
 const quality=6.5+(rating-6.5)*(votes/(votes+500));
 return (quality-6.5)*(predictive?.006:.08);
}
export function selectionScore(film,profile){return tasteScore(film,profile)+audienceScore(film)+publicQualityScore(film,profile.predictive);}
