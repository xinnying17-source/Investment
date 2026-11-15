"""Free fallback summariser (GitHub Actions, 1:30 am MYT): Google Gemini writes plain-language bilingual summaries
for today's most useful headlines that still have none (e.g. after the Claude task stops), removes clearly irrelevant
headlines, and on Sundays adds this week's developments to the storylines, grounded only in our own summaries.

Needs secrets GEMINI_API_KEY and INGEST_KEY. Optional variable GEMINI_MODEL. Does nothing when GEMINI_API_KEY is empty.
"""
import json, os, sys, re, time, datetime, urllib.request, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
conf = open(os.path.join(ROOT, 'docs', 'config.js'), encoding='utf-8').read()
URL = re.search(r"SUPABASE_URL:\s*'([^']+)'", conf).group(1)
KEY = re.search(r"SUPABASE_ANON_KEY:\s*'([^']+)'", conf).group(1)
TARGET = 15
TAGS = {'up', 'down', 'watch'}
SYMS = {'klci', 'usdmyr', 'spx', 'aapl', 'gold', 'brent'}

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

def gemini(prompt):
    """Thinking off (fast). Per model: one retry on timeout/overload; if thinkingBudget is rejected, retry without it; otherwise move to the next model."""
    key = os.environ['GEMINI_API_KEY']
    models = [m for m in [os.environ.get('GEMINI_MODEL'), 'gemini-2.5-flash', 'gemini-flash-latest'] if m]
    base = {'responseMimeType': 'application/json', 'temperature': 0.3}
    errors = []
    for m in dict.fromkeys(models):
        gc = dict(base, thinkingConfig={'thinkingBudget': 0})
        for attempt in range(3):
            try:
                return _call(m, gc, prompt, key)
            except urllib.error.HTTPError as e:
                msg = f'{m}: HTTP {e.code} {e.read().decode()[:160]}'; errors.append(msg)
                if e.code == 400 and 'thinking' in msg.lower() and 'thinkingConfig' in gc:
                    gc = dict(base); continue
                if e.code in (429, 500, 503) and attempt == 0:
                    time.sleep(20); continue
                break
            except (TimeoutError, urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError) as e:
                errors.append(f'{m}: {type(e).__name__}')
                if attempt == 0:
                    continue
                break
    raise RuntimeError('; '.join(errors[-3:]))

RULES = """Rules: write for a Malaysian beginner investor. Simplified Chinese must be natural everyday language; explain any jargon in brackets.
Only use facts stated in the headline/source given; do not invent numbers, dates or details; if the headline is an opinion or forecast, say so.
Never give buy/sell advice. Never copy article text."""

def clean_item(x, allowed):
    if not isinstance(x, dict) or x.get('id') not in allowed: return None
    f = {k: str(x.get(k, '')).strip()[:600] for k in ('title_zh', 'title_en', 'summary_zh', 'summary_en', 'impact_zh', 'impact_en')}
    if not all(f[k] for k in ('title_zh', 'title_en', 'summary_zh', 'summary_en')): return None
    f['tags'] = [{'k': t['k'], 'zh': str(t.get('zh', ''))[:20], 'en': str(t.get('en', ''))[:30]} for t in (x.get('tags') or []) if isinstance(t, dict) and t.get('k') in TAGS][:3]
    if x.get('chart_sym') in SYMS: f['chart_sym'] = x['chart_sym']
    return x['id'], f

def summaries(today):
    done = sb('GET', f'news_items?select=id&day=eq.{today}&summary_zh=not.is.null')
    need = TARGET - len(done)
    todo = sb('GET', f'news_items?select=id,country,industry,title_en,source&day=eq.{today}&summary_zh=is.null')
    print(f'{len(done)} already summarised, {len(todo)} without summary, room for {max(0, need)}')
    if need <= 0 or not todo: return
    prompt = f"""You are preparing today's financial news for a bilingual (Chinese/English) investing-education app in Malaysia.
From the headlines below, pick at most {need} that matter most to an ordinary Malaysian investor (economy, rates, ringgit, Bursa, big sectors, global markets).
Also list headlines that are clearly NOT about business, markets or the economy (sports, festivals, accidents, unrelated local news, duplicates).
{RULES}
Return JSON: {{"items":[{{"id":"...","title_zh":"...","title_en":"...","summary_zh":"2-3 sentences","summary_en":"2-3 sentences","impact_zh":"one sentence: what it means for an ordinary investor","impact_en":"...","tags":[{{"k":"up|down|watch","zh":"short","en":"short"}}],"chart_sym":"klci|usdmyr|spx|aapl|gold|brent or omit"}}],"irrelevant":["id",...]}}
Headlines:
""" + '\n'.join(json.dumps(t, ensure_ascii=False) for t in todo)
    res = gemini(prompt)
    allowed = {t['id'] for t in todo}
    ok = [c for c in (clean_item(x, allowed) for x in (res.get('items') or [])) if c][:need]
    for i, f in ok:
        sb('PATCH', 'news_items?id=eq.' + i, f, 'return=minimal')
    junk = [i for i in (res.get('irrelevant') or []) if i in allowed and i not in dict(ok)]
    if junk:
        sb('DELETE', 'news_items?id=in.(' + ','.join(junk) + ')', prefer='return=minimal')
    print(f'summarised {len(ok)}, removed {len(junk)} irrelevant')

def storylines(today):
    since = (datetime.date.fromisoformat(today) - datetime.timedelta(days=7)).isoformat()
    rows = sb('GET', f'news_items?select=country,industry,day,summary_zh,summary_en&day=gte.{since}&summary_zh=not.is.null')
    buckets = {}
    for r in rows: buckets.setdefault(f"{r['country']}-{r['industry']}", []).append(r)
    for key, items in buckets.items():
        old = sb('GET', f'news_story?key=eq.{key}&select=*')
        old = old[0] if old else {'key': key, 'country': items[0]['country'], 'industry': items[0]['industry'], 'story_zh': [], 'story_en': []}
        prompt = f"""Summarise this week's developments for the topic {key} as 1-3 dated timeline bullets, using ONLY the summaries below (no outside facts).
{RULES}
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
        if myt.weekday() == 6:  # Sunday in Malaysia
            storylines(today)
    except RuntimeError as e:
        # Gemini slow or unavailable today: headlines are still shown, so warn instead of failing the run
        print('::warning::Gemini unavailable today, summaries skipped: ' + str(e)[:300])

if __name__ == '__main__':
    main()
