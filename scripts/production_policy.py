"""Explicit production preferences, separate from private learned taste."""
import json,math,re
from pathlib import Path
POLICY=json.loads((Path(__file__).resolve().parents[1]/'config/category-rules.json').read_text())['selection']['production']

def production_budget(movie):
    value=movie.get('productionBudget')
    if value is None:value=movie.get('budget')
    return value if type(value) in (int,float) and math.isfinite(value) and value>0 else None

def production_exclusion(movie):
    raw=movie.get('keywords') or []
    if isinstance(raw,dict):raw=raw.get('keywords') or []
    if not isinstance(raw,list):raw=[]
    words={re.sub(r'\s+',' ',re.sub('[-_]',' ',str(k if isinstance(k,str) else k.get('name','')).lower())).strip() for k in raw if isinstance(k,(dict,str))}
    if words.intersection(POLICY['excluded_keywords']):return 'independent_or_low_budget'
    budget=production_budget(movie)
    if budget is not None and budget<POLICY['minimum_known_budget_usd']:return 'known_low_budget'
    return None

def budget_priority_score(movie):
    budget=production_budget(movie)
    return POLICY['budget_weight']*math.log2(1+budget/POLICY['budget_scale_usd']) if budget is not None else 0.
