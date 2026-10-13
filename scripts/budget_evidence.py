"""Optional referenced USD budgets; never infer cost from studio, title or reviews."""
import math,re,json,urllib.request,urllib.parse
from urllib.parse import urlsplit
from production_policy import production_budget

ENDPOINT='https://query.wikidata.org/sparql'
USD='http://www.wikidata.org/entity/Q4917'

def query_for(ids):
 values=[]
 for item in ids:
  mid=item.get('id')if isinstance(item,dict)else item
  if type(mid)is not int or mid<=0:continue
  imdb=((item.get('external_ids')or {}).get('imdb_id')or item.get('imdb_id')or'')if isinstance(item,dict)else''
  imdb=imdb if isinstance(imdb,str)and re.fullmatch(r'tt[0-9]{7,10}',imdb)else''
  values.append('("'+str(mid)+'" "'+imdb+'")')
 values=' '.join(values)
 return '''PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX psv: <http://www.wikidata.org/prop/statement/value/>
PREFIX pr: <http://www.wikidata.org/prop/reference/>
PREFIX schema: <http://schema.org/>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX wikibase: <http://wikiba.se/ontology#>
SELECT ?movie ?tmdb ?imdb ?amount ?lower ?currency ?reference WHERE {
 VALUES (?tmdb ?canonicalImdb) { '''+values+''' }
 { ?movie wdt:P4947 ?tmdb }
 UNION { ?movie wdt:P345 ?canonicalImdb. FILTER(?canonicalImdb != "") }
 FILTER NOT EXISTS { ?movie wdt:P4947 ?otherTmdb. FILTER(?otherTmdb != ?tmdb) }
 ?movie p:P2130 ?statement.
 ?statement psv:P2130 ?value; prov:wasDerivedFrom ?source.
 { ?source pr:P854 ?reference }
 UNION { ?source pr:P143 wd:Q328. ?reference schema:about ?movie; schema:isPartOf <https://en.wikipedia.org/>. }
 FILTER NOT EXISTS { ?statement wikibase:rank wikibase:DeprecatedRank }
 ?value wikibase:quantityAmount ?amount; wikibase:quantityUnit ?currency.
 FILTER(?currency = wd:Q4917)
 OPTIONAL { ?value wikibase:quantityLowerBound ?lower }
 OPTIONAL { ?movie wdt:P345 ?imdb }
 FILTER(?canonicalImdb = "" || ?imdb = ?canonicalImdb)
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


def request_entity(qid):
 if not re.fullmatch(r'Q[1-9]\d*',qid):raise ValueError('Invalid public entity identifier')
 req=urllib.request.Request('https://www.wikidata.org/wiki/Special:EntityData/'+qid+'.json',headers={'Accept':'application/json','User-Agent':'NightshiftFilms/1.0 (https://github.com/arturmal2805-netizen/Movies-; movie budget verification)'})
 with urllib.request.urlopen(req,timeout=10)as response:return json.load(response)

def entity_bindings(data,qid,movie):
 entities=data.get('entities',{})if isinstance(data,dict)else {};entity=entities.get(qid,{})if isinstance(entities,dict)else {}
 if not isinstance(entity,dict)or entity.get('id')!=qid:return []
 claims=entity.get('claims',{});claims=claims if isinstance(claims,dict)else {}
 def values(prop):
  return [c.get('mainsnak',{}).get('datavalue',{}).get('value')for c in claims.get(prop,[])if isinstance(c,dict)and c.get('rank')!='deprecated']
 tmdb=values('P4947')
 if tmdb and str(movie['id'])not in tmdb:return []
 imdb=(movie.get('external_ids')or {}).get('imdb_id')or movie.get('imdb_id')
 if imdb and imdb not in values('P345'):return []
 if not tmdb and not imdb:return []
 article=(entity.get('sitelinks')or {}).get('enwiki')or {};title=article.get('title')if isinstance(article,dict)else None
 rows=[]
 for claim in claims.get('P2130',[]):
  if not isinstance(claim,dict)or claim.get('rank')=='deprecated':continue
  quantity=claim.get('mainsnak',{}).get('datavalue',{}).get('value')
  if not isinstance(quantity,dict)or quantity.get('unit')!=USD:continue
  for reference in claim.get('references',[]):
   snaks=reference.get('snaks',{})if isinstance(reference,dict)else {}
   urls=[s.get('datavalue',{}).get('value')for s in snaks.get('P854',[])if isinstance(s,dict)]
   imported=any(isinstance(s,dict)and s.get('datavalue',{}).get('value',{}).get('id')=='Q328'for s in snaks.get('P143',[]))
   if imported and isinstance(title,str):urls.append('https://en.wikipedia.org/wiki/'+urllib.parse.quote(title.replace(' ','_')))
   for url in urls:
    raw={'tmdb':str(movie['id']),'imdb':imdb or'','movie':'http://www.wikidata.org/entity/'+qid,'currency':USD,'amount':quantity.get('amount'),'lower':quantity.get('lowerBound')or'','reference':url}
    rows.append({key:{'value':value}for key,value in raw.items()})
 return rows

class BudgetResolver:
 """Entity JSON is a fast independent route when the query service is down."""
 def __init__(self,movie_fetch,entity_fetch=request_entity,query_fetch=request):
  self.movie_fetch=movie_fetch;self.entity_fetch=entity_fetch;self.query_fetch=query_fetch;self.query_failed=False;self.entities={}
 def __call__(self,ids):
  from recommendation_sources import detail_path
  from concurrent.futures import ThreadPoolExecutor
  movies=[self.movie_fetch(detail_path(mid))for mid in ids]
  def fetch(movie):
   qid=(movie.get('external_ids')or {}).get('wikidata_id')
   if not isinstance(qid,str)or not re.fullmatch(r'Q[1-9]\d*',qid):return [],False
   try:
    if qid not in self.entities:self.entities[qid]=self.entity_fetch(qid)
    return entity_bindings(self.entities[qid],qid,movie),True
   except Exception:return [],False
  with ThreadPoolExecutor(max_workers=4)as executor:results=list(executor.map(fetch,movies))
  rows=[row for result,_ in results for row in result];resolved=parse_evidence({'results':{'bindings':rows}},movies)
  missing=[mid for mid in ids if mid not in resolved]
  if missing and not self.query_failed:
   try:
    extra=self.query_fetch([m for m in movies if m['id']in missing]);rows.extend(extra.get('results',{}).get('bindings',[]))
   except Exception:self.query_failed=True
  if not rows and self.query_failed and not any(ok for _,ok in results):raise RuntimeError('Referenced budget sources unavailable')
  return {'results':{'bindings':rows}}
