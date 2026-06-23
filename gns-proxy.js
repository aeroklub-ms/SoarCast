#!/usr/bin/env node
/*
  gns-proxy.js — tiny zero-dependency CORS proxy for the CBS 3D tracker.

  api.glideandseek.com sends no Access-Control-Allow-Origin header, so the
  browser blocks direct fetches from tracker.html. Run this next to the
  tracker and it forwards

      http://localhost:8010/proxy/<path>  →  https://api.glideandseek.com/<path>
  http://localhost:8010/metar/<path>  →  https://aviationweather.gov/<path>

  adding permissive CORS headers on the way back. tracker.html automatically
  tries the local proxy when the direct fetch fails (see _gnsFetch and the
  METAR fetcher).

  Usage:  node gns-proxy.js          (default port 8010)
          node gns-proxy.js 9000     (custom port)

  Smoke test:  curl http://localhost:8010/proxy/v2/aircraft
               curl 'http://localhost:8010/metar/api/data/metar?ids=KJFK&format=json&hours=1'
*/
const http  = require('http');
const https = require('https');

const PORT = parseInt(process.argv[2], 10) || 8010;

// Route prefix → upstream host.  Order matters: longest prefix first.
const ROUTES = [
  { prefix: '/proxy/', host: 'api.glideandseek.com' },
  { prefix: '/metar/', host: 'aviationweather.gov' }
];

const server = http.createServer((req, res) => {
  const cors = {
    'Access-Control-Allow-Origin':  req.headers.origin || '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': req.headers['access-control-request-headers'] || '*'
  };

  if (req.method === 'OPTIONS') { res.writeHead(204, cors); res.end(); return; }

  const route = req.method === 'GET' ? ROUTES.find(r => req.url.startsWith(r.prefix)) : null;
  if (!route) {
    res.writeHead(404, { ...cors, 'Content-Type': 'text/plain' });
    res.end('Use GET /proxy/<gns path> or /metar/<aviationweather path>');
    return;
  }

  const path = req.url.slice(route.prefix.length - 1);   // keeps leading slash + query
  const upstream = https.request(
    { hostname: route.host, path, method: 'GET',
      headers: { accept: 'application/json', 'user-agent': 'cbs-tracker-proxy/1.0' },
      timeout: 15000 },
    up => {
      res.writeHead(up.statusCode, {
        ...cors,
        'Content-Type': up.headers['content-type'] || 'application/json'
      });
      up.pipe(res);
    }
  );
  upstream.on('timeout', () => upstream.destroy(new Error('upstream timeout')));
  upstream.on('error', err => {
    if (!res.headersSent) {
      res.writeHead(502, { ...cors, 'Content-Type': 'text/plain' });
    }
    res.end(`Upstream error: ${err.message}`);
  });
  upstream.end();
});

server.listen(PORT, () => {
  for (const r of ROUTES)
    console.log(`[gns-proxy] http://localhost:${PORT}${r.prefix}  →  https://${r.host}`);
  console.log(`[gns-proxy] smoke test: curl http://localhost:${PORT}/proxy/v2/aircraft`);
});
