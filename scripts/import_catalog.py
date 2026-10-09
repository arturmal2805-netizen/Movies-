"""Refresh verified metadata; retain the last successful values on provider errors."""
import json, os, datetime, urllib.request, urllib.parse, urllib.error
from pathlib import Path
TARGET = Path(__file__).resolve().parents[1] / 'data/catalog.json'
# Stable TMDB identities for the curated catalog; never match by title alone.
IDS = {1:157336,2:120467,3:693134,4:313369,5:546554,6:508442,7:329865,8:194,9:76341,10:370755,11:105,12:76}

def get_json(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=25) as response:
        return json.load(response)

def trakt_failure(error):
    """Classify a bounded response; never persist its body, headers, URL or keys."""
    if not isinstance(error, urllib.error.HTTPError):
        return {'category':'network_or_response'}
    result = {'httpStatus':error.code, 'category':'http_error'}
    try:
        body = error.read(8192).decode('utf-8', errors='replace').lower()
        headers = error.headers or {}
        html = 'text/html' in headers.get('Content-Type','').lower() or '<html' in body or '<!doctype html' in body
        result['responseType'] = 'html' if html else 'json' if 'application/json' in headers.get('Content-Type','').lower() else 'text'
        if headers.get('cf-mitigated','').lower() == 'challenge' or html and any(marker in body for marker in ('cloudflare','just a moment','attention required','you have been blocked')):
            result['category'] = 'edge_security_block'
        elif any(marker in body for marker in ('invalid api key','invalid_api_key','invalid client','invalid_client')):
            result['category'] = 'invalid_client_id'
        elif any(marker in body for marker in ('vip required','requires vip','subscription required','api use policy','application is not approved','app is not approved','application has been disabled')):
            result['category'] = 'application_access_restricted'
        elif error.code == 401:
            result['category'] = 'authentication_rejected'
        elif error.code == 403:
            result['category'] = 'access_forbidden'
        elif error.code == 429:
            result['category'] = 'rate_limited'
    except Exception:
        pass
    return result

def refresh(snapshot, request=get_json, environ=None, now=None):
    environ = os.environ if environ is None else environ
    now = now or datetime.datetime.now(datetime.timezone.utc).isoformat()
    snapshot = json.loads(json.dumps(snapshot))
    snapshot.update(schemaVersion=1, checkedAt=now)
    records = snapshot.setdefault('films', {})
    states = snapshot.setdefault('sources', {})
    token, key = environ.get('TMDB_ACCESS_TOKEN'), environ.get('OMDB_API_KEY')
    successes = {'tmdb':0,'imdb':0}
    failures = {'tmdb':0,'imdb':0}
    for film_id, tmdb_id in IDS.items():
        record = records.setdefault(str(film_id), {})
        if token:
            try:
                movie = request(f'https://api.themoviedb.org/3/movie/{tmdb_id}', {'Authorization':f'Bearer {token}'})
                if movie.get('id') != tmdb_id: raise ValueError('Identity mismatch')
                poster, popularity = movie.get('poster_path'), movie.get('popularity')
                if not poster or not isinstance(popularity, (int,float)): raise ValueError('Incomplete metadata')
                record.update(poster=f'https://image.tmdb.org/t/p/w500{poster}',popularity=popularity,tmdbUpdatedAt=now,tmdbId=tmdb_id)
                if movie.get('imdb_id'): record['imdbId'] = movie['imdb_id']
                successes['tmdb'] += 1
            except Exception:
                # Do not log request URLs, headers, credentials or raw provider errors.
                failures['tmdb'] += 1
        if key and record.get('imdbId'):
            try:
                result = request('https://www.omdbapi.com/?'+urllib.parse.urlencode({'apikey':key,'i':record['imdbId']}))
                rating = float(result['imdbRating'])
                if result.get('imdbID') != record['imdbId'] or not 0 <= rating <= 10: raise ValueError('Invalid rating')
                record.update(imdb=rating,imdbUpdatedAt=now)
                # OMDb's Rotten Tomatoes rating is NOT guaranteed to be Popcornmeter.
                successes['imdb'] += 1
            except Exception:
                failures['imdb'] += 1
        elif key:
            failures['imdb'] += 1
    for provider, credential in [('tmdb',token),('imdb',key)]:
        previous = states.get(provider,{})
        state = dict(previous)
        state.update(status='not_connected' if not credential else 'ok' if successes[provider]==len(IDS) else 'degraded' if successes[provider] else 'error',lastAttempt=now,imported=successes[provider],failed=failures[provider])
        if successes[provider]: state['lastSuccess']=now
        states[provider]=state
    # Public provider health contains no user data or credentials.
    trakt_key = ''.join(environ.get('TRAKT_CLIENT_ID', '').split())
    previous = states.get('trakt', {})
    state = dict(previous, status='not_connected' if not trakt_key else 'error', lastAttempt=now)
    for field in ('httpStatus','diagnostic','baselineDiagnostic'):
        state.pop(field, None)
    if trakt_key:
        # First preserve evidence from the original request, then test explicit app identification.
        for agent in (None, 'Nightshift/1.0'):
            try:
                headers = {'trakt-api-version':'2','trakt-api-key':trakt_key,'Content-Type':'application/json'}
                if agent: headers['User-Agent'] = agent
                result = request('https://api.trakt.tv/movies/trending?limit=1', headers)
                if not isinstance(result, list): raise ValueError('Invalid Trakt response')
                state.update(status='ok', lastSuccess=now)
                state.pop('httpStatus', None)
                state.pop('diagnostic', None)
                break
            except Exception as error:
                diagnostic = trakt_failure(error)
                state['diagnostic'] = diagnostic
                if diagnostic.get('httpStatus'): state['httpStatus'] = diagnostic['httpStatus']
                if agent is None: state['baselineDiagnostic'] = diagnostic
    states['trakt'] = state
    return snapshot

if __name__ == '__main__':
    old=json.loads(TARGET.read_text()) if TARGET.exists() else {'films':{},'sources':{}}
    result=refresh(old)
    temporary=TARGET.with_suffix('.tmp')
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(TARGET)
    for name,state in result['sources'].items():
        print(name,state['status'],'imported:',state.get('imported',0),'failed:',state.get('failed',0))
