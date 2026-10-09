import {categoryRules} from './category-rules.js?v=liquid-focus21';
export const categoryOptions = [
 ['all','✦','Все фильмы'],
 ['horror','☠','Horror'],
 ['creature-horror','◉','Creature Horror'],
 ['dystopian','▦','Dystopian Movies'],
 ['psychological-horror','◈','Psychological Horror'],
 ['body-horror','⌁','Body Horror'],
 ['folklore-horror','☾','Folk Horror']
];

const normalize = value => String(value||'').toLocaleLowerCase('ru').replace(/[-_]/g,' ').replace(/\s+/g,' ').trim();
export function filmCategories(film) {
 const ids=Array.isArray(film.genreIds)?film.genreIds:[];
 const words=(Array.isArray(film.keywords)?film.keywords:[]).map(k=>normalize(typeof k==='string'?k:k?.name)).filter(Boolean);
 const description=normalize(film.description||film.overview);
 const horror=ids.includes(27)||film.genre==='Ужасы';
 const found=new Set();
 for(const [category,known] of Object.entries(categoryRules.known)) {
  if(known.includes(film.tmdbId)){found.add(category);continue;}
  if(category!=='dystopian'&&!horror)continue;
  // Exact provider keywords take priority; descriptions only match explicit subgenre labels.
  const keyword=categoryRules.keywords[category].some(term=>words.includes(term))||(categoryRules.keyword_groups?.[category]||[]).some(group=>group.every(term=>words.includes(term)));
  const phrase=categoryRules.phrases[category].some(term=>{
   const at=description.indexOf(term);if(at<0)return false;
   if(/(?:not(?: a)?|не)\s*$/.test(description.slice(Math.max(0,at-8),at)))return false;
   return (at===0||!/[\p{L}\p{N}]/u.test(description[at-1]))&&!/[\p{L}\p{N}]/u.test(description[at+term.length]||'');
  });
  if(keyword||phrase)found.add(category);
 }
 if(horror||[...found].some(id=>id!=='dystopian'))found.add('horror');
 return categoryOptions.slice(1).map(([id])=>id).filter(id=>found.has(id));
}

export function isEligibleForDiscovery(film){
 const policy=categoryRules.selection;
 if(!Number.isInteger(film.year)||film.year<policy.minimum_year)return false;
 const ids=new Set(film.genreIds||[]),labels={'Документальный':99,'Документальное':99,'Documentary':99,'Мелодрама':10749,'Романтика':10749,'Romance':10749,'Драма':18,'Drama':18,'Боевик':28,'Action':28};
 if(labels[film.genre])ids.add(labels[film.genre]);
 if(policy.always_excluded_genres.some(id=>ids.has(id)))return false;
 const target=filmCategories(film).some(id=>id==='horror'||id==='dystopian');
 return !policy.excluded_genres.some(id=>ids.has(id))||policy.allow_target_mixed_genres&&target;
}
