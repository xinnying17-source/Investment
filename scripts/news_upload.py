"""Two modes.
  --raw : (GitHub Actions, no AI) upload headline-only items + market closes, delete items older than keep_days.
  default: (Claude) add bilingual summaries to existing items (PATCH) and upsert storylines.
Upload curated news + markets + storylines to Supabase and delete items older than keep_days.

Input: news/_work/curated.json  {"items":[...], "stories":[...]}  and news/_work/markets.json
Item fields: id, day (YYYY-MM-DD), country, industry, published_at, source, url, title_zh, title_en,
             summary_zh, summary_en, impact_zh, impact_en, tags [{k:'up'|'down'|'watch', zh, en}], chart_sym, story_key
Story fields: key, country, industry, title_zh, title_en, story_zh, story_en  (story_* = list of {d, zh/en text})
Writes require the x-ingest-key header; in the cloud session the network proxy injects it.
Locally you can set INGEST_KEY in the environment instead.
"""
import json, os, sys, datetime, urllib.request, email.utils
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, 'news', 'buckets.json'), encoding='utf-8'))
WORK = os.path.join(ROOT, 'news', '_work')
conf = open(os.path.join(ROOT, 'docs', 'config.js'), encoding='utf-8').read()
import re
URL = re.search(r"SUPABASE_URL:\s*'([^']+)'", conf).group(1)
KEY = re.search(r"SUPABASE_ANON_KEY:\s*'([^']+)'", conf).group(1)

def call(method, path, body=None, prefer=None):
    h = {'apikey': KEY, 'Content-Type': 'application/json'}
    if os.environ.get('INGEST_KEY'):
        h['x-ingest-key'] = os.environ['INGEST_KEY']
    if prefer:
        h['Prefer'] = prefer
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(URL + '/rest/v1/' + path, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode()

def raw_items():
    """Headlines only (no AI): top items per bucket from candidates.json, English title + link."""
    cand = json.load(open(os.path.join(WORK, 'candidates.json'), encoding='utf-8'))
    n = CFG['max_items_per_bucket']; per = {}; out = []
    day = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)).date().isoformat()  # Malaysia date
    for it in cand['items']:
        k = (it['country'], it['industry'])
        if per.get(k, 0) >= n:
            continue
        per[k] = per.get(k, 0) + 1
        try:
            pub = email.utils.parsedate_to_datetime(it['published']).isoformat() if it.get('published') else None
        except Exception:
            pub = None
        title = it['title'].rsplit(' - ', 1)[0] if it.get('source') and it['title'].endswith(' - ' + it['source']) else it['title']
        out.append({'id': it['id'], 'day': day, 'country': it['country'], 'industry': it['industry'], 'published_at': pub,
                    'source': it.get('source', ''), 'url': it['url'], 'title_en': title})
    return out

def main_raw():
    if not os.environ.get('INGEST_KEY'):
        sys.exit('INGEST_KEY secret is missing: add it under Settings → Secrets and variables → Actions (value = the Supabase news write key).')
    items = raw_items()
    # Hourly runs: skip headlines removed as off-topic, and keep at most max_items_per_bucket_day per bucket per day
    try:
        st, body = call('GET', 'news_meta?k=eq.news_ai&select=v'); m = json.loads(body)
        skip = set((m[0]['v'] or {}).get('skip', [])) if m else set()
        st, body = call('GET', 'news_items?select=id,country,industry&day=eq.' + (items[0]['day'] if items else '1970-01-01'))
        have = json.loads(body)
    except Exception as e:
        print('could not read existing items, uploading as is:', e); skip, have = set(), []
    known = {h['id'] for h in have}; cnt = {}
    for h in have: cnt[(h['country'], h['industry'])] = cnt.get((h['country'], h['industry']), 0) + 1
    cap = CFG.get('max_items_per_bucket_day', 6); keep = []
    for it in items:
        k = (it['country'], it['industry'])
        if it['id'] in skip or it['id'] in known: continue
        if cnt.get(k, 0) >= cap: continue
        cnt[k] = cnt.get(k, 0) + 1; keep.append(it)
    print(f'{len(items)} fetched, {len(keep)} new after skipping known/off-topic/over-cap')
    items = keep
    # ignore-duplicates: never overwrite an item that already has AI summaries
    if items:
        print('raw items', len(items), call('POST', 'news_items?on_conflict=id', items, 'resolution=ignore-duplicates,return=minimal')[0])
    mk = json.load(open(os.path.join(WORK, 'markets.json'), encoding='utf-8')) if os.path.exists(os.path.join(WORK, 'markets.json')) else {}
    if mk:
        rows = [{'sym': k, 'name_zh': v['zh'], 'name_en': v['en'], 'x': v['x'], 'v': v['v'], 'src': v.get('src', ''), 'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()} for k, v in mk.items()]
        print('markets', call('POST', 'market_snap?on_conflict=sym', rows, 'resolution=merge-duplicates,return=minimal')[0])
    cutoff = (datetime.date.today() - datetime.timedelta(days=CFG['keep_days'])).isoformat()
    deep_cutoff = (datetime.date.today() - datetime.timedelta(days=CFG.get('keep_days_deep', 180))).isoformat()
    try:  # deep analyses are kept longer: they are the history behind the timeline of related news
        print('cleanup', call('DELETE', 'news_items?day=lt.' + cutoff + '&depth=neq.deep', prefer='return=minimal')[0],
              call('DELETE', 'news_items?day=lt.' + deep_cutoff, prefer='return=minimal')[0])
    except Exception:  # news_v2.sql not applied yet (no depth column)
        print('cleanup', call('DELETE', 'news_items?day=lt.' + cutoff, prefer='return=minimal')[0])
    meta = {'k': 'last_run', 'v': {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'items': len(items), 'status': 'ok'}}
    print('meta', call('POST', 'news_meta?on_conflict=k', [meta], 'resolution=merge-duplicates,return=minimal')[0])

def main():
    if '--raw' in sys.argv:
        return main_raw()
    cur = json.load(open(os.path.join(WORK, 'curated.json'), encoding='utf-8'))
    mk = json.load(open(os.path.join(WORK, 'markets.json'), encoding='utf-8')) if os.path.exists(os.path.join(WORK, 'markets.json')) else {}
    items = cur.get('items', [])
    for it in items:
        for f in ('id', 'title_zh', 'title_en', 'summary_zh', 'summary_en'):
            if not it.get(f):
                sys.exit(f'item {it.get("id")} missing {f}')
    if items:
        for it in items:  # enrich existing rows only (PATCH keeps day/url/source from the raw upload)
            fields = {k: v for k, v in it.items() if k in ('title_zh', 'summary_zh', 'summary_en', 'impact_zh', 'impact_en', 'tags', 'chart_sym', 'story_key')}
            call('PATCH', 'news_items?id=eq.' + it['id'], fields, 'return=minimal')
        print('enriched', len(items))
    if cur.get('stories'):
        st = [{**s, 'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()} for s in cur['stories']]
        print('stories', call('POST', 'news_story?on_conflict=key', st, 'resolution=merge-duplicates,return=minimal')[0])
    print('done')

if __name__ == '__main__':
    main()
