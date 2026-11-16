"""Free summariser (GitHub Actions, every hour 7am-midnight MYT): Google Gemini writes plain-language bilingual
summaries for EVERY recent headline that has none, then a second, independent Gemini pass fact-checks each one
against the source headlines, and a program checks that every number appears in the sources.
Anything that fails is rewritten once in a stricter mode; if it still fails it stays as the original headline.
Summaries written earlier (by any tool) are checked the same way and rewritten if they add facts.

Accuracy rule: our only sources are the headline itself and other outlets' headlines about the same story
(Google News RSS gives no article text), so a summary may only restate what those headlines say.

Needs secrets GEMINI_API_KEY and INGEST_KEY. Optional variable GEMINI_MODEL. Does nothing when GEMINI_API_KEY is empty.
Bookkeeping (verified ids, failures, removed ids) lives in news_meta k='news_ai'.
"""
import json, os, sys, re, time, datetime, urllib.request, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
conf = open(os.path.join(ROOT, 'docs', 'config.js'), encoding='utf-8').read()
URL = re.search(r"SUPABASE_URL:\s*'([^']+)'", conf).group(1)
KEY = re.search(r"SUPABASE_ANON_KEY:\s*'([^']+)'", conf).group(1)
WORK = os.path.join(ROOT, 'news', '_work')
BATCH = 30            # headlines per Gemini call (bigger batches = fewer calls from the daily budget)
MAX_NEW = 90          # new summaries per run (keeps us well inside the free quota)
MAX_RECHECK = 45      # older, not-yet-verified summaries re-checked per run
MAX_FAIL = 2          # runs in a row an item may fail before we stop retrying it
TAGS = {'up', 'down', 'watch'}
SYMS = {'klci', 'usdmyr', 'spx', 'aapl', 'gold', 'brent'}
FIELDS = ('title_zh', 'title_en', 'summary_zh', 'summary_en', 'impact_zh', 'impact_en')

def sb(method, path, body=None, prefer=None):
    h = {'apikey': KEY, 'Content-Type': 'application/json', 'x-ingest-key': os.environ.get('INGEST_KEY', '')}
    if prefer: h['Prefer'] = prefer
    req = urllib.request.Request(URL + '/rest/v1/' + path, data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        t = r.read().decode()
        return json.loads(t) if t.strip().startswith(('[', '{')) else t

def _call(model, gc, prompt, key):
    body = {'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': gc}
    req = urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', 'x-goog-api-key': key}, method='POST')
    with urllib.request.urlopen(req, timeout=150) as r:
        out = json.load(r)
    return json.loads(out['candidates'][0]['content']['parts'][0]['text'])

_MODELS = None
_DOWN = False
# ---- daily call budget shared by every script and every hourly run (news_meta k='gemini_budget')
LIMIT = int(os.environ.get('GEMINI_DAILY_LIMIT') or '20')  # set the repo variable GEMINI_DAILY_LIMIT to change it
_BUDGET = None

def _myt_day():
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)).date().isoformat()

def budget():
    """{'day', 'calls', 'quota_hit'} for today (Malaysia time)."""
    global _BUDGET
    if _BUDGET is None:
        try:
            r = sb('GET', 'news_meta?k=eq.gemini_budget&select=v'); v = (r[0]['v'] if r else None) or {}
        except Exception:
            v = {}
        _BUDGET = v if v.get('day') == _myt_day() else {'day': _myt_day(), 'calls': 0, 'quota_hit': False}
    return _BUDGET

def _save_budget():
    try: sb('POST', 'news_meta?on_conflict=k', [{'k': 'gemini_budget', 'v': _BUDGET}], 'resolution=merge-duplicates,return=minimal')
    except Exception: pass

def calls_left():
    b = budget()
    return 0 if b.get('quota_hit') else max(0, LIMIT - b['calls'])

