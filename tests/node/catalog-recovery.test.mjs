import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';
const page = await readFile(new URL('../../site-healer/buy.html', import.meta.url), 'utf8');
const start = page.indexOf('  function loadCatalog()');
const end = page.indexOf('\n  refreshData();', start);
assert.ok(start > 0 && end > start);
function setup(healerMode, fetch) {
  const elements = new Map();
  const ctx = {
    healerMode, fetch, API_BASE: '/api', liveMode: false, orderPending: false,
    products: [], cart: {items: [{code: 'A', qty: 1}, {code: 'B', qty: 1}]},
    document: {getElementById(id) {
      if (!elements.has(id)) elements.set(id, {classList: {toggle(name, value) {this[name] = value;}}});
      return elements.get(id);
    }},
    pick: (p, keys) => keys.map(k => p[k]).find(v => v !== undefined),
    renderCats() {}, render() {}, paintCart() {},
    removeFromCart(code) {ctx.cart.items = ctx.cart.items.filter(x => x.code !== code);},
  };
  vm.createContext(ctx);
  vm.runInContext(page.slice(start, end), ctx);
  return {ctx, elements};
}
const response = products => ({ok: true, json: async () => ({products})});
const flush = () => new Promise(resolve => setImmediate(resolve));
for (const malformed of [null, {}, {products: {}}]) {
  const {ctx} = setup(true, async () => ({ok: true, json: async () => malformed}));
  ctx.refreshData(); await flush();
  assert.equal(ctx.liveMode, false);
  assert.equal(ctx.cart.items.length, 2);
}
{
  let online = false;
  const {ctx, elements} = setup(true, async () => {
    if (!online) throw Error('network unavailable');
    return response([{code: 'A'}, {code: 'B'}]);
  });
  ctx.products = [{code: 'A'}];
  ctx.refreshData(); await flush();
  assert.equal(ctx.products[0].code, 'A', 'network failure retains the previous catalog');
  assert.equal(ctx.cart.items.length, 2, 'network failure retains the cart');
  assert.equal(elements.get('empty').hidden, false);
  assert.match(elements.get('empty').textContent, /خوانده نشد/);
  online = true;
  ctx.refreshData(); await flush();
  assert.equal(ctx.liveMode, true);
  assert.equal(ctx.cart.items.length, 2);
  assert.equal(elements.get('empty').textContent, 'محصولی مطابق جستجو پیدا نشد.', 'recovery clears the stale error');
}
{
  let online = false;
  const {ctx, elements} = setup(false, async url => {
    if (url === 'data.json') return response([{code: 'Z'}]);
    if (!online) throw Error('offline');
    return response([{code: 'A'}, {code: 'B'}]);
  });
  ctx.refreshData(); await flush();
  assert.equal(ctx.cart.items.length, 2);
  assert.equal(elements.get('demobar').classList.show, true);
  online = true;
  ctx.refreshData(); await flush();
  assert.equal(ctx.cart.items.length, 2);
  assert.equal(elements.get('demobar').classList.show, false);
}
{
  const {ctx} = setup(true, async () => response([{code: 'Z'}]));
  ctx.refreshData(); await flush();
  assert.equal(ctx.cart.items.length, 0, 'prune all missing items without skipping adjacent entries');
}
{
  const {ctx} = setup(false, async url => url === 'data.json'
    ? {ok: false, status: 404} : Promise.reject(Error('offline')));
  ctx.refreshData(); await flush();
  assert.equal(ctx.cart.items.length, 2);
}
console.log('PASS: malformed live catalog, offline cart retention, live recovery, complete pruning and fallback failure');
