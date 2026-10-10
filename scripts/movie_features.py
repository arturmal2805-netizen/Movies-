"""Conservative categories and bounded taste features, shared by discovery and ranking."""
import json, math, re
from pathlib import Path
from collections import defaultdict
from taste_model import fit_margin,margin_features,MODEL_VERSION
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
 if row.get('impression')=='neutral' and values and all(value==5 for value in values):return 0
 return sign*.8+adjustment*.2

class TasteProfile(dict):
 def __init__(self,*args,anchors=()):
  super().__init__(*args);self.anchors=anchors;self.neighbor_index=defaultdict(list)
  for i,(_,vector,_) in enumerate(anchors):
   for key in vector:
    if specific_feature(key):self.neighbor_index[key].append(i)

def profile(ratings):
 ratings=list(ratings)
 sums=defaultdict(float);counts=defaultdict(int);shares=defaultdict(float);anchors=[]
 for row in ratings:
  signal=rating_signal(row)
  if not signal:continue
  vector=features(row.get('metadata') or {})
  anchors.append((signal,vector,row.get('updated_at') or row.get('ratedAt') or ''))
  for key,share in vector.items():sums[key]+=signal*share;shares[key]+=share;counts[key]+=1
 baseline=sum(a[0] for a in anchors)/len(anchors) if anchors else 0
 # Contrast with the user's own baseline: mass rejection must not erase every horror preference.
 weights={key:.25*sums[key]/(counts[key]+2)+.75*(sums[key]-baseline*shares[key])/(counts[key]+4) for key in sums}
 result=TasteProfile(weights,anchors=[(signal,vector,sum(share*importance(key) for key,share in vector.items())) for signal,vector,_ in anchors])
 result.contrast_weights=weights
 positive=defaultdict(float);negative=defaultdict(float);positive_support=defaultdict(int);positive_count=negative_count=0;examples=[]
 for row in ratings:
  label=row.get('impression')
  if label not in ('like','dislike'):continue
  if label=='like':positive_count+=1;counts_by_class=positive
  else:negative_count+=1;counts_by_class=negative
  vector=predictive_features(row.get('metadata') or {})
  examples.append((margin_features(vector),label=='like'))
  for key,share in vector.items():
   counts_by_class[key]+=share
   if label=='like':positive_support[key]+=1
 # Class-normalized log odds with a two-observation empirical prior.
 # Equal +1 pseudocounts can reward tags seen only in rejected movies when
 # classes are imbalanced. Split prior mass by the user's actual class ratio.
 # Unobserved evidence is neutral; negative-only evidence is always negative.
 result.predictive=positive_count>=3 and negative_count>=3 and positive_count+negative_count>=20
 if result.predictive:
  total=positive_count+negative_count;positive_prior=2*positive_count/total;negative_prior=2*negative_count/total
  result.balanced_weights={key:math.log((positive[key]+positive_prior)/(positive_count+positive_prior))-math.log((negative[key]+negative_prior)/(negative_count+negative_prior)) for key in positive.keys()|negative.keys()}
  learned,result.bias=fit_margin(examples);result.clear();result.update(learned)
 result.positive_support=dict(positive_support)
 result.training_count=positive_count+negative_count;result.positive_count=positive_count;result.negative_count=negative_count
 result.model_version=MODEL_VERSION if result.predictive else 'contrast-fallback'
 return result

