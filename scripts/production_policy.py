"""Explicit production preferences, separate from private learned taste."""
import json,math,re
from pathlib import Path
from interests import director_selected,pattern_affinity
POLICY=json.loads((Path(__file__).resolve().parents[1]/'config/category-rules.json').read_text())['selection']['production']

def production_budget(movie):
    value=movie.get('productionBudget')
    if value is None:value=movie.get('budget')
    return value if type(value) in (int,float) and math.isfinite(value) and value>0 else None

def provider_words(movie):
    raw=movie.get('keywords') or []
    if isinstance(raw,dict):raw=raw.get('keywords') or []
    if not isinstance(raw,list):return set()
    return {normalize(k if isinstance(k,str) else k.get('name','')) for k in raw if isinstance(k,(dict,str))}

def normalize(value):return re.sub(r'\s+',' ',re.sub('[-_]',' ',str(value).lower())).strip()

def director_focus(movie,interests=None):return director_selected(movie,interests)

def style_affinity(movie,model=None):
    if model is not None:return pattern_affinity(movie,model)
    words=provider_words(movie)
    groups=sum(bool(words.intersection(group)) for group in POLICY.get('style_groups',[]))
    return groups*.5 if groups>=2 else 0.

def production_exclusion(movie,require_budget=True,legacy=False,interests=None):
    ids=movie.get('genreIds')
    if not isinstance(ids,list):ids=[g.get('id') for g in movie.get('genres',[]) if isinstance(g,dict)] if isinstance(movie.get('genres'),list) else movie.get('genre_ids',[])
    ids=set(i for i in ids if type(i) is int) if isinstance(ids,list) else set()
    if not legacy and any(set(pair).issubset(ids) for pair in POLICY.get('excluded_genre_combinations',[])):return 'horror_comedy'
    words=provider_words(movie)
    banned=set(['independent film','low budget','microbudget','micro budget'] if legacy else POLICY['excluded_keywords'])
    if not legacy and director_focus(movie,interests):banned-=set(['independent film','low budget','microbudget','micro budget'])
    if words.intersection(banned):return 'independent_or_low_budget'
    budget=production_budget(movie)
    if budget is not None and budget<(10000000 if legacy else POLICY['minimum_known_budget_usd']) and (legacy or not director_focus(movie,interests)):return 'known_low_budget'
    if budget is None and require_budget and not legacy and POLICY.get('require_known_budget'):return 'unverified_budget'
    return None

def budget_priority_score(movie):
    budget=production_budget(movie)
    return POLICY['budget_weight']*math.log2(1+budget/POLICY['budget_scale_usd']) if budget is not None else 0.
