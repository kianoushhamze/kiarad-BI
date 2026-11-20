import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { once } from 'node:events';

const upstream = createServer(async (req, res) => {
  res.setHeader('Content-Type', 'application/json');
  if (req.url === '/public/catalog') return res.end(JSON.stringify({products: [{code: 'TEST', in_stock: true}]}));
  if (req.url === '/site-banners/42/image') {
    res.setHeader('Content-Type', 'image/png');
    return res.end(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]));
  }
  if (req.url === '/public/feeds/products.csv') {
    res.setHeader('Content-Type', 'text/csv; charset=utf-8');
    return res.end('\uFEFFpage_unique,title\nA1,Test product\n');
  }
  if (req.url !== '/site-orders') {
    res.statusCode = 404;
    return res.end('{}');
  }
  if (req.headers.authorization !== 'Bearer test-only') {
    res.statusCode = 401;
    return res.end(JSON.stringify({detail: 'Login required'}));
  }
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const data = JSON.parse(Buffer.concat(chunks));
  assert.equal(data.items[0].code, 'TEST');
  assert.equal(data.request_id, 'checkout_test_fixture');
  res.end(JSON.stringify({ok: true, order_id: 42, total_irr: 15000}));
});
upstream.listen(0, '127.0.0.1');
await once(upstream, 'listening');
const child = spawn(process.execPath, ['scripts/serve_kiaradhealer.mjs'], {
  cwd: new URL('../../', import.meta.url),
  env: {...process.env, KIARAD_SITE_PORT: '0', KIARAD_API_URL: 'http://127.0.0.1:' + upstream.address().port},
});
try {
  const [data] = await Promise.race([
    once(child.stdout, 'data'),
    once(child, 'exit').then(() => { throw new Error('Server exited'); }),
    new Promise((_, reject) => setTimeout(() => reject(new Error('Startup timed out')), 5000).unref()),
  ]);
  const base = 'http://127.0.0.1:' + String(data).trim().split(' ').at(-1);
  assert.match(await (await fetch(base)).text(), /href="\/buy\/"/);
  assert.match(await (await fetch(base + '/buy/')).text(), /function submitOrder/);
  assert.deepEqual(await (await fetch(base + '/api/public/catalog')).json(), {products: [{code: 'TEST'}]});
  const bannerImage = await fetch(base + '/api/site-banners/42/image');
  assert.equal(bannerImage.status, 200);
  assert.equal(bannerImage.headers.get('content-type'), 'image/png');
  assert.deepEqual([...new Uint8Array(await bannerImage.arrayBuffer())], [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  const csv = await fetch(base + '/api/public/feeds/products.csv');
  assert.equal(csv.status, 200);
  assert.match(csv.headers.get('content-type') || '', /^text\/csv/i);
  const csvBytes = Buffer.from(await csv.arrayBuffer());
  assert.deepEqual([...csvBytes.subarray(0, 3)], [0xef, 0xbb, 0xbf]);
  assert.equal(csvBytes.subarray(3).toString('utf8'), 'page_unique,title\nA1,Test product\n');
  assert.equal((await fetch(base + '/api/public/feeds/products.csv', {method: 'POST'})).status, 405);
  assert.equal((await fetch(base + '/api/site-orders/all')).status, 404);
  assert.equal((await fetch(base + '/api/site-orders')).status, 405);
  const body = JSON.stringify({items: [{code: 'TEST', qty: 1}], request_id: 'checkout_test_fixture'});
  const request = {method: 'POST', headers: {'Content-Type': 'application/json'}, body};
  assert.equal((await fetch(base + '/api/site-orders', request)).status, 401);
  const receipt = await fetch(base + '/api/site-orders', {
    ...request, headers: {...request.headers, Authorization: 'Bearer test-only'},
  });
  assert.deepEqual(await receipt.json(), {ok: true, order_id: 42, total_irr: 15000});
  console.log('PASS: showcase, checkout, catalog, API boundaries, authentication and receipt');
} finally {
  child.kill();
  upstream.closeAllConnections();
  await new Promise(resolve => upstream.close(resolve));
}
