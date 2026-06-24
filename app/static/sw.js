/**
 * 2026 WC 分析 - Service Worker
 *
 * 策略：
 * - 静态资源（HTML/CSS/JS）：Stale-While-Revalidate（秒开 + 后台更新）
 * - API GET（赛程/积分/球队/预测）：Network-First + 离线兜底
 * - API POST/PUT：失败时静默（不让 PWA 干扰后台管理）
 *
 * 缓存版本：wc2026-v6
 */

const CACHE_VERSION = 'wc2026-v6';  // v0.16.1: score recommendation v2.1 + acceptance green
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const API_CACHE = `${CACHE_VERSION}-api`;

// 关键静态资源（首屏必需）
const STATIC_ASSETS = [
  '/',
  '/static/index.html',
  '/static/css/styles.css',
  '/static/js/app.js',
  '/static/manifest.json',
  '/static/icons/favicon.svg',
  '/static/icons/icon-192.png',
];

// 不缓存的路径（管理员/调度接口）
const SKIP_CACHE_PATHS = [
  '/api/admin',
  '/api/sync',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      // 容忍单个资源失败
      return Promise.allSettled(
        STATIC_ASSETS.map((url) =>
          cache.add(url).catch((err) => console.warn('[SW] cache.add failed:', url, err))
        )
      );
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => !key.startsWith(CACHE_VERSION))
          .map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);

  // 跳过管理/同步接口
  if (SKIP_CACHE_PATHS.some((p) => url.pathname.startsWith(p))) {
    return;
  }

  // 跨域请求（如 Tailwind CDN）：网络优先，无网时忽略
  if (url.origin !== location.origin) {
    return;
  }

  // API 请求：Network-First，离线时返回缓存
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request));
    return;
  }

  // 静态资源：Stale-While-Revalidate
  event.respondWith(staleWhileRevalidate(request));
});

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(API_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }
    return new Response(JSON.stringify({ error: 'offline', message: '离线模式：暂无可用缓存' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);
  const networkFetch = fetch(request).then((response) => {
    if (response.ok) cache.put(request, response.clone());
    return response;
  }).catch(() => null);
  return cached || (await networkFetch) || new Response('离线', { status: 503 });
}

// 后台消息：可手动触发赛前 10 分钟缓存比赛包
self.addEventListener('message', (event) => {
  if (event.data?.type === 'PRECACHE_MATCH') {
    const matchId = event.data.matchId;
    event.waitUntil(
      caches.open(API_CACHE).then((cache) =>
        Promise.allSettled([
          cache.add(`/api/matches/${matchId}`),
          cache.add(`/api/matches/${matchId}/prediction`),
        ])
      ).then(() => event.source?.postMessage({ type: 'PRECACHED', matchId }))
    );
  }
});