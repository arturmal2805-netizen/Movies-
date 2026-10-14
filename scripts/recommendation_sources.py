"""Discovery adapters return canonical TMDB IDs; metadata providers do not count."""
import os
import datetime
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
from simkl_source import FEED_URL, HEADERS, entries
from movie_features import genres,RULES,normalize

def detail_path(mid):return f'movie/{mid}?language=ru-RU&append_to_response=keywords,credits'

def annotate_query(rows,path):
    query=urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
    if query.get('sort_by')==['popularity.desc']:
        rows=[dict(m,_personal_routes=['audience-popularity']) if isinstance(m,dict) else m for m in rows]
    if query.get('sort_by')==['vote_count.desc']:
        rows=[dict(m,_personal_routes=['audience-votes']) if isinstance(m,dict) else m for m in rows]
    if query.get('sort_by')==['vote_average.desc']:
        rows=[dict(m,_personal_routes=['audience-quality']) if isinstance(m,dict) else m for m in rows]
    for parameter,label in [('with_companies','liked-studio'),('with_cast','liked-cast')]:
        if query.get(parameter):rows=[dict(m,_personal_routes=list(dict.fromkeys(m.get('_personal_routes',[])+[label]))) if isinstance(m,dict) else m for m in rows]
    words=query.get('with_keywords',[])
    if words in (['4565'],['4458']):return [dict(m,_discovery_category='dystopian') if isinstance(m,dict) else m for m in rows]
    if words and ',' in words[0]:return [dict(m,_matched_theme_groups=[words[0]]) if isinstance(m,dict) else m for m in rows]
    return rows

def excluded(config,mid):return mid in config.get('_excluded_ids',set())


def resolve_ids(backend,ids,config):
    def resolve(mid):
        try:
            detail=backend.movie(detail_path(mid))
            if isinstance(detail,dict) and detail.get('id')==mid:return dict(detail,genre_ids=genres(detail))
        except Exception:pass
        return None
    with ThreadPoolExecutor(max_workers=config.get('discovery_workers',4)) as executor:
        return [m for m in executor.map(resolve,ids) if m]


def simkl_candidates(backend,preferred,config):
    """Official public feed needs no credentials; never use SIMKL IDs as TMDB IDs."""
    rows=entries(backend.request(FEED_URL,HEADERS));ids=[]
    for row in rows[:config.get('candidate_limit',40)]:
        if row.get('type','movie') not in ('movie','movies'):continue
        external=row.get('ids',{})
        if not isinstance(external,dict):continue
        mid=external.get('tmdb')
        if isinstance(mid,str) and mid.isascii() and mid.isdigit():mid=int(mid)
        try:
            if type(mid) is not int or mid<=0:
                imdb=external.get('imdb','')
                if not isinstance(imdb,str) or not imdb.startswith('tt') or not imdb[2:].isascii() or not imdb[2:].isdigit():continue
                found=backend.movie('find/'+imdb+'?external_source=imdb_id').get('movie_results',[])
                if len(found)!=1:continue
                mid=found[0].get('id')
            if type(mid) is int and mid>0 and mid not in ids and not excluded(config,mid):ids.append(mid)
        except Exception:continue
    candidates=resolve_ids(backend,ids,config)
    if ids and not candidates:raise RuntimeError('SIMKL candidates could not be resolved')
    return candidates


def director_candidates(backend,names,config):
    # Resolve exact, unambiguous public names; never infer a person's ID.
    def fetch(name):
        try:
            anchors=config.get('_director_anchor_ids',{}).get(name,[])[:2]
            if anchors:
                # Imported names may be translated. Resolve one unambiguous
                # director from a liked film, or the intersection of two films.
                people=None
                for mid in anchors[:2]:
                    detail=backend.movie(detail_path(mid));crew=(detail.get('credits') or {}).get('crew',[])
                    credited={p['id'] for p in crew if isinstance(p,dict) and p.get('job')=='Director' and type(p.get('id')) is int and p['id']>0}
                    people=credited if people is None else people.intersection(credited)
            else:
                data=backend.movie('search/person?'+urllib.parse.urlencode({'query':name,'include_adult':'false','language':'ru-RU','page':1}))
                people={p['id'] for p in data.get('results',[]) if isinstance(p,dict) and type(p.get('id')) is int and p['id']>0 and normalize(name) in {normalize(p.get('name')),normalize(p.get('original_name'))}}
            if len(people)!=1:return []
            person_id=next(iter(people))
            credits=backend.movie('person/'+str(person_id)+'/movie_credits?language=ru-RU')
            return [dict(m,_liked_directors=[name],_director_alias_ids={name:person_id}) for m in credits.get('crew',[]) if isinstance(m,dict) and m.get('job')=='Director' and type(m.get('id')) is int and m['id']>0 and not excluded(config,m['id'])][:80]
        except Exception:return []
    with ThreadPoolExecutor(max_workers=config.get('discovery_workers',4)) as executor:
        return [m for result in executor.map(fetch,names[:8]) for m in result]


