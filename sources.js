export const cardRule = 'У карточки должны быть постер, IMDb score и популярность TMDB с указанием источника и даты обновления. Отсутствующие значения не выдумываются.';
export const sourceDefinitions = [
 {id:'local',name:'Локальный каталог',purpose:'Исходная подборка из 12 фильмов',status:'local',note:'Встроен в сайт. Это не внешний импорт.'},
 {id:'tmdb',name:'TMDB',purpose:'Постеры и popularity score',status:'not_connected',note:'Автоматический импорт подготовлен. Нужен TMDB_ACCESS_TOKEN в GitHub Actions.'},
 {id:'trakt',name:'Trakt',purpose:'Тренды и популярные фильмы для персонального подбора',status:'scheduled',note:'Ожидаем подтверждённое пополнение через Trakt. Войдите в аккаунт, чтобы проверить серверную коллекцию.'},
 {id:'imdb',name:'IMDb через OMDb',purpose:'Рейтинг IMDb',status:'not_connected',note:'Сейчас оценки записаны вручную. Для обновлений нужен OMDB_API_KEY в GitHub Actions.'},
 {id:'netflix',name:'Netflix',purpose:'Каталог стриминга',status:'not_connected',note:'Прямой импорт не подключён. Наличие фильма на Netflix не проверяется.'},
 {id:'shudder',name:'Shudder',purpose:'Каталог стриминга',status:'not_connected',note:'Прямой импорт не подключён. Наличие фильма на Shudder не проверяется.'}
];
export function hasCompleteMetadata(f){return Boolean(f.poster&&Number.isFinite(f.imdb)&&Number.isFinite(f.popularity));}
export function sourceState(id,snapshot,now=Date.now(),collection=[]){
 const base=sourceDefinitions.find(s=>s.id===id);
 if(id==='local')return {...base,status:'local'};
 if(id==='trakt'){
  const times=collection.filter(row=>row.reason&&Array.isArray(row.metadata?.discoverySources)&&row.metadata.discoverySources.includes('trakt')).map(row=>Date.parse(row.created_at)).filter(time=>Number.isFinite(time)&&time<=now);
  if(!times.length)return {...base};
  const latest=Math.max(...times),stale=now-latest>3*60*60*1000;
  return {...base,status:stale?'stale':'ok',lastSuccess:new Date(latest).toISOString(),note:stale?'Ранее Trakt добавлял фильмы. Свежих подтверждённых пополнений пока нет.':'Сервер подтвердил пополнение фильмом, найденным через Trakt. Последующая доступность API проверяется при очередном подборе.'};
 }
 const entry=snapshot?.sources?.[id];
 if(!entry)return {...base};
 const stamp=Date.parse(entry.lastSuccess||'');
 const stale=!Number.isFinite(stamp)||now-stamp>3*60*60*1000;
 return {...base,...entry,status:entry.status==='ok'&&stale?'stale':entry.status};
}
