"""Private recommendations stay in Supabase, never in the public Pages snapshot."""
import os,json,datetime,urllib.request,urllib.parse,math,time,base64,threading,copy,uuid
from concurrent.futures import Future,ThreadPoolExecutor
from pathlib import Path
from recommendation_sources import discover,hourly_limit,detail_path
from movie_features import profile,match_score,genres,keywords,director,classify,normalize,feature_metadata
from import_catalog import IDS
GENRES={28:'Боевик',12:'Приключения',16:'Анимация',35:'Комедия',80:'Криминал',99:'Документальный',18:'Драма',10751:'Семейный',14:'Фэнтези',36:'История',27:'Ужасы',10402:'Музыка',9648:'Детектив',10749:'Мелодрама',878:'Фантастика',10770:'Телефильм',53:'Триллер',10752:'Военный',37:'Вестерн'}

def taste(ratings):return {value:weight for (kind,value),weight in profile(ratings).items() if kind=='genre'}

def valid_candidate(movie,minimum_votes,today):
 if not isinstance(movie,dict) or type(movie.get('id')) is not int or movie['id']<=0:return False
 if movie.get('adult') or not movie.get('poster_path'):return False
 try:
  released=datetime.date.fromisoformat(movie.get('release_date',''))
  count=float(movie.get('vote_count',0));rating=float(movie.get('vote_average',0));popularity=float(movie.get('popularity',0))
  return released<=today and count>=minimum_votes and 0<=rating<=10 and all(math.isfinite(v) for v in (count,rating,popularity))
 except (ValueError,TypeError):return False

def rank_candidates(candidates,ratings,collection,minimum_votes=100,now=None):
 excluded={int(r['tmdb_id']) for r in ratings+collection}|set(IDS.values())
 tastes=profile(ratings);ranked=[];seen=set();today=(now.date() if now else datetime.datetime.now(datetime.timezone.utc).date())
 for movie in candidates:
  if not valid_candidate(movie,minimum_votes,today) or movie['id'] in seen or movie['id'] in excluded:continue
  seen.add(movie['id']);count=float(movie['vote_count'])
  # Shrink low-vote perfect scores; taste is bounded so common genres cannot drown out specific themes.
  quality=(float(movie['vote_average'])*count+6.5*500)/(count+500)
  value=match_score(movie,tastes)*5+quality*.4+min(8,math.log1p(max(0,float(movie.get('popularity',0)))))*.1
  favorite=sorted((g for g in genres(movie) if tastes.get(('genre',g),0)>0),key=lambda g:tastes[('genre',g)],reverse=True)
  themes=sorted((normalize(k if isinstance(k,str) else k.get('name')) for k in keywords(movie) if tastes.get(('keyword',normalize(k if isinstance(k,str) else k.get('name'))),0)>0),key=lambda name:tastes[('keyword',name)],reverse=True)
  reason='Совпадает с вашими оценками: '+', '.join(GENRES.get(g,'Жанр') for g in favorite[:2])+'.' if favorite else 'Для знакомства с новым жанром; учтены оценки и популярность TMDB.'
  if themes:reason+=' Близкие темы: '+', '.join(themes[:2])+'.'
  if not ratings:reason='Стартовая рекомендация по оценкам TMDB. После ваших оценок подбор станет персональным.'
  ranked.append((value,movie,reason))
 return sorted(ranked,key=lambda entry:(-entry[0],entry[1]['id']))

