"""Bounded canonical refresh before a new recommendation model is used."""
import os
from recommend import Backend,read_rows,load_config,enrich_history,validated_uuid


def warm_profiles(backend,users,config,max_passes=10):
 failures=0
 for user in users:
  uid=user['user_id']
  try:
   ratings=read_rows(backend,'ratings?user_id=eq.'+uid+'&select=*&order=tmdb_id')
   collection=read_rows(backend,'collection?user_id=eq.'+uid+'&select=*&order=tmdb_id')
   refreshed=0
   for _ in range(max_passes):
    count=enrich_history(backend,uid,ratings,collection,config)
    refreshed+=count
    if not count:break
   unfinished=any(isinstance(r.get('metadata'),dict) and r['metadata'].get('title') and not r['metadata'].get('productionChecked') for r in ratings+collection)
   if unfinished:
    print('Some historical metadata is unavailable or deferred; original records retained.')
    if not refreshed:failures+=1
  except Exception:
   failures+=1;print('Personal history refresh incomplete; original opinions retained.')
 return failures


def main():
 backend=Backend();config=load_config()
 uid=os.environ.get('RECOMMENDATION_USER_ID','').strip()
 if uid:uid=validated_uuid(uid,'User')
 users=read_rows(backend,'profiles?select=user_id'+('&user_id=eq.'+uid if uid else ''))
 if warm_profiles(backend,users,config):raise RuntimeError('Personal history refresh failed; retry the job')
 print('Bounded personal history refresh finished.')


if __name__=='__main__':main()
