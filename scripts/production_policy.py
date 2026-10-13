"""Explicit production preferences, separate from private learned taste."""
import json,re
from pathlib import Path
from interests import director_selected,pattern_affinity
POLICY=json.loads((Path(__file__).resolve().parents[1]/'config/category-rules.json').read_text())['selection']['production']

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

def production_exclusion(movie,interests=None):
    ids=movie.get('genreIds')
    if not isinstance(ids,list):ids=[g.get('id') for g in movie.get('genres',[]) if isinstance(g,dict)] if isinstance(movie.get('genres'),list) else movie.get('genre_ids',[])
    ids=set(i for i in ids if type(i) is int) if isinstance(ids,list) else set()
    if any(set(pair).issubset(ids) for pair in POLICY.get('excluded_genre_combinations',[])):return 'horror_comedy'
    if provider_words(movie).intersection(POLICY['excluded_keywords']):return 'camp_or_parody'
    return None
