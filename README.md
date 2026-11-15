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
