"""Private recommendations stay in Supabase, never in the public Pages snapshot."""
import os,json,hashlib,datetime,urllib.request,urllib.parse,math,time,base64,threading,copy,uuid
from collections import Counter
from itertools import combinations
from concurrent.futures import Future,ThreadPoolExecutor
from statistics import median
from pathlib import Path
from recommendation_sources import discover,hourly_limit,detail_path
from movie_features import profile,match_score,rejection_score,genres,keywords,director,classify,normalize,feature_metadata,eligible_for_discovery,rating_signal,features,specific_feature,GENERIC
from import_catalog import IDS
from synopsis_model import synopsis_score
from production_model import production_score
from audience_priority import audience_production_score,public_quality_score,public_quality_tier,selection_priority_score,confidence_quality,SELECTION_VERSION
from interests import normalize_interests,build_style_model,style_key
from imdb_audience import enrich_audience,validated_imdb_metrics,validated_critics_score
from imdb_datasets import PublicImdbIndex,default_path
from candidate_policy import valid_candidate
from production_policy import production_exclusion,POLICY,director_focus,style_affinity
GENRES={28:'Боевик',12:'Приключения',16:'Анимация',35:'Комедия',80:'Криминал',99:'Документальный',18:'Драма',10751:'Семейный',14:'Фэнтези',36:'История',27:'Ужасы',10402:'Музыка',9648:'Детектив',10749:'Мелодрама',878:'Фантастика',10770:'Телефильм',53:'Триллер',10752:'Военный',37:'Вестерн'}
SEARCH_GENERIC=GENERIC|{'spin off','prequel','reboot','franchise','based on short film','based on play or musical'}

def taste(ratings):return {value:weight for (kind,value),weight in profile(ratings).items() if kind=='genre'}

def preferred_keyword_seeds(ratings,tastes):
 # Smoothed weights can be optimistic for rare tags. Search expansion needs
 # actual repeated positive evidence, not tags seen only in rejected movies.
 positive_support={};keyword_ids={}
 for row in ratings:
  if row.get('impression')!='like':continue
  for name in set(normalize(k if isinstance(k,str) else k.get('name')) for k in keywords(row.get('metadata') or {})):
   positive_support[name]=positive_support.get(name,0)+1
 for row in ratings:
  metadata=row.get('metadata') or {}
  for name,kid in zip(metadata.get('keywords') or [],metadata.get('keywordIds') or []):
   name=normalize(name if isinstance(name,str) else name.get('name'))
   if name in SEARCH_GENERIC:continue
   weight=tastes.get(('keyword',name),0)
   if tastes.predictive and (positive_support.get(name,0)<2 or tastes.balanced_weights.get(('keyword',name),0)<=0):continue
   if type(kid) is int and kid>0 and weight>0:
    keyword_ids[kid]=tastes.balanced_weights.get(('keyword',name),0)*math.log1p(positive_support.get(name,0)) if tastes.predictive else weight
 return sorted(keyword_ids,key=lambda kid:(-keyword_ids[kid],kid))[:12]

def preferred_periods(tastes,limit=2):
 # Search directions, not new age restrictions. Keep broad discovery alongside.
 if not tastes.predictive:return []
 keys=[key for key in tastes.balanced_weights if key[0]=='period' and tastes.positive_support.get(key,0)>=3 and tastes.balanced_weights[key]>0]
 return [key[1]*5 for key in sorted(keys,key=lambda key:(-tastes.balanced_weights[key],-key[1]))[:limit]]

def preferred_audience_languages(ratings):
 counts=Counter()
 for row in ratings:
  m=row.get('metadata')or{}
  if row.get('impression')!='like' or not eligible_for_discovery(m):continue
  lang=m.get('originalLanguage')or m.get('original_language')
  if isinstance(lang,str)and len(lang)==2 and lang.isascii()and lang.isalpha()and lang!='xx':counts[lang.lower()]+=1
 total=sum(counts.values())
 return [lang for lang,n in counts.most_common(2)if n>=3 and n/max(1,total)>=.6]

def preferred_production_seeds(tastes,kind,limit=6):
 model=getattr(tastes,'production_model',{})
 if not model.get('ready'):return []
 required=2 if kind=='company' else 3
 keys=[k for k,v in model['frequency'].items() if k[0]==kind and v>0 and model['positive_support'].get(k,0)>=required]
 return [int(k[1]) for k in sorted(keys,key=lambda k:(-model['frequency'][k]*math.log1p(model['positive_support'][k]),int(k[1])))[:limit]]

def supported_preference(tastes,key):
 if tastes.get(key,0)<=0:return False
 if not tastes.predictive:return True
 return tastes.positive_support.get(key,0)>=2 and tastes.balanced_weights.get(key,0)>0

def preferred_keyword_groups(ratings):
 # An AND-query expresses a repeated combination, not an isolated broad tag.
 # Count films once, compare class-normalized evidence, and diversify groups.
 positive=Counter();negative=Counter();p=n=0
 for row in ratings:
  if row.get('impression') not in ('like','dislike'):continue
  metadata=row.get('metadata') or {}
  if not eligible_for_discovery(metadata):continue
  specific={value for kind,value in features(metadata) if kind=='keyword' and value not in SEARCH_GENERIC}
  ids={kid for name,kid in zip(metadata.get('keywords') or [],metadata.get('keywordIds') or [])
       if type(kid) is int and kid>0 and isinstance(name,str) and normalize(name) in specific}
  if row['impression']=='like':p+=1;counter=positive
  else:n+=1;counter=negative
  counter.update(combinations(sorted(ids)[:24],2))
 if p<3 or n<3:return []
 pp=2*p/(p+n);np=2*n/(p+n)
 pool={pair:(math.log((count+pp)/(p+pp))-math.log((negative[pair]+np)/(n+np)))*math.log1p(count)
       for pair,count in positive.items() if count>=3}
 pool={pair:weight for pair,weight in pool.items() if weight>0}
 selected=[];used=Counter()
 while pool and len(selected)<4:
  pair=max(pool,key=lambda pair:(pool[pair]/(1+sum(used[kid] for kid in pair)),tuple(-kid for kid in pair)))
  selected.append(list(pair));used.update(pair);pool.pop(pair)
 return selected



