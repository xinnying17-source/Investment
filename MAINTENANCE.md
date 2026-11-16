# Nightly maintenance

Three parts, chosen to keep Claude usage low and keep working on the free Claude plan:

| Time (Malaysia) | Who | Cost | What |
|---|---|---|---|
| Every hour 7:07 am – 11:07 pm | GitHub Actions + Google Gemini free API | Free | Fetch new headlines + market prices (max 6 per category per day), then Gemini writes Chinese/English summaries for **every** headline without one. A second Gemini pass fact-checks each summary and a program checks every number against the source headlines; failures get one stricter rewrite, otherwise the original headline stays. Older summaries (from any tool) are re-checked once and withdrawn if they fail. Off-topic headlines are removed and remembered. |
| 12:00 am | GitHub Actions (full run) | Free | All of the above, plus delete news older than 7 days, run `tests/smoke.js --live`, record `news_meta.health`, open an issue on failure, and Sunday storylines. |
| 12:30 am | Claude scheduled task (paid plan only) | Claude usage (small) | Fix bugs only if tonight's health check failed; write summaries only if Gemini is down (see below). Usually stops after one check. |

**Accuracy rule for every summary (Gemini or Claude):** the only sources are the headline and other outlets' headlines on the same story (Google News gives no article text). A summary may only restate them in plain language: no added names, numbers, dates, reasons or outcomes; forecasts/plans/talks stay forecasts/plans/talks; jargon may get a short textbook definition in brackets; `impact` is general education about this kind of news ("这类消息通常…"), never a new fact and never buy/sell advice. Bookkeeping lives in `news_meta` key `news_ai` (`verified`, `failed`, `skip`).

Owner decisions this routine must respect:
- Small fixes go live via a merged pull request; big changes become a pull request for the owner.
- News covers Malaysia + Global only.
- Never change the design, wording style, settings, or user data except to fix a bug. Never skip or weaken a test.

## Claude task steps (12:30 am)
1. Work from the latest `main`.
2. Read health: `GET {SUPABASE_URL}/rest/v1/news_meta?k=eq.health` (anon key from `docs/config.js`).
3. **Summaries (fallback only):** count today's items without a Chinese summary:
   `news_items?select=id,title_en,source&day=eq.<today MYT>&summary_zh=is.null`.
   If there are 10 or fewer, stop here: the hourly Gemini job handles them.
   If more (Gemini is down), write summaries for up to 15 of them following the **accuracy rule** above exactly
   (`title_zh`, `title_en`, `summary_zh`/`summary_en` 1–2 sentences, `impact_zh`/`impact_en`, `tags`, optional `chart_sym`),
   save as `news/_work/curated.json` `{"items":[...]}` and run `python3 scripts/news_upload.py`. Do not delete anything; the Gemini job removes off-topic items and will fact-check these summaries too.
4. Storylines: skip (the Sunday midnight Actions run does them).
5. **Bugs** (only if `health.ok` is false): reproduce with `node tests/smoke.js`, fix on a new branch, `python3 scripts/build_app.py`, re-run until it passes.
   - Small fix (≤ ~40 lines, no feature/design/wording change): open a PR and merge it once tests pass.
   - Bigger: open a PR only, explained in simple Chinese.
   If the failure is only a news source being down, don't change code; just report it.
6. Finish with a short Chinese summary: health result, summaries written (usually 0), PRs.

## On the free Claude plan
Scheduled Claude tasks need Pro or above. After a downgrade the 12:30 am task stops by itself; the hourly and midnight GitHub Actions keep everything running. Bug fixes then become manual: the failed-check issue tells you something broke. The workflow re-enables itself every night, so GitHub's 60-day idle pause doesn't apply.
