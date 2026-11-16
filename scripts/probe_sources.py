"""Diagnostic (run in GitHub Actions): which news sources give us full article text?
For each RSS feed: fetch it, then try to extract the full text of the first 3 articles with trafilatura.
Also tests decoding Google News links to the publisher URL. Prints a table; changes nothing."""
import json, sys, time, urllib.request, xml.etree.ElementTree as ET
import trafilatura
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
      'Accept-Language': 'en-MY,en;q=0.9'}
FEEDS = {
 'my:TheStar-business': 'https://www.thestar.com.my/rss/Business/Business-News',
 'my:MalayMail-money': 'https://www.malaymail.com/feed/rss/money',
 'my:FMT-business': 'https://www.freemalaysiatoday.com/category/category/business/feed/',
 'my:NST-business': 'https://www.nst.com.my/feed/business',
 'my:Bernama': 'https://www.bernama.com/en/rssfeed.php',
 'my:BusinessToday': 'https://www.businesstoday.com.my/feed/',
 'my:TheSun-business': 'https://thesun.my/rss/business',
 'my:TheEdge': 'https://theedgemalaysia.com/rss',
 'my:MalaysiaKini-business': 'https://www.malaysiakini.com/rss/en/news.rss',
 'asia:CNA-business': 'https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6936',
 'asia:SCMP-business': 'https://www.scmp.com/rss/92/feed',
 'gl:CNBC-top': 'https://www.cnbc.com/id/100003114/device/rss/rss.html',
 'gl:CNBC-economy': 'https://www.cnbc.com/id/20910258/device/rss/rss.html',
 'gl:CNBC-markets': 'https://www.cnbc.com/id/15839069/device/rss/rss.html',
 'gl:MarketWatch': 'https://feeds.content.dowjones.io/public/rss/mw_topstories',
 'gl:Yahoo-Finance': 'https://finance.yahoo.com/news/rssindex',
 'gl:Investing.com': 'https://www.investing.com/rss/news.rss',
 'gl:Fed-press': 'https://www.federalreserve.gov/feeds/press_all.xml',
 'gl:BBC-business': 'https://feeds.bbci.co.uk/news/business/rss.xml',
 'gl:Guardian-business': 'https://www.theguardian.com/uk/business/rss',
 'gl:AP-business': 'https://apnews.com/hub/business?format=rss',
 'gl:CoinDesk': 'https://www.coindesk.com/arc/outboundfeeds/rss/',
}

def get(url, t=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=t) as r:
        return r.read(), r.geturl()

def items(xml):
    root = ET.fromstring(xml); out = []
    for it in root.iter():
        if it.tag.split('}')[-1] not in ('item', 'entry'): continue
        link = ''
        for c in it:
            n = c.tag.split('}')[-1]
            if n == 'link': link = (c.text or '').strip() or c.get('href', '')
        title = next(((c.text or '').strip() for c in it if c.tag.split('}')[-1] == 'title'), '')
        if link: out.append((title, link))
    return out

def article(url):
    try:
        html, final = get(url, 20)
    except Exception as e:
        return 0, f'{type(e).__name__} {getattr(e, "code", "")}'
    txt = trafilatura.extract(html.decode('utf-8', 'ignore'), favor_precision=True) or ''
    return len(txt), (txt[:90].replace('\n', ' ') if txt else 'no text extracted')

rows = []
for name, url in FEEDS.items():
    try:
        xml, _ = get(url); its = items(xml)
    except Exception as e:
        rows.append((name, 'FEED FAIL', f'{type(e).__name__} {getattr(e, "code", "")}', '')); continue
    lens = []
    for t, l in its[:3]:
        n, info = article(l); lens.append(n); time.sleep(0.5)
    ok = sum(1 for n in lens if n > 1200)
    rows.append((name, f'{len(its)} items', f'full text {ok}/{len(lens)}', 'chars ' + ','.join(map(str, lens))))
for r in rows: print(' | '.join(r))
RESULT = {'feeds': [list(r) for r in rows], 'gnews': []}

# Google News links -> publisher URL
print('\n--- Google News decode test')
try:
    from googlenewsdecoder import gnewsdecoder
    xml, _ = get('https://news.google.com/rss/search?q=Bursa+Malaysia+when:1d&hl=en-MY&gl=MY&ceid=MY:en')
    for t, l in items(xml)[:6]:
        try:
            d = gnewsdecoder(l, interval=1)
            u = d.get('decoded_url') if d.get('status') else None
        except Exception as e:
            u = None
        n, info = article(u) if u else (0, 'decode failed')
        print(f'{n:6d} chars | {(u or "-")[:80]} | {t[:60]}'); RESULT['gnews'].append([n, (u or '-')[:120], t[:80]])
except Exception as e:
    print('decoder unavailable:', e)

# save to Supabase (news_meta k='probe') so results are readable without the Actions log
import os, re as _re
conf = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs', 'config.js'), encoding='utf-8').read()
U = _re.search(r"SUPABASE_URL:\s*'([^']+)'", conf).group(1); K = _re.search(r"SUPABASE_ANON_KEY:\s*'([^']+)'", conf).group(1)
req = urllib.request.Request(U + '/rest/v1/news_meta?on_conflict=k', method='POST', data=json.dumps([{'k': 'probe', 'v': RESULT}]).encode(),
      headers={'apikey': K, 'Content-Type': 'application/json', 'Prefer': 'resolution=merge-duplicates,return=minimal', 'x-ingest-key': os.environ.get('INGEST_KEY', '')})
print('saved probe result', urllib.request.urlopen(req, timeout=20).status)