def models():
    """Pick working models from Google's live list (names get retired, e.g. a hard-coded one returned 404)."""
    global _MODELS
    if _MODELS is not None: return _MODELS
    want = [os.environ.get('GEMINI_MODEL') or '', 'gemini-flash-latest', 'gemini-2.5-flash', 'gemini-flash-lite-latest']
    try:
        req = urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models?pageSize=200', headers={'x-goog-api-key': os.environ['GEMINI_API_KEY']})
        with urllib.request.urlopen(req, timeout=30) as r:
            live = {m['name'].split('/', 1)[1] for m in json.load(r).get('models', []) if 'generateContent' in m.get('supportedGenerationMethods', [])}
        flash = sorted((m for m in live if re.fullmatch(r'gemini-\d+(\.\d+)?-flash(-lite)?', m)), reverse=True)
        _MODELS = [m for m in dict.fromkeys(want + flash) if m and m in live][:4] or [m for m in want if m]
    except Exception as e:
        print('model list unavailable, using defaults:', type(e).__name__); _MODELS = [m for m in want if m]
    print('Gemini models:', ', '.join(_MODELS))
    return _MODELS

def gemini(prompt, temperature=0.2):
    """Thinking off (fast). Busy (429/500/503) or timeout: wait 30s then 60s and retry, then try the next model.
    If every model fails, mark Gemini as down for the rest of this run (next hour's run tries again)."""
    global _DOWN
    if _DOWN: raise RuntimeError('Gemini marked unavailable earlier in this run')
    if calls_left() <= 0: raise RuntimeError(f'daily Gemini budget used ({budget()["calls"]}/{LIMIT}) or quota reached; continuing tomorrow')
    key = os.environ['GEMINI_API_KEY']
    base = {'responseMimeType': 'application/json', 'temperature': temperature}
    errors = []
    for m in models():
        gc = dict(base, thinkingConfig={'thinkingBudget': 0})
        for attempt in range(3):
            try:
                out = _call(m, gc, prompt, key)
                budget()['calls'] += 1; _save_budget()  # only successful calls use the daily budget
                return out
            except urllib.error.HTTPError as e:
                msg = f'{m}: HTTP {e.code} {e.read().decode()[:120]}'; errors.append(msg)
                if e.code == 429 and 'quota' in msg.lower():  # daily free quota used up: stop for today, no retries
                    budget()['quota_hit'] = True; _save_budget(); _DOWN = True
                    raise RuntimeError('Gemini daily quota reached; continuing tomorrow')
                if e.code == 400 and 'thinkingConfig' in gc:  # some models reject thinkingBudget=0: retry without it
                    gc = dict(base); continue
                if e.code in (429, 500, 503) and attempt < 2:
                    time.sleep(30 * (attempt + 1)); continue
                break
            except (TimeoutError, urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError) as e:
                errors.append(f'{m}: {type(e).__name__}')
                if attempt < 1:
                    continue
                break
    _DOWN = True
    raise RuntimeError('; '.join(errors[-3:]))

# ---------------------------------------------------------------- sources
STOP = set('a an the of to in on for and or with at by from as is are be after over into amid its it this that new says said will may could'.split())
def words(t): return {w for w in re.findall(r'[a-z0-9]+', t.lower()) if w not in STOP and len(w) > 2}

def related_titles(item, pool):
    """Other outlets' headlines in this run that clearly describe the same story (strong word overlap)."""
    w = words(item['title_en']); out = []
    if len(w) < 3: return out
    for c in pool:
        if c['id'] == item['id']: continue
        cw = words(c['title'])
        if len(w & cw) >= 3 and len(w & cw) / min(len(w), len(cw) or 1) >= 0.6:
            out.append(c['title'])
    return out[:4]

def source_of(item, pool):
    rel = list(dict.fromkeys((item.get('related') or []) + related_titles(item, pool)))
    return {'id': item['id'], 'headline': item['title_en'], 'outlet': item.get('source') or '', 'same_story_other_outlets': rel}

# ---------------------------------------------------------------- number check
MONTHS = 'january february march april may june july august september october november december'.split()
WORDNUM = {w: i for i, w in enumerate('zero one two three four five six seven eight nine ten eleven twelve'.split())}
WORDNUM.update({'half': 0.5, 'dozen': 12, 'hundred': 100, 'thousand': 1000, 'million': 1e6, 'billion': 1e9, 'trillion': 1e12})

