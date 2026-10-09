"""Conservative categories and bounded taste features, shared by discovery and ranking."""
import json, math, re
from pathlib import Path
from collections import defaultdict
RULES=json.loads((Path(__file__).resolve().parents[1]/'config/category-rules.json').read_text())
ORDER=[*RULES['known'],'comedy','adventure','anime']
GENERIC={'based on novel or book','based on true story','sequel','remake','duringcreditsstinger','aftercreditsstinger','independent film','woman director'}

def normalize(value):return re.sub(r'\s+',' ',re.sub('[-_]',' ',str(value or '').lower())).strip()

def keywords(movie):
 raw=movie.get('keywords') or []
 if isinstance(raw,dict):raw=raw.get('keywords') or []
 if not isinstance(raw,list):return []
 return [k for k in raw if isinstance(k,(dict,str))]

def genres(movie):
 raw=movie.get('genreIds')
 if raw is None:
  raw=[g.get('id') for g in movie.get('genres') or [] if isinstance(g,dict)] if 'genres' in movie else movie.get('genre_ids',[])
 return list(dict.fromkeys(g for g in raw if type(g) is int)) if isinstance(raw,list) else []

def director(movie):
 credits=movie.get('credits');crew=credits.get('crew') or [] if isinstance(credits,dict) else []
 names=[c.get('name','') for c in crew if isinstance(c,dict) and c.get('job')=='Director']
 return movie.get('director') or ', '.join(names)

def classify(movie):
 ids=genres(movie); words={normalize(k if isinstance(k,str) else k.get('name')) for k in keywords(movie)}
 description=normalize(movie.get('description') or movie.get('overview')); found=set()
 horror=27 in ids or movie.get('genre')=='Ужасы'
 for category,known in RULES['known'].items():
  if movie.get('tmdbId',movie.get('id')) in known:found.add(category);continue
  if category!='dystopian' and not horror:continue
  hit=bool(words.intersection(RULES['keywords'][category]))
  for term in RULES['phrases'][category]:
   match=re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',description)
   if match and not re.search(r'(?:not(?: a)?|не)\s*$',description[max(0,match.start()-8):match.start()]):hit=True
  if hit:found.add(category)
 if 35 in ids or movie.get('genre')=='Комедия':found.add('comedy')
 if 12 in ids or movie.get('genre')=='Приключения':found.add('adventure')
 lang=movie.get('originalLanguage',movie.get('original_language'))
 countries=movie.get('productionCountries') or [c.get('iso_3166_1') for c in movie.get('production_countries') or [] if isinstance(c,dict)]
 if movie.get('genre')=='Аниме' or 16 in ids and (lang=='ja' or 'anime' in words or not lang and 'JP' in countries):found.add('anime')
 return [c for c in ORDER if c in found]

def features(movie):
 groups={'genre':genres(movie),'category':classify(movie),'keyword':list(dict.fromkeys(normalize(k if isinstance(k,str) else k.get('name')) for k in keywords(movie)))[:24], 'director':[normalize(director(movie))]}
 result={}
 for kind,values in groups.items():
  values=[v for v in values if v and (kind!='keyword' or v not in GENERIC)]
  for value in values:result[(kind,value)]=1/math.sqrt(len(values))
 return result

def rating_signal(row):
 sign={'like':1,'dislike':-1,'neutral':0,'watched':0}.get(row.get('impression'),0)
 values=[row.get(k) for k in ('plot','cinematography') if type(row.get(k)) in (int,float) and 1<=row[k]<=10]
 adjustment=(sum(values)/len(values)-5.5)/4.5 if values else 0
 return sign*.8+adjustment*.2

def profile(ratings):
 sums=defaultdict(float);counts=defaultdict(int)
 for row in ratings:
  signal=rating_signal(row)
  for key,share in features(row.get('metadata') or {}).items():sums[key]+=signal*share;counts[key]+=1
 return {key:value/(counts[key]+2) for key,value in sums.items()}

IMPORTANCE={'genre':3,'category':4,'keyword':4,'director':2}
def match_score(movie,taste):return sum(taste.get(key,0)*share*IMPORTANCE[key[0]] for key,share in features(movie).items())

def feature_metadata(detail):
 rows=[k for k in keywords(detail) if isinstance(k,dict) and isinstance(k.get('name'),str) and type(k.get('id')) is int]
 return {'genreIds':genres(detail),'keywords':[k['name'] for k in rows],'keywordIds':[k['id'] for k in rows],
         'director':director(detail),'originalLanguage':detail.get('original_language',''),
         'productionCountries':[c['iso_3166_1'] for c in detail.get('production_countries') or [] if isinstance(c,dict) and isinstance(c.get('iso_3166_1'),str)],
         'moods':classify(detail),'featureVersion':2}
