"""Refresh verified metadata; retain the last successful values on provider errors."""
import json, os, datetime, urllib.request, urllib.parse
from pathlib import Path
TARGET = Path(__file__).resolve().parents[1] / 'data/catalog.json'
# Stable TMDB identities for the curated catalog; never match by title alone.
IDS = {1:157336,2:120467,3:693134,4:313369,5:546554,6:508442,7:329865,8:194,9:76341,10:370755,11:105,12:76}

def get_json(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=25) as response:
        return json.load(response)

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
    return snapshot

if __name__ == '__main__':
    old=json.loads(TARGET.read_text()) if TARGET.exists() else {'films':{},'sources':{}}
    result=refresh(old)
    temporary=TARGET.with_suffix('.tmp')
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(TARGET)
    for name,state in result['sources'].items():
        print(name,state['status'],'imported:',state.get('imported',0),'failed:',state.get('failed',0))
