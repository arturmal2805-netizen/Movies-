"""Bounded public audience checks through canonical IMDb IDs, without DB writes."""
import os,re,math,datetime,threading,urllib.parse
from concurrent.futures import ThreadPoolExecutor

ID=re.compile(r'tt[0-9]{7,12}\Z')

def validated_imdb_metrics(movie):
 remote=movie.get('remoteMetrics')
 if not isinstance(remote,dict)or remote.get('imdbVerified')is not True:return None
 identity=remote.get('imdbId');canonical=movie.get('imdb_id')or movie.get('imdbId')
 if not isinstance(identity,str)or not ID.fullmatch(identity)or canonical and canonical!=identity:return None
 rating,votes=remote.get('imdb'),remote.get('imdbVoteCount')
 if type(rating)not in(int,float)or not math.isfinite(rating)or not 0<rating<=10 or type(votes)not in(int,float)or not math.isfinite(votes)or not 0<votes<=10**10 or votes!=int(votes):return None
 return {'rating':rating,'votes':int(votes)}

def parse_metrics(result,identity):
 if not isinstance(result,dict)or result.get('Response')!='True'or result.get('Type')!='movie'or result.get('imdbID')!=identity:return None
 raw=result.get('imdbVotes');rating=result.get('imdbRating')
 if not isinstance(raw,str)or not re.fullmatch(r'(?:[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)',raw):return None
 if not isinstance(rating,str)or not re.fullmatch(r'(?:[0-9]|10)(?:\.[0-9])?',rating):return None
 votes=int(raw.replace(',',''));score=float(rating)
 if not 0<votes<=10**10 or not 0<score<=10:return None
 return {'imdb':score,'imdbVoteCount':votes,'imdbId':identity,'imdbVerified':True,
         'imdbUpdatedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()}

def enrich_audience(backend,movies,limit):
 key=os.environ.get('OMDB_API_KEY','').strip()
 stats={'imdbConfigured':bool(key and callable(getattr(backend,'request',None))),
        'imdbRequests':0,'imdbResolved':0,'imdbProviderFailures':0,'imdbDataRejected':0}
 if not stats['imdbConfigured']:return stats
 groups={}
 for movie in movies:
  identity=movie.get('imdb_id')
  if isinstance(identity,str)and ID.fullmatch(identity)and not validated_imdb_metrics(movie):groups.setdefault(identity,[]).append(movie)
 chosen=list(groups)[:max(0,min(80,limit))];lock=threading.Lock()
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
      movie['remoteMetrics']={**remote,**proof}
     stats['imdbResolved']+=1
    else:stats['imdbDataRejected']+=1
  except Exception:
   with lock:stats['imdbProviderFailures']+=1
 with ThreadPoolExecutor(max_workers=4)as executor:list(executor.map(fetch,chosen))
 return stats
