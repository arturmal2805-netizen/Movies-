"""Conservative categories and bounded taste features, shared by discovery and ranking."""
import json, math, re
from pathlib import Path
from collections import defaultdict
RULES=json.loads((Path(__file__).resolve().parents[1]/'config/category-rules.json').read_text())
ORDER=['horror',*RULES['known']]
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
  hit=bool(words.intersection(RULES['keywords'][category])) or any(all(term in words for term in group) for group in RULES.get('keyword_groups',{}).get(category,[]))
  for term in RULES['phrases'][category]:
   match=re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',description)
   if match and not re.search(r'(?:not(?: a)?|не)\s*$',description[max(0,match.start()-8):match.start()]):hit=True
  if hit:found.add(category)
 if horror or any(c!='dystopian' for c in found):found.add('horror')
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

class TasteProfile(dict):
 def __init__(self,*args,anchors=()):super().__init__(*args);self.anchors=anchors

def profile(ratings):
 sums=defaultdict(float);counts=defaultdict(int);anchors=[]
 for row in ratings:
  signal=rating_signal(row)
  if not signal:continue
  vector=features(row.get('metadata') or {})
  anchors.append((signal,vector,row.get('updated_at') or row.get('ratedAt') or ''))
  for key,share in vector.items():sums[key]+=signal*share;counts[key]+=1
 return TasteProfile({key:value/(counts[key]+2) for key,value in sums.items()},anchors=[(signal,vector,sum(share*importance(key) for key,share in vector.items())) for signal,vector,_ in sorted(anchors,key=lambda a:a[2],reverse=True)[:60]])

IMPORTANCE={'genre':1,'category':5,'keyword':4,'director':2}
def importance(key):return .5 if key==('category','horror') else IMPORTANCE[key[0]]

def nearby_score(vector,anchors):
 # Weighted Jaccard: shared horror alone is weak evidence; specific themes/directors matter more.
 matches=[];candidate_total=sum(share*importance(key) for key,share in vector.items())
 for signal,anchor,anchor_total in anchors:
  shared=sum(min(vector[key],share)*importance(key) for key,share in anchor.items() if key in vector)
  total=candidate_total+anchor_total-shared
  similarity=shared/total if total else 0
  if similarity>=.12:matches.append((similarity,signal))
 matches=sorted(matches,key=lambda pair:pair[0],reverse=True)[:6]
 return sum(sim*signal for sim,signal in matches)/(1.5+sum(sim for sim,_ in matches))

def match_score(movie,taste):
 vector=features(movie)
 return sum(taste.get(key,0)*share*importance(key) for key,share in vector.items())+nearby_score(vector,getattr(taste,'anchors',()))*2


def feature_metadata(detail):
 rows=[k for k in keywords(detail) if isinstance(k,dict) and isinstance(k.get('name'),str) and type(k.get('id')) is int]
 return {'genreIds':genres(detail),'keywords':[k['name'] for k in rows],'keywordIds':[k['id'] for k in rows],
         'director':director(detail),'originalLanguage':detail.get('original_language',''),
         'productionCountries':[c['iso_3166_1'] for c in detail.get('production_countries') or [] if isinstance(c,dict) and isinstance(c.get('iso_3166_1'),str)],
         'moods':classify(detail),'featureVersion':2}


def eligible_for_discovery(movie):
 policy=RULES['selection']
 try:year=int(movie.get('year') or str(movie.get('release_date',''))[:4])
 except (TypeError,ValueError):return False
 if year<policy['minimum_year']:return False
 ids=set(genres(movie));label={'Документальный':99,'Документальное':99,'Documentary':99,'Мелодрама':10749,'Романтика':10749,'Romance':10749,'Драма':18,'Drama':18,'Боевик':28,'Action':28}.get(movie.get('genre'))
 if label:ids.add(label)
 if ids.intersection(policy['always_excluded_genres']):return False
 target=bool(set(classify(movie)).intersection(('horror','dystopian'))) or movie.get('_discovery_category')=='dystopian'
 return not ids.intersection(policy['excluded_genres']) or policy['allow_target_mixed_genres'] and target
