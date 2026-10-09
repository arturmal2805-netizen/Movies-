"""Private recommendations stay in Supabase, never in the public Pages snapshot."""
import os,json,datetime,urllib.request,urllib.parse,math
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

def rank_candidates(candidates,ratings,collection):
 excluded={int(r['tmdb_id']) for r in ratings+collection}|set(IDS.values())
 weights=taste(ratings)
 ranked=[]
 for movie in candidates:
  if movie.get('id') in excluded or movie.get('adult') or not movie.get('poster_path'):continue
  if not movie.get('release_date') or movie['release_date']>datetime.date.today().isoformat():continue
  genres=movie.get('genre_ids',[])
  match=sum(weights.get(g,0) for g in genres)
  # Taste dominates; quality and popularity only break similar matches.
  value=match*10+float(movie.get('vote_average',0))*.3+math.log1p(max(0,float(movie.get('popularity',0))))*.1
  favorite=sorted((g for g in genres if weights.get(g,0)>0),key=lambda g:weights[g],reverse=True)
  reason='Совпадает с вашими оценками: '+', '.join(GENRES.get(g,'Жанр') for g in favorite[:2])+'.' if favorite else 'Для знакомства с новым жанром; учтены оценки и популярность TMDB.'
  if not ratings:reason='Стартовая рекомендация по оценкам TMDB. После ваших оценок подбор станет персональным.'
  ranked.append((value,movie,reason))
 return sorted(ranked,key=lambda entry:(-entry[0],entry[1]['id']))

class Backend:
 def __init__(self):
  self.url=os.environ['SUPABASE_URL'].rstrip('/')
  self.key=os.environ['SUPABASE_SERVICE_ROLE_KEY']
  self.tmdb=os.environ['TMDB_ACCESS_TOKEN']
 def request(self,url,headers,method='GET',body=None):
  req=urllib.request.Request(url,headers=headers,method=method,data=json.dumps(body).encode() if body is not None else None)
  with urllib.request.urlopen(req,timeout=30) as response:
   raw=response.read();return json.loads(raw) if raw else None
 def db(self,path,method='GET',body=None,prefer=None):
  headers={'apikey':self.key,'Authorization':'Bearer '+self.key,'Content-Type':'application/json'}
  if prefer:headers['Prefer']=prefer
  return self.request(self.url+'/rest/v1/'+path,headers,method,body)
 def movie(self,path):return self.request('https://api.themoviedb.org/3/'+path,{'Authorization':'Bearer '+self.tmdb})

def run():
 needed=['SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','TMDB_ACCESS_TOKEN']
 if not all(os.environ.get(k) for k in needed):
  print('Personal recommendations not connected: required server configuration missing.');return
 b=Backend();users=b.db('profiles?select=user_id,last_recommendation_at');now=datetime.datetime.now(datetime.timezone.utc)
 for user in users:
  if user.get('last_recommendation_at') and (now-datetime.datetime.fromisoformat(user['last_recommendation_at'].replace('Z','+00:00'))).total_seconds()<3600:continue
  uid=user['user_id'];ratings=b.db('ratings?user_id=eq.'+uid+'&select=*');collection=b.db('collection?user_id=eq.'+uid+'&select=*')
  recent=sum(1 for row in collection if row.get('reason') and row.get('created_at') and (now-datetime.datetime.fromisoformat(row['created_at'].replace('Z','+00:00'))).total_seconds()<3600)
  budget=max(0,3-recent)
  if not budget:continue
  weights=taste(ratings);preferred=sorted((g for g,v in weights.items() if v>0),key=lambda g:weights[g],reverse=True)[:3]
  query={'language':'ru-RU','include_adult':'false','sort_by':'popularity.desc','vote_count.gte':100}
  candidates={}
  # Broad pool plus preferred genres, up to 4 pages total.
  for genres in ['', '|'.join(map(str,preferred))] if preferred else ['']:
   for page in [1,2]:
    params=dict(query,page=page)
    if genres:params['with_genres']=genres
    for movie in b.movie('discover/movie?'+urllib.parse.urlencode(params)).get('results',[]):candidates[movie['id']]=movie
  added=0
  for _,movie,reason in rank_candidates(list(candidates.values()),ratings,collection):
   if added>=budget:break
   detail=b.movie(f"movie/{movie['id']}?language=ru-RU")
   if not detail.get('runtime') or not detail.get('poster_path'):continue
   fid=10000000+detail['id'];genre_ids=[g['id'] for g in detail.get('genres',[])]
   metadata={'id':fid,'tmdbId':detail['id'],'title':detail['title'],'original':detail.get('original_title',detail['title']),'year':int(detail['release_date'][:4]),'genre':GENRES.get(genre_ids[0],'Кино') if genre_ids else 'Кино','genreIds':genre_ids,'minutes':detail['runtime'],'rating':detail.get('vote_average',0),'ratingSource':'TMDB','director':'','moods':['wonder'],'symbol':'✦','colors':['#4c6478','#263443'],'caption':reason,'description':detail.get('overview',''),'recommendationReason':reason,'remoteMetrics':{'poster':'https://image.tmdb.org/t/p/w500'+detail['poster_path'],'popularity':detail.get('popularity',0),'tmdbUpdatedAt':now.isoformat()}}
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
if __name__=='__main__':
 try:run()
 except Exception:
  print('Recommendation update failed; previous private collection retained. Check server configuration and provider access.');raise SystemExit(1)
