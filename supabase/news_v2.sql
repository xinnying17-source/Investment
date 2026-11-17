-- 深度新闻分析（第 1 阶段）：在 Supabase → SQL Editor 整段执行一次。可以重复执行，不会弄坏资料。
-- 需要先执行过 news.sql 和 private.sql（用到 ingest_ok() 和 is_owner()）。

-- 1) 新闻表加栏位：全文分析、关键数字、含义、受影响股票、来源、相关旧闻、关键词
alter table public.news_items
  add column if not exists depth text not null default 'brief',      -- 'brief' 只有标题摘要；'deep' 读过全文
  add column if not exists article_zh text, add column if not exists article_en text,
  add column if not exists points jsonb not null default '[]'::jsonb, -- 关键数字/重点 [{zh,en}]
  add column if not exists meaning_zh text, add column if not exists meaning_en text,
  add column if not exists stocks jsonb not null default '[]'::jsonb, -- [{y,code,name,effect,zh,en}]
  add column if not exists sources jsonb not null default '[]'::jsonb,-- [{outlet,title,url}]
  add column if not exists related jsonb not null default '[]'::jsonb,-- 相关旧闻 id
  add column if not exists keywords text[] not null default '{}';
create index if not exists news_items_keywords on public.news_items using gin (keywords);
create index if not exists news_items_day on public.news_items (day desc);

-- 2) 每日市场总结
create table if not exists public.market_brief (
  day date primary key,
  zh text, en text,
  data jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);
-- 3) 股票价格（给新闻里的股票小图表用）
create table if not exists public.stock_snap (
  y text primary key, code text, name text, cur text,
  x jsonb, v jsonb,
  updated_at timestamptz not null default now()
);

-- 4) 权限：只有主人和后台任务能读，只有后台任务能写
do $$ declare t text; begin
  foreach t in array array['market_brief','stock_snap'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists "owner read" on public.%I', t);
    execute format('drop policy if exists "ingest write" on public.%I', t);
    execute format('create policy "owner read" on public.%I for select using (public.is_owner() or public.ingest_ok())', t);
    execute format('create policy "ingest write" on public.%I for all using (public.ingest_ok()) with check (public.ingest_ok())', t);
  end loop;
end $$;

select 'ok' as "完成";
