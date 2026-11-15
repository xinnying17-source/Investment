-- 财经新闻板块：在 Supabase → SQL Editor 整段执行一次。
-- 所有人（包括没登录的访客）都只能「读」新闻；只有带着正确 x-ingest-key 的每日任务能写入或删除。

create schema if not exists private;
create table if not exists private.ingest_key (k text primary key);
revoke all on schema private from anon, authenticated;

create or replace function public.ingest_ok() returns boolean
language sql security definer stable set search_path = public, private as $$
  select exists (
    select 1 from private.ingest_key
    where k = coalesce(current_setting('request.headers', true)::json ->> 'x-ingest-key', '')
  );
$$;

create table if not exists public.news_items (
  id text primary key,
  day date not null,
  country text not null,
  industry text not null,
  published_at timestamptz,
  source text,
  url text not null,
  title_zh text, title_en text,
  summary_zh text, summary_en text,
  impact_zh text, impact_en text,
  tags jsonb not null default '[]'::jsonb,
  chart_sym text,
  story_key text,
  created_at timestamptz not null default now()
);
create index if not exists news_items_bucket on public.news_items (country, industry, day desc);

create table if not exists public.news_story (
  key text primary key, country text, industry text,
  title_zh text, title_en text,
  story_zh jsonb, story_en jsonb,
  updated_at timestamptz not null default now()
);
create table if not exists public.market_snap (
  sym text primary key, name_zh text, name_en text,
  x jsonb, v jsonb, src text,
  updated_at timestamptz not null default now()
);
create table if not exists public.news_meta (k text primary key, v jsonb, updated_at timestamptz not null default now());

do $$ declare t text; begin
  foreach t in array array['news_items','news_story','market_snap','news_meta'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists "public read" on public.%I', t);
    execute format('drop policy if exists "ingest write" on public.%I', t);
    execute format('create policy "public read" on public.%I for select using (true)', t);
    execute format('create policy "ingest write" on public.%I for all using (public.ingest_ok()) with check (public.ingest_ok())', t);
  end loop;
end $$;

-- 产生每日任务专用的写入钥匙（只执行一次）。执行后复制结果，按 Claude 的提示填进安全表单，不要贴在聊天里。
insert into private.ingest_key (k)
select replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '')
where not exists (select 1 from private.ingest_key);
select k as "复制这串写入钥匙" from private.ingest_key;
