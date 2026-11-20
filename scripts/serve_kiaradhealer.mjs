import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = dirname(dirname(fileURLToPath(import.meta.url)));
const root = process.env.KIARAD_SITE_DIR || join(repo, 'site-healer');
const port = Number(process.env.KIARAD_SITE_PORT || 8090);
const api = new URL(process.env.KIARAD_API_URL || 'http://127.0.0.1:8000');
if (!['http:', 'https:'].includes(api.protocol) || api.username || api.password) {
  throw new Error('KIARAD_API_URL must be an HTTP(S) backend origin.');
}
const routes = new Map([
  ['/api/public/catalog', 'GET'],
  ['/api/public/feeds/torob', ['GET', 'POST']],
  ['/api/public/feeds/products.json', 'GET'],
  ['/api/public/feeds/products.csv', 'GET'],
  ['/api/site-banners', 'GET'],
  ['/api/site-auth/me', 'GET'],
  ['/api/site-auth/login', 'POST'],
  ['/api/site-auth/register', 'POST'],
  ['/api/site-orders', 'POST'],
  ['/api/site-orders/mine', 'GET'],
]);
const files = new Map([
  ['/', [root, 'index.html', 'text/html; charset=utf-8']],
  ['/index.html', [root, 'index.html', 'text/html; charset=utf-8']],
  ['/buy/', [root, 'buy.html', 'text/html; charset=utf-8']],
]);
for (const font of ['Vazirmatn-Bold.ttf', 'Vazirmatn-Regular.ttf', 'lalezar.woff2']) {
  const asset = [root, 'fonts/' + font, font.endsWith('.ttf') ? 'font/ttf' : 'font/woff2'];
  files.set('/fonts/' + font, asset);
  files.set('/buy/fonts/' + font, asset);
}

function reply(res, status, detail) {
  res.writeHead(status, {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'});
  res.end(JSON.stringify({detail}));
}

async function proxy(req, res, pathname) {
  const bannerImage = /^\\/api\\/site-banners\\/\\d+\\/image$/.test(pathname);
  const allowed = bannerImage ? ['GET'] : [].concat(routes.get(pathname) || []);
  if (!allowed.length) return reply(res, 404, 'Unknown storefront endpoint');
  if (!allowed.includes(req.method)) {
    res.setHeader('Allow', allowed.join(', '));
    return reply(res, 405, 'Method not allowed');
  }
  const method = req.method;
  const headers = {Accept: pathname.endsWith('.csv') ? 'text/csv' : 'application/json'};
  if (req.headers.authorization) headers.Authorization = req.headers.authorization;
  let body;
  if (method === 'POST') {
    if (!/^application\/json(?:;|$)/i.test(req.headers['content-type'] || '')) {
      return reply(res, 415, 'Expected JSON');
    }
    headers['Content-Type'] = 'application/json';
    const chunks = [];
    let length = 0;
    for await (const chunk of req.iterator({destroyOnReturn: false})) {
      length += chunk.length;
      if (length > 128 * 1024) {
        res.setHeader('Connection', 'close');
        return reply(res, 413, 'Request too large');
      }
      chunks.push(chunk);
    }
    body = Buffer.concat(chunks);
  }
  const upstream = await fetch(new URL(pathname.slice(4), api.origin), {
    method, headers, body, redirect: 'error', signal: AbortSignal.timeout(15000),
  });
  const payload = Buffer.from(await upstream.arrayBuffer());
  const contentType = upstream.headers.get('content-type') || 'application/octet-stream';
  res.writeHead(upstream.status, {'Content-Type': contentType, 'Cache-Control': 'no-store'});
  res.end(payload);
}

createServer(async (req, res) => {
  let pathname;
  try {
    pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  } catch {
    return reply(res, 400, 'Invalid path');
  }
  try {
    if (pathname.startsWith('/api/')) return await proxy(req, res, pathname);
    if (!['GET', 'HEAD'].includes(req.method)) return reply(res, 405, 'Method not allowed');
    if (pathname === '/buy') {
      res.writeHead(308, {Location: '/buy/'});
      return res.end();
    }
    const asset = files.get(pathname);
    if (!asset) return reply(res, 404, 'Not found');
    const [base, filename, type] = asset;
    const data = await readFile(join(base, filename));
    res.writeHead(200, {'Content-Type': type, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'});
    res.end(req.method === 'HEAD' ? undefined : data);
  } catch (error) {
    if (res.headersSent) return res.destroy();
    return reply(res, error.code === 'ENOENT' ? 404 : 502, 'Storefront service unavailable');
  }
}).listen(port, process.env.KIARAD_SITE_HOST || '127.0.0.1', function () {
  console.log('KiaradHealer ready on port ' + this.address().port);
});
