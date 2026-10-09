"""Discovery adapters return canonical TMDB IDs; metadata providers do not count."""
import os
import urllib.parse
from simkl_source import FEED_URL, HEADERS, entries


def simkl_candidates(backend, preferred, config):
    """Official public feed needs no credentials; never use SIMKL IDs as TMDB IDs."""
    rows = entries(backend.request(FEED_URL, HEADERS))
    limit = config.get('candidate_limit', 40)
    ids, candidates = set(), []
    # Bound lookups even when records are malformed or cannot be matched.
    for row in rows[:limit]:
        if row.get('type', 'movie') not in ('movie', 'movies'):
            continue
        external = row.get('ids', {})
        if not isinstance(external, dict):
            continue
        mid = external.get('tmdb')
        if isinstance(mid, str) and mid.isascii() and mid.isdigit():
            mid = int(mid)
        try:
            if type(mid) is not int or mid <= 0:
                imdb = external.get('imdb', '')
                if not isinstance(imdb, str) or not imdb.startswith('tt') or not imdb[2:].isascii() or not imdb[2:].isdigit():
                    continue
                found = backend.movie('find/' + imdb + '?external_source=imdb_id').get('movie_results', [])
                if len(found) != 1:
                    continue
                mid = found[0].get('id')
            if type(mid) is not int or mid <= 0 or mid in ids:
                continue
            ids.add(mid)
            detail = backend.movie(f'movie/{mid}?language=ru-RU')
            if not isinstance(detail, dict) or detail.get('id') != mid:
                continue
            candidates.append(dict(detail, genre_ids=[g['id'] for g in detail.get('genres', [])]))
        except Exception:
            continue
    if rows and not candidates:
        raise RuntimeError('SIMKL candidates could not be resolved')
    return candidates


def tmdb_candidates(backend, preferred, config):
    query = {'language': 'ru-RU', 'include_adult': 'false',
             'sort_by': 'popularity.desc', 'vote_count.gte': config['minimum_votes']}
    candidates = []
    for genres in ['', '|'.join(map(str, preferred))] if preferred else ['']:
        for page in range(1, config.get('pages', 2) + 1):
            params = dict(query, page=page)
            if genres:
                params['with_genres'] = genres
            candidates.extend(backend.movie('discover/movie?' + urllib.parse.urlencode(params)).get('results', []))
    return candidates


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
    candidates = []
    for mid in list(dict.fromkeys(i for i in ids if type(i) is int and i > 0))[:config.get('candidate_limit', 40)]:
        detail = backend.movie(f'movie/{mid}?language=ru-RU')
        detail['genre_ids'] = [g['id'] for g in detail.get('genres', [])]
        candidates.append(detail)
    return candidates


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
            if type(mid) is int and mid > 0 and mid not in ids:
                ids.append(mid)
    if not successful:
        raise RuntimeError('Trakt discovery unavailable')
    # Each list supplies at most half the budget; duplicates are resolved once.
    candidates = []
    for mid in ids[:limit]:
        try:
            detail = backend.movie(f'movie/{mid}?language=ru-RU')
            if not isinstance(detail, dict) or detail.get('id') != mid:
                continue
            detail = dict(detail, genre_ids=[g['id'] for g in detail.get('genres', [])])
            candidates.append(detail)
        except Exception:
            continue
    if ids and not candidates:
        raise RuntimeError('Trakt candidates could not be resolved')
    return candidates


ADAPTERS = {'tmdb_discover': tmdb_candidates, 'tmdb_id_feed': tmdb_id_feed, 'trakt': trakt_candidates, 'simkl': simkl_candidates}


def discover(backend, preferred, config):
    pool, statuses = {}, []
    for source in config['sources']:
        if not source.get('enabled', False):
            continue
        name = source['id']
        try:
            candidates = ADAPTERS[source['adapter']](backend, preferred, dict(source, minimum_votes=config['minimum_votes']))
            valid = [m for m in candidates if type(m.get('id')) is int and m['id'] > 0]
            for movie in valid:
                mid = movie['id']
                if mid not in pool:
                    pool[mid] = dict(movie, discovery_sources=[])
                if name not in pool[mid]['discovery_sources']:
                    pool[mid]['discovery_sources'].append(name)
            statuses.append({'source': name, 'status': 'ok', 'candidates': len(valid)})
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
