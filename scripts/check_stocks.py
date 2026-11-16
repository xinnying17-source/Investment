"""Verify every symbol in news/stocks.json against Yahoo Finance (runs in GitHub Actions).
Prints symbol, Yahoo's own name and last price, so a wrong code is obvious. Exit 1 if any symbol has no data.
Also writes news/_work/stock_prices.json (last 30 closes) for the app's stock mini-charts."""
import json, os, sys, time, urllib.parse, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = json.load(open(os.path.join(ROOT, 'news', 'stocks.json'), encoding='utf-8'))['stocks']
UA = {'User-Agent': 'Mozilla/5.0 (compatible; investing-guide/1.0)'}
out, bad = {}, []
for s in S:
    try:
        url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + urllib.parse.quote(s['y']) + '?range=3mo&interval=1d'
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            res = json.load(r)['chart']['result'][0]
        m = res['meta']; cl = res['indicators']['quote'][0]['close']
        pts = [(time.strftime('%Y-%m-%d', time.gmtime(t)), round(c, 4)) for t, c in zip(res['timestamp'], cl) if c is not None][-30:]
        yname = m.get('longName') or m.get('shortName') or '?'
        print(f"OK  {s['y']:10s} ours={s['name']:35s} yahoo={yname[:40]:40s} last={pts[-1][1] if pts else '-'} {m.get('currency','')}")
        out[s['y']] = {'x': [p[0] for p in pts], 'v': [p[1] for p in pts], 'cur': m.get('currency', ''), 'yname': yname}
    except Exception as e:
        print(f"BAD {s['y']:10s} {s['name']}: {type(e).__name__} {getattr(e, 'code', '')}"); bad.append(s['y'])
    time.sleep(0.3)
os.makedirs(os.path.join(ROOT, 'news', '_work'), exist_ok=True)
json.dump(out, open(os.path.join(ROOT, 'news', '_work', 'stock_prices.json'), 'w'), ensure_ascii=False)
print(f'{len(out)} ok, {len(bad)} bad: {bad}')
sys.exit(1 if bad else 0)
