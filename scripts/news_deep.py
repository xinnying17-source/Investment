"""Deep news analysis (GitHub Actions, hourly, free Gemini).

For the most important events of the day (several outlets reporting the same story count as one event):
 1. resolve the publisher links and extract the full article text (trafilatura), up to 3 articles per event;
 2. split the text into numbered sentences [s1], [s2] ...;
 3. Gemini writes a full article in Chinese and English, key points, a 'what it means' note and the
    stocks that may be affected (only from news/stocks.json). EVERY sentence must cite the source sentences it uses;
 4. a program checks every sentence: cited ids must exist and every number must appear in the cited sentences
    (unit changes such as 1.2 billion = 12亿 allowed). Failing sentences are removed; if too many fail the event is
    rewritten once with the problems listed, otherwise it stays a short headline summary;
 5. related earlier news is linked by keyword overlap in the database (no AI tokens);
 6. duplicates of the same event are hidden (depth='dup').

Private app: the owner reads full Chinese write-ups of articles for personal use; the text is not republished.
Needs INGEST_KEY and GEMINI_API_KEY. Writes into news_items (columns from supabase/news_v2.sql).
"""
import json, os, re, sys, time, datetime, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from news_summarize_gemini import sb, gemini, nums, words, WORDNUM, MONTHS  # shared helpers
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, 'news', '_work')
STOCKS = {s['y']: s for s in json.load(open(os.path.join(ROOT, 'news', 'stocks.json'), encoding='utf-8'))['stocks']}
PER_RUN = int(os.environ.get('DEEP_PER_RUN', '6'))      # events analysed per hourly run
PER_DAY = int(os.environ.get('DEEP_PER_DAY', '45'))     # cap per Malaysian day
MAX_SENT = 140                                          # source sentences sent to Gemini (~5-6k tokens)
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
      'Accept-Language': 'en-MY,en;q=0.9'}

# ------------------------------------------------------------------ fetching full text
def http(url, t=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=t) as r:
        return r.read().decode('utf-8', 'ignore'), r.geturl()

SPLIT = re.compile(r'(?<=[.!?])["”’)]?\s+(?=[A-Z0-9“"(])')
def sentences(text):
    out = []
    for para in text.split('\n'):
        para = para.strip()
        if len(para) < 25: continue
        out += [s.strip() for s in SPLIT.split(para) if len(s.strip()) > 15]
    return out

# ------------------------------------------------------------------ clustering
def cluster(cands):
    """Group headlines about the same story (strong word overlap)."""
    groups = []
    for c in cands:
        w = words(c['title'])
        for g in groups:
            gw = g['w']
            if len(w & gw) >= 3 and len(w & gw) / max(1, min(len(w), len(gw))) >= 0.5:
                g['items'].append(c); g['w'] |= w; break
        else:
            groups.append({'w': set(w), 'items': [c]})
    return groups

# ------------------------------------------------------------------ checking
def allowed_from(text):
    t = text.lower(); a = set(nums(t))
    for i, m in enumerate(MONTHS):
        if m in t: a.add(i + 1)
    for w, v in WORDNUM.items():
        if re.search(r'\b' + w + r'\b', t): a.add(v)
    for q in re.findall(r'\bq([1-4])\b', t): a.add(float(q))
    return a

def num_ok(sentence, allowed):
    for n in nums(sentence):
        if not any(abs(n - a * 10 ** k) <= 1e-6 * max(1, abs(n)) for a in allowed for k in range(-4, 5)):
            return False, n
    return True, None