def rank_candidates(candidates,ratings,collection,minimum_votes=100,now=None,preliminary=False,tastes=None):
 excluded={int(r['tmdb_id']) for r in ratings+collection}|set(IDS.values())
 if tastes is None:tastes=profile(ratings)
 ranked=[];seen=set();tie_scores={};today=(now.date() if now else datetime.datetime.now(datetime.timezone.utc).date())
 for movie in candidates:
  if not valid_candidate(movie,minimum_votes,today,require_target=False if preliminary else None,interests=getattr(tastes,'interests',None)) or movie['id'] in seen or movie['id'] in excluded:continue
  seen.add(movie['id'])
  personal=match_score(movie,tastes)
  # Learned fit, review confidence, audience breadth and style jointly order
  # the pool. A negative match causes more search, never a score-based veto.
  value=selection_priority_score(movie,personal,getattr(tastes,'style_model',None))
  tie_scores[movie['id']]=personal+public_quality_score(movie,tastes.predictive)
  # Sparse lists omit director/keywords; prioritize verifying personalized
  # routes. The final ranking uses canonical evidence rather than route bonuses.
  if preliminary:tie_scores[movie['id']]+=.4*bool(movie.get('_liked_directors'))+.2*bool(movie.get('_matched_theme_groups'))+.08*bool(movie.get('_liked_anchor_ids'))
  categories=classify(movie)
  favorite=sorted((g for g in genres(movie) if tastes.get(('genre',g),0)>0),key=lambda g:tastes[('genre',g)],reverse=True)
  themes=sorted((normalize(k if isinstance(k,str) else k.get('name')) for k in keywords(movie) if supported_preference(tastes,('keyword',normalize(k if isinstance(k,str) else k.get('name'))))),key=lambda name:tastes[('keyword',name)],reverse=True)
  reason='Совпадает с вашими оценками: '+', '.join(GENRES.get(g,'Жанр') for g in favorite[:2])+'.' if favorite else 'Для знакомства с новым жанром; учтены оценки и популярность TMDB.'
  if themes:reason='По вашим оценкам подходят темы: '+', '.join(themes[:2])+'.'
  elif personal<=0 and ratings:reason='Выбран по популярности TMDB и размеру аудитории; личное совпадение пока слабое.'
  evidence=validated_imdb_metrics(movie)
  if evidence and evidence['votes']>=10000 and personal<=0:reason='Подтверждённая аудитория IMDb: '+format(evidence['votes'],',').replace(',',' ')+' голосов; личное совпадение пока слабое.'
  if style_affinity(movie,getattr(tastes,'style_model',None))>0:reason='Совпадает сочетание тем из понравившихся примеров; учтены отзывы и популярность.'
  if not ratings:reason='Стартовая рекомендация по оценкам TMDB. После ваших оценок подбор станет персональным.'
  if 'horror' in categories:reason='Приоритет хоррорам. '+reason
  elif 'dystopian' in categories:reason='Приоритет антиутопиям. '+reason
  ranked.append((value,movie,reason))
 return sorted(ranked,key=lambda entry:(-entry[0],-tie_scores[entry[1]['id']],entry[1]['id']))

def diverse_candidates(ranked,strict_audience=False):
 if strict_audience:return list(ranked)
 # Diversity breaks close matches. An accumulating penalty must not override
 # personal evidence late in a batch or reward irrelevant mixed genres.
 remaining=list(ranked);used={};result=[]
 while remaining and len(result)<100:
  def priority(entry):
   ids=genres(entry[1]);penalty=min(.6,sum(used.get(g,0) for g in ids)/max(1,len(ids))*.12)
   return entry[0]-penalty,-entry[1]['id']
  index=max(range(len(remaining)),key=lambda i:priority(remaining[i]));entry=remaining.pop(index);result.append(entry)
  for genre in genres(entry[1]):used[genre]=used.get(genre,0)+1
 return result+remaining

def audience_votes(movie):
 value=movie.get('vote_count')
 if value is None:value=(movie.get('remoteMetrics')or{}).get('voteCount')if isinstance(movie.get('remoteMetrics'),dict)else None
 return value if type(value)in(int,float)and math.isfinite(value)and value>0 else 0

def selection55_diagnostics(final,target,tastes,ratings,collection):
 chosen=[e[1]for e in final[:target]];pool=[e[1]for e in final]
 def previous(m):
  remote=m.get('remoteMetrics');remote=remote if isinstance(remote,dict)else{}
  pop=m.get('popularity');pop=remote.get('popularity')if pop is None else pop;votes=audience_votes(m)
  public=(6*math.log2(1+pop)if type(pop)in(int,float)and math.isfinite(pop)and pop>0 else 0)+2.5*math.log2(1+votes)
  personal=match_score(m,tastes)
  rating=m.get('rating',m.get('vote_average'));quality=5+(rating-5)*(votes/(votes+300))if type(rating)in(int,float)and math.isfinite(rating)and 0<rating<=10 and votes>0 else 5.
  return public+10*(quality-6)+7*math.tanh(personal/3)+6*style_affinity(m,tastes.style_model)
 old=sorted(pool,key=lambda m:(-previous(m),-(match_score(m,tastes)+public_quality_score(m,tastes.predictive)),m['id']))[:target]
 rated={r['tmdb_id']for r in ratings}
 queued=[r['metadata']for r in collection if r.get('tmdb_id')not in rated and isinstance(r.get('metadata'),dict)and eligible_for_discovery(r['metadata'])and not production_exclusion(r['metadata'])]
 recent=sorted([r for r in ratings if (r.get('metadata')or{}).get('recommendationMode')in('manual','scheduled')],key=lambda r:str(r.get('updated_at')or''),reverse=True)[:30]
 return {'audiencePool1000':sum(audience_votes(m)>=1000 for m in pool),
         'audiencePool3000':sum(audience_votes(m)>=3000 for m in pool),
         'selectedAudience1000':sum(audience_votes(m)>=1000 for m in chosen),
         'selectedAudience3000':sum(audience_votes(m)>=3000 for m in chosen),
         'previous50Audience1000':sum(audience_votes(m)>=1000 for m in old),
         'previous50MedianVoteCount':median([audience_votes(m)for m in old])if old else 0,
         'highestAvailableVoteCount':max([audience_votes(m)for m in pool],default=0),
         'unratedExistingEligible':len(queued),'unratedExistingAudience1000':sum(audience_votes(m)>=1000 for m in queued),
         'latestThirtyFeedback':dict(Counter(r.get('impression')for r in recent))}

def audience_diagnostics(ranked,budget,predictive=False):
 # Export aggregate pool evidence so a weak future batch can be diagnosed
 # against the audience options that were actually available in that run.
 proposed=[entry[1] for entry in ranked[:budget]]
 strongest=sorted((entry[1] for entry in ranked),key=lambda m:(-public_quality_tier(m),-audience_production_score(m,legacy=True),m['id']))[:budget]
 def center(movies,key):
  values=[m[key] for m in movies if type(m.get(key)) in (int,float) and math.isfinite(m[key])]
  return round(median(values),3) if values else None
 return {'recommendationProposedPopularityMedian':center(proposed,'popularity'),
         'recommendationProposedVoteMedian':center(proposed,'vote_count'),
         'recommendationAudiencePoolPopularityMedian':center(strongest,'popularity'),
         'recommendationAudiencePoolVoteMedian':center(strongest,'vote_count')}


class RequestFailure(RuntimeError):
 """Safe diagnostics only: never include URLs, headers, body, or credentials."""
 pass

def error_summary(error):
 return str(error) if isinstance(error,RequestFailure) else type(error).__name__

