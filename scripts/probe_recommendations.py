"""Read-only live search validation. No ratings, collection or profile writes."""
import datetime,os
from recommend import Backend,read_rows,load_config,recommend_user,error_summary

def summarize(report,error=None):
 path=os.environ.get('GITHUB_STEP_SUMMARY')
 if not path:return
 with open(path,'a')as out:
  out.write('### Read-only candidate search49\n\n')
  out.write('| Aggregate | Result |\n| --- | --- |\n')
  for key,value in report.items():out.write('| '+key+' | '+str(value)+' |\n')
  out.write('\nNo ratings, collection, profile timestamps or preferences were written.\n')
  if error:out.write('\nValidation did not pass: '+error+'\n')

if __name__=='__main__':
 backend=Backend();users=read_rows(backend,'profiles?select=user_id')
 for user in users:
  try:
   count=recommend_user(backend,user,datetime.datetime.now(datetime.timezone.utc),load_config(),manual=True,dry_run=True)
   print('Read-only search result:',count,'permitted distinct candidates; no database writes.')
   if count<15:raise RuntimeError('Search returned fewer than15 permitted candidates; quantity target not verified')
   summarize(backend.search_report)
  except Exception as error:
   summarize(getattr(backend,'search_report',{}),error_summary(error));raise
