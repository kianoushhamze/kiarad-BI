import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { once } from 'node:events';

const upstream = createServer(async (req, res) => {
  res.setHeader('Content-Type', 'application/json');
  if (req.url === '/public/catalog') return res.end(JSON.stringify({products: [{code: 'TEST'}]}));
  if (req.url === '/public/feeds/products.csv') {
    res.setHeader('Content-Type', 'text/csv; charset=utf-8');
    return res.end('\uFEFFpage_unique,title\\nA1,Test product\\n');
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
  const csv = await fetch(base + '/api/public/feeds/products.csv');
  assert.equal(csv.status, 200);
  assert.match(csv.headers.get('content-type') || '', /^text\\/csv/i);
  assert.equal(await csv.text(), '\uFEFFpage_unique,title\\nA1,Test product\\n');
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