class Backend:
 def __init__(self):
  self.url=os.environ['SUPABASE_URL'].strip().rstrip('/')
  # API tokens contain no whitespace; clipboard wrapping must not break HTTP headers.
  self.key=''.join(os.environ['SUPABASE_SERVICE_ROLE_KEY'].split())
  self.tmdb=''.join(os.environ['TMDB_ACCESS_TOKEN'].split())
  self._movie_cache={};self._cache_lock=threading.Lock();self.imdb_index=PublicImdbIndex(default_path())
  try:
   parsed=urllib.parse.urlsplit(self.url)
   valid=parsed.scheme=='https' and bool(parsed.hostname) and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment and parsed.path in ('','/') and not any(c.isspace() for c in self.url)
  except ValueError:valid=False
  if not valid:raise RequestFailure('SUPABASE_URL must be an HTTPS project URL')
  for name,token in [('SUPABASE_SERVICE_ROLE_KEY',self.key),('TMDB_ACCESS_TOKEN',self.tmdb)]:
   if not token or any(not(c.isascii() and (c.isalnum() or c in '._-')) for c in token):raise RequestFailure(name+': invalid token format; paste only the key value')
  if self.key.startswith('sb_publishable_'):raise RequestFailure('Server key is a public publishable key; use service_role or sb_secret key')
  if self.key.count('.')==2:
   try:role=json.loads(base64.urlsafe_b64decode(self.key.split('.')[1]+'==='))['role']
   except Exception:raise RequestFailure('Server JWT key has invalid format') from None
   if role!='service_role':raise RequestFailure('Server JWT key must have service_role role; anon key is insufficient')

 def request(self,url,headers,method='GET',body=None):
  if url.startswith(self.url+'/rest/v1/'):
   table=url.split('/rest/v1/',1)[1].split('?',1)[0]
   label='Supabase '+(table if table in ('profiles','ratings','collection') else 'database')+' '+method
  elif url.startswith(self.url+'/auth/v1/'):label='Supabase account interests '+method
  else:label='TMDB' if url.startswith('https://api.themoviedb.org/') else 'OMDb' if url.startswith('https://www.omdbapi.com/') else 'Trakt' if url.startswith('https://api.trakt.tv/') else 'Discovery feed'
  req=urllib.request.Request(url,headers=headers,method=method,data=json.dumps(body).encode() if body is not None else None)
  for attempt in range(3):
   try:
    with urllib.request.urlopen(req,timeout=20) as response:
     raw=response.read();return json.loads(raw) if raw else None
   except urllib.error.HTTPError as error:
    if method!='GET' or error.code not in (429,500,502,503,504) or attempt==2:
     hint=' Verify the server key belongs to this Supabase project.' if label.startswith('Supabase') and error.code in (401,403) else ''
     code=''
     try:
      value=json.loads(error.read()).get('code')
      if value in ('42501','42P01','PGRST205','PGRST301','PGRST302','invalid_api_key'):code=' code='+value
     except Exception:pass
     raise RequestFailure(label+': HTTP '+str(error.code)+code+hint) from None
   except ValueError:
    raise RequestFailure(label+': invalid request format; check configuration values') from None
   except (urllib.error.URLError,TimeoutError):
    if method!='GET' or attempt==2:raise RequestFailure(label+': network unavailable or timeout') from None
   time.sleep(2**attempt)

 def db(self,path,method='GET',body=None,prefer=None):
  headers={'apikey':self.key,'Content-Type':'application/json'}
  # New secret keys are API keys, not JWTs. The Supabase gateway sets the server role.
  if not self.key.startswith('sb_secret_'):headers['Authorization']='Bearer '+self.key
  if prefer:headers['Prefer']=prefer
  return self.request(self.url+'/rest/v1/'+path,headers,method,body)
 def load_interests(self,uid):
  uid=validated_uuid(uid,'User ID')
  user=self.request(self.url+'/auth/v1/admin/users/'+uid,{'apikey':self.key,'Authorization':'Bearer '+self.key})
  if not isinstance(user,dict) or user.get('id')!=uid:raise RequestFailure('Interests: account metadata was not confirmed')
  return normalize_interests((user.get('user_metadata') or {}).get('nightshift_interests'))

 def movie(self,path):
  # Per-run, thread-safe single-flight cache. Failed lookups remain retryable; never cache DB writes.
  with self._cache_lock:
   future=self._movie_cache.get(path);owner=future is None
   if owner:future=Future();self._movie_cache[path]=future
  if owner:
   try:future.set_result(self.request('https://api.themoviedb.org/3/'+path,{'Authorization':'Bearer '+self.tmdb}))
   except Exception as error:
    future.set_exception(error)
    with self._cache_lock:self._movie_cache.pop(path,None)
  return copy.deepcopy(future.result())

def load_config():
 config=json.loads((Path(__file__).resolve().parents[1]/'config/recommendations.json').read_text())
 for key in ('base_per_hour','extra_per_source','maximum_per_hour','minimum_votes'):
  if type(config[key]) is not int or config[key]<0:raise ValueError('Invalid recommendation limit')
 if not 1<=config['maximum_per_hour']<=100:raise ValueError('Hourly maximum must be 1..100')
 if type(config.get('history_enrichment_per_run',12)) is not int or not 0<=config.get('history_enrichment_per_run',12)<=300:raise ValueError('Unbounded history enrichment')
 for key in ('discovery_workers','detail_workers'):
  if type(config.get(key,4)) is not int or not 1<=config.get(key,4)<=4:raise ValueError('Worker count must be 1..4')
 if type(config.get('page_window',20)) is not int or not 2<=config.get('page_window',20)<=20:raise ValueError('Page window must be 2..20')
 if type(config.get('discovery_request_limit',24)) is not int or not 8<=config.get('discovery_request_limit',24)<=64:raise ValueError('Discovery request limit must be 8..64')
 for key,default,upper in [('manual_batch_target',30,100),('manual_anchor_limit',36,48),('search_rounds',3,12),('detail_candidate_limit',240,2400),('manual_quality_pool',160,2400)]:
  if type(config.get(key,default)) is not int or not 1<=config.get(key,default)<=upper:raise ValueError('Unbounded '+key)
 ids=[s['id'] for s in config['sources']]
 if len(ids)!=len(set(ids)):raise ValueError('Source IDs must be unique')
 for source in config['sources']:
  if not 1<=source.get('pages',2)<=5 or not 1<=source.get('candidate_limit',40)<=100:raise ValueError('Unbounded source')
 return config

def read_rows(b,path):
 rows=[];offset=0
 while True:
  page=b.db(path+f'&limit=500&offset={offset}')
  rows.extend(page)
  if len(page)<500:return rows
  offset+=500