def nums(text):
    out = []
    for n in re.findall(r'\d+(?:[.,]\d+)*', text):
        try: out.append(float(n.replace(',', '')))
        except ValueError: pass
    return out

def allowed_numbers(src):
    t = ' '.join([src['headline']] + src['same_story_other_outlets']).lower()
    a = set(nums(t))
    for i, m in enumerate(MONTHS):
        if m in t or m[:3] + ' ' in t: a.add(i + 1)
    for w, v in WORDNUM.items():
        if re.search(r'\b' + w + r'\b', t): a.add(v)
    for q in re.findall(r'\bq([1-4])\b', t): a.add(float(q))
    return a

def numbers_ok(out, src):
    """Every number we wrote must come from the sources (allowing unit changes such as 1 billion = 10亿 = 1,000 million)."""
    allowed = allowed_numbers(src)
    text = ' '.join(out.get(k, '') for k in ('title_zh', 'title_en', 'summary_zh', 'summary_en'))
    for n in nums(text):
        if not any(abs(n - a * 10 ** k) <= 1e-6 * max(1, abs(n)) for a in allowed for k in range(-4, 5)):
            return False, f'number {n:g} is not in the source headlines'
    return True, ''

# ---------------------------------------------------------------- write + verify
RULES = """STRICT ACCURACY RULES (most important):
- Your ONLY sources are the headline(s) given for each item. You have NOT read the article.
- Say only what the headline(s) say. Never add names, numbers, dates, places, reasons, quotes or outcomes that are not in them, even if you believe they are true.
- If a headline is a forecast, opinion, plan, talks or a claim, say so (e.g. 预计 / 据报道 / 分析认为 / 正在商谈), never present it as a done fact.
- You MAY explain a jargon word with a short textbook definition in brackets, e.g. 周期股（业绩跟着经济起伏的股票）.
- impact: one sentence of GENERAL investing education about this KIND of news, starting like "这类消息通常…" / "News like this usually…". It must not state anything new about this specific event and never give buy/sell advice.
- tags: "up" or "down" only if the headline itself clearly says something rose/fell or is clearly good/bad news for the sector; otherwise "watch".
STYLE: Simplified Chinese must be natural everyday Malaysian-Chinese language, short sentences, no copied English sentences. English plain and simple."""

def write(items, feedback=None):
    fb = ('\nA fact-checker rejected your earlier version of these items. Fix exactly these problems, and when unsure say less:\n' +
          '\n'.join(f'- {i}: {p}' for i, p in feedback.items())) if feedback else ''
    prompt = f"""You are writing headline summaries for a bilingual (Chinese/English) investing-education app for beginners in Malaysia.
{RULES}{fb}
For EVERY item below return:
{{"items":[{{"id":"...","title_zh":"plain Chinese headline","title_en":"repeat the original headline exactly","summary_zh":"1-2 short sentences restating the headline plainly","summary_en":"same in English","impact_zh":"这类消息通常…","impact_en":"News like this usually…","tags":[{{"k":"up|down|watch","zh":"2-6 Chinese characters naming who is affected","en":"short"}}],"chart_sym":"klci|usdmyr|spx|aapl|gold|brent or omit"}}],
"irrelevant":["ids of headlines clearly NOT about business, markets, companies or the economy (sports, crime, festivals, accidents, celebrity, adverts)"]}}
Items:
""" + '\n'.join(json.dumps(s, ensure_ascii=False) for s in items)
    return gemini(prompt, 0.2)

