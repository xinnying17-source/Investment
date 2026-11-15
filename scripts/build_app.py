"""Build the installable web app (docs/) from investment-guide.html + app-src/.

Run:  python3 scripts/build_app.py
GitHub Pages serves the docs/ folder.
"""
import os, re, shutil, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC, APP, OUT = os.path.join(ROOT, 'investment-guide.html'), os.path.join(ROOT, 'app-src'), os.path.join(ROOT, 'docs')
os.makedirs(os.path.join(OUT, 'vendor'), exist_ok=True)
body = open(SRC, encoding='utf-8').read()
title = re.search(r'<title>(.*?)</title>', body).group(1)
body = re.sub(r'<title>.*?</title>\n?', '', body, count=1)
body = re.sub(r'<meta name="claude:viewport-fit-sides"[^>]*>\n?', '', body, count=1)
head = f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{title}</title>
<meta name="description" content="投资新手的白话学习 App：概念地图、真实案例图表、组合类型、5 年投资模拟器。">
<meta name="theme-color" content="#17302A">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" type="image/png" href="icons/favicon.png">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="投资地图">
<style>:root{{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}body{{margin:0;font:14px/1.5 system-ui,sans-serif}}img{{max-width:100%}}[hidden]{{display:none!important}}</style>
</head>
<body>
<script src="config.js"></script>
<script src="vendor/supabase.js"></script>
<script src="cloud.js"></script>
'''
tail = '''
<script>
if('serviceWorker' in navigator){window.addEventListener('load',()=>navigator.serviceWorker.register('sw.js').catch(()=>{}));}
</script>
</body>
</html>
'''
open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(head + body + tail)
for f in ['cloud.js', 'sw.js', 'manifest.webmanifest']:
    shutil.copy(os.path.join(APP, f), os.path.join(OUT, f))
if not os.path.exists(os.path.join(OUT, 'config.js')):  # keep the user's filled-in config
    shutil.copy(os.path.join(APP, 'config.js'), os.path.join(OUT, 'config.js'))
for f in os.listdir(os.path.join(APP, 'vendor')):
    shutil.copy(os.path.join(APP, 'vendor', f), os.path.join(OUT, 'vendor', f))
subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'make_icons.py'), os.path.join(OUT, 'icons')], check=True)
open(os.path.join(OUT, '.nojekyll'), 'w').close()
print('built', OUT)
