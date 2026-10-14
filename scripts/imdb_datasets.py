"""Daily public IMDb index; contains no account data and needs no API key.

Official non-commercial datasets: https://developer.imdb.com/non-commercial-datasets/
A failed refresh never replaces the last verified index.
"""
import csv,datetime,gzip,io,json,math,os,re,sqlite3,tempfile,time,urllib.request
from pathlib import Path

ID=re.compile(r'tt[0-9]{7,12}\Z')
BASE='https://datasets.imdbws.com/'
SCHEMA=1
FILM_TYPES={'movie','tvMovie','video','short'}

def default_path():return Path(os.environ.get('IMDB_DATASET_PATH',str(Path(tempfile.gettempdir())/'nightshift-imdb/public.db')))

def rows(lines,required):
 reader=csv.DictReader(lines,delimiter='\t',quoting=csv.QUOTE_NONE)
 if reader.fieldnames is None or not set(required).issubset(reader.fieldnames):raise ValueError('Unexpected public dataset columns')
 return reader

def build_index(path,rating_lines,basic_lines,stamp=None,minimum_ratings=100000):
 """Write atomically only after both complete gzip streams pass validation."""
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 fd,name=tempfile.mkstemp(prefix='imdb-',suffix='.tmp',dir=path.parent);os.close(fd)
 conn=None
 try:
  conn=sqlite3.connect(name)
  conn.execute('CREATE TABLE audience (id TEXT PRIMARY KEY,rating REAL NOT NULL,votes INTEGER NOT NULL) WITHOUT ROWID')
  conn.execute('CREATE TABLE films (id TEXT PRIMARY KEY,kind TEXT NOT NULL,year INTEGER,genres TEXT NOT NULL) WITHOUT ROWID')
  conn.execute('CREATE TABLE metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID')
  count=0;batch=[]
  for row in rows(rating_lines,('tconst','averageRating','numVotes')):
   identity=row.get('tconst');rating=row.get('averageRating','');votes=row.get('numVotes','')
   if not isinstance(identity,str)or not ID.fullmatch(identity)or not re.fullmatch(r'(?:[0-9]|10)(?:\.[0-9])?',rating)or not re.fullmatch(r'[1-9][0-9]*',votes):continue
   rating=float(rating);votes=int(votes)
   if not 0<rating<=10 or not 0<votes<=10**10:continue
   batch.append((identity,rating,votes));count+=1
   if len(batch)>=10000:conn.executemany('INSERT OR REPLACE INTO audience VALUES (?,?,?)',batch);batch=[]
   if count>5000000:raise ValueError('Unexpected public dataset size')
  conn.executemany('INSERT OR REPLACE INTO audience VALUES (?,?,?)',batch)
  if count<minimum_ratings:raise ValueError('Public ratings dataset incomplete')
  # All canonical movie audiences are useful, even when not genre Horror.
  rated={r[0]for r in conn.execute('SELECT id FROM audience')};film_count=0;horror_count=0;batch=[]
  for row in rows(basic_lines,('tconst','titleType','isAdult','startYear','genres')):
   identity=row.get('tconst');kind=row.get('titleType')
   if identity not in rated or kind not in FILM_TYPES:continue
   from imdb_audience import GENRES
   genres=list(dict.fromkeys(g for g in row.get('genres','').split(',')if g in GENRES))
   if row.get('isAdult')=='1'and 'Adult'not in genres:genres.append('Adult')
   raw=row.get('startYear','');year=int(raw)if re.fullmatch(r'[0-9]{4}',raw)else None
   batch.append((identity,kind,year,json.dumps(genres,separators=(',',':'))));film_count+=1
   horror_count+=int('Horror'in genres and not set(genres)&{'Comedy','Adult','Animation','Family','Documentary'})
   if len(batch)>=10000:conn.executemany('INSERT OR REPLACE INTO films VALUES (?,?,?,?)',batch);batch=[]
  conn.executemany('INSERT OR REPLACE INTO films VALUES (?,?,?,?)',batch)
  if minimum_ratings and film_count<10000:raise ValueError('Public film dataset incomplete')
  updated=stamp or datetime.datetime.now(datetime.timezone.utc).isoformat()
  conn.executemany('INSERT INTO metadata VALUES (?,?)',[('schema',str(SCHEMA)),('updated',updated),('ratings',str(count)),('films',str(film_count)),('horror',str(horror_count))])
  conn.commit()
  if conn.execute('PRAGMA quick_check').fetchone()!=('ok',):raise ValueError('Invalid public index')
  conn.close();conn=None
  os.replace(name,path)
  return {'ratings':count,'films':film_count,'horror':horror_count}
 finally:
  if conn is not None:conn.close()
  if os.path.exists(name):os.unlink(name)

