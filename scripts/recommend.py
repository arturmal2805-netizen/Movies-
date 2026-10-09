"""Private recommendations stay in Supabase, never in the public Pages snapshot."""
import os,json,datetime,urllib.request,urllib.parse,math,time,base64
from pathlib import Path
from recommendation_sources import discover,hourly_limit
from import_catalog import IDS
GENRES={28:'Боевик',12:'Приключения',16:'Анимация',35:'Комедия',80:'Криминал',99:'Документальный',18:'Драма',10751:'Семейный',14:'Фэнтези',36:'История',27:'Ужасы',10402:'Музыка',9648:'Детектив',10749:'Мелодрама',878:'Фантастика',10770:'Телефильм',53:'Триллер',10752:'Военный',37:'Вестерн'}

def taste(ratings):
 weights={}
 for row in ratings:
  sign={'like':1,'neutral':0,'dislike':-1,'watched':0}.get(row.get('impression'),0)
  values=[row.get(k) for k in ('plot','cinematography') if isinstance(row.get(k),(int,float))]
  if values:sign+=sum(values)/len(values)/5.5-1
  for genre in row.get('metadata',{}).get('genreIds',[]):weights[genre]=weights.get(genre,0)+sign
 return weights

def rank_candidates(candidates,ratings,collection,minimum_votes=100):
 excluded={int(r['tmdb_id']) for r in ratings+collection}|set(IDS.values())
 weights=taste(ratings)
 ranked=[]
 seen=set()
 for movie in candidates:
  if movie.get('id') in seen:continue
  seen.add(movie.get('id'))
  if movie.get('id') in excluded or movie.get('adult') or not movie.get('poster_path'):continue
  if not movie.get('release_date') or movie['release_date']>datetime.date.today().isoformat():continue
  if float(movie.get('vote_count',0))<minimum_votes:continue
  genres=movie.get('genre_ids',[])
  match=sum(weights.get(g,0) for g in genres)
  # Taste dominates; quality and popularity only break similar matches.
  value=match*10+float(movie.get('vote_average',0))*.3+math.log1p(max(0,float(movie.get('popularity',0))))*.1
  favorite=sorted((g for g in genres if weights.get(g,0)>0),key=lambda g:weights[g],reverse=True)
  reason='Совпадает с вашими оценками: '+', '.join(GENRES.get(g,'Жанр') for g in favorite[:2])+'.' if favorite else 'Для знакомства с новым жанром; учтены оценки и популярность TMDB.'
  if not ratings:reason='Стартовая рекомендация по оценкам TMDB. После ваших оценок подбор станет персональным.'
  ranked.append((value,movie,reason))
 return sorted(ranked,key=lambda entry:(-entry[0],entry[1]['id']))

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
 def movie(self,path):return self.request('https://api.themoviedb.org/3/'+path,{'Authorization':'Bearer '+self.tmdb})

def load_config():
 config=json.loads((Path(__file__).resolve().parents[1]/'config/recommendations.json').read_text())
 for key in ('base_per_hour','extra_per_source','maximum_per_hour','minimum_votes'):
  if type(config[key]) is not int or config[key]<0:raise ValueError('Invalid recommendation limit')
 if not 1<=config['maximum_per_hour']<=100:raise ValueError('Hourly maximum must be 1..100')
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

