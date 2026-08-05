// 誠毅淨值日報 / 誠毅基金 Service Worker
// 內容更新時請調高版本號以觸發更新
const VERSION = 'v6';
const SHELL = 'shell-' + VERSION;
const SHELL_FILES = [
  './',
  './index.html',
  './client.html',
  './manifest.webmanifest',
  './client.webmanifest',
  './html2canvas.min.js',
  './icons/icon-192.png',
  './icons/icon-512.png'
];

// 動態內容：優先網路、失敗回快取（線上永遠最新、離線可看最後一次）
const NETWORK_FIRST = /(?:data\.json|funds_client\.json|funds_master\.json|client\.html|index\.html)$/;

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

  if(NETWORK_FIRST.test(url.pathname)){
    e.respondWith(
      fetch(req).then(res => {
        const copy = res.clone();
        caches.open(SHELL).then(c => c.put(req, copy));
        return res;
      }).catch(() => caches.match(req).then(r => r || caches.match('./client.html')))
    );
    return;
  }

  // 其他靜態殼層：優先快取
  e.respondWith(caches.match(req).then(r => r || fetch(req)));
});