def verify(pairs):
    prompt = """You are a strict, independent fact-checker. For each item you get the SOURCE headline(s) and a WRITTEN summary in Chinese and English.
Mark ok=false if ANY of these is true:
- title/summary (zh or en) states a fact, name, number, date, place, cause, quote or outcome that is not directly stated in the source headline(s);
- it turns a forecast/plan/claim/talks into a completed fact, or changes who did what, or gets a direction wrong (rise vs fall, increase vs decrease);
- the Chinese and English versions say different things;
- impact states anything specific about this event instead of general education, or gives buy/sell advice;
- a tag of up/down contradicts the headline.
A short textbook definition of a jargon word in brackets is allowed. Plain-language rewording is allowed when the meaning is unchanged.
Return JSON {"results":[{"id":"...","ok":true|false,"problem":"short description of the exact unsupported or wrong part, empty if ok"}]}
Items:
""" + '\n'.join(json.dumps({'id': s['id'], 'source': {'headline': s['headline'], 'other_outlets': s['same_story_other_outlets']},
                            'written': {k: o.get(k, '') for k in FIELDS} | {'tags': o.get('tags', [])}}, ensure_ascii=False) for s, o in pairs)
    res = gemini(prompt, 0.0)
    return {r.get('id'): (bool(r.get('ok')), str(r.get('problem', ''))[:200]) for r in (res.get('results') or []) if isinstance(r, dict)}

def clean_item(x, allowed):
    if not isinstance(x, dict) or x.get('id') not in allowed: return None
    f = {k: str(x.get(k, '')).strip()[:500] for k in FIELDS}
    if not all(f[k] for k in ('title_zh', 'title_en', 'summary_zh', 'summary_en')): return None
    f['tags'] = [{'k': t['k'], 'zh': str(t.get('zh', ''))[:12], 'en': str(t.get('en', ''))[:30]} for t in (x.get('tags') or []) if isinstance(t, dict) and t.get('k') in TAGS][:3]
    f['chart_sym'] = x['chart_sym'] if x.get('chart_sym') in SYMS else None
    return x['id'], f

def check(pairs):
    """pairs: [(src, out)] -> (passed {id: out}, failed {id: problem}). Items the checker could not reach are in neither."""
    passed, failed, to_judge = {}, {}, []
    for s, o in pairs:
        ok, why = numbers_ok(o, s)
        if ok: to_judge.append((s, o))
        else: failed[s['id']] = why
    for i in range(0, len(to_judge), BATCH):
        chunk = to_judge[i:i + BATCH]
        try:
            verdict = verify(chunk)
        except RuntimeError as e:
            print('verify unavailable, will retry next run:', str(e)[:200]); continue
        for s, o in chunk:
            ok, why = verdict.get(s['id'], (False, 'not checked'))
            if ok: passed[s['id']] = o
            else: failed[s['id']] = why or 'unsupported detail'
    return passed, failed

def process(srcs):
    """Write -> check -> one stricter rewrite of failures -> check. Returns (passed, failed, irrelevant)."""
    passed, failed, junk = {}, {}, set()
    by_id = {s['id']: s for s in srcs}
    for i in range(0, len(srcs), BATCH):
        chunk = srcs[i:i + BATCH]
        try:
            res = write(chunk)
        except RuntimeError as e:
            print('write unavailable:', str(e)[:200]); break
        allowed = {s['id'] for s in chunk}
        junk |= {j for j in (res.get('irrelevant') or []) if j in allowed}
        outs = dict(c for c in (clean_item(x, allowed) for x in (res.get('items') or [])) if c)
        p, f = check([(by_id[k], v) for k, v in outs.items() if k not in junk])
        passed.update(p)
        f.update({k: 'no summary returned' for k in allowed - set(outs) - junk})
        if f:  # one stricter retry with the checker's feedback
            retry = [by_id[k] for k in f]
            try:
                res2 = write(retry, feedback=f)
                outs2 = dict(c for c in (clean_item(x, set(f)) for x in (res2.get('items') or [])) if c)
                p2, f2 = check([(by_id[k], v) for k, v in outs2.items()])
                passed.update(p2)
                failed.update({k: f2.get(k, f[k]) for k in f if k not in p2})
            except RuntimeError as e:
                print('retry unavailable:', str(e)[:200]); failed.update(f)
    return passed, failed, junk

# ---------------------------------------------------------------- bookkeeping
def load_meta():
    r = sb('GET', 'news_meta?k=eq.news_ai&select=v')
    v = (r[0]['v'] if r else None) or {}
    return {'verified': v.get('verified', []), 'failed': v.get('failed', {}), 'skip': v.get('skip', [])}

