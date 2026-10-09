import unittest
import os
import io
import json
import base64
import urllib.error
from unittest.mock import patch
from recommend import Backend, RequestFailure, error_summary

class DiagnosticTests(unittest.TestCase):
 def backend(self,key='sb_secret_test'):
  with patch.dict(os.environ,{'SUPABASE_URL':'https://project.example','SUPABASE_SERVICE_ROLE_KEY':key,'TMDB_ACCESS_TOKEN':'tmdb-test'}):return Backend()
 def test_new_secret_key_is_not_used_as_jwt(self):
  backend=self.backend()
  with patch.object(backend,'request',return_value=[]) as request:
   backend.db('profiles?select=user_id')
   headers=request.call_args.args[1]
   self.assertEqual(headers['apikey'],'sb_secret_test')
   self.assertNotIn('Authorization',headers)
 def test_legacy_service_role_uses_bearer(self):
  body=base64.urlsafe_b64encode(json.dumps({'role':'service_role'}).encode()).decode().rstrip('=')
  key='header.'+body+'.signature';backend=self.backend(key)
  with patch.object(backend,'request',return_value=[]) as request:
   backend.db('profiles?select=user_id')
   self.assertEqual(request.call_args.args[1]['Authorization'],'Bearer '+key)
 def test_public_key_is_rejected_without_disclosing_value(self):
  for key in ['sb_publishable_secret-value','header.'+base64.urlsafe_b64encode(b'{"role":"anon"}').decode()+'.signature']:
   with self.assertRaises(RequestFailure) as ctx:self.backend(key)
   self.assertNotIn(key,str(ctx.exception))
 def test_http_error_hides_credentials_user_ids_and_response_message(self):
  backend=self.backend();url='https://project.example/rest/v1/ratings?user_id=eq.private-user'
  failure=urllib.error.HTTPError(url,401,'private-token',{},io.BytesIO(b'{"code":"42501","message":"private-token"}'))
  with patch('urllib.request.urlopen',side_effect=failure):
   with self.assertRaises(RequestFailure) as ctx:backend.db('ratings?user_id=eq.private-user')
  msg=error_summary(ctx.exception)
  self.assertIn('Supabase ratings GET: HTTP 401 code=42501',msg)
  for private in ['private-token','private-user','sb_secret_test','project.example']:self.assertNotIn(private,msg)
