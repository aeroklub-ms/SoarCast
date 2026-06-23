// Championship Broadcast Studio — tile cache Service Worker
//
// Cesium World Terrain and Bing imagery tiles are immutable: a given
// quadtree node at (level, x, y) returns the same bytes forever.  So
// cache-first with no expiry is the right strategy — first visit pays
// the network cost, every subsequent visit is served from disk.
//
// FIRST-LOAD TUNING: the cache is empty on first load, so every cache.match
// misses and every miss wants a cache.put.  Hundreds of simultaneous disk
// writes during the initial tile flood contend for I/O.  We cap WRITE
// CONCURRENCY (not whether a tile caches): overflow writes are QUEUED and
// drained a few at a time.  The response itself is returned immediately and is
// never blocked behind a write, so the network path stays fast while the cache
// still fully populates.
//
// (Earlier this DROPPED any tile over the in-flight cap — which meant ~170 of
//  the ~180 tiles per view were never cached, so every revisit re-paid the full
//  network cost and the "instant on revisit" promise never materialised.  The
//  queue below fixes that: one visit to an area now caches all of it.)
//
// We only intercept tile-host fetches; everything else passes straight through.

const CACHE_NAME = 'cbs-tiles-v1';
const MAX_INFLIGHT_WRITES = 6;     // disk-write concurrency cap (I/O smoothing)
const MAX_QUEUED_WRITES   = 800;   // memory safety valve for the pending queue
let   _inflightWrites = 0;
const _writeQueue = [];            // [{req, resp}] tiles waiting for a write slot

const CACHEABLE_HOSTS = ['cesium.com', 'virtualearth.net', 'tile.openstreetmap.org'];

// Open the cache once; reused by every fetch (avoids a caches.open per request).
const _cacheP = caches.open(CACHE_NAME);

self.addEventListener('install',  () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

function shouldCache(req) {
  if (req.method !== 'GET') return false;
  if (req.headers.has('range')) return false;     // partial responses can't share a key
  let u;
  try { u = new URL(req.url); } catch (_) { return false; }
  return CACHEABLE_HOSTS.some(h => u.hostname.endsWith(h));
}

// Drain the write queue, keeping at most MAX_INFLIGHT_WRITES puts in flight.
// This caps disk-I/O concurrency (the original goal) WITHOUT dropping tiles —
// every queued tile is eventually written, so a second visit to an area is
// fully disk-served and instant.
function _drainWrites(cache) {
  while (_inflightWrites < MAX_INFLIGHT_WRITES && _writeQueue.length) {
    const { req, resp } = _writeQueue.shift();
    _inflightWrites++;
    cache.put(req, resp)
      .catch(() => {})
      .finally(() => { _inflightWrites--; _drainWrites(cache); });
  }
}

self.addEventListener('fetch', (e) => {
  if (!shouldCache(e.request)) return;

  e.respondWith((async () => {
    const cache = await _cacheP;
    const hit   = await cache.match(e.request);
    if (hit) return hit;
    try {
      const resp = await fetch(e.request);
      // Queue the write (non-blocking — the response returns immediately).
      // Overflow is QUEUED, not dropped, so the cache fully populates after a
      // single visit.  The queue is bounded only as a memory safety valve; a
      // tile dropped at that ceiling simply re-caches next time it's seen.
      if (resp.ok && resp.type !== 'opaque') {
        if (_writeQueue.length < MAX_QUEUED_WRITES) {
          _writeQueue.push({ req: e.request, resp: resp.clone() });
          _drainWrites(cache);
        }
      }
      return resp;
    } catch (err) {
      return hit || Response.error();
    }
  })());
});