def diverse_candidates(ranked):
 # Gentle batch diversity: do not fill the whole hour with the same main genre.
 remaining=list(ranked);used={};result=[]
 while remaining and len(result)<100:
  def priority(entry):
   ids=genres(entry[1]);penalty=sum(used.get(g,0) for g in ids)/max(1,len(ids))*.12
   return entry[0]-penalty,-entry[1]['id']
  index=max(range(len(remaining)),key=lambda i:priority(remaining[i]));entry=remaining.pop(index);result.append(entry)
  for genre in genres(entry[1]):used[genre]=used.get(genre,0)+1
 return result+remaining


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
  self._movie_cache={};self._cache_lock=threading.Lock()
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
 if type(config.get('history_enrichment_per_run',12)) is not int or not 0<=config.get('history_enrichment_per_run',12)<=12:raise ValueError('Unbounded history enrichment')
 for key in ('discovery_workers','detail_workers'):
  if type(config.get(key,4)) is not int or not 1<=config.get(key,4)<=4:raise ValueError('Worker count must be 1..4')
 if type(config.get('page_window',20)) is not int or not 2<=config.get('page_window',20)<=20:raise ValueError('Page window must be 2..20')
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

def enrich_history(b,uid,ratings,collection,config):
 # Small resumable migration: enrich rated films first, without altering ratings, saved flags or timestamps.
 pending={}
 for table,rows in [('ratings',ratings),('collection',collection)]:
  for row in rows:
   metadata=row.get('metadata')
   if not isinstance(metadata,dict) or not metadata.get('title') or metadata.get('featureVersion')==2:continue
   mid=row.get('tmdb_id')
   if type(mid) is int and mid>0:pending.setdefault(mid,[]).append((table,row))
 selected=list(pending)[:config.get('history_enrichment_per_run',12)]
 def fetch(mid):
  try:
   detail=b.movie(detail_path(mid))
   return detail if isinstance(detail,dict) and detail.get('id')==mid else None
  except Exception:return None
 completed=0
 with ThreadPoolExecutor(max_workers=config.get('detail_workers',4)) as executor:
  details=list(executor.map(fetch,selected))
 for mid,detail in zip(selected,details):
  if detail is None:continue
  extra=feature_metadata(detail)
  for table,row in pending[mid]:
   metadata=dict(row['metadata'],**extra)
   if row['metadata'].get('director') and not metadata['director']:metadata['director']=row['metadata']['director']
   try:
    b.db(table+'?user_id=eq.'+uid+'&tmdb_id=eq.'+str(mid),'PATCH',{'metadata':metadata})
    row['metadata']=metadata;completed+=1
   except Exception:continue
 if selected:print('History metadata refreshed:',completed,'records; other collection fields retained.')