def check_lines(lines, sid):
    """lines: [{t, c:[ids]}] -> (kept lines, problems). Each line needs valid citations and only cited numbers."""
    kept, probs = [], []
    for ln in lines or []:
        if not isinstance(ln, dict) or not str(ln.get('t', '')).strip(): continue
        t = str(ln['t']).strip(); cites = [str(x).lstrip('s') for x in (ln.get('c') or [])]
        cites = [c for c in cites if c.isdigit() and int(c) in sid]
        if not cites:
            probs.append(f'no valid citation: "{t[:60]}"'); continue
        ok, n = num_ok(t, allowed_from(' '.join(sid[int(c)] for c in cites)))
        if not ok:
            probs.append(f'number {n:g} not in cited sentences {cites}: "{t[:60]}"'); continue
        kept.append({'t': t, 'c': [int(c) for c in cites]})
    return kept, probs

def check(res, sid):
    out, probs, total = {}, [], 0
    for lang in ('zh', 'en'):
        paras = []
        for p in (res.get('article_' + lang) or []):
            total += len(p or []); k, pr = check_lines(p, sid); probs += pr
            if k: paras.append(k)
        out['article_' + lang] = paras
        lead, pr = check_lines(res.get('lead_' + lang), sid); probs += pr; total += len(res.get('lead_' + lang) or [])
        out['lead_' + lang] = lead
    pts = []
    for p in res.get('points') or []:
        if not isinstance(p, dict): continue
        kz, prz = check_lines([{'t': p.get('zh', ''), 'c': p.get('c')}], sid)
        ke, pre = check_lines([{'t': p.get('en', ''), 'c': p.get('c')}], sid)
        total += 2; probs += prz + pre
        if kz and ke: pts.append({'zh': kz[0]['t'], 'en': ke[0]['t'], 'c': kz[0]['c']})
    out['points'] = pts[:6]
    dropped = len(probs) / max(1, total)
    return out, probs, dropped

# ------------------------------------------------------------------ writing
RULES = """You write in-depth news articles for ONE private reader: a Malaysian beginner investor.
SOURCE: numbered sentences from the original article(s) are given as {"s": id, "t": text}. They are your ONLY source of facts.
STRICT RULES:
- Every sentence you write must list the ids of the source sentences that support it in "c". A sentence with no support must not be written.
- Never add facts, names, numbers, dates, quotes, causes or outcomes that are not in the cited sentences. Keep forecasts/claims/plans as forecasts/claims/plans and say who said them.
- Chinese: natural Simplified Chinese, short paragraphs. Keep company names, people, organisations, products, tickers and technical terms in ENGLISH (e.g. Nvidia, Bank Negara Malaysia, OPR, Bursa Malaysia, Jensen Huang); for common terms you may add Chinese in brackets the first time, e.g. 隔夜政策利率（OPR）. Do not force-translate proper names.
- Cover the whole story: what happened, who, numbers, why (as reported), reactions, what comes next (as reported). Do not shorten into a summary; 4-8 paragraphs.
- 'meaning' is YOUR analysis for a beginner: what this means for markets, sectors and ordinary investors in Malaysia. It may use general economic knowledge but no new facts about this event; write it as analysis.
- 'stocks': only symbols from the ALLOWED STOCKS list, only when the story clearly concerns that company or its sector; effect is up/down/mixed/watch, with a one-sentence reason. Empty list if none fit.
- 'keywords': 4-8 lowercase English names/topics for linking related news over time (companies, people, institutions, themes like "opr", "palm oil", "data centre")."""

def write(src_sents, event, industries, feedback=None):
    allowed = '\n'.join(f"{y}: {s['name']} ({s['sector']})" for y, s in STOCKS.items())
    fb = ('\nYOUR PREVIOUS VERSION FAILED THE CHECKER. Fix these problems (drop a claim rather than guess):\n' + '\n'.join('- ' + p for p in feedback[:25])) if feedback else ''
    prompt = f"""{RULES}{fb}
ALLOWED STOCKS:
{allowed}
EVENT HEADLINES: {json.dumps([i['title'] for i in event['items']][:5], ensure_ascii=False)}
Return JSON:
{{"title_zh":"...","title_en":"...",
"lead_zh":[{{"t":"sentence","c":[ids]}}],"lead_en":[...],            // 2 sentences: the core of the story
"article_zh":[[{{"t":"sentence","c":[ids]}}, ...], ...],"article_en":[[...]],   // paragraphs of sentences
"points":[{{"zh":"key fact or number","en":"...","c":[ids]}}],          // 3-6
"meaning_zh":"3-5 sentences","meaning_en":"...",
"stocks":[{{"y":"symbol from list","effect":"up|down|mixed|watch","zh":"reason","en":"reason"}}],
"keywords":["..."],"industry":"one of {industries}","irrelevant":false}}   // irrelevant=true if this is not about business/markets/economy
SOURCE SENTENCES:
""" + '\n'.join(json.dumps({'s': i, 't': t}, ensure_ascii=False) for i, t in src_sents)
    return gemini(prompt, 0.2)

