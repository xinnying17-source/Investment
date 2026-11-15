-- 把 App 变成只有你自己能用：新闻资料只让「你的账号」和后台任务（带写入钥匙）读取。
-- 在 Supabase → SQL Editor 整段执行一次。执行前，把下面的 你的登录邮箱 换成你登录 App 用的邮箱。

-- 1) 记录谁是主人（放在 private schema，外人看不到）
create schema if not exists private;
create table if not exists private.app_owner (id uuid primary key);
insert into private.app_owner (id)
select id from auth.users where lower(email) = lower('你的登录邮箱')
on conflict do nothing;

-- 2) 判断目前登录的人是不是主人（security definer：函数自己有权限读 private 表）
create or replace function public.is_owner() returns boolean
language sql security definer stable set search_path = public, private as $$
  select exists (select 1 from private.app_owner where id = auth.uid());
$$;

-- 3) 新闻相关的表：取消「所有人可读」，改成只有主人或后台任务可读
do $$ declare t text; begin
  foreach t in array array['news_items','news_story','market_snap','news_meta'] loop
    execute format('drop policy if exists "public read" on public.%I', t);
    execute format('drop policy if exists "owner read" on public.%I', t);
    execute format('create policy "owner read" on public.%I for select using (public.is_owner() or public.ingest_ok())', t);
  end loop;
end $$;

-- 4) 检查：第一行应该显示 1（找到你的账号）。下面列出所有注册过的账号，不是你的可以到 Authentication → Users 删除。
select count(*) as "主人账号数（应为 1）" from private.app_owner;
select email, created_at from auth.users order by created_at;
