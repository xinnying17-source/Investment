"""Upload curated news + markets + storylines to Supabase and delete items older than keep_days.

Input: news/_work/curated.json  {"items":[...], "stories":[...]}  and news/_work/markets.json
Item fields: id, day (YYYY-MM-DD), country, industry, published_at, source, url, title_zh, title_en,
             summary_zh, summary_en, impact_zh, impact_en, tags [{k:'up'|'down'|'watch', zh, en}], chart_sym, story_key
Story fields: key, country, industry, title_zh, title_en, story_zh, story_en  (story_* = list of {d, zh/en text})
Writes require the x-ingest-key header; in the cloud session the network proxy injects it.
Locally you can set INGEST_KEY in the environment instead.
"""
import json, os, sys, datetime, urllib.request
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

def main():
    cur = json.load(open(os.path.join(WORK, 'curated.json'), encoding='utf-8'))
    mk = json.load(open(os.path.join(WORK, 'markets.json'), encoding='utf-8')) if os.path.exists(os.path.join(WORK, 'markets.json')) else {}
    items = cur.get('items', [])
    for it in items:
        for f in ('title_zh', 'title_en', 'summary_zh', 'summary_en', 'url', 'country', 'industry', 'day'):
            if not it.get(f):
                sys.exit(f'item {it.get("id")} missing {f}')
    if items:
        print('items', call('POST', 'news_items?on_conflict=id', items, 'resolution=merge-duplicates,return=minimal')[0])
    if cur.get('stories'):
        st = [{**s, 'updated_at': datetime.datetime.utcnow().isoformat() + 'Z'} for s in cur['stories']]
        print('stories', call('POST', 'news_story?on_conflict=key', st, 'resolution=merge-duplicates,return=minimal')[0])
    if mk:
        rows = [{'sym': k, 'name_zh': v['zh'], 'name_en': v['en'], 'x': v['x'], 'v': v['v'], 'src': v.get('src', ''), 'updated_at': datetime.datetime.utcnow().isoformat() + 'Z'} for k, v in mk.items()]
        print('markets', call('POST', 'market_snap?on_conflict=sym', rows, 'resolution=merge-duplicates,return=minimal')[0])
    cutoff = (datetime.date.today() - datetime.timedelta(days=CFG['keep_days'])).isoformat()
    print('cleanup', call('DELETE', 'news_items?day=lt.' + cutoff, prefer='return=minimal')[0])
    meta = {'k': 'last_run', 'v': {'at': datetime.datetime.utcnow().isoformat() + 'Z', 'items': len(items), 'status': cur.get('status', 'ok')}}
    print('meta', call('POST', 'news_meta?on_conflict=k', [meta], 'resolution=merge-duplicates,return=minimal')[0])

if __name__ == '__main__':
    main()
