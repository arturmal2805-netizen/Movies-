"""Best-effort final status when the job stops before/during the main script."""
import os
from recommend import Backend,validated_uuid,finish_manual_job
if __name__=='__main__':
 request_id=validated_uuid(os.environ.get('RECOMMENDATION_REQUEST_ID'),'Request ID')
 backend=Backend();jobs=backend.db('recommendation_jobs?id=eq.'+request_id+'&select=user_id,status')
 if jobs and jobs[0]['status'] in ('queued','running'):
  user_id=validated_uuid(jobs[0]['user_id'],'User ID')
  finish_manual_job(backend,request_id,user_id,'failed')