def save_meta(m):
    m = {'verified': m['verified'][-2000:], 'failed': dict(list(m['failed'].items())[-1000:]), 'skip': m['skip'][-2000:]}
    sb('POST', 'news_meta?on_conflict=k', [{'k': 'news_ai', 'v': m}], 'resolution=merge-duplicates,return=minimal')

def summaries(today):
    pool = []
    cpath = os.path.join(WORK, 'candidates.json')
    if os.path.exists(cpath):
        pool = json.load(open(cpath, encoding='utf-8'))['items']
    rel = {c['id']: c.get('related') or [] for c in pool}
    def orig(c):  # Google News appends " - Source" to titles
        t = c['title']; return t.rsplit(' - ', 1)[0] if c.get('source') and t.endswith(' - ' + c['source']) else t
    original = {c['id']: orig(c) for c in pool}
    meta = load_meta(); verified = set(meta['verified']); skip = set(meta['skip'])
    since2 = (datetime.date.fromisoformat(today) - datetime.timedelta(days=1)).isoformat()
    since7 = (datetime.date.fromisoformat(today) - datetime.timedelta(days=7)).isoformat()

    # 1) everything recent without a Chinese summary
    # deep-analysed items (and their duplicates) are handled by news_deep.py; skip them here
    try:
        sb('GET', 'news_items?select=depth&limit=1'); dep = '&depth=in.(brief,nodeep)'
    except Exception:
        dep = ''  # news_v2.sql not applied yet
    todo = sb('GET', f'news_items?select=id,title_en,source&day=gte.{since2}&summary_zh=is.null{dep}&order=published_at.desc')
    todo = [t for t in todo if meta['failed'].get(t['id'], 0) < MAX_FAIL and t['id'] not in skip][:MAX_NEW]
    # 2) older summaries that were never fact-checked by this pipeline
    old = sb('GET', f'news_items?select=id,title_en,source,summary_zh&day=gte.{since7}&summary_zh=not.is.null{dep}')
    recheck = [t for t in old if t['id'] not in verified][:MAX_RECHECK]
    print(f'{len(todo)} to summarise, {len(recheck)} older summaries to fact-check')

    restored = 0
    for t in todo + recheck:  # older runs let AI overwrite title_en; put the real headline back
        o = original.get(t['id'])
        if o and o != t['title_en']:
            sb('PATCH', 'news_items?id=eq.' + t['id'], {'title_en': o}, 'return=minimal'); t['title_en'] = o; restored += 1
    if restored: print(f'restored {restored} original English headlines')
    if calls_left() <= 0:
        print('no Gemini budget left today; summaries continue tomorrow'); return
    srcs = [source_of({**t, 'related': rel.get(t['id'])}, pool) for t in todo + recheck]
    if not srcs: return
    # Older summaries: check what is published now first; only rewrite the ones that fail
    old_ids = {t['id'] for t in recheck}
    if recheck:
        cur = {r['id']: r for r in sb('GET', 'news_items?select=*&id=in.(' + ','.join(old_ids) + ')')}
        ok_old, bad_old = check([(s, cur[s['id']]) for s in srcs if s['id'] in cur])
        verified |= set(ok_old)
        srcs = [s for s in srcs if s['id'] not in ok_old]
        print(f'fact-check of older summaries: {len(ok_old)} ok, {len(bad_old)} need a rewrite, {len(recheck) - len(ok_old) - len(bad_old)} not checked (Gemini busy)')
        srcs = [s for s in srcs if s['id'] not in old_ids or s['id'] in bad_old]
    passed, failed, junk = process(srcs)

    for i, f in passed.items():
        f = {k: v for k, v in f.items() if k != 'title_en'}  # keep the original English headline as published
        sb('PATCH', 'news_items?id=eq.' + i, f, 'return=minimal'); verified.add(i); meta['failed'].pop(i, None)
    for i in failed:
        meta['failed'][i] = meta['failed'].get(i, 0) + 1
        if i in old_ids:  # a published summary that cannot be verified is withdrawn; the headline + link stay
            sb('PATCH', 'news_items?id=eq.' + i, {k: None for k in FIELDS if k != 'title_en'} | {'tags': [], 'chart_sym': None}, 'return=minimal')
    if junk:
        sb('DELETE', 'news_items?id=in.(' + ','.join(junk) + ')', prefer='return=minimal'); skip |= junk
    meta['verified'] = list(verified); meta['skip'] = list(skip)
    save_meta(meta)
    print(f'published {len(passed)} checked summaries, {len(failed)} left as original headline, removed {len(junk)} off-topic')