def schedule_slot(value):
 # Same hourly boundary as GitHub cron 17 * * * *; independent of run delays and Kyiv DST.
 return int((value.timestamp()-17*60)//3600)

def parsed_time(value):
 try:
  stamp=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
  return stamp if stamp.tzinfo else stamp.replace(tzinfo=datetime.timezone.utc)
 except (ValueError,TypeError,AttributeError):return None

def anchor_feedback(ratings):
 # Rate a discovery direction by actual user feedback on its returned films,
 # not by the seed film's own score. Deduplicate IDs; shared attribution gets
 # fractional credit so one result cannot count as many independent outcomes.
 latest={}
 for row in ratings:
  mid=row.get('tmdb_id')
  if type(mid) is not int or mid<=0:continue
  if mid not in latest or str(row.get('updated_at') or '')>=str(latest[mid].get('updated_at') or ''):latest[mid]=row
 counts={}
 for row in latest.values():
  impression=row.get('impression')
  if impression not in ('like','neutral','dislike'):continue
  anchors=(row.get('metadata') or {}).get('recommendationAnchorIds') or []
  if not isinstance(anchors,list):continue
  anchors={mid for mid in anchors if type(mid) is int and mid>0 and mid!=row['tmdb_id']}
  for mid in anchors:
   good,total=counts.get(mid,(0,0));mass=1/len(anchors)
   counts[mid]=(good+mass*{'like':1,'neutral':.5,'dislike':0}[impression],total+mass)
 # Two-observation prior: unseen directions are neutral; repeated misses lower
 # search priority without banning an anchor or adding a candidate score veto.
 return {mid:(good+1)/(total+2) for mid,(good,total) in counts.items()}

def liked_movie_seeds(ratings,limit=6,rotation=0):
 # Six near-identical favorites produce near-identical recommendation lists.
 # Keep explicit positive anchors, but cover their different themes and directors.
 rows={r['tmdb_id']:r for r in ratings if type(r.get('tmdb_id')) is int and r['tmdb_id']>0 and rating_signal(r)>.4 and eligible_for_discovery(r.get('metadata') or {})}
 selected=[];used={};feedback=anchor_feedback(ratings)
 def select(row):
  mid=row['tmdb_id'];selected.append(mid);rows.pop(mid)
  for key in features(row.get('metadata') or {}):used[key]=used.get(key,0)+1
 # Preserve recent positives, but a repeatedly failed direction must not occupy
 # a reserved slot forever while other positive anchors remain untested.
 recent=sorted((r for r in rows.values() if parsed_time(r.get('updated_at'))),key=lambda r:(feedback.get(r['tmdb_id'],.5),r['updated_at'],r['tmdb_id']),reverse=True)
 for row in recent[:min(4,max(1,limit//3),limit)]:select(row)
 def priority(row):
  vector=features(row.get('metadata') or {})
  coverage=sum(share/(1+used.get(key,0)) for key,share in vector.items() if specific_feature(key))
  stamp=parsed_time(row.get('updated_at'))
  rotation_bonus=int.from_bytes(hashlib.sha256(f"{rotation}:{row['tmdb_id']}".encode()).digest()[:4],'big')/2**32*.8 if rotation else 0
  return rating_signal(row)*2+coverage*.25+rotation_bonus+2*(feedback.get(row['tmdb_id'],.5)-.5),stamp.timestamp() if stamp else 0,-row['tmdb_id']
 while rows and len(selected)<min(48,limit):
  select(max(rows.values(),key=priority))
 return selected

def preference_director_names(metadata):
 aliases=metadata.get('directorAliases')
 names=[n for n in aliases if isinstance(n,str) and n.strip()] if isinstance(aliases,list) else []
 return list(dict.fromkeys(names)) or [director(metadata)]

def preferred_director_seeds(ratings,tastes,limit=8,rotation=0):
 # Repeated positives, or one explicit 9+/9+ like without a rejected film
 # by that director. Public credits verify identity in either case.
 names={}
 for row in ratings:
  metadata=row.get('metadata') or {}
  if row.get('impression')=='like' and eligible_for_discovery(metadata):
   for name in preference_director_names(metadata):
    if isinstance(name,str) and name and ',' not in name:names[normalize(name)]=name
 if not tastes.predictive:return []
 keys=[key for key in names if tastes.positive_support.get(('director',key),0)>=2 and tastes.balanced_weights.get(('director',key),0)>0]
 negatives={normalize(name) for r in ratings if r.get('impression')=='dislike' for name in preference_director_names(r.get('metadata') or {})}
 for row in ratings:
  for raw in preference_director_names(row.get('metadata') or {}):
   name=normalize(raw)
   if name in names and name not in negatives and name not in keys and row.get('impression')=='like' and (row.get('metadata') or {}).get('ratingFeedbackStage')!='interest' and (row.get('plot') or 0)>=9 and (row.get('cinematography') or 0)>=9 and tastes.balanced_weights.get(('director',name),0)>0:keys.append(name)
 ordered=sorted(keys,key=lambda key:(-tastes.balanced_weights[('director',key)],key))
 fixed=ordered[:min(4,limit)];extra=ordered[len(fixed):]
 if extra:
  offset=rotation%len(extra);extra=extra[offset:]+extra[:offset]
 return [names[key] for key in (fixed+extra)[:limit]]


def director_anchor_ids(ratings,names):
 result={name:[] for name in names}
 for row in ratings:
  for name in preference_director_names(row.get('metadata') or {}):
   if name in result and row.get('impression')=='like' and type(row.get('tmdb_id')) is int and row['tmdb_id']>0:
    if row['tmdb_id'] not in result[name]:result[name].append(row['tmdb_id'])
 return {name:ids[:2] for name,ids in result.items()}


def history_enrichment_ids(pending,limit):
 if limit<=0:return []
 # Refresh all available preferences and a spread of counterexamples together.
 # A prefix of TMDB IDs would systematically miss the latest failed batches.
 positive=[mid for mid,entries in pending.items() if any(t=='ratings' and r.get('impression')=='like' for t,r in entries)]
 positive.sort(key=lambda mid:not any(eligible_for_discovery(r.get('metadata') or {}) for t,r in pending[mid] if t=='ratings'))
 selected=positive[:max(1,limit//2)]
 def spread(ids,count):
  count=min(count,len(ids))
  return [ids[i*len(ids)//count] for i in range(count)] if count else []
 negative=[mid for mid,entries in pending.items() if mid not in selected and any(t=='ratings' and r.get('impression')=='dislike' and eligible_for_discovery(r.get('metadata') or {}) for t,r in entries)]
 selected+=spread(negative,limit-len(selected))
 remaining=[mid for mid in pending if mid not in selected]
 selected+=spread(remaining,limit-len(selected))
 return selected

def enrich_history(b,uid,ratings,collection,config):
 # Small resumable migration: enrich rated films first, without altering ratings, saved flags or timestamps.
 pending={}
 for table,rows in [('ratings',ratings),('collection',collection)]:
  for row in rows:
   metadata=row.get('metadata')
   if not isinstance(metadata,dict) or not metadata.get('title'):continue
   metrics=metadata.get('remoteMetrics') or {};metrics=metrics if isinstance(metrics,dict) else {}
   pop=metadata.get('popularity');pop=metrics.get('popularity') if pop is None else pop
   story=metadata.get('description') or metadata.get('overview')
   context_complete=(isinstance(story,str) and bool(story.strip()) or metadata.get('synopsisChecked')) and (type(pop) in (int,float) and math.isfinite(pop) and pop>=0 or metadata.get('reachChecked'))
   if metadata.get('featureVersion')==2 and all(key in metadata for key in ('keywords','productionCountries','originalLanguage')) and context_complete and metadata.get('productionChecked'):continue
   mid=row.get('tmdb_id')
   if type(mid) is int and mid>0:pending.setdefault(mid,[]).append((table,row))
 selected=history_enrichment_ids(pending,config.get('history_enrichment_per_run',12))
 def fetch(mid):
  try:
   detail=b.movie(detail_path(mid))
   return detail if isinstance(detail,dict) and detail.get('id')==mid else None
  except Exception:return None
 with ThreadPoolExecutor(max_workers=config.get('detail_workers',4)) as executor:
  details=list(executor.map(fetch,selected))
 writes=[]
 for mid,detail in zip(selected,details):
  if detail is None:continue
  extra=feature_metadata(detail)
  for table,row in pending[mid]:
   metadata=dict(row['metadata'],**extra)
   if not (isinstance(metadata.get('description') or metadata.get('overview'),str) and (metadata.get('description') or metadata.get('overview')).strip()):
    if isinstance(detail.get('overview'),str):metadata['description']=detail['overview']
   metadata['synopsisChecked']=True;metadata['reachChecked']=True
   metrics=metadata.get('remoteMetrics');metrics=dict(metrics) if isinstance(metrics,dict) else {}
   pop=metadata.get('popularity');pop=metrics.get('popularity') if pop is None else pop
   if not (type(pop) in (int,float) and math.isfinite(pop) and pop>=0):
    canonical_pop=detail.get('popularity')
    if type(canonical_pop) in (int,float) and math.isfinite(canonical_pop) and canonical_pop>=0:metrics['popularity']=canonical_pop
   if type(detail.get('vote_count')) is int and detail['vote_count']>=0:metrics['voteCount']=detail['vote_count']
   if metrics:metadata['remoteMetrics']=metrics
   if row['metadata'].get('director') and not metadata['director']:metadata['director']=row['metadata']['director']
   writes.append((table,row,metadata,mid))
 def write(item):
  table,row,metadata,mid=item
  try:
   path=table+'?user_id=eq.'+uid+'&tmdb_id=eq.'+str(mid)
   if table=='ratings' and parsed_time(row.get('updated_at')):
    path+='&updated_at=eq.'+urllib.parse.quote(row['updated_at'],safe='')
   written=b.db(path,'PATCH',{'metadata':metadata},'return=representation')
   if written==[]:return False # A newer opinion or a deleted row wins the race.
   row['metadata']=metadata;return True
  except Exception:return False
 with ThreadPoolExecutor(max_workers=config.get('detail_workers',4)) as executor:
  completed=sum(executor.map(write,writes))
 if selected:print('History metadata refreshed:',completed,'records; other collection fields retained.')
 return completed


def focus_reference_ids(backend,ratings,interests=None):
    # Explicitly named references guide retrieval; never fabricate rating rows.
    result=[]
    for reference in POLICY.get('focus_reference_titles',[]):
        if not director_focus({'director':reference['director']},interests):continue
        matches=[r['tmdb_id'] for r in ratings if isinstance(r.get('metadata'),dict) and r['metadata'].get('original')==reference['title'] and r['metadata'].get('year')==reference['year'] and r.get('impression')=='like']
        if not matches:
            try:
                data=backend.movie('search/movie?'+urllib.parse.urlencode({'query':reference['title'],'primary_release_year':reference['year'],'language':'en-US','include_adult':'false'}))
                matches=[m['id'] for m in data.get('results',[]) if isinstance(m,dict) and type(m.get('id')) is int and m['id']>0 and m.get('original_title')==reference['title'] and str(m.get('release_date',''))[:4]==str(reference['year'])]
            except Exception:matches=[]
        if len(set(matches))==1:result.append(matches[0])
    focused=[r for r in ratings if r.get('impression')=='like' and type(r.get('tmdb_id')) is int and director_focus(r.get('metadata') or {},interests) and eligible_for_discovery(r.get('metadata') or {})]
    focused.sort(key=lambda r:(str(r.get('updated_at') or ''),r['tmdb_id']),reverse=True)
    return list(dict.fromkeys(result+[r['tmdb_id'] for r in focused]))[:12]

def recommend_user(b,user,now,config,manual=False,request_id=None,dry_run=False):
 slot=schedule_slot(now)
 previous=parsed_time(user.get('last_recommendation_at'))
 if not manual and previous and schedule_slot(previous)>=slot:
  print('Private batch skipped: this scheduled hour has already completed.')
  return 0
 uid=user['user_id'];ratings=read_rows(b,'ratings?user_id=eq.'+uid+'&select=*&order=tmdb_id');collection=read_rows(b,'collection?user_id=eq.'+uid+'&select=*&order=tmdb_id')
 if not dry_run:enrich_history(b,uid,ratings,collection,config)
 tastes=profile(ratings)
 tastes.interests=normalize_interests(b.load_interests(uid) if callable(getattr(b,'load_interests',None)) else user.get('interests'))
 tastes.style_model=build_style_model(ratings,tastes.interests)
 # Search quality depends on learned preferences, not on the job's trigger.
 # Manual mode only changes the batch budget and bypasses hourly guards.
 personal_search=tastes.predictive
 print('Personalized ranking:',tastes.model_version,'decisive ratings:',tastes.training_count,'personal score filters: disabled')
 weights={value:weight for (kind,value),weight in tastes.items() if kind=='genre'}
 preferred=sorted((g for g,v in weights.items() if v>0 and g in (27,53,878)),key=lambda g:weights[g],reverse=True)[:3]
 seed_rotation=int(request_id.replace('-','')[-8:],16) if request_id else schedule_slot(now)
 preferred_movies=liked_movie_seeds(ratings,limit=config.get('manual_anchor_limit',36) if personal_search else 6,rotation=seed_rotation)
 preferred_movies=list(dict.fromkeys(focus_reference_ids(b,ratings,tastes.interests)+preferred_movies))[:config.get('manual_anchor_limit',36)]
 preferred_directors=[] # Favorites supply style references, not filmography-only routes.
 search_config=dict(config,_preferred_movie_ids=preferred_movies,_preferred_directors=preferred_directors,_director_anchor_ids=director_anchor_ids(ratings,preferred_directors),_now=now,_page_seed=(int(request_id.replace('-','')[-8:],16) if request_id else len(collection)) if manual else 0,_excluded_ids={int(r['tmdb_id']) for r in ratings+collection}|set(IDS.values()),_preferred_keywords=preferred_keyword_seeds(ratings,tastes))
 search_config['_discovery_pages']={}
 search_config['_discovery_totals']={}
 search_config['_discovery_stats']={}
 search_config['_anchor_coverage']=set()
 search_config['_preferred_keyword_groups']=preferred_keyword_groups(ratings)
 search_config['_preferred_periods']=preferred_periods(tastes)
 search_config['_include_similar']=personal_search
 search_config['_evidence_routes']=personal_search
 search_config['_preferred_companies']=preferred_production_seeds(tastes,'company')
 search_config['_preferred_cast']=preferred_production_seeds(tastes,'cast',limit=4)
 search_config['_genre_priority']=tastes.interests['genrePriority']
 search_config['_preferred_languages']=preferred_audience_languages(ratings)
 style_ids=[]
 for row in ratings:
  m=row.get('metadata') or {}
  if row.get('impression')!='like' or not director_focus(m,tastes.interests):continue
  for name,kid in zip(m.get('keywords',[]),m.get('keywordIds',[])):
   if type(kid) is int and kid>0 and tastes.style_model['weights'].get(style_key(name),0)>0:style_ids.append((tastes.style_model['weights'][style_key(name)],kid))
 search_config['_preferred_keywords']=list(dict.fromkeys([kid for _,kid in sorted(style_ids,reverse=True)]+search_config['_preferred_keywords']))[:12]
 search_config['_anchor_batch_size']=12 if personal_search else 6
 candidates,statuses=discover(b,preferred,search_config)
 print('Discovery:',json.dumps(statuses))
 ranked=rank_candidates(candidates,ratings,collection,config['minimum_votes'],now,preliminary=True,tastes=tastes)
 print('Candidate pool:',len(candidates),'eligible:',len(ranked))
 stamps=[parsed_time(row.get('created_at')) for row in collection if row.get('reason') and (row.get('metadata') or {}).get('recommendationMode')!='manual']
 stamps=[stamp for stamp in stamps if stamp and stamp<=now]
 recent=sum(1 for stamp in stamps if (now-stamp).total_seconds()<3600)
 in_slot=sum(1 for stamp in stamps if schedule_slot(stamp)==slot)
 # A target batch belongs to its scheduled hour; the hard maximum remains a rolling 60-minute cap.
 # Base is not a minimum: even one eligible film is saved within the remaining budget.
 budget=config.get('manual_batch_target',30) if manual else min(max(0,hourly_limit(config,ranked)-in_slot),max(0,config['maximum_per_hour']-recent))
 if manual:print('Manual request: hourly guards bypassed; per-request target:',budget)
 if not budget:
  print('Private batch skipped: scheduled-hour budget or rolling 60-minute maximum reached.')
  return 0
 production_rejections=set();detail_rejections=Counter();rejection_lock=threading.Lock();potential={}
 def hydrate(entry):
  movie=entry[1]
  def reject(reason,fetched=True):
   with rejection_lock:detail_rejections[reason]+=1
   return None,fetched
  try:
   detail=b.movie(detail_path(movie['id']))
   if not isinstance(detail,dict)or detail.get('id')!=movie['id']:return reject('identity_mismatch')
   detail=dict(detail)
   index=getattr(b,'imdb_index',None)
   if isinstance(index,PublicImdbIndex):index.enrich([detail])
   exclusion=production_exclusion(detail,interests=tastes.interests)
   if exclusion:
    production_rejections.add(movie['id']);return reject(exclusion)
   if not eligible_for_discovery(detail,require_target=False):return reject('year_country_or_excluded_genre')
   if not valid_candidate(detail,config['minimum_votes'],now.date(),require_target=False,interests=tastes.interests):return reject('release_poster_or_public_metadata')
   if not detail.get('title')or type(detail.get('runtime'))not in(int,float)or detail['runtime']<=0:return reject('missing_title_or_runtime')
   crew=(detail.get('credits')or {}).get('crew',[])
   director_ids={person['id']for person in crew if isinstance(person,dict)and person.get('job')=='Director'and type(person.get('id'))is int}
   aliases=[name for name,pid in movie.get('_director_alias_ids',{}).items()if type(pid)is int and pid in director_ids]
   shaped=dict(detail,genre_ids=genres(detail),directorAliases=aliases,discovery_sources=movie.get('discovery_sources',[]),_liked_anchor_ids=movie.get('_liked_anchor_ids',[]),_liked_directors=movie.get('_liked_directors',[]),_personal_routes=movie.get('_personal_routes',[]),_matched_theme_groups=movie.get('_matched_theme_groups',[]))
   if not eligible_for_discovery(shaped):
    with rejection_lock:potential[shaped['id']]=shaped
    return reject('outside_horror_or_dystopia')
   return shaped,True
  except Exception as error:return reject(error_summary(error),False)
 # Coarse discover results lack keywords/countries: filter taste only after canonical enrichment.
 # Exhaust the current pool before rotating pages; never fill a batch with rejected movies.
 attempted=set();details={};fetched_any=False;final=[]
 search_unavailable=any(s.get('source')=='tmdb' and s.get('status')=='failed' for s in statuses)
 metadata_failures=0
 detail_limit=config.get('detail_candidate_limit',240)
 quality_pool=min(detail_limit,config.get('manual_quality_pool',160)) if personal_search else 0
 rounds=config.get('search_rounds',3)
 def needs_personal_search():
  return personal_search and sum(match_score(entry[1],tastes)>0 for entry in final[:budget])<budget
 pool={entry[1]['id']:entry[1] for entry in ranked}
 for search_round in range(rounds):
  final=rank_candidates(list(details.values()),ratings,collection,config['minimum_votes'],now,tastes=tastes)

  if search_round:
   followup=dict(search_config,_search_round=search_round,
                 _page_seed=search_config['_page_seed']+search_round,
                 _excluded_ids=search_config['_excluded_ids']|set(pool),
                 sources=[s for s in config['sources'] if s['adapter']=='tmdb_discover'])
   if not any(s.get('enabled') for s in followup['sources']):break
   try:
    extra,statuses=discover(b,preferred,followup)
   except Exception:
    print('Search refill unavailable; retaining verified candidates.')
    search_unavailable=True
    break
   for candidate in extra:pool.setdefault(candidate['id'],candidate)
   search_unavailable=search_unavailable or any(s.get('source')=='tmdb' and s.get('status')=='failed' for s in statuses)
   print('Refill discovery:',json.dumps(statuses))
  pending=rank_candidates(list(pool.values()),ratings,collection,config['minimum_votes'],now,preliminary=True,tastes=tastes)
  pending=[entry for entry in pending if entry[1]['id'] not in attempted]
  while pending and len(attempted)<detail_limit and (len(final)<budget or len(attempted)<quality_pool or needs_personal_search() or (manual or personal_search) and pending[0][0]>=min(entry[0] for entry in final[:budget])):
   chunk=pending[:min(60,max(20,(budget-len(final))*2),detail_limit-len(attempted))]
   pending=pending[len(chunk):]
   attempted.update(entry[1]['id'] for entry in chunk)
   with ThreadPoolExecutor(max_workers=config.get('detail_workers',4)) as executor:hydrated=list(executor.map(hydrate,chunk))
   metadata_failures+=sum(not fetched for _,fetched in hydrated)
   fetched_any=fetched_any or any(fetched for _,fetched in hydrated)
   new_details=[detail for detail,_ in hydrated if detail]
   details.update({m['id']:m for m in new_details})
   final=diverse_candidates(rank_candidates(list(details.values()),ratings,collection,config['minimum_votes'],now,tastes=tastes),strict_audience=True)
  print('Search pass:',search_round+1,'unique pool:',len(pool),'discovery requests:',search_config['_discovery_stats'].get('requests',0),'details attempted:',len(attempted),'metadata failures:',metadata_failures,'canonical eligible:',len(details),'personalized eligible:',len(final),'target:',budget)
  good_fit=sum(match_score(entry[1],tastes)>0 for entry in final[:budget])
  print('Search fit:',good_fit,'positive personal scores in top',min(budget,len(final)))
  # Weak matches are a reason to search further, not to discard valid films.
  if len(final)>=budget and len(attempted)>=quality_pool and (not personal_search or good_fit>=budget) or len(attempted)>=detail_limit:break
 # IMDb has a separate, verified audience count; a small TMDB audience is
 # not sufficient evidence of obscurity. No guessed IDs, no second budget gate.
 ordered=[];seen_imdb=set()
 by_votes=sorted(final,key=lambda e:(-audience_votes(e[1]),-e[0],e[1]['id']))
 alternative=sorted(potential.values(),key=lambda m:(-audience_votes(m),-selection_priority_score(m,match_score(m,tastes),tastes.style_model),m['id']))
 for i in range(max(len(final),len(alternative))):
  lanes=[final[i][1],by_votes[i][1]]if i<len(final)else[]
  if i<len(alternative):lanes.append(alternative[i])
  for m in lanes:
   if m['id']not in seen_imdb:ordered.append(m);seen_imdb.add(m['id'])
 dataset_index=getattr(b,'imdb_index',None)
 dataset_ready=isinstance(dataset_index,PublicImdbIndex)and dataset_index.metadata()is not None
 imdb_stats=enrich_audience(b,ordered,(40 if dataset_ready else 320)if manual else 12,eligible=lambda m:eligible_for_discovery(m)and not production_exclusion(m),good_target=min(15,budget))
 rescued=0
 for mid,m in potential.items():
  if eligible_for_discovery(m)and not production_exclusion(m):details[mid]=m;rescued+=1
 if rescued:detail_rejections['outside_horror_or_dystopia']-=rescued
 for mid,m in list(details.items()):
  rejection=production_exclusion(m)
  if rejection:detail_rejections[rejection]+=1;production_rejections.add(mid);del details[mid]
 final=rank_candidates(list(details.values()),ratings,collection,config['minimum_votes'],now,tastes=tastes)
 b.search_report={'candidateCount':len(pool),'verifiedCount':len(details),'accepted':min(budget,len(final)),
  'positivePersonal':sum(match_score(e[1],tastes)>0 for e in final[:budget]),
  'styleMatches':sum(style_affinity(e[1],tastes.style_model)>0 for e in final[:budget]),
  'detailsAttempted':len(attempted),'detailRejections':dict(detail_rejections),
  'medianPopularity':median([e[1].get('popularity',0)for e in final[:budget]])if final else 0,
  'medianVoteCount':median([e[1].get('vote_count',0)for e in final[:budget]])if final else 0,
  'medianPublicRating':median([e[1].get('vote_average',0)for e in final[:budget]])if final else 0}
 evidence=[validated_imdb_metrics(e[1])for e in final[:budget]]
 evidence=[m for m in evidence if m]
 b.search_report.update(imdb_stats)
 index=getattr(b,'imdb_index',None)
 b.search_report.update(imdbDatasetReady=isinstance(index,PublicImdbIndex)and index.metadata()is not None,imdbDatasetResolved=sum((m.get('remoteMetrics')or{}).get('imdbSource')=='IMDb datasets'for m in details.values()),imdbDatasetIdentities=search_config['_discovery_stats'].get('imdbDatasetIdentities',0))
 critics=[validated_critics_score(e[1])for e in final[:budget]];critics=[v for v in critics if v is not None]
 b.search_report.update(imdbGenreRescued=rescued,selectedCritics70=sum(v>=70 for v in critics),selectedEstablishedGood=sum(m['rating']>=6.5 and m['votes']>=10000 for m in evidence),medianMetascore=median(critics)if critics else None,
  selectedImdb6_5=sum(m['rating']>=6.5 for m in evidence),poolImdb6_5=sum(bool(validated_imdb_metrics(m))and validated_imdb_metrics(m)['rating']>=6.5 for m in details.values()))
 b.search_report.update(selectedImdb10000=sum(m['votes']>=10000 for m in evidence),selectedImdbVerified=len(evidence),
  medianImdbVoteCount=median([m['votes']for m in evidence])if evidence else None,
  medianImdbRating=median([m['rating']for m in evidence])if evidence else None,
  knownImdbPool10000=sum(bool(validated_imdb_metrics(m))and validated_imdb_metrics(m)['votes']>=10000 for m in details.values()))
 b.search_report.update(selection55_diagnostics(final,budget,tastes,ratings,collection))
 if attempted and not fetched_any:raise RequestFailure('Candidate metadata unavailable; retry next run')
 if not final and (search_unavailable or metadata_failures):raise RequestFailure('Search incomplete: provider requests failed; retry the manual request')
 if len(final)<budget:print('Batch below target:',len(final),'of',budget,'after bounded search; excluded films are not used as filler.')
 audience_summary=audience_diagnostics(final,budget,tastes.predictive)
 audience_summary['recommendationProductionExcludedCount']=len(production_rejections)
 print('Audience and production selection evidence:',json.dumps(audience_summary))
 added=0
 for _,detail,reason in final:
  if added>=budget:break
  movie=detail
  fid=10000000+detail['id'];genre_ids=genres(detail)
  metadata={'id':fid,'tmdbId':detail['id'],'title':detail['title'],'original':detail.get('original_title',detail['title']),'year':int(detail['release_date'][:4]),'genre':GENRES.get(genre_ids[0],'Кино') if genre_ids else 'Кино','genreIds':genre_ids,'minutes':detail['runtime'],'rating':detail.get('vote_average',0),'ratingSource':'TMDB','director':director(detail),'moods':classify(detail),'symbol':'✦','colors':['#4c6478','#263443'],'caption':reason,'description':detail.get('overview',''),'synopsisChecked':True,'reachChecked':True,'recommendationReason':reason,'remoteMetrics':{'poster':'https://image.tmdb.org/t/p/w500'+detail['poster_path'],'popularity':detail.get('popularity'),'voteCount':detail.get('vote_count'),'tmdbUpdatedAt':now.isoformat()}}
  metadata['discoverySources']=movie.get('discovery_sources',[])
  if detail.get('remoteMetrics',{}).get('imdbVerified')is True:metadata['remoteMetrics'].update(detail['remoteMetrics'])
  if 'horror'in classify(detail):metadata['genre']='Ужасы'
  metadata.update(feature_metadata(detail))
  metadata.update(recommendationSearchVersion='audience-search55',recommendationAnchorIds=detail.get('_liked_anchor_ids',[]),recommendationDirectorSeeds=detail.get('_liked_directors',[]),recommendationModel=tastes.model_version,recommendationScore=round(match_score(detail,tastes),6),recommendationConfidence=round(rejection_score(detail,tastes),6),recommendationTrainingCount=tastes.training_count,recommendationPositiveCount=tastes.positive_count,recommendationNegativeCount=tastes.negative_count)
  metadata['recommendationAudienceScore']=round(audience_production_score(detail,style_model=tastes.style_model),6)
  metadata['recommendationAudiencePriority']=round(audience_production_score(detail,style_model=tastes.style_model),6)
  metadata.update(audience_summary)
  metadata['recommendationOrderingScore']=round(selection_priority_score(detail,match_score(detail,tastes),tastes.style_model),6)
  metadata['recommendationProductionPolicy']='content-policy50'
  metadata['recommendationStyleAffinity']=style_affinity(detail,tastes.style_model)
  metadata['recommendationStyleReferenceCount']=tastes.style_model['reference_count']
  metadata['recommendationGenrePriority']=tastes.interests['genrePriority']
  metadata['recommendationPublicQualityTier']=public_quality_tier(detail)
  metadata['recommendationOrderingSecondaryScore']=round(match_score(detail,tastes)+public_quality_score(detail,tastes.predictive),6)
  metadata['recommendationDiscoveryRequests']=search_config['_discovery_stats'].get('requests',0)
  metadata['recommendationSynopsisScore']=round(.25*synopsis_score(detail,tastes.synopsis_model),6)
  metadata['recommendationSynopsisDocuments']=tastes.synopsis_model.get('document_count',0)
  metadata['recommendationProductionScore']=round(.5*production_score(detail,tastes.production_model),6)
  metadata['recommendationProductionPositiveCount']=tastes.production_model.get('positive_count',0)
  metadata['recommendationProductionNegativeCount']=tastes.production_model.get('negative_count',0)
  metadata['recommendationPersonalRoutes']=detail.get('_personal_routes',[])
  metadata['recommendationThemeGroups']=detail.get('_matched_theme_groups',[])
  metadata['recommendationAnchorCount']=len(preferred_movies)
  metadata['recommendationAnchorCoverage']=len(search_config['_anchor_coverage'])
  metadata['recommendationCandidateCount']=len(pool)
  metadata['recommendationDetailsAttempted']=len(attempted)
  metadata['recommendationQualityPoolTarget']=quality_pool
  metadata['recommendationBatchTarget']=budget
  metadata['recommendationMode']='manual' if manual else 'scheduled'
  metadata['recommendationSelectionVersion']=SELECTION_VERSION
  metadata['recommendationVerifiedPoolSize']=len(details)
  metadata['recommendationSearchPasses']=search_round+1
  metadata['recommendationFit']='positive' if match_score(detail,tastes)>0 else 'weak'
  if request_id:metadata['recommendationRequestId']=request_id
  inserted=[{}] if dry_run else b.db('collection?on_conflict=user_id,tmdb_id','POST',{'user_id':uid,'tmdb_id':detail['id'],'metadata':metadata,'reason':reason},'resolution=ignore-duplicates,return=representation')
  if inserted:added+=1
 if not manual and not dry_run:b.db('profiles?user_id=eq.'+uid,'PATCH',{'last_recommendation_at':now.isoformat()})
 print('Read-only candidate probe; would add:' if dry_run else 'Private recommendation batch complete; added:',added)
 return added
def validated_uuid(value,label):
 try:return str(uuid.UUID(value))
 except (ValueError,TypeError,AttributeError):raise RequestFailure(label+': invalid UUID') from None

def finish_manual_job(b,request_id,user_id,status,added=0):
 b.db('recommendation_jobs?id=eq.'+request_id+'&user_id=eq.'+user_id+'&status=in.(queued,running)', 'PATCH',
      {'status':status,'added_count':added,'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'error_code':'workflow_failed' if status=='failed' else None})

def run():
 needed=['SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','TMDB_ACCESS_TOKEN']
 missing=[k for k in needed if not os.environ.get(k)]
 if missing:
  print('Missing configuration names:',', '.join(missing));raise RuntimeError('Configuration incomplete')
 print('Loading recommendation configuration and connecting to Supabase profiles')
 config=load_config();b=Backend();now=datetime.datetime.now(datetime.timezone.utc)
 manual=os.environ.get('MANUAL_RECOMMENDATIONS','false').lower()=='true'
 target=os.environ.get('RECOMMENDATION_USER_ID','').strip();request_id=os.environ.get('RECOMMENDATION_REQUEST_ID','').strip()
 if target:target=validated_uuid(target,'User ID')
 if request_id:
  request_id=validated_uuid(request_id,'Request ID')
  if not manual:raise RequestFailure('A queued request requires manual mode')
  jobs=b.db('recommendation_jobs?id=eq.'+request_id+'&select=id,user_id,status')
  if not jobs or jobs[0]['status']!='queued':
   print('Manual request is already handled or does not exist.');return
  owner=validated_uuid(jobs[0]['user_id'],'Job owner')
  if target and target!=owner:raise RequestFailure('Request does not match the specified user')
  target=owner
  run_id=os.environ.get('GITHUB_RUN_ID','')
  run_url='https://github.com/arturmal2805-netizen/Movies-/actions/runs/'+run_id if run_id.isdigit() else None
  claimed=b.db('recommendation_jobs?id=eq.'+request_id+'&user_id=eq.'+target+'&status=eq.queued','PATCH',
               {'status':'running','started_at':now.isoformat(),'run_url':run_url},'return=representation')
  if not claimed:
   print('Manual request is already handled or does not match this user.');return
 users=[];offset=0
 try:
  while True:
   path=f'profiles?select=user_id,last_recommendation_at&order=user_id&limit=500&offset={offset}'
   if target:path+='&user_id=eq.'+target
   page=b.db(path);users.extend(page)
   if len(page)<500:break
   offset+=500
  if target and not users:raise RequestFailure('The requested user profile does not exist')
  failures=0;added=0
  for user in users:
   try:added+=recommend_user(b,user,now,config,manual=manual,request_id=request_id or None)
   except Exception as error:
    failures+=1;print('Private batch failed:',error_summary(error),'; existing collection retained. Retry on next run.')
  print('Profiles processed:',len(users),'failed:',failures)
  if not failures and os.environ.get('GITHUB_ACTIONS')=='true':print('::notice title=Recommendation batch55::'+json.dumps({'added':added,'manual':manual,'profiles':len(users)},separators=(',',':')))
  if failures:raise RuntimeError('Some private batches failed')
  if request_id:finish_manual_job(b,request_id,target,'completed',added)
 except Exception:
  if request_id:
   try:finish_manual_job(b,request_id,target,'failed')
   except Exception:print('Could not update manual job status.')
  raise
if __name__=='__main__':
 try:run()
 except Exception as error:
  print('Recommendation update failed:',error_summary(error),'; previous private collection retained.');raise SystemExit(1)
