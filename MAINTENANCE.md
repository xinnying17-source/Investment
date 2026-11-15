# Nightly maintenance (runs automatically at 12:00 am, Malaysia time)

A scheduled Claude task starts a fresh cloud session every night and follows this file.
Owner decisions this routine must respect:
- Small fixes go live automatically; big changes become a pull request for the owner to merge.
- News covers Malaysia + Global only.
- Never change the design, wording style, settings, or data of existing users unless fixing a bug.

## 1. Update the code
- `git fetch origin main` and work from the latest `main`.

## 2. Refresh financial news
1. `python3 scripts/news_fetch.py` → writes `news/_work/candidates.json` (headlines from the last ~24h) and `news/_work/markets.json`.
2. For every bucket in `news/buckets.json`, pick at most `max_items_per_bucket` headlines that matter to a Malaysian beginner investor. Skip duplicates, opinion pieces, adverts and anything already covered in the last 7 days (check with a read of `news_items`).
3. For each picked headline write a JSON item (fields listed in `scripts/news_upload.py`):
   - `title_zh` / `title_en`: a short plain-language headline in each language.
   - `summary_zh` / `summary_en`: 2–3 sentences in everyday language. Explain jargon in brackets. Never copy the article text; summarise from the headline and what you can verify (WebSearch is allowed). If unsure, say so.
   - `impact_zh` / `impact_en`: one sentence “what this means for an ordinary investor”, educational, never a buy/sell call.
   - `tags`: 1–3 of `{k:"up"|"down"|"watch", zh, en}` for who is affected and how.
   - `chart_sym`: one of the market symbols if a price chart helps (e.g. `brent` for oil news, `aapl` for Apple, `usdmyr` for ringgit news), otherwise omit.
   - `day`: today in Malaysia time (YYYY-MM-DD). `id`: from the candidate.
4. Update storylines (`stories`): for each bucket with news, keep one story `key = country-industry` with up to 8 dated bullets covering the last ~90 days (`story_zh` / `story_en` = `[{d, t}]`). Add the new development; drop the oldest beyond 8. Use background knowledge or WebSearch for older context, clearly dated.
5. Save as `news/_work/curated.json` and run `python3 scripts/news_upload.py` (deletes items older than 7 days automatically).
6. If fetching fails, upload `{"items":[],"status":"fetch failed: <reason>"}` so the app shows the warning, and report it.

## 3. Check for bugs
1. `node tests/smoke.js --live`.
2. If it passes and news uploaded: stop and report “all good”.
3. If something fails, find the cause and fix it on a new branch, then rebuild the app with `python3 scripts/build_app.py` and re-run the test until it passes.
   - **Small fix** (≤ ~40 changed lines, no new feature, no text/design change beyond the bug): open a PR, then merge it yourself once the smoke test passes.
   - **Anything bigger**: open a PR and leave it for the owner, explaining the problem in plain Chinese.
4. Never skip or weaken a test to make it pass.

## 4. Report
Finish with a short summary: news items added per bucket, markets updated, test result, and any PR opened or merged.
