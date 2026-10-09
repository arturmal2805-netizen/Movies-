import {categoryRules} from './category-rules.js';
export const categoryOptions = [
 ['all','✦','Все фильмы'],
 ['creature-horror','◉','Creature Horror'],
 ['dystopian','▦','Dystopian Movies'],
 ['psychological-horror','◈','Psychological Horror'],
 ['body-horror','⌁','Body Horror'],
 ['folklore-horror','☾','Folklore Horror'],
 ['comedy','☺','Комедия'],
 ['adventure','↗','Приключение'],
 ['anime','✧','Аниме']
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
  const keyword=categoryRules.keywords[category].some(term=>words.includes(term));
  const phrase=categoryRules.phrases[category].some(term=>{
   const at=description.indexOf(term);if(at<0)return false;
   if(/(?:not(?: a)?|не)\s*$/.test(description.slice(Math.max(0,at-8),at)))return false;
   return (at===0||!/[\p{L}\p{N}]/u.test(description[at-1]))&&!/[\p{L}\p{N}]/u.test(description[at+term.length]||'');
  });
  if(keyword||phrase)found.add(category);
 }
 if(ids.includes(35)||film.genre==='Комедия')found.add('comedy');
 if(ids.includes(12)||film.genre==='Приключения')found.add('adventure');
 const countries=Array.isArray(film.productionCountries)?film.productionCountries:[];
 const japanese=film.originalLanguage==='ja'||!film.originalLanguage&&countries.includes('JP');
 if(film.genre==='Аниме'||ids.includes(16)&&(japanese||words.includes('anime')))found.add('anime');
 return categoryOptions.slice(1).map(([id])=>id).filter(id=>found.has(id));
}
