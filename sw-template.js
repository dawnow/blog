// Workbox 运行时自托管在 static/sw/（约 28 KB），不依赖 Google CDN。
// 升级 workbox-build 时，必须同步替换 static/sw/ 下的同名文件。
importScripts('/sw/workbox-sw.js');
workbox.setConfig({ modulePathPrefix: '/sw/' });

const CACHE_PREFIX = 'thethinningdark';

workbox.core.setCacheNameDetails({ prefix: CACHE_PREFIX });
workbox.core.skipWaiting();
workbox.core.clientsClaim();

// 只预缓存应用外壳（CSS / JS / 图标 / manifest / offline.html）。
// 页面不再进预缓存：导航走下面的 NetworkFirst，保证部署后第一次访问就是新内容。
workbox.precaching.precacheAndRoute(self.__WB_MANIFEST);
workbox.precaching.cleanupOutdatedCaches();

// 接管后清掉旧版本留下的缓存（旧前缀是 Dawner-*）
self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        const keys = await caches.keys();
        await Promise.all(
            keys.filter((k) => !k.startsWith(CACHE_PREFIX)).map((k) => caches.delete(k))
        );
    })());
});

// 页面导航：先网络（3 秒超时），失败回落缓存，再失败给离线页
workbox.routing.registerRoute(
    ({ request }) => request.mode === 'navigate',
    new workbox.strategies.NetworkFirst({
        cacheName: `${CACHE_PREFIX}-pages`,
        networkTimeoutSeconds: 3,
        plugins: [
            new workbox.expiration.ExpirationPlugin({
                maxEntries: 50,
                maxAgeSeconds: 30 * 24 * 60 * 60,
            }),
        ],
    })
);

// 图片：缓存优先
workbox.routing.registerRoute(
    /\.(?:png|jpe?g|gif|bmp|webp|svg|ico)$/,
    new workbox.strategies.CacheFirst({
        cacheName: `${CACHE_PREFIX}-images`,
        plugins: [
            new workbox.expiration.ExpirationPlugin({
                maxEntries: 200,
                maxAgeSeconds: 30 * 24 * 60 * 60,
            }),
            new workbox.cacheableResponse.CacheableResponsePlugin({ statuses: [0, 200] }),
        ],
    })
);

// 字体：缓存优先（HTTP 已是 immutable，这里只为离线兜底）
workbox.routing.registerRoute(
    /\/fonts\/.*\.woff2$/,
    new workbox.strategies.CacheFirst({
        cacheName: `${CACHE_PREFIX}-fonts`,
        plugins: [
            new workbox.expiration.ExpirationPlugin({
                maxEntries: 10,
                maxAgeSeconds: 365 * 24 * 60 * 60,
            }),
            new workbox.cacheableResponse.CacheableResponsePlugin({ statuses: [0, 200] }),
        ],
    })
);

// 断网且目标页没进过缓存时，显示离线页
workbox.routing.setCatchHandler(async ({ request }) => {
    if (request.mode === 'navigate') {
        const cached = await workbox.precaching.matchPrecache('/offline.html');
        if (cached) return cached;
    }
    return Response.error();
});
