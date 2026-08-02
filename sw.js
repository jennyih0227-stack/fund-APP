// 誠毅淨值日報 Service Worker
// 內容更新時請調高版本號以觸發更新
const VERSION = 'v5';
const SHELL = 'shell-' + VERSION;
const SHELL_FILES = [
  './',
  './index.html',
  './manifest.webmanifest',
  './html2canvas.min.js',
  './icons/icon-192.png',
  './icons/icon-512.png'
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== SHELL).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if(req.method !== 'GET') return;
  const url = new URL(req.url);

  // data.json：優先網路，失敗回快取（離線可看最後一次資料）
  if(url.pathname.endsWith('data.json')){
    e.respondWith(
      fetch(req).then(res => {
        const copy = res.clone();
        caches.open(SHELL).then(c => c.put('./data.json', copy));
        return res;
      }).catch(() => caches.match('./data.json'))
    );
    return;
  }

  // 其他（殼層）：優先快取
  e.respondWith(caches.match(req).then(r => r || fetch(req)));
});
