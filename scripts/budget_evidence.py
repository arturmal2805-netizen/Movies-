"""Optional referenced USD budgets; never infer cost from studio, title or reviews."""
import math,re,json,urllib.request,urllib.parse
from urllib.parse import urlsplit
from production_policy import production_budget

ENDPOINT='https://query.wikidata.org/sparql'
USD='http://www.wikidata.org/entity/Q4917'

def query_for(ids):
 values=' '.join('"'+str(mid)+'"' for mid in ids if type(mid)is int and mid>0)
 return '''PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX psv: <http://www.wikidata.org/prop/statement/value/>
PREFIX pr: <http://www.wikidata.org/prop/reference/>
PREFIX schema: <http://schema.org/>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX wikibase: <http://wikiba.se/ontology#>
SELECT ?movie ?tmdb ?imdb ?amount ?lower ?currency ?reference WHERE {
 VALUES ?tmdb { '''+values+''' }
 ?movie wdt:P4947 ?tmdb; p:P2130 ?statement.
 ?statement psv:P2130 ?value; prov:wasDerivedFrom ?source.
 { ?source pr:P854 ?reference }
 UNION { ?source pr:P143 wd:Q328. ?reference schema:about ?movie; schema:isPartOf <https://en.wikipedia.org/>. }
 FILTER NOT EXISTS { ?statement wikibase:rank wikibase:DeprecatedRank }
 ?value wikibase:quantityAmount ?amount; wikibase:quantityUnit ?currency.
 FILTER(?currency = wd:Q4917)
 OPTIONAL { ?value wikibase:quantityLowerBound ?lower }
 OPTIONAL { ?movie wdt:P345 ?imdb }
}'''

def request(ids):
 url=ENDPOINT+'?'+urllib.parse.urlencode({'query':query_for(ids),'format':'json'})
 req=urllib.request.Request(url,headers={'Accept':'application/sparql-results+json','User-Agent':'NightshiftFilms/1.0 (https://github.com/arturmal2805-netizen/Movies-; movie budget verification)'})
 with urllib.request.urlopen(req,timeout=15)as response:return json.load(response)

def parse_evidence(data,movies):
 by_id={str(m['id']):m for m in movies if type(m.get('id'))is int}
 found={}
 bindings=data.get('results',{}).get('bindings',[]) if isinstance(data,dict)else []
 if not isinstance(bindings,list):return {}
 for row in bindings:
  if not isinstance(row,dict):continue
  def value(key):
   item=row.get(key);result=item.get('value','') if isinstance(item,dict)else '';return result if isinstance(result,str)else ''
  mid=value('tmdb');movie=by_id.get(mid)
  if movie is None or value('currency')!=USD or not re.fullmatch(r'https?://www.wikidata.org/entity/Q[1-9]\d*',value('movie')):continue
  imdb=(movie.get('external_ids')or {}).get('imdb_id')or movie.get('imdb_id')
  if imdb and imdb!=value('imdb'):continue
  reference=value('reference')
  try:parsed=urlsplit(reference)
  except ValueError:continue
  if parsed.scheme not in ('http','https')or not parsed.hostname or parsed.username or parsed.password:continue
  try:
   nominal=float(value('amount'));amount=float(value('lower')or value('amount'))
  except (ValueError,TypeError):continue
  if not math.isfinite(amount)or not math.isfinite(nominal)or amount<=0 or amount>nominal:continue
  evidence={'amountUSD':amount,'source':'wikidata','entityUrl':value('movie').replace('/entity/','/wiki/').replace('http:','https:'),'referenceUrl':reference,'tmdbId':int(mid),'imdbId':imdb or None}
  # Conflicting/ranged claims are treated conservatively. A low estimate
  # cannot be replaced by a higher one merely to pass the minimum.
  if mid not in found or amount<found[mid]['amountUSD']:found[mid]=evidence
 return {int(mid):evidence for mid,evidence in found.items()}

class BudgetVerifier:
 def __init__(self,limit=400,fetch=request):self.limit=limit;self.fetch=fetch;self.attempted=set();self.resolved={};self.failures=0
 def verify(self,movies):
  pending=[m for m in movies if production_budget(m)is None and m.get('id')not in self.attempted]
  pending=pending[:max(0,self.limit-len(self.attempted))]
  for start in range(0,len(pending),20):
   batch=pending[start:start+20];self.attempted.update(m['id']for m in batch)
   try:self.resolved.update(parse_evidence(self.fetch([m['id']for m in batch]),batch))
   except Exception:
    self.failures+=1
    # An unavailable optional service must not spend the whole request on
    # repeated timeouts. Verified TMDB candidates remain usable.
    if self.failures>=2:self.limit=len(self.attempted);break
  for movie in movies:
   evidence=self.resolved.get(movie.get('id'))
   if evidence and production_budget(movie)is None:movie.update(budget=evidence['amountUSD'],budgetEvidence=evidence)
  return sum('budgetEvidence'in m for m in movies)
