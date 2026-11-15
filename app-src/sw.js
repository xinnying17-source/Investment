// Offline cache for the app shell. Bump VERSION when files change.
const VERSION='ig-v5';
const SHELL=['./','./index.html','./manifest.webmanifest','./config.js','./cloud.js','./vendor/supabase.js','./icons/icon-192.png','./icons/icon-512.png','./icons/apple-touch-icon.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(VERSION).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()));});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==VERSION).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',e=>{const r=e.request;if(r.method!=='GET')return;const u=new URL(r.url);if(u.origin!==location.origin)return;
  if(r.mode==='navigate'||u.pathname.endsWith('/')||u.pathname.endsWith('.html')||u.pathname.endsWith('config.js')){
    e.respondWith(fetch(r).then(res=>{const c=res.clone();caches.open(VERSION).then(x=>x.put(r,c));return res;}).catch(()=>caches.match(r).then(m=>m||caches.match('./index.html'))));return;}
  e.respondWith(caches.match(r).then(m=>m||fetch(r).then(res=>{const c=res.clone();caches.open(VERSION).then(x=>x.put(r,c));return res;})));});

self.addEventListener('push',e=>{let d={};try{d=e.data?e.data.json():{};}catch(_){d={body:e.data&&e.data.text()};}
  e.waitUntil(self.registration.showNotification(d.title||'投资白话地图',{body:d.body||'',icon:'icons/icon-192.png',badge:'icons/icon-192.png',tag:'ig-daily',data:{url:d.url||'./#today'}}));});
self.addEventListener('notificationclick',e=>{e.notification.close();const u=new URL((e.notification.data&&e.notification.data.url)||'./#today',self.registration.scope).href;
  e.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(cs=>{for(const c of cs){if('focus' in c){c.navigate&&c.navigate(u);return c.focus();}}return clients.openWindow(u);}));});
