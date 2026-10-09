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

// Known films remain classifiable when an older saved record lacks keywords.
const known = {
 'creature-horror': [348,679,1091,106,9362,5876,9392,300668],
 dystopian: [76341,78,339846,9693,110415,7299,70160,254320,9314],
 'psychological-horror': [493922,530385,310131,694,242224,270303,44214],
 'body-horror': [1091,9426,837,933260,630240,393519,300668],
 'folklore-horror': [310131,530385]
};

export function filmCategories(film) {
 const ids = Array.isArray(film.genreIds)?film.genreIds:[];
 const words = Array.isArray(film.keywords)?film.keywords.map(k=>typeof k==='string'?k:k?.name||'').join(' '):'';
 const text = `${words} ${film.description||film.overview||''}`.toLocaleLowerCase('ru').replace(/[-_]/g,' ');
 const horror = ids.includes(27)||film.genre==='Ужасы';
 const found = new Set(Object.entries(known).filter(([,values])=>values.includes(film.tmdbId)).map(([id])=>id));
 if(horror&&/creature feature|creature horror|monster movie|giant monster|монстр|чудовищ/.test(text))found.add('creature-horror');
 if(/dystopi|антиутоп/.test(text))found.add('dystopian');
 if(horror&&/psychological horror|psychological thriller|психологическ.{0,20}(?:ужас|хоррор)/.test(text))found.add('psychological-horror');
 if(horror&&/body horror|телесн.{0,20}(?:ужас|хоррор)|боди хоррор/.test(text))found.add('body-horror');
 if(horror&&/folk horror|folklore horror|folk tale|фолк.{0,20}(?:ужас|хоррор)/.test(text))found.add('folklore-horror');
 if(ids.includes(35)||film.genre==='Комедия')found.add('comedy');
 if(ids.includes(12)||film.genre==='Приключения')found.add('adventure');
 const countries=Array.isArray(film.productionCountries)?film.productionCountries:[];
 if(film.genre==='Аниме'||/\banime\b/.test(words.toLowerCase())||ids.includes(16)&&(film.originalLanguage==='ja'||countries.includes('JP')))found.add('anime');
 return categoryOptions.slice(1).map(([id])=>id).filter(id=>found.has(id));
}
