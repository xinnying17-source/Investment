# Nightly maintenance

Two parts, chosen to keep Claude usage low:

| Time (Malaysia) | Who | Cost | What |
|---|---|---|---|
| 12:00 am | GitHub Actions (`.github/workflows/nightly.yml`) | Free | Fetch headlines + market prices, upload headline-only news, delete news older than 7 days, run `tests/smoke.js --live`, record the result as `news_meta.health`, open an issue on failure |
| 12:30 am | Claude scheduled task | Claude usage | Add plain-language summaries to the 10–15 most important new headlines; update storylines on Sundays only; fix bugs only if tonight's health check failed |

Owner decisions this routine must respect:
- Small fixes go live via a merged pull request; big changes become a pull request for the owner.
- News covers Malaysia + Global only.
- Never change the design, wording style, settings, or user data except to fix a bug. Never skip or weaken a test.

## Claude task steps (12:30 am)
1. Work from the latest `main`.
2. Read health: `GET {SUPABASE_URL}/rest/v1/news_meta?k=eq.health` (anon key from `docs/config.js`).
3. **Summaries** (always): read today's items without a Chinese summary:
   `news_items?select=id,country,industry,title_en,source,url&day=eq.<today MYT>&summary_zh=is.null`.
   Pick the **10–15 most useful** for a Malaysian beginner investor across both countries (skip duplicates, adverts, opinion pieces).
   For each, write: `title_zh`, `title_en` (plain), `summary_zh`/`summary_en` (2–3 everyday sentences, jargon explained in brackets, never copied text, say when unsure), `impact_zh`/`impact_en` (one educational sentence, never buy/sell advice), `tags` (1–3 of `{k:"up"|"down"|"watch", zh, en}`), optional `chart_sym` (`klci`, `usdmyr`, `spx`, `aapl`, `gold`, `brent`).
   Save as `news/_work/curated.json` `{"items":[...]}` and run `python3 scripts/news_upload.py` (it PATCHes only those rows).
4. **Storylines** (Sundays only): for buckets with news this week, upsert `stories` (`key = country-industry`, up to 8 dated bullets over ~90 days, `story_zh`/`story_en` = `[{d,t}]`).
5. **Bugs** (only if `health.ok` is false): reproduce with `node tests/smoke.js`, fix on a new branch, `python3 scripts/build_app.py`, re-run until it passes.
   - Small fix (≤ ~40 lines, no feature/design/wording change): open a PR and merge it once tests pass.
   - Bigger: open a PR only, explained in simple Chinese.
   If the failure is only a news source being down, don't change code; just report it.
6. Finish with a short Chinese summary: items summarised, storylines updated (or skipped), health result, PRs.
