"""Refresh verified metadata; retain the last successful values on provider errors."""
import json, os, datetime, urllib.request, urllib.parse, urllib.error
from pathlib import Path
from simkl_source import FEED_URL, HEADERS, entries, credential_url, client_id, auth_diagnostic, api_requirements
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
        markers = ('origin','cors','permission','approved','disabled','invalid','client','api key','cloudflare','blocked','policy','vip','subscription','forbidden','denied','rate limit','error code: 1020','error code: 1015')
        result['reasonHints'] = [marker for marker in markers if marker in body]
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
        for agent, origin in ((None,None), ('Nightshift/1.0',None), ('Nightshift/1.0','https://arturmal2805-netizen.github.io')):
            try:
                headers = {'trakt-api-version':'2','trakt-api-key':trakt_key,'Content-Type':'application/json'}
                if agent: headers['User-Agent'] = agent
                if origin: headers['Origin'] = origin
                result = request('https://api.trakt.tv/movies/trending?limit=1', headers)
                if not isinstance(result, list): raise ValueError('Invalid Trakt response')
                state.update(status='ok', lastSuccess=now)
                if origin: state['originRequired'] = True
                else: state.pop('originRequired', None)
                state.pop('httpStatus', None)
                state.pop('diagnostic', None)
                break
            except Exception as error:
                diagnostic = trakt_failure(error)
                state['diagnostic'] = diagnostic
                if diagnostic.get('httpStatus'): state['httpStatus'] = diagnostic['httpStatus']
                if agent is None: state['baselineDiagnostic'] = diagnostic
    if trakt_key and state['status'] != 'ok':
        checks = {}
        for name, endpoint, credential in [('popular','popular',trakt_key),('withoutKey','trending',None)]:
            try:
                headers = {'trakt-api-version':'2','User-Agent':'Nightshift/1.0','Content-Type':'application/json'}
                if credential: headers['trakt-api-key'] = credential
                value = request('https://api.trakt.tv/movies/'+endpoint+'?limit=1', headers)
                if not isinstance(value, list): raise ValueError('Invalid response')
                checks[name] = {'status':'ok'}
                if credential:
                    state.update(status='ok', lastSuccess=now, verifiedEndpoint=endpoint)
                    state.pop('httpStatus',None)
                    state.pop('diagnostic',None)
            except Exception as error:
                checks[name] = trakt_failure(error)
        state['diagnosticChecks'] = checks
    else:
        state.pop('diagnosticChecks', None)
    states['trakt'] = state
    state = dict(states.get('simkl', {}), status='error', lastAttempt=now)
    for field in ('httpStatus', 'credentialHttpStatus', 'credentialStatus', 'credentialDiagnostic'):
        state.pop(field, None)
    try:
        rows = entries(request(FEED_URL, HEADERS))
        state.update(status='ok', lastSuccess=now, available=len(rows))
    except Exception as error:
        if isinstance(error, urllib.error.HTTPError): state['httpStatus'] = error.code
    key = environ.get('SIMKL_CLIENT_ID', '')
    state['credentialStatus'] = 'not_configured' if not key.strip() else 'error'
    if key.strip():
        try:
            value = request(credential_url(key), dict(HEADERS, **{'simkl-api-key': client_id(key)}))
            if not isinstance(value, dict) or type(value.get('id')) is not int or value['id'] <= 0 or not isinstance(value.get('simkl'), dict) or value.get('error'):
                raise ValueError('Invalid SIMKL credential response')
            state['credentialStatus'] = 'ok'
        except Exception as error:
            if isinstance(error, urllib.error.HTTPError): state['credentialHttpStatus'] = error.code
            state['credentialDiagnostic'] = auth_diagnostic(error)
    # Inspect current API contracts separately from frozen Apiary documentation.
    if state.get('credentialHttpStatus') == 401 and not state.get('apiRequirements'):
        try:
            state['apiRequirements'] = api_requirements(request('https://api.simkl.org/openapi.json', HEADERS))
            state['apiDocumentationStatus'] = 'loaded'
        except Exception as error:
            state['apiDocumentationStatus'] = 'unavailable'
            if isinstance(error, urllib.error.HTTPError): state['apiDocumentationHttpStatus'] = error.code
    states['simkl'] = state
    return snapshot

if __name__ == '__main__':
    old=json.loads(TARGET.read_text()) if TARGET.exists() else {'films':{},'sources':{}}
    result=refresh(old)
    temporary=TARGET.with_suffix('.tmp')
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(TARGET)
    for name,state in result['sources'].items():
        print(name,state['status'],'imported:',state.get('imported',0),'failed:',state.get('failed',0))
        if name == 'trakt' and state.get('diagnostic'):
            print('Trakt check:', state['diagnostic'].get('httpStatus', 'no HTTP response'), state['diagnostic']['category'])
        if name == 'simkl':
            print('SIMKL feed:', state['status'], 'Client ID:', state.get('credentialStatus'),
                  'HTTP:', state.get('credentialHttpStatus', state.get('httpStatus', 'none')))
