import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';

const upstream = createServer((req, res) => {
  res.writeHead(200, {'Content-Type':'application/json'});
  res.end(JSON.stringify({path:req.url, method:req.method, auth:req.headers.authorization ?? ''}));
});
upstream.listen(0, '127.0.0.1');
await once(upstream, 'listening');
const port = process.env.KIARAD_HTTP_TEST_PORT ?? '18881';
const child = spawn(process.execPath, [fileURLToPath(new URL('../../scripts/serve_kiaradhealer.mjs', import.meta.url))], {
  env: {...process.env, KIARAD_SITE_PORT:port, KIARAD_API_URL:`http://127.0.0.1:${upstream.address().port}`},
  stdio:['ignore','pipe','pipe'],
});
const base = `http://127.0.0.1:${port}`;
try {
  await Promise.race([once(child.stdout,'data'), once(child,'exit').then(()=>{throw new Error('server exited');}),
    new Promise((_,reject)=>setTimeout(()=>reject(new Error('startup timeout')),5000).unref())]);
  for (const [path, method, expected] of [
    ['/', 'GET', 200], ['/%ZZ','GET',400], ['/', 'GET',200], ['/', 'HEAD',200],
    ['/','POST',405], ['/missing','GET',404],
  ]) {
    const res = await fetch(base+path, {method});
    assert.equal(res.status, expected, `${method} ${path}`);
    if(method==='HEAD') assert.equal(await res.text(), '');
    else await res.arrayBuffer();
  }
  const res = await fetch(base+'/api/site-orders', {method:'POST', headers:{Authorization:'Bearer test-only','Content-Type':'application/json'}, body:'{}'});
  assert.deepEqual(await res.json(), {path:'/site-orders',method:'POST',auth:'Bearer test-only'});
  console.log('PASS: 7 storefront HTTP scenarios; mock upstream only, no real orders');
} finally {
  child.kill();
  if(child.exitCode===null) await once(child,'exit');
  upstream.closeAllConnections();
  await new Promise(resolve=>upstream.close(resolve));
}
