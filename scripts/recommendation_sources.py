"""Discovery adapters return canonical TMDB IDs; metadata providers do not count."""
import os
import datetime
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
from simkl_source import FEED_URL, HEADERS, entries
from movie_features import genres,RULES,normalize

def detail_path(mid):return f'movie/{mid}?language=ru-RU&append_to_response=keywords,credits'

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
            if len(anchors)==2:
                # Imported display names may be translated. Two known liked films
                # must share exactly one credited director; no name guessing.
                people=None
                for mid in anchors:
                    detail=backend.movie(detail_path(mid));crew=(detail.get('credits') or {}).get('crew',[])
                    credited={p['id'] for p in crew if isinstance(p,dict) and p.get('job')=='Director' and type(p.get('id')) is int and p['id']>0}
                    people=credited if people is None else people.intersection(credited)
            else:
                data=backend.movie('search/person?'+urllib.parse.urlencode({'query':name,'include_adult':'false','language':'ru-RU','page':1}))
                people={p['id'] for p in data.get('results',[]) if isinstance(p,dict) and type(p.get('id')) is int and p['id']>0 and normalize(name) in {normalize(p.get('name')),normalize(p.get('original_name'))}}
            if len(people)!=1:return []
            credits=backend.movie('person/'+str(next(iter(people)))+'/movie_credits?language=ru-RU')
            return [dict(m,_liked_directors=[name]) for m in credits.get('crew',[]) if isinstance(m,dict) and m.get('job')=='Director' and type(m.get('id')) is int and m['id']>0 and not excluded(config,m['id'])][:80]
        except Exception:return []
    with ThreadPoolExecutor(max_workers=config.get('discovery_workers',4)) as executor:
        return [m for result in executor.map(fetch,names[:4]) for m in result]


def tmdb_candidates(backend, preferred, config):
    now=config.get('_now') or datetime.datetime.now(datetime.timezone.utc)
    query={'language':'ru-RU','include_adult':'false','include_video':'false',
           'primary_release_date.lte':now.date().isoformat(),'primary_release_date.gte':str(RULES['selection']['minimum_year'])+'-01-01','vote_count.gte':config['minimum_votes'],'without_genres':','.join(map(str,RULES['selection']['always_excluded_genres']))}
    strategies=[{'sort_by':'popularity.desc','with_genres':27},{'sort_by':'vote_average.desc','with_genres':27},
                {'sort_by':'popularity.desc','with_keywords':4565}]
    # Broad sci-fi/thriller lists waste the shortlist on unrelated family/adventure films.
    strategies.extend(dict(sort_by='popularity.desc',**({'with_genres':'27,53'} if genre==53 else {'with_genres':878,'with_keywords':4565})) for genre in preferred[:3] if genre in (53,878))
    strategies=[{'sort_by':'popularity.desc','with_genres':27,'with_keywords':keyword} for keyword in config.get('_preferred_keywords',[])[:4]]+strategies
    count=config.get('pages',2);window=max(count,min(20,config.get('page_window',20)))
    slot=int((now.timestamp()-17*60)//3600)+config.get('_page_seed',0)
    # Keep page 1 for fresh hits; rotate deeper pages so an exhausted first page is not the whole catalog.
    pages=[1]+[2+(slot*(count-1)+i)%(window-1) for i in range(count-1)]
    paths=['discover/movie?'+urllib.parse.urlencode(dict(query,**strategy,page=page)) for strategy in strategies for page in pages][:24]
    seeds=[mid for mid in config.get('_preferred_movie_ids',[])[:12] if type(mid) is int and mid>0]
    groups=max(1,(len(seeds)+5)//6);search_round=config.get('_search_round',0);start=6*(search_round%groups)
    paths.extend('movie/'+str(mid)+'/recommendations?language=ru-RU&page='+str(1+search_round//groups) for mid in seeds[start:start+6])
    def fetch(path):
        try:
            data=backend.movie(path)
            if not isinstance(data,dict) or not isinstance(data.get('results'),list):return None
            rows=data['results']
            if path.startswith('movie/'):
                anchor=int(path.split('/')[1]);rows=[dict(m,_liked_anchor_ids=[anchor]) if isinstance(m,dict) else m for m in rows]
            if urllib.parse.parse_qs(urllib.parse.urlsplit(path).query).get('with_keywords')==['4565']:rows=[dict(m,_discovery_category='dystopian') if isinstance(m,dict) else m for m in rows]
            return rows
        except Exception:return None
    with ThreadPoolExecutor(max_workers=config.get('discovery_workers',4)) as executor:
        results=list(executor.map(fetch,paths))
    pool=[m for result in results if isinstance(result,list) for m in result
          if isinstance(m,dict) and not excluded(config,m.get('id'))]
    names=config.get('_preferred_directors',[])
    if names and search_round==0:pool.extend(director_candidates(backend,names,config))
    if all(result is None for result in results) and not pool:raise RuntimeError('TMDB discovery unavailable')
    return pool


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


ADAPTERS = {'tmdb_discover': tmdb_candidates, 'tmdb_id_feed': tmdb_id_feed, 'trakt': trakt_candidates, 'simkl': simkl_candidates}


def discover(backend, preferred, config):
    pool, statuses = {}, []
    for source in config['sources']:
        if not source.get('enabled', False):
            continue
        name = source['id']
        try:
            candidates = ADAPTERS[source['adapter']](backend, preferred, dict(source, minimum_votes=config['minimum_votes'], _excluded_ids=config.get('_excluded_ids',set()), _now=config.get('_now'), _page_seed=config.get('_page_seed',0), _search_round=config.get('_search_round',0), _preferred_movie_ids=config.get('_preferred_movie_ids',[]), _preferred_keywords=config.get('_preferred_keywords',[]), _preferred_directors=config.get('_preferred_directors',[]), _director_anchor_ids=config.get('_director_anchor_ids',{}), page_window=config.get('page_window',20), discovery_workers=config.get('discovery_workers',4)))
            valid = [m for m in candidates if isinstance(m,dict) and type(m.get('id')) is int and m['id'] > 0 and not excluded(config,m['id'])]
            for movie in valid:
                mid = movie['id']
                if mid not in pool:
                    pool[mid] = dict(movie, discovery_sources=[])
                for field in ('_liked_anchor_ids','_liked_directors'):
                    if movie.get(field):pool[mid][field]=list(dict.fromkeys(pool[mid].get(field,[])+movie[field]))
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
