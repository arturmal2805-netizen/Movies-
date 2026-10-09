-- Run once in Supabase SQL Editor. GitHub token stays in Vault, never in the browser.
create extension if not exists pg_net with schema extensions;
create extension if not exists supabase_vault with schema vault;

create table if not exists public.recommendation_jobs (
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null references auth.users(id) on delete cascade,
 status text not null default 'queued' check (status in ('queued','running','completed','failed')),
 added_count integer not null default 0 check (added_count >= 0),
 created_at timestamptz not null default now(),
 started_at timestamptz,
 finished_at timestamptz,
 accepted_at timestamptz,
 github_request_id bigint,
 run_url text,
 error_code text
);
create unique index if not exists recommendation_jobs_one_active
 on public.recommendation_jobs(user_id) where status in ('queued','running');
alter table public.recommendation_jobs enable row level security;
drop policy if exists recommendation_jobs_read_own on public.recommendation_jobs;
create policy recommendation_jobs_read_own on public.recommendation_jobs
 for select to authenticated using (user_id=auth.uid());
revoke all on public.recommendation_jobs from anon,authenticated;
grant select on public.recommendation_jobs to authenticated;
grant all on public.recommendation_jobs to service_role;

create or replace function public.start_manual_recommendation()
returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare
 caller uuid := auth.uid();
 job public.recommendation_jobs;
 github_token text;
 http_id bigint;
begin
 if caller is null then raise exception 'manual_auth_required' using errcode='28000'; end if;
 perform pg_advisory_xact_lock(hashtextextended(caller::text,0));
 select * into job from public.recommendation_jobs
  where user_id=caller and status in ('queued','running') limit 1;
 if found then return jsonb_build_object('id',job.id,'status',job.status); end if;
 select decrypted_secret into github_token from vault.decrypted_secrets
  where name='nightshift_github_actions_token' limit 1;
 github_token=regexp_replace(github_token,'[[:space:]]+','','g');
 if github_token is null or github_token !~ '^[A-Za-z0-9_]+$' then
  raise exception 'manual_not_configured' using errcode='P0001';
 end if;
 insert into public.profiles(user_id) values(caller) on conflict do nothing;
 insert into public.recommendation_jobs(user_id) values(caller) returning * into job;
 select net.http_post(
  url:='https://api.github.com/repos/arturmal2805-netizen/Movies-/actions/workflows/recommendations.yml/dispatches',
  headers:=jsonb_build_object('Authorization','Bearer '||btrim(github_token),'Accept','application/vnd.github+json',
   'X-GitHub-Api-Version','2022-11-28','Content-Type','application/json','User-Agent','Nightshift/1.0'),
  body:=jsonb_build_object('ref','main','inputs',jsonb_build_object('manual','true','request_id',job.id::text)),
  timeout_milliseconds:=10000
 ) into http_id;
 update public.recommendation_jobs set github_request_id=http_id where id=job.id;
 return jsonb_build_object('id',job.id,'status',job.status);
end $$;
revoke all on function public.start_manual_recommendation() from public,anon;
grant execute on function public.start_manual_recommendation() to authenticated;

create or replace function public.manual_recommendation_status(job_id uuid)
returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare
 job public.recommendation_jobs;
 code integer;
 network_error text;
begin
 if auth.uid() is null then raise exception 'manual_auth_required' using errcode='28000'; end if;
 select * into job from public.recommendation_jobs where id=job_id and user_id=auth.uid();
 if not found then raise exception 'manual_not_found' using errcode='P0002'; end if;
 -- Report HTTP rejection honestly; a pg_net queue entry is not a confirmed GitHub dispatch.
 if job.status='queued' and job.accepted_at is null and job.github_request_id is not null then
  select status_code,error_msg into code,network_error from net._http_response where id=job.github_request_id;
  if found then
   if code=204 and network_error is null then
    update public.recommendation_jobs set accepted_at=now() where id=job.id and status='queued';
   else
    update public.recommendation_jobs set status='failed',finished_at=now(),
      error_code=case when network_error is not null then 'github_unavailable' else 'github_rejected' end
      where id=job.id and status='queued';
   end if;
   select * into job from public.recommendation_jobs where id=job_id and user_id=auth.uid();
  end if;
 end if;
 return jsonb_build_object('id',job.id,'status',job.status,'added_count',job.added_count,
  'run_url',job.run_url,'error_code',job.error_code,'accepted_at',job.accepted_at);
end $$;
revoke all on function public.manual_recommendation_status(uuid) from public,anon;
grant execute on function public.manual_recommendation_status(uuid) to authenticated;

-- Separately, create a fine-grained GitHub token for Movies- with Actions: Read and write.
-- Save it in Vault under exactly: nightshift_github_actions_token
-- SQL alternative (replace the placeholder only in Supabase, never in a Git commit/chat):
-- select vault.create_secret('PASTE_GITHUB_TOKEN_HERE','nightshift_github_actions_token','Nightshift manual Actions dispatch');