class PublicImdbIndex:
 def __init__(self,path):self.path=Path(path);self._mapping={}
 def metadata(self):
  try:
   with sqlite3.connect('file:'+str(self.path)+'?mode=ro',uri=True)as c:
    info=dict(c.execute('SELECT key,value FROM metadata'))
   age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(info['updated'])).total_seconds()
   if info.get('schema')!=str(SCHEMA)or not 0<=age<=7*86400:return None
   return info
  except (sqlite3.Error,OSError,ValueError,KeyError):return None
 def lookup(self,identities):
  wanted=list(dict.fromkeys(i for i in identities if isinstance(i,str)and ID.fullmatch(i)))
  info=self.metadata()
  if not wanted or info is None:return {}
  out={}
  with sqlite3.connect('file:'+str(self.path)+'?mode=ro',uri=True)as c:
   for start in range(0,len(wanted),500):
    group=wanted[start:start+500];query='SELECT a.id,a.rating,a.votes,f.year,f.genres FROM audience a JOIN films f ON f.id=a.id WHERE a.id IN ('+','.join('?'for _ in group)+')'
    for identity,rating,votes,year,genres in c.execute(query,group):
     proof={'imdbId':identity,'imdbVerified':True,'imdb':rating,'imdbVoteCount':votes,'imdbGenres':json.loads(genres),'imdbSource':'IMDb datasets','imdbUpdatedAt':info['updated']}
     if year is not None:proof['imdbYear']=year
     out[identity]=proof
  return out
 def enrich(self,movies):
  evidence=self.lookup([m.get('imdb_id')for m in movies]);resolved=0
  for movie in movies:
   proof=evidence.get(movie.get('imdb_id'))
   if proof:
    prior=movie.get('remoteMetrics');prior=dict(prior)if isinstance(prior,dict)and prior.get('imdbId')in(None,proof['imdbId'])else{}
    movie['remoteMetrics']={**prior,**proof};resolved+=1
  return resolved
 def candidates(self,minimum_year,maximum_year,limit=1500,target_genre="Horror",minimum_votes=1000):
  if target_genre not in ("Horror","Thriller"):raise ValueError("Unsupported retrieval genre")
  if type(minimum_votes)is not int or minimum_votes<1000:raise ValueError("Invalid retrieval audience floor")
  if self.metadata()is None:return []
  with sqlite3.connect('file:'+str(self.path)+'?mode=ro',uri=True)as c:
   results=c.execute('SELECT a.id,a.rating,a.votes,f.year,f.genres FROM audience a JOIN films f ON f.id=a.id WHERE f.kind=? AND f.year>=? AND f.year<=? AND a.votes>=? AND instr(f.genres,?)>0 AND instr(f.genres,?)=0 AND instr(f.genres,?)=0 AND instr(f.genres,?)=0 AND instr(f.genres,?)=0 AND instr(f.genres,?)=0 ORDER BY a.votes DESC,a.id LIMIT ?',('movie',minimum_year,maximum_year,minimum_votes,*[json.dumps(g)for g in (target_genre,'Comedy','Adult','Animation','Family','Documentary')],max(1,min(5000,limit))))
   # Genre restrictions constrain this retrieval route, not global eligibility.
   found=[]
   for identity,rating,votes,year,genres in results:
    tags=json.loads(genres)
    if target_genre in tags and not set(tags)&{'Comedy','Adult','Animation','Family','Documentary'}:found.append((identity,rating,votes,year))
   return sorted(found,key=lambda r:(-(r[1]-4.5)*math.log2(1+r[2]),-r[2],r[0]))
 def mapping(self,identities):return {i:self._mapping[i]for i in identities if i in self._mapping}
 def record_mapping(self,identity,mid):
  # Per-run only. Cache artifacts must contain the entire public datasets,
  # never a user's lookup/selection history.
  if isinstance(identity,str)and ID.fullmatch(identity)and type(mid)is int and mid>0:self._mapping[identity]=mid

class BoundedLines:
 def __init__(self,response):self.response=response;self.read=0;self.start=time.monotonic()
 def __iter__(self):
  with gzip.GzipFile(fileobj=self.response)as gz:
   with io.TextIOWrapper(gz,encoding='utf-8',errors='strict')as text:
    for line in text:
     self.read+=len(line)
     if self.read>4*1024**3 or time.monotonic()-self.start>900:raise ValueError('Public download exceeded bound')
     yield line

def prepare(path=None):
 path=Path(path or default_path());index=PublicImdbIndex(path);info=index.metadata();today=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
 if info and info['updated'].startswith(today):return {'ready':True,'fresh':True,'cached':True,**{k:int(info[k])for k in ('ratings','films','horror')}}
 try:
  # No authorization headers are sent to the public dataset host.
  with urllib.request.urlopen(urllib.request.Request(BASE+'title.ratings.tsv.gz',headers={'User-Agent':'Nightshift public audience index/1.0'}),timeout=45)as ratings:
   with urllib.request.urlopen(urllib.request.Request(BASE+'title.basics.tsv.gz',headers={'User-Agent':'Nightshift public audience index/1.0'}),timeout=45)as basics:
    result=build_index(path,BoundedLines(ratings),BoundedLines(basics))
  return {'ready':True,'fresh':True,'cached':False,**result}
 except Exception:
  return {'ready':bool(info),'fresh':False,'cached':bool(info),'refreshFailed':True}

if __name__=='__main__':
 result=prepare();print('Public IMDb index:',json.dumps(result,separators=(',',':')))
 if os.environ.get('GITHUB_ACTIONS')=='true':print('::notice title=IMDb public index::'+json.dumps(result,separators=(',',':')))
 output=os.environ.get('GITHUB_OUTPUT')
 if output:
  with open(output,'a')as out:out.write('fresh='+str(result['fresh']).lower()+'\n')
