"""Read-only personal taste audit. Keep inputs/reports outside the public repository."""
import argparse,collections,json,math,os,urllib.request,uuid
from movie_features import features,profile,match_score,contrast_score,balanced_score,rating_signal,keywords,eligible_for_discovery,rejection_score,predictive_features,importance

def patterns(rows):
 grouped=collections.defaultdict(list)
 for row in rows:
  for key in features(row.get('metadata') or {}):grouped[key].append(rating_signal(row))
 baseline=sum(rating_signal(r) for r in rows)/len(rows) if rows else 0
 result=[]
 for (kind,value),signals in grouped.items():
  if len(signals)<3:continue
  average=sum(signals)/len(signals)
  result.append({'kind':kind,'feature':value,'support':len(signals),'mean_signal':round(average,4),'lift_from_personal_baseline':round(average-baseline,4)})
 return sorted(result,key=lambda r:(-r['lift_from_personal_baseline'],-r['support']))

def legacy_score(movie,rows):
 # Frozen pre-upgrade baseline, including the previous last-60 neighbor limit.
 sums=collections.defaultdict(float);counts=collections.Counter();anchors=[]
 for r in rows:
  signal=rating_signal(r)
  if not signal:continue
  vector=features(r.get('metadata') or {})
  anchors.append((str(r.get('updated_at') or ''),signal,vector))
  for key,share in vector.items():sums[key]+=signal*share;counts[key]+=1
 from movie_features import importance
 vector=features(movie);total=sum(share*importance(key) for key,share in vector.items());matches=[]
 for _,signal,anchor in sorted(anchors,key=lambda a:a[0],reverse=True)[:60]:
  shared=sum(min(vector.get(key,0),share)*importance(key) for key,share in anchor.items())
  union=total+sum(share*importance(key) for key,share in anchor.items())-shared
  sim=shared/union if union else 0
  if sim>=.12:matches.append((sim,signal))
 nearest=sorted(matches,reverse=True)[:6]
 return sum(sums[key]/(counts[key]+2)*share*importance(key) for key,share in vector.items())+2*sum(sim*signal for sim,signal in nearest)/(1.5+sum(sim for sim,_ in nearest))

def prior_frequency_weights(rows):
 # Frozen equal-pseudocount baseline; keep diagnostics comparable after upgrades.
 positive=collections.defaultdict(float);negative=collections.defaultdict(float);p=n=0
 for row in rows:
  label=row.get('impression')
  if label not in ('like','dislike'):continue
  if label=='like':p+=1;counts=positive
  else:n+=1;counts=negative
  for key,share in predictive_features(row.get('metadata') or {}).items():counts[key]+=share
 return {key:math.log((positive[key]+1)/(p+2))-math.log((negative[key]+1)/(n+2)) for key in positive.keys()|negative.keys()}

def prior_frequency_score(movie,rows,weights=None):
 weights=prior_frequency_weights(rows) if weights is None else weights
 vector=predictive_features(movie)
 return 3*sum(weights.get(key,0)*share*importance(key) for key,share in vector.items())/max(1,sum(share*importance(key) for key,share in vector.items()))


def evaluation(rows):
 # No self-rating leakage: the later films are never present in the training profile.
 decisive=[r for r in rows if r.get('impression') in ('like','dislike')]
 if len(decisive)<20:return {'status':'insufficient_decisive_ratings'}
 decisive=sorted(decisive,key=lambda r:(str(r.get('updated_at') or ''),r.get('tmdb_id',0)))
 split=int(len(decisive)*.8);train=decisive[:split];test=decisive[split:];model=profile(train);old_weights=prior_frequency_weights(train)
 def metrics(score):
  predictions=[(score(r.get('metadata') or {}),r['impression']=='like') for r in test]
  positive=[s for s,y in predictions if y];negative=[s for s,y in predictions if not y]
  auc=sum(1 if p>n else .5 if p==n else 0 for p in positive for n in negative)/(len(positive)*len(negative)) if positive and negative else None
  top=sorted(predictions,key=lambda prediction:prediction[0],reverse=True)[:min(10,len(predictions))]
  return {'pairwise_auc':round(auc,4) if auc is not None else None,'precision_at_10':round(sum(y for _,y in top)/len(top),4)}
 return {'status':'evaluated','split':'chronological_80_20' if all(r.get('updated_at') for r in decisive) else 'stable_id_fallback_80_20','training_count':len(train),'held_out_count':len(test),'held_out_like_rate':round(sum(r['impression']=='like' for r in test)/len(test),4),'previous':metrics(lambda movie:legacy_score(movie,train)),'previous_full_history':metrics(lambda movie:contrast_score(movie,model)),'previous_balanced':metrics(lambda movie:prior_frequency_score(movie,train,old_weights)),'current':metrics(lambda movie:match_score(movie,model))}

def validate_rows(rows):
 if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):raise ValueError('Expected a JSON array of ratings')
 ids=[r.get('tmdb_id') for r in rows];duplicate=len(ids)-len(set(ids))
 if duplicate:raise ValueError('Duplicate film IDs: export one user only without repeated ratings')
 if len({r['user_id'] for r in rows if r.get('user_id')})>1:raise ValueError('Do not combine different users into one taste profile')

