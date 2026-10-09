"""SIMKL public trending feed and optional Client ID verification."""
import urllib.parse

FEED_URL = 'https://data.simkl.in/discover/trending/movies/today_100.json'
HEADERS = {'User-Agent': 'Nightshift/1.0', 'Accept': 'application/json'}


def client_id(value):
    key = ''.join(value.split())
    if not key or key.startswith('simkl_cs_') or not all(c.isascii() and (c.isalnum() or c in '_-') for c in key):
        raise ValueError('SIMKL Client ID missing or invalid; Client Secret is not a Client ID')
    return key


def entries(value):
    if isinstance(value, dict):
        value = next((value[k] for k in ('movies', 'items', 'data') if isinstance(value.get(k), list)), None)
    if not isinstance(value, list):
        raise ValueError('Invalid SIMKL trending response')
    return [entry.get('movie', entry) for entry in value if isinstance(entry, dict)
            and isinstance(entry.get('movie', entry), dict)]


def credential_url(value):
    return 'https://api.simkl.com/ratings?' + urllib.parse.urlencode(
        {'tmdb': 157336, 'type': 'movie', 'fields': 'simkl', 'client_id': client_id(value)})
