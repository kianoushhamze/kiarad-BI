import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';

const page = await readFile(new URL('../../site-healer/buy.html', import.meta.url), 'utf8');
const start = page.indexOf('  function loadCatalog()');
const end = page.indexOf('\n  refreshData();', start);
assert.ok(start > 0 && end > start);

function setup(healerMode = true) {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {
      hidden: true, textContent: '', className: '',
      classList: {shown: false, toggle(_, value) {this.shown = value;}},
    });
    return elements.get(id);
  };
  const ctx = {
    healerMode, liveMode: false, orderPending: false, API_BASE: '/api', products: [],
    cart: {items: [{code: 'A', qty: 1}, {code: 'B', qty: 2}]},
    document: {getElementById: element},
    pick: (p, keys) => keys.map(k => p[k]).find(v => v !== undefined && v !== null),
    renderCats() {}, render() {}, paintCart() {},
    removeFromCart(code) {ctx.cart.items = ctx.cart.items.filter(it => it.code !== code);},
  };
  vm.createContext(ctx);
  vm.runInContext(page.slice(start, end), ctx);
  const refresh = async fetch => {
    ctx.fetch = fetch;
    ctx.refreshData();
    await new Promise(resolve => setImmediate(resolve));
  };
  return {ctx, element, refresh};
}
const response = products => ({ok: true, json: async () => ({products})});

test('malformed live payload preserves cart and shows an error, then recovers', async () => {
  const {ctx, element, refresh} = setup();
  await refresh(async () => ({ok: true, json: async () => ({error: 'unavailable'})}));
  assert.equal(ctx.liveMode, false);
  assert.equal(ctx.cart.items.length, 2);
  assert.equal(element('empty').hidden, false);
  assert.match(element('empty').textContent, /خوانده نشد/);
  await refresh(async () => response([{code: 'A', name: 'A', price: 1000, stock: 1}]));
  assert.equal(ctx.liveMode, true);
  assert.deepEqual(Array.from(ctx.cart.items, it => it.code), ['A']);
  assert.equal(element('empty').textContent, 'محصولی مطابق جستجو پیدا نشد.');
});

test('network failure retains the cart and previous catalog', async () => {
  const {ctx, refresh} = setup();
  ctx.products = [{code: 'A'}];
  await refresh(async () => {throw new Error('offline');});
  assert.equal(ctx.cart.items.length, 2);
  assert.equal(ctx.products[0].code, 'A');
  assert.equal(ctx.liveMode, false);
});

test('saved catalog cannot delete cart entries and recovery clears offline banner', async () => {
  const {ctx, element, refresh} = setup(false);
  await refresh(async url => url === 'data.json' ? response([]) : Promise.reject(new Error('offline')));
  assert.equal(ctx.cart.items.length, 2);
  assert.equal(element('demobar').classList.shown, true);
  await refresh(async () => response([{code: 'A'}, {code: 'B'}]));
  assert.equal(element('demobar').classList.shown, false);
  assert.equal(ctx.cart.items.length, 2);
});

test('invalid saved catalog preserves cart', async () => {
  const {ctx, refresh} = setup(false);
  await refresh(async url => url === 'data.json'
    ? {ok: false, json: async () => ({products: []})}
    : Promise.reject(new Error('offline')));
  assert.equal(ctx.cart.items.length, 2);
});

test('valid live catalog removes all missing lines without skipping adjacent items', async () => {
  const {ctx, refresh} = setup();
  await refresh(async () => response([]));
  assert.equal(ctx.cart.items.length, 0);
});
