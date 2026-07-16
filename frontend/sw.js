/* BiliSum Service Worker — proxies B站 API requests to avoid CORS + cookie issues */
const PROXY_BASE = 'http://127.0.0.1:8000/api/bili/proxy-fetch?url=';
const BILI_ORIGINS = /^https?:\/\/(api|www|s1|s2|i0|i1|i2)\.(bilibili|hdslb)\.com\//;

self.addEventListener('fetch', (event) => {
  const url = event.request.url;
  // Only intercept B站 API GET requests
  if (!BILI_ORIGINS.test(url)) return;
  if (event.request.method !== 'GET') return;

  const proxiedUrl = PROXY_BASE + encodeURIComponent(url);
  // Clone with same init but pointed at our proxy
  event.respondWith(
    fetch(proxiedUrl, {
      method: event.request.method,
      headers: event.request.headers,
      mode: 'cors',
      credentials: 'include',
    })
  );
});
