"""Read-only live search validation. No ratings, collection or profile writes."""
import datetime,os,json,traceback
from release_validation import compare_release
from recommend import Backend,read_rows,load_config,recommend_user,error_summary

def summarize(report,error=None):
 path=os.environ.get('GITHUB_STEP_SUMMARY')
 evidence=json.dumps(report,sort_keys=True,separators=(',',':'))
 suffix=(' error='+error)if error else ''
 print('::'+('error'if error else'notice')+' title=Read-only search57::'+(evidence+suffix).replace('%','%25').replace('\r','%0D').replace('\n','%0A'))
 if not path:return
 with open(path,'a')as out:
  out.write('### Read-only candidate search57\n\n')
  out.write('| Aggregate | Result |\n| --- | --- |\n')
  for key,value in report.items():out.write('| '+key+' | '+str(value)+' |\n')
  out.write('\nNo ratings, collection, profile timestamps or preferences were written.\n')
  if error:out.write('\nValidation did not pass: '+error+'\n')

if __name__=='__main__':
 backend=None
 try:
  backend=Backend();users=read_rows(backend,'profiles?select=user_id')
  if not users:raise RuntimeError('No private profile available for a real search validation')
  for user in users:
   backend.search_report={}
   count=recommend_user(backend,user,datetime.datetime.now(datetime.timezone.utc),load_config(),manual=True,dry_run=True)
   if os.environ.get('VALIDATE_RELEASE_RANKING')=='true':
    rows=read_rows(backend,'ratings?user_id=eq.'+user['user_id']+'&select=*&order=tmdb_id')
    backend.search_report['releaseComparison']=compare_release(rows,backend.load_interests(user['user_id']))
   print('Read-only search result:',count,'permitted distinct candidates; no database writes.')
   if os.environ.get('REQUIRE_IMDB_DATASET')=='true'and not backend.search_report.get('imdbDatasetReady'):raise RuntimeError('Public IMDb source unavailable; broader audience verification not established')
   if count<15:raise RuntimeError('Search returned fewer than 15 permitted candidates; quantity target not verified')
   summarize(backend.search_report)
 except Exception as error:
  frame=traceback.extract_tb(error.__traceback__)[-1]
  summarize(getattr(backend,'search_report',{}),error_summary(error)+' at '+os.path.basename(frame.filename)+':'+str(frame.lineno));raise