def recommend_user(b,user,now,config,manual=False,request_id=None):
 slot=schedule_slot(now)
 previous=parsed_time(user.get('last_recommendation_at'))
 if not manual and previous and schedule_slot(previous)>=slot:
  print('Private batch skipped: this scheduled hour has already completed.')
  return 0
 uid=user['user_id'];ratings=read_rows(b,'ratings?user_id=eq.'+uid+'&select=*&order=tmdb_id');collection=read_rows(b,'collection?user_id=eq.'+uid+'&select=*&order=tmdb_id')
 enrich_history(b,uid,ratings,collection,config)
 weights=taste(ratings);preferred=sorted((g for g,v in weights.items() if v>0),key=lambda g:weights[g],reverse=True)[:3]
 tastes=profile(ratings);keyword_ids={}
 for row in ratings:
  metadata=row.get('metadata') or {}
  for name,kid in zip(metadata.get('keywords') or [],metadata.get('keywordIds') or []):
   weight=tastes.get(('keyword',normalize(name)),0)
   if type(kid) is int and kid>0 and weight>0:keyword_ids[kid]=weight
 search_config=dict(config,_now=now,_excluded_ids={int(r['tmdb_id']) for r in ratings+collection}|set(IDS.values()),_preferred_keywords=sorted(keyword_ids,key=keyword_ids.get,reverse=True)[:2])
 candidates,statuses=discover(b,preferred,search_config)
 print('Discovery:',json.dumps(statuses))
 ranked=rank_candidates(candidates,ratings,collection,config['minimum_votes'],now)
 print('Candidate pool:',len(candidates),'eligible:',len(ranked))
 stamps=[parsed_time(row.get('created_at')) for row in collection if row.get('reason') and (row.get('metadata') or {}).get('recommendationMode')!='manual']
 stamps=[stamp for stamp in stamps if stamp and stamp<=now]
 recent=sum(1 for stamp in stamps if (now-stamp).total_seconds()<3600)
 in_slot=sum(1 for stamp in stamps if schedule_slot(stamp)==slot)
 # A target batch belongs to its scheduled hour; the hard maximum remains a rolling 60-minute cap.
 # Base is not a minimum: even one eligible film is saved within the remaining budget.
 budget=hourly_limit(config,ranked) if manual else min(max(0,hourly_limit(config,ranked)-in_slot),max(0,config['maximum_per_hour']-recent))
 if manual:print('Manual request: hourly guards bypassed; per-request target:',budget)
 if not budget:
  print('Private batch skipped: scheduled-hour budget or rolling 60-minute maximum reached.')
  return 0
 def hydrate(entry):
  movie=entry[1]
  try:
   detail=b.movie(detail_path(movie['id']))
   if not valid_candidate(detail,config['minimum_votes'],now.date()) or detail['id']!=movie['id'] or not detail.get('title') or type(detail.get('runtime')) not in (int,float) or detail['runtime']<=0:return None
   return dict(detail,genre_ids=genres(detail),discovery_sources=movie.get('discovery_sources',[]))
  except Exception:return None
 # Enrich a shortlist in parallel, then rerank with themes, subgenres and directors.
 # A bounded shortlist avoids spending API quotas on every discovered film.
 shortlist=ranked[:min(180,max(budget*3,budget+8))]
 with ThreadPoolExecutor(max_workers=config.get('detail_workers',4)) as executor:details=[d for d in executor.map(hydrate,shortlist) if d]
 if shortlist and not details:raise RequestFailure('Candidate metadata unavailable; retry next run')
 final=diverse_candidates(rank_candidates(details,ratings,collection,config['minimum_votes'],now))
 print('Enriched candidates:',len(details),'target:',budget)
 added=0
 for _,detail,reason in final:
  if added>=budget:break
  movie=detail
  fid=10000000+detail['id'];genre_ids=genres(detail)
  metadata={'id':fid,'tmdbId':detail['id'],'title':detail['title'],'original':detail.get('original_title',detail['title']),'year':int(detail['release_date'][:4]),'genre':GENRES.get(genre_ids[0],'Кино') if genre_ids else 'Кино','genreIds':genre_ids,'minutes':detail['runtime'],'rating':detail.get('vote_average',0),'ratingSource':'TMDB','director':director(detail),'moods':classify(detail),'symbol':'✦','colors':['#4c6478','#263443'],'caption':reason,'description':detail.get('overview',''),'recommendationReason':reason,'remoteMetrics':{'poster':'https://image.tmdb.org/t/p/w500'+detail['poster_path'],'popularity':detail.get('popularity',0),'tmdbUpdatedAt':now.isoformat()}}
  metadata['discoverySources']=movie.get('discovery_sources',[])
  metadata.update(feature_metadata(detail))
  metadata['recommendationMode']='manual' if manual else 'scheduled'
  if request_id:metadata['recommendationRequestId']=request_id
  if os.environ.get('OMDB_API_KEY') and detail.get('imdb_id'):
   try:
    result=b.request('https://www.omdbapi.com/?'+urllib.parse.urlencode({'apikey':os.environ['OMDB_API_KEY'],'i':detail['imdb_id']}),{})
    rating=float(result['imdbRating'])
    if result.get('imdbID')==detail['imdb_id'] and 0<=rating<=10:metadata['remoteMetrics'].update(imdb=rating,imdbUpdatedAt=now.isoformat())
   except Exception:pass
  inserted=b.db('collection?on_conflict=user_id,tmdb_id','POST',{'user_id':uid,'tmdb_id':detail['id'],'metadata':metadata,'reason':reason},'resolution=ignore-duplicates,return=representation')
  if inserted:added+=1
 if not manual:b.db('profiles?user_id=eq.'+uid,'PATCH',{'last_recommendation_at':now.isoformat()})
 print('Private recommendation batch complete; added:',added)
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