def predictive_features(movie):
 vector=features(movie)
 language=movie.get('originalLanguage') or movie.get('original_language')
 if language:vector[('language',language)]=1
 try:year=int(movie.get('year') or str(movie.get('release_date',''))[:4])
 except (TypeError,ValueError):year=0
 if year:vector[('period',year//5)]=1
 return vector

def specific_feature(key):return key[0] in ('keyword','director') or key[0]=='category' and key[1]!='horror'

IMPORTANCE={'genre':1,'category':5,'keyword':4,'director':2,'language':.75,'period':.75}
def importance(key):return .5 if key==('category','horror') else IMPORTANCE[key[0]]

def nearby_score(vector,anchors):
 # Weighted Jaccard: shared horror alone is weak evidence; specific themes/directors matter more.
 matches=[];candidate_total=sum(share*importance(key) for key,share in vector.items())
 for signal,anchor,anchor_total in anchors:
  shared=sum(min(vector[key],share)*importance(key) for key,share in anchor.items() if key in vector)
  total=candidate_total+anchor_total-shared
  similarity=shared/total if total else 0
  specific=any(key in vector and specific_feature(key) for key in anchor)
  if similarity>=.12 and specific:matches.append((similarity,signal))
 matches=sorted(matches,key=lambda pair:pair[0],reverse=True)[:6]
 return sum(sim*signal for sim,signal in matches)/(1.5+sum(sim for sim,_ in matches))

def contrast_score(movie,taste):
 vector=features(movie)
 index=getattr(taste,'neighbor_index',None);anchors=getattr(taste,'anchors',())
 if index is not None:anchors=[anchors[i] for i in sorted({i for key in vector for i in index.get(key,())})]
 weights=getattr(taste,'contrast_weights',taste)
 return sum(weights.get(key,0)*share*importance(key) for key,share in vector.items())+nearby_score(vector,anchors)*2

def balanced_score(movie,taste):
 if not getattr(taste,'predictive',False):return contrast_score(movie,taste)
 vector=predictive_features(movie);weights=taste.balanced_weights
 return 3*sum(weights.get(key,0)*share*importance(key) for key,share in vector.items())/max(1,sum(share*importance(key) for key,share in vector.items()))

def rejection_score(movie,taste):
 if not getattr(taste,'predictive',False):return contrast_score(movie,taste)
 return taste.bias+sum(taste.get(key,0)*share for key,share in margin_features(predictive_features(movie)).items())

def match_score(movie,taste):
 if not getattr(taste,'predictive',False):return contrast_score(movie,taste)
 # Keep ranking and rejection distinct. Frequency evidence uses the empirical
 # prior, while the classifier controls acceptance and search seeds.
 return .25*rejection_score(movie,taste)+.75*balanced_score(movie,taste)


def feature_metadata(detail):
 rows=[k for k in keywords(detail) if isinstance(k,dict) and isinstance(k.get('name'),str) and type(k.get('id')) is int]
 return {'genreIds':genres(detail),'keywords':[k['name'] for k in rows],'keywordIds':[k['id'] for k in rows],
         'director':director(detail),'originalLanguage':detail.get('original_language',''),
         'productionCountries':[c['iso_3166_1'] for c in detail.get('production_countries') or [] if isinstance(c,dict) and isinstance(c.get('iso_3166_1'),str)],
         'moods':classify(detail),'featureVersion':2}


def eligible_for_discovery(movie,require_target=None):
 policy=RULES['selection']
 try:year=int(movie.get('year') or str(movie.get('release_date',''))[:4])
 except (TypeError,ValueError):return False
 if year<policy['minimum_year']:return False
 ids=set(genres(movie));label={'Семейный':10751,'Family':10751,'Документальный':99,'Документальное':99,'Documentary':99,'Анимация':16,'Мультфильм':16,'Animation':16,'Аниме':16,'Anime':16,'Мелодрама':10749,'Романтика':10749,'Romance':10749,'Драма':18,'Drama':18,'Боевик':28,'Action':28}.get(movie.get('genre'))
 if label:ids.add(label)
 if ids.intersection(policy['always_excluded_genres']):return False
 countries=movie.get('productionCountries') or movie.get('production_countries') or []
 countries={str(c if isinstance(c,str) else c.get('iso_3166_1','')).upper() for c in countries if isinstance(c,(dict,str))}
 if countries.intersection(policy['excluded_countries']) or str(movie.get('originalLanguage') or movie.get('original_language') or '').lower() in policy['excluded_languages']:return False
 # A search result can lack thematic keywords. Conditional genre/target checks wait for details.
 if require_target is False:return True
 target=bool(set(classify(movie)).intersection(('horror','dystopian'))) or movie.get('_discovery_category')=='dystopian'
 if (policy.get('require_target',False) if require_target is None else require_target) and not target:return False
 return not ids.intersection(policy['excluded_genres']) or policy['allow_target_mixed_genres'] and target