def analyze(rows):
 validate_rows(rows)
 metadata=[r.get('metadata') or {} for r in rows]
 return {'ratings_count':len(rows),'impressions':dict(collections.Counter(r.get('impression','unknown') for r in rows)),'model_anchor_count':len(profile(rows).anchors),'metadata_coverage':{'with_keywords':sum(bool(keywords(m)) for m in metadata),'with_director':sum(bool(m.get('director')) for m in metadata),'with_country_field':sum('productionCountries' in m for m in metadata),'with_language':sum(bool(m.get('originalLanguage')) for m in metadata)},'excluded_by_current_policy':sum(not eligible_for_discovery(m) for m in metadata),'patterns':patterns(rows),'validation':evaluation(rows),'notes':['Correlations in rated films are not proof of causality.','Held-out metrics measure ordering of rated films, not success on unseen recommendations.','No synthetic ratings are substituted for missing private data.']}

def compare_exports(previous,current):
 # Validate user scope and unique IDs, then train only on the earlier export.
 validate_rows(previous);validate_rows(current)
 users={r['user_id'] for r in previous+current if r.get('user_id')}
 if len(users)>1:raise ValueError('Do not compare different users')
 seen={r['tmdb_id']:r for r in previous}
 fresh=[r for r in current if r['tmdb_id'] not in seen]
 test=[r for r in fresh if r.get('impression') in ('like','dislike') and eligible_for_discovery(r.get('metadata') or {})]
 model=profile(previous);old_weights=prior_frequency_weights(previous);predictions=[(match_score(r['metadata'],model),r['impression']=='like',rejection_score(r['metadata'],model)) for r in test]
 positives=[s for s,y,_ in predictions if y];negatives=[s for s,y,_ in predictions if not y]
 ordered=sorted(predictions,key=lambda p:p[0],reverse=True)
 prior=[(.25*rejection_score(r['metadata'],model)+.75*prior_frequency_score(r['metadata'],previous,old_weights),r['impression']=='like') for r in test]
 prior_pos=[s for s,y in prior if y];prior_neg=[s for s,y in prior if not y]
 return {'previous_count':len(previous),'current_count':len(current),'new_count':len(fresh),
         'new_impressions':dict(collections.Counter(r.get('impression') for r in fresh)),
         'changed_existing_count':sum(r!=seen[r['tmdb_id']] for r in current if r['tmdb_id'] in seen),
         'actual_model_versions':dict(collections.Counter((r.get('metadata') or {}).get('recommendationModel','not_recorded') for r in fresh)),
         'actual_search_versions':dict(collections.Counter((r.get('metadata') or {}).get('recommendationSearchVersion','not_recorded') for r in fresh)),
         'held_out_count':len(test),'held_out_like_count':len(positives),'training_count':model.training_count,
         'prior_likes_at_10':sum(y for _,y in sorted(prior,reverse=True)[:10]),
         'prior_pairwise_auc':sum((a>b)+.5*(a==b) for a in prior_pos for b in prior_neg)/(len(prior_pos)*len(prior_neg)) if prior_pos and prior_neg else None,
         'pairwise_auc':sum((a>b)+.5*(a==b) for a in positives for b in negatives)/(len(positives)*len(negatives)) if positives and negatives else None,
         'likes_at_10':sum(y for _,y,_ in ordered[:10]),'likes_at_30':sum(y for _,y,_ in ordered[:30]),
         'gate_passed':sum(z>=-.8 for _,_,z in predictions),'gate_retained_likes':sum(y and z>=-.8 for _,y,z in predictions),
         'notes':['New IDs are held out; existing changed ratings are not used as fresh test examples.',
                  'Retrospective ordering of rated candidates is not live API batch validation.']}


def read_supabase(user_id):
 uuid.UUID(user_id);key=os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
 if not key:raise ValueError('SUPABASE_SERVICE_ROLE_KEY is missing; add it in environment secrets')
 key=''.join(key.split());headers={'apikey':key}
 if not key.startswith('sb_secret_'):headers['Authorization']='Bearer '+key
 url=os.environ.get('SUPABASE_URL','https://tecntqujshynuttfdxhx.supabase.co').rstrip('/');rows=[]
 for offset in range(0,100000,500):
  request=urllib.request.Request(url+'/rest/v1/ratings?user_id=eq.'+user_id+'&select=*&order=tmdb_id&limit=500&offset='+str(offset),headers=headers)
  page=json.load(urllib.request.urlopen(request,timeout=30));rows.extend(page)
  if len(page)<500:return rows
 raise ValueError('Unexpectedly large export; check user scope')

if __name__=='__main__':
 parser=argparse.ArgumentParser();source=parser.add_mutually_exclusive_group(required=True);source.add_argument('--input');source.add_argument('--user-id');parser.add_argument('--output',required=True);parser.add_argument('--previous-input');args=parser.parse_args()
 rows=json.load(open(args.input)) if args.input else read_supabase(args.user_id)
 report=analyze(rows)
 if args.previous_input:report['export_comparison']=compare_exports(json.load(open(args.previous_input)),rows)
 open(args.output,'w').write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print('Analyzed',len(rows),'ratings; private report saved to the requested local file.')
