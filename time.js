export const siteTimeZone='Europe/Kyiv';
export function kyivTime(value=Date.now(),date=true){
 return new Intl.DateTimeFormat('ru-RU',{timeZone:siteTimeZone,...(date?{day:'2-digit',month:'2-digit',year:'numeric'}:{}),hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(value));
}
export function recentRecommendations(collection,now=Date.now()){
 const ids=new Set();let latest=null;
 for(const row of collection){
  if(!row.reason)continue;
  const added=Date.parse(row.created_at);
  if(!Number.isFinite(added)||added>now)continue;
  if(latest===null||added>latest)latest=added;
  if(now-added<60*60*1000)ids.add(row.tmdb_id);
 }
 return {count:ids.size,latest};
}

// GitHub Actions cron: 17 * * * *. UTC arithmetic also handles Kyiv DST.
export function nextRecommendationRun(now=Date.now()){
 const hour=60*60*1000;
 const slot=Math.floor(now/hour)*hour+17*60*1000;
 return slot>now?slot:slot+hour;
}
