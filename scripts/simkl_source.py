"""SIMKL public trending feed and optional Client ID verification."""
import urllib.parse
import urllib.error

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


def auth_diagnostic(error):
    """Record only whitelisted error hints, never body text or credentials."""
    result = {'category': 'network_or_response'}
    if isinstance(error, urllib.error.HTTPError):
        result = {'httpStatus': error.code, 'category': 'authentication_rejected' if error.code == 401 else 'http_error'}
        try:
            body = error.read(8192).decode('utf-8', errors='replace').lower()
            result['reasonHints'] = [hint for hint in ('token', 'oauth', 'bearer', 'client_id', 'invalid', 'expired', 'missing', 'required', 'app-name', 'app-version', 'verified', 'revoked', 'auth v2') if hint in body]
        except Exception:
            pass
    return result


def api_requirements(spec):
    """Public documentation summary; fetched without any app credentials."""
    paths = spec.get('paths', {})
    get = paths.get('/ratings', {}).get('get', {})
    if not get:
        raise ValueError('SIMKL ratings documentation missing')
    return {'security': get.get('security', spec.get('security', [])),
            'parameters': [{'name': p.get('name'), 'in': p.get('in'), 'required': p.get('required', False), 'description': p.get('description', '')[:800]} for p in get.get('parameters', [])],
            'description': get.get('description', '')[:2500],
            'securitySchemes': {k: {'type': v.get('type'), 'scheme': v.get('scheme'), 'name': v.get('name'), 'in': v.get('in')} for k, v in spec.get('components', {}).get('securitySchemes', {}).items()}}