# ------------------------------------------------------------------ main
def related_ids(keywords, exclude, since):
    if not keywords: return []
    kw = ','.join('"' + k.replace('"', '') + '"' for k in keywords[:8])
    rows = sb('GET', f'news_items?select=id,keywords,day&depth=eq.deep&day=gte.{since}&keywords=ov.{{{urllib.parse.quote(kw)}}}&order=day.desc&limit=40')
    scored = sorted(((len(set(r['keywords']) & set(keywords)), r['day'], r['id']) for r in rows if r['id'] not in exclude), reverse=True)
    return [i for s, d, i in scored if s >= 2][:6]

def main():
    if not os.environ.get('GEMINI_API_KEY') or not os.environ.get('INGEST_KEY'):
        print('GEMINI_API_KEY / INGEST_KEY missing: deep analysis skipped'); return
    myt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    today = myt.date().isoformat()
    try:
        done_today = sb('GET', f'news_items?select=id&day=eq.{today}&depth=eq.deep')
    except Exception as e:
        print('::warning::news_v2.sql not applied yet (no depth column?):', str(e)[:200]); return
    room = min(PER_RUN, PER_DAY - len(done_today))
    if room <= 0: print('daily deep-analysis cap reached'); return
    data = json.load(open(os.path.join(WORK, 'candidates.json'), encoding='utf-8'))
    direct = data.get('direct') or []
    heads = data['items']  # Google News headlines: used to judge importance and to hide duplicates
    for c in heads: c['title'] = c['title'].rsplit(' - ', 1)[0] if c.get('source') and c['title'].endswith(' - ' + c['source']) else c['title']
    known = {r['id']: r['depth'] for r in sb('GET', 'news_items?select=id,depth&id=in.(' + ','.join(d['id'] for d in direct) + ')')} if direct else {}
    groups = cluster([dict(d, direct=True) for d in direct] + [dict(h, direct=False) for h in heads])
    events = []
    for g in groups:
        ds = [i for i in g['items'] if i['direct']]
        if not ds or any(known.get(i['id']) in ('deep', 'nodeep', 'dup') for i in ds): continue
        outlets = {i.get('source') for i in g['items']}
        events.append((len(outlets), 1 if ds[0]['country'] == 'my' else 0, g, ds))
    events.sort(key=lambda e: (-e[0], -e[1]))
    print(f'{len(direct)} full-text articles, {len(heads)} headlines -> {len(events)} new events; analysing up to {room}')
    inds = {c: [i['key'] for i in v] for c, v in json.load(open(os.path.join(ROOT, 'news', 'buckets.json'), encoding='utf-8'))['industries'].items()}
    since = (myt.date() - datetime.timedelta(days=180)).isoformat()
    analysed = 0
    for score, _, g, ds in events:
        if analysed >= room: break
        lead = ds[0]; texts, srcs = [], []
        for it in ds[:3]:
            try:
                html_, final = http(it['url']); import trafilatura
                txt = trafilatura.extract(html_, favor_precision=True) or ''
            except Exception:
                txt, final = '', it['url']
            if len(txt) >= 900:
                texts.append(txt); srcs.append({'outlet': it.get('source', ''), 'title': it['title'], 'url': final})
            time.sleep(0.5)
        base = {'id': lead['id'], 'day': today, 'country': lead['country'], 'industry': inds[lead['country']][0],
                'published_at': lead.get('published'), 'source': lead.get('source', ''), 'url': lead['url'], 'title_en': lead['title']}
        if not texts:
            sb('POST', 'news_items?on_conflict=id', [dict(base, depth='nodeep')], 'resolution=merge-duplicates,return=minimal'); continue
        sid, owner, n = {}, {}, 0
        per = MAX_SENT // len(texts)
        for si, t in enumerate(texts):
            for x in sentences(t)[:per]:
                n += 1; sid[n] = x; owner[n] = si
        try:
            res = write(list(sid.items()), g, inds[lead['country']])
            if res.get('irrelevant'):
                sb('POST', 'news_items?on_conflict=id', [dict(base, depth='nodeep')], 'resolution=merge-duplicates,return=minimal')
                print('not business news, skipped:', lead['title'][:60]); continue
            out, probs, dropped = check(res, sid)
            if dropped > 0.25 or len(out['article_zh']) < 2:
                print(f'rewrite ({dropped:.0%} failed): {lead["title"][:60]}')
                res = write(list(sid.items()), g, inds[lead['country']], feedback=probs)
                out, probs, dropped = check(res, sid)
        except RuntimeError as e:
            print('::warning::Gemini unavailable, stopping this run:', str(e)[:200]); break
        if dropped > 0.25 or len(out['article_zh']) < 2 or len(out['article_en']) < 2:
            sb('POST', 'news_items?on_conflict=id', [dict(base, depth='nodeep')], 'resolution=merge-duplicates,return=minimal')
            print(f'rejected after rewrite ({dropped:.0%} unsupported): {lead["title"][:60]}'); continue
        stocks = [{'y': x['y'], 'code': STOCKS[x['y']]['code'], 'name': STOCKS[x['y']]['name'], 'effect': x.get('effect') if x.get('effect') in ('up', 'down', 'mixed', 'watch') else 'watch',
                   'zh': str(x.get('zh', ''))[:200], 'en': str(x.get('en', ''))[:200]} for x in (res.get('stocks') or []) if isinstance(x, dict) and x.get('y') in STOCKS][:6]
        kws = sorted({str(k).lower().strip()[:40] for k in (res.get('keywords') or []) if str(k).strip()})[:8]
        for p in out['article_zh'] + out['article_en']:
            for ln in p: ln['src'] = sorted({owner[c] for c in ln['c']})
        row = dict(base, depth='deep', industry=res.get('industry') if res.get('industry') in inds[lead['country']] else base['industry'],
                   title_zh=str(res.get('title_zh', ''))[:200],
                   summary_zh=''.join(l['t'] for l in out['lead_zh']) or None, summary_en=' '.join(l['t'] for l in out['lead_en']) or None,
                   article_zh=json.dumps(out['article_zh'], ensure_ascii=False), article_en=json.dumps(out['article_en'], ensure_ascii=False),
                   points=out['points'], meaning_zh=str(res.get('meaning_zh', ''))[:1500], meaning_en=str(res.get('meaning_en', ''))[:1500],
                   stocks=stocks, sources=srcs, keywords=kws, tags=[],
                   related=related_ids(kws, {i['id'] for i in g['items']}, since))
        sb('POST', 'news_items?on_conflict=id', [row], 'resolution=merge-duplicates,return=minimal')
        dups = [i['id'] for i in g['items'] if i['id'] != lead['id']]
        if dups: sb('PATCH', 'news_items?id=in.(' + ','.join(dups) + ')', {'depth': 'dup'}, 'return=minimal')
        analysed += 1
        print(f'deep ✓ [{score} outlets] {len(texts)} article(s), {sum(len(p) for p in out["article_zh"])} zh sentences, {len(probs)} removed, {len(stocks)} stocks: {lead["title"][:60]}')
    print(f'analysed {analysed} events')

if __name__ == '__main__':
    main()
