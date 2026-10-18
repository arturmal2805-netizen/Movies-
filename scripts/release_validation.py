"""Read-only release comparison on private ratings; emits aggregate counts only."""
import hashlib
from movie_features import profile,match_score,eligible_for_discovery
from production_policy import production_exclusion
from interests import normalize_interests,build_style_model
from audience_priority import selection_priority_score56,selection_priority_score,public_quality_score,public_recognition_bonus

def compare_release(rows,interests=None):
 unique={}
 for row in rows:
  mid=row.get('tmdb_id')
  if type(mid)is not int or mid<=0:continue
  if mid not in unique or str(row.get('updated_at')or'')>=str(unique[mid].get('updated_at')or''):unique[mid]=row
 rows=sorted(unique.values(),key=lambda r:r['tmdb_id'])
 if len(rows)<100:return {'status':'insufficient','rows':len(rows)}
 preferences=normalize_interests(interests)
 fold=lambda r:int(hashlib.sha256(str(r['tmdb_id']).encode()).hexdigest()[:8],16)%5
 variants={str(w):{'likes10':0,'likes30':0,'nonRejected10':0,'nonRejected30':0,'regressingFolds':0}for w in (0,3,6)}
 tests=0;positives=0
 for part in range(5):
  train=[r for r in rows if fold(r)!=part];taste=profile(train);style=build_style_model(train,preferences)
  test=[r for r in rows if fold(r)==part and r.get('impression')in('like','neutral','dislike')and eligible_for_discovery(r.get('metadata')or{})and not production_exclusion(r.get('metadata')or{},interests=preferences)]
  predictions=[];tests+=len(test);positives+=sum(r['impression']=='like'for r in test)
  for row in test:
   movie=row['metadata'];fit=match_score(movie,taste);base=selection_priority_score56(movie,fit,style)
   if abs(selection_priority_score(movie,fit,style)-base-public_recognition_bonus(movie))>1e-8:raise RuntimeError('Release score differs from the evaluated public reach formula')
   predictions.append((row,base,fit+public_quality_score(movie,taste.predictive)))
  baseline=None
  for weight in (0,3,6):
   ordered=sorted(predictions,key=lambda p:(-p[1]-public_recognition_bonus(p[0]['metadata'],weight),-p[2],p[0]['tmdb_id']))
   counts={}
   for n in (10,30):
    counts['likes'+str(n)]=sum(r['impression']=='like'for r,_,_ in ordered[:n])
    counts['nonRejected'+str(n)]=sum(r['impression']in('like','neutral')for r,_,_ in ordered[:n])
   if baseline is None:baseline=counts
   dest=variants[str(weight)]
   for key,value in counts.items():dest[key]+=value
   dest['regressingFolds']+=any(counts[key]<baseline[key]for key in counts)
 return {'status':'compared','rows':len(rows),'tested':tests,'positives':positives,'baseline':'audience-first56','variants':variants,'folds':5}
