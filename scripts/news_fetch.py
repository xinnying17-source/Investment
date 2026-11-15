"""Fetch candidate headlines (last ~24h) for every country/industry bucket, plus 10 days of market closes.

Writes news/_work/candidates.json and news/_work/markets.json (git-ignored scratch).
Sources: Google News RSS search (headlines + links only), Yahoo chart API with Stooq as fallback.
Run:  python3 scripts/news_fetch.py
"""
import json, os, sys, time, hashlib, urllib.parse, urllib.request, csv, io
import xml.etree.ElementTree as ET
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, 'news', 'buckets.json'), encoding='utf-8'))
WORK = os.path.join(ROOT, 'news', '_work'); os.makedirs(WORK, exist_ok=True)
UA = {'User-Agent': 'Mozilla/5.0 (compatible; investing-guide-news/1.0)'}

def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def rss(country, q):
    p = CFG['countries'][country]['rss']
    url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q': q + ' when:1d', **p})
    root = ET.fromstring(get(url))
    out = []
    for it in root.iter('item'):
        title = (it.findtext('title') or '').strip()
        src = it.find('source')
        out.append({'title': title, 'url': (it.findtext('link') or '').strip(), 'published': it.findtext('pubDate'),
                    'source': src.text.strip() if src is not None and src.text else ''})
    return out[:15]

def market(m):
    try:
        raw = json.loads(get('https://query1.finance.yahoo.com/v8/finance/chart/' + urllib.parse.quote(m['yahoo']) + '?range=1mo&interval=1d'))
        r = raw['chart']['result'][0]; ts = r['timestamp']; cl = r['indicators']['quote'][0]['close']
        pts = [(time.strftime('%Y-%m-%d', time.gmtime(t)), c) for t, c in zip(ts, cl) if c is not None][-10:]
        if len(pts) >= 2:
            return {'x': [p[0] for p in pts], 'v': [round(p[1], 4) for p in pts], 'src': 'Yahoo Finance'}
    except Exception as e:
        print('yahoo fail', m['sym'], e, file=sys.stderr)
    try:
        raw = get('https://stooq.com/q/d/l/?' + urllib.parse.urlencode({'s': m['stooq'], 'i': 'd'})).decode()
        rows = [r for r in csv.DictReader(io.StringIO(raw)) if r.get('Close') not in (None, '', 'null')]
        if len(rows) >= 2:
            rows = rows[-10:]
            return {'x': [r['Date'] for r in rows], 'v': [round(float(r['Close']), 4) for r in rows], 'src': 'Stooq'}
    except Exception as e:
        print('stooq fail', m['sym'], e, file=sys.stderr)
    return None

def main():
    cands, seen, errors = [], set(), []
    for country, inds in CFG['industries'].items():
        for ind in inds:
            try:
                items = rss(country, ind['q'])
            except Exception as e:
                errors.append(f'{country}/{ind["key"]}: {e}'); items = []
            for it in items:
                k = it['title'].lower()[:90]
                if not it['url'] or k in seen:
                    continue
                seen.add(k)
                it.update({'id': hashlib.sha1(it['url'].encode()).hexdigest()[:16], 'country': country, 'industry': ind['key']})
                cands.append(it)
            time.sleep(0.5)
    mk = {}
    for m in CFG['markets']:
        d = market(m)
        if d:
            mk[m['sym']] = {**d, 'zh': m['zh'], 'en': m['en']}
    json.dump({'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'items': cands, 'errors': errors},
              open(os.path.join(WORK, 'candidates.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(mk, open(os.path.join(WORK, 'markets.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{len(cands)} candidate headlines, {len(mk)}/{len(CFG["markets"])} markets, {len(errors)} bucket errors')
    if errors:
        print('\n'.join(errors[:10]), file=sys.stderr)

if __name__ == '__main__':
    main()
