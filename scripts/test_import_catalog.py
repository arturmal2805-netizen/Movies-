import unittest
from import_catalog import refresh, IDS, trakt_failure
class ImportTests(unittest.TestCase):
 def test_missing_keys_report_disconnected(self):
  value=refresh({'films':{},'sources':{}},environ={},now='2026-10-09T10:00:00Z')
  self.assertEqual(value['sources']['tmdb']['status'],'not_connected')
 def test_outage_preserves_snapshot(self):
  def fail(*args): raise TimeoutError()
  value=refresh({'films':{'1':{'popularity':123,'poster':'cached.jpg'}},'sources':{}},request=fail,environ={'TMDB_ACCESS_TOKEN':'test'})
  self.assertEqual(value['films']['1']['popularity'],123)
  self.assertEqual(value['sources']['tmdb']['status'],'error')
 def test_success_and_no_popcornmeter_substitution(self):
  def response(url,headers=None):
   if 'themoviedb' in url:return {'id':int(url.rsplit('/',1)[1]),'poster_path':'/poster.jpg','popularity':34.5,'imdb_id':'tt123'}
   return {'imdbID':'tt123','imdbRating':'8.1','Ratings':[{'Source':'Rotten Tomatoes','Value':'95%'}]}
  value=refresh({'films':{},'sources':{}},request=response,environ={'TMDB_ACCESS_TOKEN':'test','OMDB_API_KEY':'test'})
  self.assertEqual(value['sources']['tmdb']['imported'],len(IDS))
  self.assertEqual(value['films']['1']['imdb'],8.1)
  self.assertNotIn('popcornmeter',value['films']['1'])

 def test_trakt_health_confirms_response_without_adding_films(self):
  calls=[]
  def response(url,headers):
   calls.append((url,headers));return []
  value=refresh({'films':{},'sources':{}},request=response,environ={'TRAKT_CLIENT_ID':' fake-\nclient '},now='2026-10-09T10:00:00Z')
  self.assertEqual(value['sources']['trakt']['status'],'ok')
  self.assertEqual(value['sources']['trakt']['lastSuccess'],'2026-10-09T10:00:00Z')
  self.assertEqual(calls[0][1]['trakt-api-key'],'fake-client')
  self.assertNotIn('fake-client',str(value))
 def test_trakt_failure_reports_safe_status_and_preserves_last_success(self):
  import urllib.error
  def fail(url,headers):raise urllib.error.HTTPError(url,401,'private-key',{},None)
  value=refresh({'films':{},'sources':{'trakt':{'status':'ok','lastSuccess':'2026-10-09T09:00:00Z'}}},request=fail,environ={'TRAKT_CLIENT_ID':'fake-client'},now='2026-10-09T10:00:00Z')
  self.assertEqual(value['sources']['trakt']['status'],'error')
  self.assertEqual(value['sources']['trakt']['httpStatus'],401)
  self.assertEqual(value['sources']['trakt']['lastSuccess'],'2026-10-09T09:00:00Z')
  self.assertNotIn('private-key',str(value))
  self.assertNotIn('fake-client',str(value))
 def test_trakt_invalid_response_cannot_confirm_connection(self):
  value=refresh({'films':{},'sources':{}},request=lambda *_:{'error':'private-error'},environ={'TRAKT_CLIENT_ID':'fake-client'})
  self.assertEqual(value['sources']['trakt']['status'],'error')
  self.assertNotIn('lastSuccess',value['sources']['trakt'])

 def test_cloudflare_block_is_classified_without_leaking_response(self):
  import urllib.error,io
  error=urllib.error.HTTPError('https://api.trakt.tv/private',403,'private-key',{'Content-Type':'text/html','cf-mitigated':'challenge'},io.BytesIO(b'<html>Cloudflare private-key</html>'))
  result=trakt_failure(error)
  self.assertEqual(result['category'],'edge_security_block')
  self.assertEqual(result['responseType'],'html')
  self.assertNotIn('private-key',str(result))
 def test_identified_app_can_recover_from_user_agent_block(self):
  import urllib.error,io
  def response(url,headers):
   if headers.get('User-Agent')=='Nightshift/1.0':return []
   raise urllib.error.HTTPError(url,403,'Forbidden',{'Content-Type':'text/html'},io.BytesIO(b'<html>Cloudflare</html>'))
  value=refresh({'films':{},'sources':{}},request=response,environ={'TRAKT_CLIENT_ID':'fake-client'})
  state=value['sources']['trakt']
  self.assertEqual(state['status'],'ok')
  self.assertEqual(state['baselineDiagnostic']['category'],'edge_security_block')
  self.assertNotIn('httpStatus',state)

 def test_origin_policy_is_identified_without_changing_credentials(self):
  import urllib.error,io
  def response(url,headers):
   if headers.get('Origin')=='https://arturmal2805-netizen.github.io':return []
   raise urllib.error.HTTPError(url,403,'Forbidden',{},io.BytesIO(b'Origin forbidden private-key'))
  state=refresh({'films':{},'sources':{}},request=response,environ={'TRAKT_CLIENT_ID':'fake-client'})['sources']['trakt']
  self.assertEqual(state['status'],'ok')
  self.assertTrue(state['originRequired'])
  self.assertIn('origin',state['baselineDiagnostic']['reasonHints'])
  self.assertNotIn('private-key',str(state))
if __name__=='__main__':unittest.main()
