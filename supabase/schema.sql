-- Run once in the Supabase SQL Editor. Private user data never goes into GitHub.
create table if not exists public.profiles (
 user_id uuid primary key references auth.users(id) on delete cascade,
 created_at timestamptz not null default now(),
 last_recommendation_at timestamptz
);
create table if not exists public.ratings (
 user_id uuid not null references auth.users(id) on delete cascade,
 tmdb_id bigint not null check (tmdb_id > 0),
 cinematography integer check (cinematography between 1 and 10),
 plot integer check (plot between 1 and 10),
 impression text not null check (impression in ('like','neutral','dislike','watched')),
 metadata jsonb not null default '{}',
 updated_at timestamptz not null default now(),
 primary key(user_id,tmdb_id)
);
create table if not exists public.collection (
 user_id uuid not null references auth.users(id) on delete cascade,
 tmdb_id bigint not null check (tmdb_id > 0),
 metadata jsonb not null,
 reason text,
 saved boolean not null default false,
 created_at timestamptz not null default now(),
 primary key(user_id,tmdb_id)
);
alter table public.profiles enable row level security;
alter table public.ratings enable row level security;
alter table public.collection enable row level security;
drop policy if exists profiles_own on public.profiles;
create policy profiles_own on public.profiles for all to authenticated using(user_id=auth.uid()) with check(user_id=auth.uid());
drop policy if exists ratings_own on public.ratings;
create policy ratings_own on public.ratings for all to authenticated using(user_id=auth.uid()) with check(user_id=auth.uid());
drop policy if exists collection_own on public.collection;
create policy collection_own on public.collection for all to authenticated using(user_id=auth.uid()) with check(user_id=auth.uid());
revoke all on public.profiles,public.ratings,public.collection from anon;
grant select,insert,update,delete on public.profiles,public.ratings,public.collection to authenticated;
grant all on public.profiles,public.ratings,public.collection to service_role;
