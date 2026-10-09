"""Discovery adapters return canonical TMDB IDs; metadata providers do not count."""
import os
import urllib.parse


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


ADAPTERS = {'tmdb_discover': tmdb_candidates, 'tmdb_id_feed': tmdb_id_feed}


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
