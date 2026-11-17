"""Fetch candidate headlines (last ~24h) for every country/industry bucket, plus 10 days of market closes.

Writes news/_work/candidates.json and news/_work/markets.json (git-ignored scratch).
Sources: Google News RSS search (headlines + links only), Yahoo chart API with Stooq as fallback.
Run:  python3 scripts/news_fetch.py
"""
import json, os, re, html, sys, time, hashlib, datetime, email.utils, urllib.parse, urllib.request, csv, io
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
                    'source': src.text.strip() if src is not None and src.text else '', 'related': related(it.findtext('description') or '', title)})
    return out[:15]

def related(desc, title):
    """Other outlets' headlines for the same story (Google News clusters them in the description). Used as extra facts."""
    heads = [html.unescape(re.sub(r'<[^>]+>', '', h)).strip() for h in re.findall(r'<a [^>]*>(.*?)</a>', desc, re.S)]
    srcs = [html.unescape(re.sub(r'<[^>]+>', '', f)).strip() for f in re.findall(r'<font[^>]*>(.*?)</font>', desc, re.S)]
    out = []
    for i, h in enumerate(heads):
        if h and h.lower() not in title.lower():
            out.append(h + (' - ' + srcs[i] if i < len(srcs) and srcs[i] else ''))
    return out[:5]

def direct_items(max_age_h=36):
    """Articles from publishers whose RSS links open to the full text (used for deep analysis)."""
    out, seen = [], set()
    for f in CFG.get('direct_feeds', []):
        try:
            root = ET.fromstring(get(f['url']))
        except Exception as e:
            print('direct feed fail', f['name'], e, file=sys.stderr); continue
        for it in root.iter('item'):
            title = html.unescape((it.findtext('title') or '').strip()); link = (it.findtext('link') or '').strip()
            if not title or not link or link in seen: continue
            try:
                pub = email.utils.parsedate_to_datetime(it.findtext('pubDate'))
                if (datetime.datetime.now(datetime.timezone.utc) - pub).total_seconds() > max_age_h * 3600: continue
                pub = pub.isoformat()
            except Exception:
                pub = None
            seen.add(link)
            out.append({'id': hashlib.sha1(link.encode()).hexdigest()[:16], 'title': title, 'url': link, 'published': pub,
                        'source': f['name'], 'country': f['country']})
        time.sleep(0.3)
    return out

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
    direct = direct_items()
    mk = {}
    for m in CFG['markets']:
        d = market(m)
        if d:
            mk[m['sym']] = {**d, 'zh': m['zh'], 'en': m['en']}
    json.dump({'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'items': cands, 'direct': direct, 'errors': errors},
              open(os.path.join(WORK, 'candidates.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(mk, open(os.path.join(WORK, 'markets.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{len(direct)} direct articles (full-text sources), {len(cands)} candidate headlines, {len(mk)}/{len(CFG["markets"])} markets, {len(errors)} bucket errors')
    if errors:
        print('\n'.join(errors[:10]), file=sys.stderr)

if __name__ == '__main__':
    main()
