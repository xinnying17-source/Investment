"""Record tonight's GitHub Actions result in Supabase (news_meta 'health') so the Claude task knows whether a fix is needed."""
import json, os, datetime, urllib.request, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
conf = open(os.path.join(ROOT, 'docs', 'config.js'), encoding='utf-8').read()
URL = re.search(r"SUPABASE_URL:\s*'([^']+)'", conf).group(1)
KEY = re.search(r"SUPABASE_ANON_KEY:\s*'([^']+)'", conf).group(1)
steps = {k: os.environ.get(k, '') for k in ('FETCH', 'UPLOAD', 'TEST')}
ok = all(v == 'success' for v in steps.values())
row = [{'k': 'health', 'v': {'at': datetime.datetime.utcnow().isoformat() + 'Z', 'ok': ok, 'steps': steps, 'run': os.environ.get('RUN_URL', '')}}]
req = urllib.request.Request(URL + '/rest/v1/news_meta?on_conflict=k', data=json.dumps(row).encode(), method='POST',
                             headers={'apikey': KEY, 'Content-Type': 'application/json', 'x-ingest-key': os.environ.get('INGEST_KEY', ''),
                                      'Prefer': 'resolution=merge-duplicates,return=minimal'})
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        print('health', 'ok' if ok else 'FAILED', r.status)
except Exception as e:
    print('could not record health:', e)