def storylines(today):
    since = (datetime.date.fromisoformat(today) - datetime.timedelta(days=7)).isoformat()
    rows = sb('GET', f'news_items?select=country,industry,day,summary_zh,summary_en&day=gte.{since}&summary_zh=not.is.null')
    buckets = {}
    for r in rows: buckets.setdefault(f"{r['country']}-{r['industry']}", []).append(r)
    for key, items in buckets.items():
        old = sb('GET', f'news_story?key=eq.{key}&select=*')
        old = old[0] if old else {'key': key, 'country': items[0]['country'], 'industry': items[0]['industry'], 'story_zh': [], 'story_en': []}
        prompt = f"""Summarise this week's developments for the topic {key} as 1-3 dated timeline bullets, using ONLY the summaries below (no outside facts, no new numbers or names).
Also give a short topic title if none exists (existing: {old.get('title_zh') or '-'} / {old.get('title_en') or '-'}).
Return JSON: {{"title_zh":"...","title_en":"...","zh":[{{"d":"YYYY-MM-DD","t":"..."}}],"en":[{{"d":"YYYY-MM-DD","t":"..."}}]}}
Summaries:
""" + '\n'.join(json.dumps({'day': i['day'], 'zh': i['summary_zh'], 'en': i['summary_en']}, ensure_ascii=False) for i in items)
        try:
            res = gemini(prompt)
        except Exception as e:
            print('storyline skipped', key, e); continue
        ok = lambda a: [{'d': str(p.get('d', ''))[:10], 't': str(p.get('t', ''))[:300]} for p in (a or []) if isinstance(p, dict) and p.get('t')][:3]
        zh, en = ok(res.get('zh')), ok(res.get('en'))
        if not zh or not en: continue
        src_nums = {'headline': ' '.join(i['summary_en'] + ' ' + i['summary_zh'] for i in items), 'same_story_other_outlets': []}
        if not numbers_ok({'summary_zh': ' '.join(p['t'] for p in zh), 'summary_en': ' '.join(p['t'] for p in en)}, src_nums)[0]:
            print('storyline rejected (number not in summaries)', key); continue
        row = {'key': key, 'country': old['country'], 'industry': old['industry'],
               'title_zh': old.get('title_zh') or str(res.get('title_zh', ''))[:60], 'title_en': old.get('title_en') or str(res.get('title_en', ''))[:80],
               'story_zh': ((old.get('story_zh') or []) + zh)[-8:], 'story_en': ((old.get('story_en') or []) + en)[-8:],
               'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        sb('POST', 'news_story?on_conflict=key', [row], 'resolution=merge-duplicates,return=minimal')
        print('storyline updated', key)

def main():
    if not os.environ.get('GEMINI_API_KEY'):
        print('GEMINI_API_KEY not set: free summariser is off (the Claude task handles summaries).'); return
    if not os.environ.get('INGEST_KEY'):
        print('::error::INGEST_KEY secret is missing, so summaries cannot be saved. Add it under Settings → Secrets and variables → Actions.'); sys.exit(1)
    myt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    today = myt.date().isoformat()
    try:
        summaries(today)
        if myt.weekday() == 6 and os.environ.get('FULL_RUN') == 'true':  # Sunday nightly run in Malaysia
            storylines(today)
    except RuntimeError as e:
        # Gemini slow or unavailable: headlines are still shown, so warn instead of failing the run
        print('::warning::Gemini unavailable, summaries skipped: ' + str(e)[:300])

if __name__ == '__main__':
    main()