def tmdb_candidates(backend, preferred, config):
    now=config.get('_now') or datetime.datetime.now(datetime.timezone.utc)
    query={'language':'ru-RU','include_adult':'false','include_video':'false',
           'primary_release_date.lte':now.date().isoformat(),'primary_release_date.gte':str(RULES['selection']['minimum_year'])+'-01-01','vote_count.gte':config['minimum_votes'],'without_genres':','.join(map(str,RULES['selection']['always_excluded_genres']))}
    strategies=[{'sort_by':'popularity.desc','with_genres':27},{'sort_by':'vote_average.desc','with_genres':27},
                {'sort_by':'popularity.desc','with_keywords':4565}]
    if config.get('_evidence_routes'):
        strategies.extend([{'sort_by':'popularity.desc','with_keywords':4458},{'sort_by':'vote_count.desc','with_keywords':4458},
                           {'sort_by':'vote_average.desc','with_genres':27,'vote_count.gte':1000},
                           {'sort_by':'vote_average.desc','with_keywords':'4565|4458','vote_count.gte':1000}])
        # Audience count is a separate discovery route, not a higher minimum
        # or a ranking override. Decades expose unseen films behind the head
        # of the global lists while every existing route remains available.
        strategies.extend([{'sort_by':'vote_count.desc','with_genres':27},
                           {'sort_by':'vote_count.desc','with_keywords':4565}])
        minimum=RULES['selection']['minimum_year']
        for year in range(minimum,now.year+1,10):
            strategies.append({'sort_by':'vote_count.desc','with_genres':27,
                               'primary_release_date.gte':str(year)+'-01-01',
                               'primary_release_date.lte':min(now.date().isoformat(),str(year+9)+'-12-31')})
    if config.get('_evidence_routes'):
        for year in range(now.year,max(RULES['selection']['minimum_year']-1,now.year-12),-2):
            for order in ('vote_count.desc','popularity.desc'):
                strategies.append({'sort_by':order,'with_genres':27,
                    'primary_release_date.gte':str(max(RULES['selection']['minimum_year'],year-1))+'-01-01',
                    'primary_release_date.lte':min(now.date().isoformat(),str(year)+'-12-31')})
    # Broad sci-fi/thriller lists waste the shortlist on unrelated family/adventure films.
    strategies.extend(dict(sort_by='popularity.desc',**({'with_genres':'27,53'} if genre==53 else {'with_genres':878,'with_keywords':4565})) for genre in preferred[:3] if genre in (53,878))
    # Separate established audiences in the user's liked language from crowded
    # global lists. These are additional routes; the 100-vote fallback remains.
    audience_languages=[lang for lang in config.get('_preferred_languages',[])[:2]
                        if isinstance(lang,str)and len(lang)==2 and lang.isascii()and lang.isalpha()]
    market=[]
    without_comedy=','.join(map(str,[*RULES['selection']['always_excluded_genres'],35]))
    for lang in audience_languages:
        for order in ('vote_count.desc','popularity.desc','vote_average.desc'):
            market.append({'sort_by':order,'with_genres':27,'with_original_language':lang,
                           'vote_count.gte':1000,'without_genres':without_comedy})
        for year in range(RULES['selection']['minimum_year'],now.year+1,5):
            market.append({'sort_by':'vote_count.desc','with_genres':27,'with_original_language':lang,
                           'vote_count.gte':1000,'without_genres':without_comedy,
                           'primary_release_date.gte':str(year)+'-01-01',
                           'primary_release_date.lte':min(now.date().isoformat(),str(year+4)+'-12-31')})
    strategies=market+strategies
    broad_keys={tuple(sorted(strategy.items())) for strategy in strategies}
    companies=list(dict.fromkeys(c for c in config.get('_preferred_companies',[])[:6] if type(c) is int and c>0))
    actors=list(dict.fromkeys(c for c in config.get('_preferred_cast',[])[:4] if type(c) is int and c>0))
    round_number=config.get('_search_round',0)
    if companies:
        start=2*(round_number%max(1,(len(companies)+1)//2))
        strategies.extend({'sort_by':'vote_count.desc','with_genres':27,'with_companies':c} for c in companies[start:start+2])
    if actors:strategies.append({'sort_by':'vote_count.desc','with_genres':27,'with_cast':actors[round_number%len(actors)]})
    keyword_seeds=config.get('_preferred_keywords',[])[:12]
    keyword_groups=max(1,(len(keyword_seeds)+3)//4)
    keyword_start=4*(config.get('_search_round',0)%keyword_groups)
    strategies=[{'sort_by':'popularity.desc','with_genres':27,'with_keywords':keyword} for keyword in keyword_seeds[keyword_start:keyword_start+4]]+strategies
    groups=[g for g in config.get('_preferred_keyword_groups',[])[:4] if isinstance(g,list) and len(g)==2 and len(set(g))==2 and all(type(k) is int and k>0 for k in g)]
    strategies=[{'sort_by':'popularity.desc','with_genres':27,'with_keywords':','.join(map(str,g))} for g in groups]+strategies
    for year in config.get('_preferred_periods',[])[:2]:
        if type(year) is int and RULES['selection']['minimum_year']<=year<=now.year:
            strategies.append({'sort_by':'popularity.desc','with_genres':27,
                               'primary_release_date.gte':str(year)+'-01-01',
                               'primary_release_date.lte':min(now.date().isoformat(),str(year+4)+'-12-31')})
    # Budget actual new requests, not cached page-one probes. Broad popularity
    # and audience lists own a lane that narrow keyword routes cannot consume.
    unique={tuple(sorted(strategy.items())):strategy for strategy in strategies}
    strategies=list(unique.values())
    probes=['discover/movie?'+urllib.parse.urlencode({**query,**strategy,'page':1}) for strategy in strategies]
    broad=[i for i,s in enumerate(strategies) if tuple(sorted(s.items())) in broad_keys]
    personal=[i for i in range(len(probes)) if i not in broad]
    # Protect the ranked global audience lists from decade/theme proliferation.
    # They expose well-known unseen films before niche lists spend the budget.
    headline=[i for i in broad if strategies[i] in market or strategies[i] in
              [{'sort_by':order,**target} for order in ('popularity.desc','vote_count.desc')
               for target in ({'with_genres':27},{'with_keywords':4565},{'with_keywords':4458})]]
    secondary=[i for i in broad if i not in headline]
    count=config.get('pages',2);window=max(count,min(20,config.get('page_window',20)))
    limit=max(1,min(64,config.get('discovery_request_limit',24)))
    if count==1:limit=min(limit,len(probes))
    elif 'discovery_request_limit' not in config:limit=min(limit,len(probes)*count)
    ledger=config.get('_discovery_pages',{})
    totals=config.get('_discovery_totals')
    if totals is None:totals=ledger.setdefault('_totals',{})
    initial=[];requested=set();failed=set();request_count=0
    search_round=config.get('_search_round',0)
    slot=int((now.timestamp()-17*60)//3600)+config.get('_page_seed',0)
    def lookup(item):
        index,page=item;path=probes[index].rsplit('page=',1)[0]+'page='+str(page)
        try:
            data=backend.movie(path)
            if not isinstance(data,dict) or not isinstance(data.get('results'),list):return item,None
            return item,data
        except Exception:return item,None
    def page_for(index,explore=False):
        path=probes[index];seen=ledger.setdefault(path,set())
        total=totals.get(path)
        if total is None:
            return None if (index,1) in requested else 1
        if count==1:total=min(1,total)
        if explore and total>1:
            start=2+(slot*max(1,count-1))%(total-1)
            pages=list(range(start,total+1))+list(range(2,start))
        else:pages=range(1,total+1)
        return next((page for page in pages if page not in seen and (index,page) not in requested),None)
    def scan(indices,allowance,explore=False):
        nonlocal request_count
        if not indices:return
        # Several waves let page one's total_pages constrain every next request.
        # Successful pages only enter the ledger; a failed page is retried on a
        # later pass, without an infinite retry loop within the current pass.
        cursor=0;spent=0
        with ThreadPoolExecutor(max_workers=config.get('discovery_workers',4)) as executor:
            while spent<allowance and request_count<limit:
                batch=[]
                for _ in range(len(indices)):
                    index=indices[cursor%len(indices)];cursor+=1
                    if index in failed:continue
                    page=page_for(index,explore)
                    if page is not None:
                        batch.append((index,page));requested.add((index,page))
                    if len(batch)>=min(4,allowance-spent,limit-request_count):break
                if not batch:break
                for (index,page),data in executor.map(lookup,batch):
                    spent+=1;request_count+=1
                    if data is None:
                        failed.add(index);initial.append(None);continue
                    total=data.get('total_pages',window)
                    totals[probes[index]]=max(1,min(500,total)) if type(total) is int else window
                    ledger[probes[index]].add(page)
                    initial.append(annotate_query(data['results'],probes[index]))
    # Probe new routes once. Previously every refill charged the budget for
    # the same first pages even though the backend returned cached responses.
    new_routes=[i for i in broad+personal if totals.get(probes[i]) is None]
    new_routes.sort(key=lambda i:0 if 'with_companies' in strategies[i] or 'with_cast' in strategies[i] else 1 if i in headline else 2)
    if new_routes:
        with ThreadPoolExecutor(max_workers=config.get('discovery_workers',4)) as executor:
            items=[(i,1) for i in new_routes[:limit]]
            requested.update(items)
            for (index,page),data in executor.map(lookup,items):
                request_count+=1
                if data is None:
                    failed.add(index);initial.append(None);continue
                total=data.get('total_pages',window)
                totals[probes[index]]=max(1,min(500,total)) if type(total) is int else window
                ledger.setdefault(probes[index],set()).add(page)
                initial.append(annotate_query(data['results'],probes[index]))
    exploration=min(len(probes),max(1,limit//8)) if count>2 else 0
    sequential=max(request_count,limit-exploration)
    remaining=sequential-request_count
    broad_budget=remaining if not personal else int(remaining*.65)
    before=request_count
    headline_budget=int(broad_budget*.75)
    horror_headline=[i for i in headline if strategies[i].get('with_genres')==27]
    dystopia_headline=[i for i in headline if i not in horror_headline]
    first,second=(dystopia_headline,horror_headline) if config.get('_genre_priority',['horror'])[0]=='dystopian' else (horror_headline,dystopia_headline)
    scan(first,(headline_budget*3+3)//4)
    scan(second,headline_budget-(request_count-before))
    scan(first,headline_budget-(request_count-before))
    scan(secondary,broad_budget-(request_count-before))
    scan(headline,broad_budget-(request_count-before))
    scan(personal,sequential-request_count)
    # Short/exhausted personal lists return their unused slots to broad search.
    scan(broad,sequential-request_count)
    order=broad+personal
    if order:
        offset=search_round%len(order);order=order[offset:]+order[:offset]
    scan(order,limit-request_count,explore=True)
    stats=config.get('_discovery_stats')
    if isinstance(stats,dict):stats['requests']=stats.get('requests',0)+request_count
    paths=[]
    seeds=list(dict.fromkeys(mid for mid in config.get('_preferred_movie_ids',[])[:48] if type(mid) is int and mid>0))
    batch=max(1,min(12,config.get('_anchor_batch_size',6)))
    groups=max(1,(len(seeds)+batch-1)//batch);search_round=config.get('_search_round',0);start=batch*(search_round%groups)
    anchors=seeds[start:start+batch];page=1+search_round//groups
    paths.extend('movie/'+str(mid)+'/recommendations?language=ru-RU&page='+str(page) for mid in anchors)
    # Similar is a distinct content route. Rotate through every positive anchor
    # before deeper pages; broad popularity queries cannot replace these slots.
    if config.get('_include_similar'):
        paths.extend('movie/'+str(mid)+'/similar?language=ru-RU&page='+str(page) for mid in anchors)
    def fetch(path):
        try:
            data=backend.movie(path)
            if not isinstance(data,dict) or not isinstance(data.get('results'),list):return None
            rows=data['results']
            if path.startswith('movie/'):
                anchor=int(path.split('/')[1]);route='similar' if '/similar?' in path else 'recommendations'
                rows=[dict(m,_liked_anchor_ids=[anchor],_personal_routes=[route]) if isinstance(m,dict) else m for m in rows]
            return annotate_query(rows,path)
        except Exception:return None
    with ThreadPoolExecutor(max_workers=config.get('discovery_workers',4)) as executor:
        fetched=list(executor.map(fetch,paths))
    coverage=config.get('_anchor_coverage')
    if isinstance(coverage,set):
        coverage.update(int(path.split('/')[1]) for path,result in zip(paths,fetched)
                        if path.startswith('movie/') and isinstance(result,list))
    results=initial+fetched
    pool=[m for result in results if isinstance(result,list) for m in result
          if isinstance(m,dict) and not excluded(config,m.get('id'))]
    names=config.get('_preferred_directors',[])
    if names and search_round==0:pool.extend(director_candidates(backend,names,config))
    if results and all(result is None for result in results) and not pool:raise RuntimeError('TMDB discovery unavailable')
    return pool


def imdb_dataset_candidates(backend,preferred,config):
    """Retrieve known horror independently of TMDB genre tagging and OMDb quota."""
    from imdb_datasets import PublicImdbIndex
    from candidate_policy import valid_candidate
    index=getattr(backend,'imdb_index',None)
    if not isinstance(index,PublicImdbIndex)or index.metadata()is None:raise ValueError('Optional public index unavailable')
    now=config.get('_now')or datetime.datetime.now(datetime.timezone.utc)
    choices=index.candidates(RULES['selection']['minimum_year'],now.year,limit=3000)
    limit=max(1,min(240,config.get('candidate_limit',120)));bound=max(limit,min(1500,config.get('resolution_limit',1000)))
    result=[];attempted=0
    def fetch(entry):
        identity=entry[0]
        try:
            mapping=index.mapping([identity]);mid=mapping.get(identity)
            if mid is None:
                data=backend.movie('find/'+identity+'?external_source=imdb_id&language=ru-RU')
                found=data.get('movie_results')if isinstance(data,dict)else None
                if not isinstance(found,list)or len(found)!=1:return None
                mid=found[0].get('id')
            if type(mid)is not int or mid<=0 or excluded(config,mid):return None
            detail=backend.movie(detail_path(mid))
            if not isinstance(detail,dict)or detail.get('id')!=mid or detail.get('imdb_id')!=identity:return None
            index.record_mapping(identity,mid)
            detail=dict(detail);index.enrich([detail])
            if not valid_candidate(detail,config.get('minimum_votes',100),now.date()):return None
            if not detail.get('title')or type(detail.get('runtime'))not in(int,float)or detail['runtime']<=0:return None
            return detail
        except Exception:return None
    with ThreadPoolExecutor(max_workers=config.get('discovery_workers',4))as executor:
        for start in range(0,min(bound,len(choices)),40):
            wave=choices[start:min(start+40,bound)];attempted+=len(wave)
            result.extend(m for m in executor.map(fetch,wave)if m is not None)
            if len(result)>=limit:break
    stats=config.get('_discovery_stats')
    if isinstance(stats,dict):stats['imdbDatasetIdentities']=stats.get('imdbDatasetIdentities',0)+attempted
    return result[:limit]


def tmdb_id_feed(backend, preferred, config):
    """Future provider bridge: HTTPS JSON {tmdb_ids: [123, ...]}.

    Its upstream adapter must resolve IDs to TMDB, never equate IMDb IDs with TMDB.
    Secrets are referenced by environment variable name, never stored in config.
    """
    url = os.environ.get(config.get('url_env', ''), '')
    if urllib.parse.urlparse(url).scheme != 'https':
        raise ValueError('Feed requires HTTPS URL')
    headers = {}
    if config.get('token_env'):
        token = os.environ.get(config['token_env'])
        if not token:
            raise ValueError('Feed credential missing')
        headers['Authorization'] = 'Bearer ' + token
    result = backend.request(url, headers)
    ids = result.get('tmdb_ids', [])
    if not isinstance(ids, list):
        raise ValueError('Invalid feed')
    canonical=[i for i in dict.fromkeys(i for i in ids if type(i) is int and i>0) if not excluded(config,i)][:config.get('candidate_limit',40)]
    return resolve_ids(backend,canonical,config)


def trakt_candidates(backend, preferred, config):
    """Public trending/popular lists need Client ID only; all IDs resolve via TMDB."""
    key = ''.join(os.environ.get('TRAKT_CLIENT_ID', '').split())
    if not key or not all(c.isascii() and (c.isalnum() or c in '_-') for c in key):
        raise ValueError('Trakt Client ID missing or invalid')
    headers = {'trakt-api-version': '2', 'trakt-api-key': key,
               'Content-Type': 'application/json', 'User-Agent':'Nightshift/1.0'}
    limit = config.get('candidate_limit', 40)
    ids, successful = [], False
    for endpoint in ('trending', 'popular'):
        try:
            result = backend.request('https://api.trakt.tv/movies/' + endpoint +
                                     '?page=1&limit=' + str(min(100, max(1, (limit + 1) // 2))), headers)
            if not isinstance(result, list):
                raise ValueError('Invalid Trakt list')
            successful = True
        except Exception:
            continue
        for entry in result:
            if not isinstance(entry, dict):
                continue
            movie = entry.get('movie', entry)
            if not isinstance(movie, dict) or not isinstance(movie.get('ids'), dict):
                continue
            mid = movie['ids'].get('tmdb')
            if type(mid) is int and mid > 0 and mid not in ids and not excluded(config,mid):
                ids.append(mid)
    if not successful:
        raise RuntimeError('Trakt discovery unavailable')
    candidates=resolve_ids(backend,ids[:limit],config)
    if ids and not candidates:raise RuntimeError('Trakt candidates could not be resolved')
    return candidates


ADAPTERS = {'tmdb_discover': tmdb_candidates, 'imdb_dataset':imdb_dataset_candidates,'tmdb_id_feed': tmdb_id_feed, 'trakt': trakt_candidates, 'simkl': simkl_candidates}


def discover(backend, preferred, config):
    pool, statuses = {}, []
    config.setdefault('_discovery_pages',{})
    config.setdefault('_discovery_totals',{})
    config.setdefault('_discovery_stats',{})
    for source in config['sources']:
        if not source.get('enabled', False):
            continue
        name = source['id']
        try:
            options=dict(source,minimum_votes=config['minimum_votes'],
                         page_window=config.get('page_window',20),
                         discovery_workers=config.get('discovery_workers',4),
                         discovery_request_limit=config.get('discovery_request_limit',24))
            for key,default in [('_excluded_ids',set()),('_now',None),('_page_seed',0),('_search_round',0),
                                ('_preferred_movie_ids',[]),('_include_similar',False),('_evidence_routes',False),
                                ('_anchor_batch_size',6),('_preferred_keywords',[]),('_preferred_keyword_groups',[]),
                                ('_preferred_periods',[]),('_preferred_directors',[]),('_preferred_companies',[]),
                                ('_preferred_cast',[]),('_preferred_languages',[]),('_director_anchor_ids',{}),('_discovery_pages',{}),
                                ('_discovery_totals',{}),('_discovery_stats',{}),('_anchor_coverage',set()),
                                ('_genre_priority',['horror','dystopian'])]:
                options[key]=config.get(key,default)
            candidates=ADAPTERS[source['adapter']](backend,preferred,options)
            valid = [m for m in candidates if isinstance(m,dict) and type(m.get('id')) is int and m['id'] > 0 and not excluded(config,m['id'])]
            for movie in valid:
                mid = movie['id']
                if mid not in pool:
                    pool[mid] = dict(movie, discovery_sources=[])
                for field in ('_liked_anchor_ids','_liked_directors','_matched_theme_groups','_personal_routes'):
                    if movie.get(field):pool[mid][field]=list(dict.fromkeys(pool[mid].get(field,[])+movie[field]))
                if movie.get('_director_alias_ids'):pool[mid].setdefault('_director_alias_ids',{}).update(movie['_director_alias_ids'])
                if name not in pool[mid]['discovery_sources']:
                    pool[mid]['discovery_sources'].append(name)
            statuses.append({'source': name, 'status': 'ok', 'candidates': len({m['id'] for m in valid})})
        except Exception:
            # No provider URLs, responses, or tokens in logs.
            statuses.append({'source': name, 'status': 'failed', 'candidates': 0})
    if not any(s['status'] == 'ok' for s in statuses):
        raise RuntimeError('No discovery source available')
    return list(pool.values()), statuses


def hourly_limit(config, ranked):
    # Grow only for sources contributing eligible candidates, not merely enabled APIs.
    active = {s for _, movie, _ in ranked for s in movie.get('discovery_sources', [])}
    return min(config['maximum_per_hour'], config['base_per_hour'] +
               max(0, len(active) - 1) * config['extra_per_source'])
