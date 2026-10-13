"""Private editable preferences and thematic references; not authentication data."""
import json,re,math
from collections import Counter
from pathlib import Path
DEFAULT=json.loads((Path(__file__).resolve().parents[1]/'config/category-rules.json').read_text())['selection']['production']['default_interests']
GENERIC={'vampire','zombie','monster','witch','ghost','murder','death','demon','violence','blood','sequel','remake','based on novel or book','based on true story','duringcreditsstinger','aftercreditsstinger','independent film','woman director'}
def clean(value):return re.sub(r'\s+',' ',value).strip()[:120] if isinstance(value,str) else ''
def norm(value):return clean(value).lower().replace('-',' ').replace('_',' ')
def normalize_interests(value=None):
 if not isinstance(value,dict):value=DEFAULT
 priority=value.get('genrePriority');priority=priority if isinstance(priority,list) else DEFAULT['genrePriority']
 priority=list(dict.fromkeys(g for g in priority if g in ('horror','dystopian')))
 priority+=[g for g in ('horror','dystopian') if g not in priority]
 raw=value.get('directors');raw=raw if isinstance(raw,list) else DEFAULT['directors']
 selected=[];seen=set()
 for item in raw[:20]:
  name=clean(item if isinstance(item,str) else item.get('name','') if isinstance(item,dict) else '')
  if not name:continue
  aliases=item.get('aliases',[]) if isinstance(item,dict) else []
  aliases=aliases if isinstance(aliases,list) else []
  known=next((d['aliases'] for d in DEFAULT['directors'] if norm(name) in [norm(a) for a in d['aliases']+[d['name']]]),[])
  names=list(dict.fromkeys([name]+[clean(a) for a in aliases[:6] if isinstance(a,str) and clean(a)]+known))[:8]
  if any(norm(n) in seen for n in names):continue
  seen.update(norm(n) for n in names);selected.append({'name':name,'aliases':names})
 return {'version':1,'genrePriority':priority,'directors':selected}
def director_names(movie):
 credits=movie.get('credits')
 if isinstance(credits,dict):
  raw=credits.get('crew');raw=raw if isinstance(raw,list) else []
  names=[p.get('name','') for p in raw if isinstance(p,dict) and p.get('job')=='Director']
 else:names=[movie.get('director','')]+(movie.get('directorAliases') if isinstance(movie.get('directorAliases'),list) else [])
 return {norm(n) for name in names if isinstance(name,str) for n in name.split(',') if clean(n)}
def director_selected(movie,interests=None):
 targets={norm(n) for d in normalize_interests(interests)['directors'] for n in d['aliases']+[d['name']]}
 return bool(director_names(movie).intersection(targets))
def words(movie):
 raw=movie.get('keywords') or []
 if isinstance(raw,dict):raw=raw.get('keywords') or []
 return {norm(k if isinstance(k,str) else k.get('name','')) for k in raw if isinstance(k,(dict,str))} if isinstance(raw,list) else set()
def build_style_model(ratings,interests=None):
 references=[r.get('metadata') or {} for r in ratings if r.get('impression')=='like' and director_selected(r.get('metadata') or {},interests)]
 rejected=[r.get('metadata') or {} for r in ratings if r.get('impression')=='dislike']
 p=Counter(k for m in references for k in words(m) if k and k not in GENERIC)
 n=Counter(k for m in rejected for k in words(m) if k and k not in GENERIC)
 weights={k:min(3.,max(0.,math.log((v+1)/(len(references)+2))-math.log((n[k]+1)/(len(rejected)+2)) if rejected else math.log1p(v))) for k,v in p.items()}
 return {'weights':weights,'reference_count':len(references),'patterns':[sorted(k for k in words(m) if weights.get(k,0)>0) for m in references]}
def pattern_affinity(movie,model):
 candidates=words(movie);strongest=0.
 for pattern in model.get('patterns',[]):
  hits=[model.get('weights',{}).get(k,0.) for k in pattern if k in candidates]
  if len(hits)>=2:strongest=max(strongest,sum(hits))
 return min(2.,strongest/4)