def recommend_user(b,user,now,config):
 slot=schedule_slot(now)
 previous=parsed_time(user.get('last_recommendation_at'))
 if previous and schedule_slot(previous)>=slot:
  print('Private batch skipped: this scheduled hour has already completed.')
  return 0
 uid=user['user_id'];ratings=read_rows(b,'ratings?user_id=eq.'+uid+'&select=*&order=tmdb_id');collection=read_rows(b,'collection?user_id=eq.'+uid+'&select=*&order=tmdb_id')
 weights=taste(ratings);preferred=sorted((g for g,v in weights.items() if v>0),key=lambda g:weights[g],reverse=True)[:3]
 candidates,statuses=discover(b,preferred,config)
 print('Discovery:',json.dumps(statuses))
 ranked=rank_candidates(candidates,ratings,collection,config['minimum_votes'])
 stamps=[parsed_time(row.get('created_at')) for row in collection if row.get('reason')]
 stamps=[stamp for stamp in stamps if stamp and stamp<=now]
 recent=sum(1 for stamp in stamps if (now-stamp).total_seconds()<3600)
 in_slot=sum(1 for stamp in stamps if schedule_slot(stamp)==slot)
 # A target batch belongs to its scheduled hour; the hard maximum remains a rolling 60-minute cap.
 # Base is not a minimum: even one eligible film is saved within the remaining budget.
 budget=min(max(0,hourly_limit(config,ranked)-in_slot),max(0,config['maximum_per_hour']-recent))
 if not budget:
  print('Private batch skipped: scheduled-hour budget or rolling 60-minute maximum reached.')
  return 0
 added=0
 for _,movie,reason in ranked:
  if added>=budget:break
  try:detail=b.movie(f"movie/{movie['id']}?language=ru-RU")
  except Exception:continue
  if detail.get('id')!=movie['id']:continue
  if not detail.get('runtime') or not detail.get('poster_path') or detail.get('adult') or not detail.get('release_date') or detail['release_date']>now.date().isoformat():continue
  fid=10000000+detail['id'];genre_ids=[g['id'] for g in detail.get('genres',[])]
  metadata={'id':fid,'tmdbId':detail['id'],'title':detail['title'],'original':detail.get('original_title',detail['title']),'year':int(detail['release_date'][:4]),'genre':GENRES.get(genre_ids[0],'Кино') if genre_ids else 'Кино','genreIds':genre_ids,'minutes':detail['runtime'],'rating':detail.get('vote_average',0),'ratingSource':'TMDB','director':'','moods':['wonder'],'symbol':'✦','colors':['#4c6478','#263443'],'caption':reason,'description':detail.get('overview',''),'recommendationReason':reason,'remoteMetrics':{'poster':'https://image.tmdb.org/t/p/w500'+detail['poster_path'],'popularity':detail.get('popularity',0),'tmdbUpdatedAt':now.isoformat()}}
  metadata['discoverySources']=movie.get('discovery_sources',[])
  if os.environ.get('OMDB_API_KEY') and detail.get('imdb_id'):
   try:
    result=b.request('https://www.omdbapi.com/?'+urllib.parse.urlencode({'apikey':os.environ['OMDB_API_KEY'],'i':detail['imdb_id']}),{})
    rating=float(result['imdbRating'])
    if result.get('imdbID')==detail['imdb_id'] and 0<=rating<=10:metadata['remoteMetrics'].update(imdb=rating,imdbUpdatedAt=now.isoformat())
   except Exception:pass
  inserted=b.db('collection?on_conflict=user_id,tmdb_id','POST',{'user_id':uid,'tmdb_id':detail['id'],'metadata':metadata,'reason':reason},'resolution=ignore-duplicates,return=representation')
  if inserted:added+=1
 b.db('profiles?user_id=eq.'+uid,'PATCH',{'last_recommendation_at':now.isoformat()})
 print('Private recommendation batch complete; added:',added)
 return added
def run():
 needed=['SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','TMDB_ACCESS_TOKEN']
 missing=[k for k in needed if not os.environ.get(k)]
 if missing:
  print('Missing configuration names:',', '.join(missing));raise RuntimeError('Configuration incomplete')
 print('Loading recommendation configuration and connecting to Supabase profiles')
 config=load_config();b=Backend();now=datetime.datetime.now(datetime.timezone.utc)
 users=[];offset=0
 while True:
  page=b.db(f'profiles?select=user_id,last_recommendation_at&order=user_id&limit=500&offset={offset}')
  users.extend(page)
  if len(page)<500:break
  offset+=500
 failures=0
 for user in users:
  try:recommend_user(b,user,now,config)
  except Exception as error:
   failures+=1;print('Private batch failed:',error_summary(error),'; existing collection retained. Retry on next run.')
 print('Profiles processed:',len(users),'failed:',failures)
 if failures:raise RuntimeError('Some private batches failed')
if __name__=='__main__':
 try:run()
 except Exception as error:
  print('Recommendation update failed:',error_summary(error),'; previous private collection retained.');raise SystemExit(1)
