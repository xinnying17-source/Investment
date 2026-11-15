# 投资白话地图

给投资新手的白话学习工具：概念地图（45 个课题，含真实案例图表与实战题）、话术闪卡、公司调查 7 步、复利计算、4 周计划、7 种组合类型、5 年投资模拟器，以及进阶篇（各国股市、资产关系、经济周期、被动收入 0→100）。

内容仅供学习，不构成投资建议。

## 文件结构

| 路径 | 用途 |
|---|---|
| `investment-guide.html` | 主要内容（也是 claude.ai Artifact 版本的源文件） |
| `app-src/` | 独立 App 的登录/云端同步（`cloud.js`）、离线缓存（`sw.js`）、`manifest`、Supabase 客户端 |
| `scripts/build_app.py` | 把主内容 + App 外壳打包到 `docs/` |
| `docs/` | 可以直接发布的网站（GitHub Pages 用这个文件夹） |
| `supabase/schema.sql` | 云端数据库表和权限规则 |

改了 `investment-guide.html` 或 `app-src/` 之后，运行 `python3 scripts/build_app.py` 重新生成 `docs/`。

## 让 App 上线（大约 15 分钟）

### 1. 建立 Supabase 项目（免费，负责登录和云端进度）
1. 到 supabase.com 注册并 **New project**。
2. 左边 **SQL Editor** → 贴上 `supabase/schema.sql` 全部内容 → **Run**。
3. **Project Settings → API**：复制 **Project URL** 和 **anon public key**。
4. 打开 `docs/config.js`，把两个值填进去（anon key 本来就是公开的，配合 RLS 规则，每个人只能读写自己的进度）。
5. **Authentication → URL Configuration**：把你的网站地址（第 2 步得到）填进 **Site URL** 和 **Redirect URLs**，这样确认邮件和重设密码的链接会回到 App。
6. （可选）**Authentication → Providers → Email**：如果不想要求新用户先点确认邮件，可以关掉 *Confirm email*。

### 2. 用 GitHub Pages 发布
1. 把这个分支合并到 `main`。
2. GitHub 仓库 → **Settings → Pages** → Source 选 **Deploy from a branch**，Branch 选 `main`、文件夹选 `/docs` → Save。
3. 几分钟后得到网址，例如 `https://<你的用户名>.github.io/Investment/`。
   - 免费账号的 GitHub Pages 需要仓库是 **Public**。不想公开仓库，可以改用 Netlify / Cloudflare Pages / Vercel，直接上传 `docs/` 文件夹。

### 3. 加到手机主画面
- **iPhone（Safari）**：打开网址 → 分享按钮 → **加入主画面**。
- **Android（Chrome）**：打开网址 → 右上角 ⋮ → **安装应用 / 加到主画面**。
- 电脑 Chrome / Edge：网址栏右边的「安装」图标。

## 登录功能
- Email + 密码注册、登录、忘记密码（发重设邮件）。
- **保持登录**：勾选时登录状态存在这台设备，下次打开不用再登录；不勾选时，关闭浏览器后需要重新登录。
- 进度（看过的课题、已懂、计划、笔记、模拟器、进阶模块）每次变更约 1 秒后自动同步到云端；离线时先存在设备上，回到网络后再同步。
- 「先不登录」可以只在这台设备上使用。

## 财经新闻板块（只在 App 版）
1. 在 Supabase → SQL Editor 执行 `supabase/news.sql`，最后会显示一串「写入钥匙」。
2. 按 Claude 的提示把钥匙填进安全表单（不要贴在聊天里）。
3. 每晚 12 点的定时任务会按 `MAINTENANCE.md` 抓新闻、写白话中英摘要、更新图表和来龙去脉，并删除 7 天前的新闻。
4. 所有人（包括没登录的人）都只能读取新闻，只有带写入钥匙的每日任务能写入。

## 自动测试
`node tests/smoke.js`：打开所有课题的每个分页（中英文）、每个页面、三种模拟器模式，并检查手机宽度有没有横向溢出。

## 每日学习提醒
- **手机日历（推荐，最可靠）**：设置 → 每日提醒 → 「加到手机日历」，会下载一个提醒文件，打开它就加入日历。
- **App 推送（需要一次性设置）**：
  1. Supabase → Database → Extensions：打开 `pg_cron` 和 `pg_net`。
  2. SQL Editor 执行 `supabase/push.sql`。
  3. Edge Functions → Deploy a new function → 名称填 `push-reminder` → 贴上 `supabase/functions/push-reminder/index.ts` 的内容 → Deploy。
  4. 在这个函数的设置里，关掉 **Enforce JWT verification**。
  5. 用户在 App 里登录 → 设置 → 「App 推送」打开。iPhone 要先把 App 加到主画面（iOS 16.4 以上）并从主画面打开。

## 背景音乐
音乐在浏览器里用 Web Audio 即时生成（雨声钢琴、柔和氛围、棕噪音、Lo-fi），不需要音乐文件，也没有版权问题。浏览器规定要先点一下页面才能出声；切到别的 App 会自动暂停。

## 每晚自动维护（省 Claude 额度版）
| 马来西亚时间 | 谁做 | 费用 | 做什么 |
|---|---|---|---|
| 12:00 am | GitHub Actions | 免费 | 抓新闻标题和股价、上传、删除 7 天前的新闻、跑自动测试，失败就开 Issue 通知 |
| 12:30 am | Claude 定时任务 | Claude 额度 | 只为最重要的 10–15 条新闻写中英白话摘要；来龙去脉每周日更新；只有测试失败时才修 bug |

GitHub Actions 需要一个 Secret：GitHub 仓库 → Settings → Secrets and variables → Actions → New repository secret → 名称 `INGEST_KEY`，值是 Supabase 的新闻写入钥匙。

## 免费版 Claude 也能维持（Gemini 免费摘要）
1. 打开 https://aistudio.google.com/apikey ，用 Google 账号登录 → **Create API key** → 复制
2. GitHub 仓库 → Settings → Secrets and variables → Actions → New repository secret → 名称 `GEMINI_API_KEY`，贴上 key
3. 每晚 1:30am 的免费任务只会为「还没有摘要」的新闻写摘要。Claude 还在跑的时候它几乎什么都不用做；Claude 停了就自动接手。
