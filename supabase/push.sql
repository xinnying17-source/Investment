-- 每日学习提醒（App 推送）：在 Supabase → SQL Editor 整段执行一次。
-- 需要先在 Database → Extensions 打开 pg_cron 和 pg_net（下面也会尝试自动打开）。

create extension if not exists pg_cron;
create extension if not exists pg_net;

-- 每个用户的推送订阅（只能看到、修改自己的）
create table if not exists public.push_subs (
  endpoint text primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  p256dh text not null,
  auth text not null,
  hour int not null default 12 check (hour between 0 and 23),
  tz text not null default 'Asia/Kuala_Lumpur',
  lang text not null default 'zh',
  dpw int not null default 7,
  last_sent date,
  created_at timestamptz not null default now()
);
alter table public.push_subs enable row level security;
drop policy if exists "own subs" on public.push_subs;
create policy "own subs" on public.push_subs for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- 推送服务的私密设定（开启 RLS 且没有任何规则 = 只有服务端能读）
create table if not exists public.push_config (k text primary key, v text not null);
alter table public.push_config enable row level security;
insert into public.push_config (k, v)
select 'cron_secret', replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '')
where not exists (select 1 from public.push_config where k = 'cron_secret');

-- 每小时整点叫一次推送函数；函数只会提醒「现在是他设定时间」的用户
select cron.unschedule(jobid) from cron.job where jobname = 'ig-push-reminder';
select cron.schedule('ig-push-reminder', '0 * * * *', $$
  select net.http_post(
    url := 'https://xpacmtbvsrfjzhjrrmpw.supabase.co/functions/v1/push-reminder',
    headers := jsonb_build_object('Content-Type', 'application/json',
                                  'x-cron-secret', (select v from public.push_config where k = 'cron_secret')),
    body := '{}'::jsonb);
$$);
