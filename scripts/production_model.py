"""Private production evidence, learned only from canonically enriched history."""
import math
from collections import defaultdict
from taste_model import fit_margin


def production_features(movie):
    result={}
    companies=movie.get('companyIds')
    if not isinstance(companies,list):
        raw=movie.get('production_companies');raw=raw if isinstance(raw,list) else []
        companies=[c.get('id') for c in raw if isinstance(c,dict)]
    cast=movie.get('castIds')
    if not isinstance(cast,list):
        credits=movie.get('credits');credits=credits if isinstance(credits,dict) else {}
        raw=credits.get('cast');raw=raw if isinstance(raw,list) else []
        cast=[c.get('id') for c in raw if isinstance(c,dict)]
    for kind,raw,limit in [('company',companies,8),('cast',cast,6)]:
        values=list(dict.fromkeys(str(v) for v in raw if type(v) is int and v>0))[:limit]
        for value in values:result[(kind,value)]=1/math.sqrt(len(values))
    return result


def fit_production(ratings):
    # Missing metadata is not a negative example. Coverage is normalized per
    # feature family, so refreshing every like first cannot create a fake lift.
    documents=[(production_features(r.get('metadata') or {}),r['impression']=='like')
               for r in ratings if r.get('impression') in ('like','dislike')]
    documents=[(v,y) for v,y in documents if v]
    positive=sum(y for _,y in documents);negative=len(documents)-positive
    empty={'weights':{},'bias':0.,'frequency':{},'positive_support':{},
           'positive_count':positive,'negative_count':negative,'ready':False}
    if positive<3 or negative<10:return empty
    counts=[defaultdict(float),defaultdict(float)];coverage=[defaultdict(int),defaultdict(int)];support=defaultdict(int)
    for vector,label in documents:
        for kind in {k[0] for k in vector}:coverage[int(label)][kind]+=1
        for key,value in vector.items():
            counts[int(label)][key]+=value
            if label:support[key]+=1
    frequency={}
    for key in counts[0].keys()|counts[1].keys():
        p,n=coverage[1][key[0]],coverage[0][key[0]]
        # A family seen only in one class is not yet comparable.
        if not p or not n:continue
        pp,np=2*p/(p+n),2*n/(p+n)
        frequency[key]=math.log((counts[1][key]+pp)/(p+pp))-math.log((counts[0][key]+np)/(n+np))
    comparable=set(frequency)
    examples=[({k:value*.5 for k,value in v.items() if k in comparable},y) for v,y in documents]
    examples=[(v,y) for v,y in examples if v]
    if sum(y for _,y in examples)<3 or sum(not y for _,y in examples)<10:return empty
    weights,bias=fit_margin(examples,regularization=.5)
    return dict(empty,weights=weights,bias=bias,frequency=frequency,positive_support=dict(support),ready=True)


def production_score(movie,model):
    if not model.get('ready'):return 0.
    vector={k:value for k,value in production_features(movie).items() if k in model['frequency']}
    if not vector:return 0.
    margin=model['bias']+sum(model['weights'].get(k,0)*v*.5 for k,v in vector.items())
    frequency=3*sum(model['frequency'][k]*v for k,v in vector.items())/max(1,sum(vector.values()))
    return max(-2.,min(2.,.5*margin+.5*frequency))
