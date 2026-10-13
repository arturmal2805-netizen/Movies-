"""Read-only smoke check; never log user identifiers or preference contents."""
from recommend import Backend,error_summary
if __name__=='__main__':
 try:
  backend=Backend();rows=backend.db('profiles?select=user_id&limit=1')
  if rows:backend.load_interests(rows[0]['user_id'])
  print('Account interests access verified; no preference contents logged.')
 except Exception as error:
  print('Account interests access failed:',error_summary(error));raise SystemExit(1)
