"""Bounded canonical IMDb audience, critic and genre checks, without DB writes."""
import os,re,math,datetime,threading,urllib.parse
from concurrent.futures import ThreadPoolExecutor

ID=re.compile(r'tt[0-9]{7,12}\Z')
GENRES={'Action','Adventure','Animation','Biography','Comedy','Crime','Documentary','Drama','Family','Fantasy','Film-Noir','History','Horror','Music','Musical','Mystery','Romance','Sci-Fi','Sport','Thriller','War','Western','Adult'}

def verified_remote(movie):
 remote=movie.get('remoteMetrics')
 if not isinstance(remote,dict)or remote.get('imdbVerified')is not True:return None
 identity=remote.get('imdbId');canonical=movie.get('imdb_id')or movie.get('imdbId')
 if not isinstance(identity,str)or not ID.fullmatch(identity)or canonical and canonical!=identity:return None
 return remote

def validated_imdb_metrics(movie):
 remote=verified_remote(movie)
 if remote is None:return None
 rating,votes=remote.get('imdb'),remote.get('imdbVoteCount')
 if type(rating)not in(int,float)or not math.isfinite(rating)or not 0<rating<=10 or type(votes)not in(int,float)or not math.isfinite(votes)or not 0<votes<=10**10 or votes!=int(votes):return None
 return {'rating':rating,'votes':int(votes)}

def validated_critics_score(movie):
 remote=verified_remote(movie);value=remote.get('metascore')if remote else None
 return value if type(value)is int and 0<=value<=100 else None

def has_verified_genre(movie,genre):
 remote=verified_remote(movie);values=remote.get('imdbGenres')if remote else None
 return isinstance(values,list)and genre in values

def verified_imdb_year(movie):
 remote=verified_remote(movie);value=remote.get('imdbYear')if remote else None
 return value if type(value)is int else None

def parse_metrics(result,identity):
 if not isinstance(identity,str)or not ID.fullmatch(identity)or not isinstance(result,dict)or result.get('Response')!='True'or result.get('Type')!='movie'or result.get('imdbID')!=identity:return None
 proof={};raw=result.get('imdbVotes');rating=result.get('imdbRating')
 if isinstance(raw,str)and re.fullmatch(r'(?:[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)',raw)and isinstance(rating,str)and re.fullmatch(r'(?:[0-9]|10)(?:\.[0-9])?',rating):
  votes=int(raw.replace(',',''));score=float(rating)
  if 0<votes<=10**10 and 0<score<=10:proof.update(imdb=score,imdbVoteCount=votes)
 meta=result.get('Metascore')
 if isinstance(meta,str)and re.fullmatch(r'[0-9]{1,3}',meta)and int(meta)<=100:proof['metascore']=int(meta)
 raw_genres=result.get('Genre')
 if isinstance(raw_genres,str):
  genres=list(dict.fromkeys(g.strip()for g in raw_genres.split(',')if g.strip()in GENRES))
  if genres:proof['imdbGenres']=genres
 if not proof:return None
 year=result.get('Year')
 if isinstance(year,str)and re.fullmatch(r'[0-9]{4}',year):proof['imdbYear']=int(year)
 return {**proof,'imdbId':identity,'imdbVerified':True,'imdbUpdatedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()}

def enrich_audience(backend,movies,limit,eligible=None,good_target=15):
 key=os.environ.get('OMDB_API_KEY','').strip()
 stats={'imdbConfigured':bool(key and callable(getattr(backend,'request',None))),
        'imdbRequests':0,'imdbResolved':0,'imdbProviderFailures':0,'imdbDataRejected':0}
 if not stats['imdbConfigured']:return stats
 groups={}
 for movie in movies:
  identity=movie.get('imdb_id')
  proof=verified_remote(movie);metrics=validated_imdb_metrics(movie)
  needs_critics=bool(proof and proof.get('imdbSource')=='IMDb datasets'and metrics and metrics['rating']>=6 and validated_critics_score(movie)is None)
  if isinstance(identity,str)and ID.fullmatch(identity)and(proof is None or needs_critics):groups.setdefault(identity,[]).append(movie)
 chosen=list(groups)[:max(0,min(320,limit))];lock=threading.Lock()
 def fetch(identity):
  with lock:
   if stats['imdbProviderFailures']>=2:return
   stats['imdbRequests']+=1
  try:
   result=backend.request('https://www.omdbapi.com/?'+urllib.parse.urlencode({'apikey':key,'i':identity}),{})
   if isinstance(result,dict)and result.get('Response')=='False':
    error=str(result.get('Error','')).lower()
    if any(term in error for term in ('limit','api key','temporarily','unavailable')):raise RuntimeError('Optional audience provider unavailable')
   proof=parse_metrics(result,identity)
   with lock:
    if proof:
     for movie in groups[identity]:
      remote=movie.get('remoteMetrics');remote=dict(remote)if isinstance(remote,dict)else{}
      if remote.get('imdbSource')=='IMDb datasets':
       merged={**proof,**remote}
       if 'metascore'in proof:merged['metascore']=proof['metascore'];merged['omdbUpdatedAt']=proof['imdbUpdatedAt']
       merged['imdbGenres']=list(dict.fromkeys(remote.get('imdbGenres',[])+proof.get('imdbGenres',[])))
       movie['remoteMetrics']=merged
      else:movie['remoteMetrics']={**remote,**proof}
     stats['imdbResolved']+=1
    else:stats['imdbDataRejected']+=1
  except Exception:
   with lock:stats['imdbProviderFailures']+=1
 def good(movie):
  if eligible is not None and not eligible(movie):return False
  evidence=validated_imdb_metrics(movie);critic=validated_critics_score(movie)
  return bool(evidence and evidence['rating']>=6.5 and evidence['votes']>=10000)or critic is not None and critic>=70
 with ThreadPoolExecutor(max_workers=4)as executor:
  for start in range(0,len(chosen),40):
   list(executor.map(fetch,chosen[start:start+40]))
   enough=sum(any(good(m)for m in group)for group in groups.values())
   if stats['imdbProviderFailures']>=2 or enough>=max(1,good_target):break
 return stats
