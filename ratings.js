export function normalizeRating(value){
 if(typeof value==='string'&&['like','dislike','watched'].includes(value))return {impression:value};
 if(!value||typeof value!=='object'||Array.isArray(value))return null;
 const result={};
 for(const key of ['cinematography','plot'])if(Number.isInteger(value[key])&&value[key]>=1&&value[key]<=10)result[key]=value[key];
 if(['like','neutral','dislike','watched'].includes(value.impression))result.impression=value.impression;
 if(typeof value.ratedAt==='string')result.ratedAt=value.ratedAt;
 return Object.keys(result).length?result:null;
}
export function ratingWeight(value){const r=normalizeRating(value);if(!r)return 0;let weight=({like:1,neutral:0,dislike:-1,watched:0})[r.impression]||0;const scales=[r.cinematography,r.plot].filter(Number.isFinite);if(scales.length)weight+=scales.reduce((a,b)=>a+b,0)/scales.length/5.5-1;return weight;}
export function isArchived(value){const r=normalizeRating(value);return Boolean(r?.ratedAt||['watched','dislike'].includes(r?.impression));}
