import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';
const page = await readFile(new URL('../../site/index.html', import.meta.url), 'utf8');
const start = page.indexOf('  function submitOrder()');
const end = page.indexOf('  // --- Auth', start);
assert.ok(start >= 0 && end > start);

function setup(fetch) {
  const values = new Map([['token', 'test-token']]);
  const button = {disabled: false};
  const ctx = {
    healerMode: true, liveMode: true, orderPending: false, TOKEN_KEY: 'token', API_BASE: '/api',
    cart: {items: [{code: 'A', qty: 1}]}, form: {}, fetch,
    checkoutRequestId: () => 'fixture-key',
    localStorage: {getItem: k => values.get(k), removeItem: k => values.delete(k)},
    document: {getElementById: id => id === 'submitOrder' ? button : {focus() {}}},
    setCoErr(message) { ctx.message = message; },
    toast(message) { ctx.message = message; },
    closeDrawer() {}, paintAuth() {}, renderDrawer() {}, saveCart() {}, paintCart() {},
  };
  vm.createContext(ctx);
  vm.runInContext(page.slice(start, end), ctx);
  return {ctx, values, button};
}
{
  let finish, calls = 0;
  const {ctx} = setup(() => { calls++; return new Promise(resolve => { finish = resolve; }); });
  const pending = ctx.submitOrder();
  ctx.submitOrder();
  assert.equal(calls, 1);
  finish({ok: true, json: async () => ({ok: true, order_id: 5, total_irr: 1000})});
  await pending;
  assert.equal(ctx.lastOrder.order_id, 5);
  assert.equal(ctx.cart.items.length, 0);
}
for (const fetch of [
  async () => { throw new Error('offline'); },
  async () => ({ok: true, json: async () => ({ok: true, order_id: 5})}),
]) {
  const {ctx, button} = setup(fetch);
  await ctx.submitOrder();
  assert.equal(ctx.cart.items.length, 1);
  assert.equal(ctx.lastOrder, undefined);
  assert.equal(ctx.orderPending, false);
  assert.equal(button.disabled, false);
  assert.ok(ctx.message);
}
{
  const {ctx, values} = setup(async () => ({status: 401}));
  await ctx.submitOrder();
  assert.equal(values.has('token'), false);
  assert.equal(ctx.cart.items.length, 1);
  assert.match(ctx.message, /منقضی/);
}
console.log('PASS: duplicate click, confirmed receipt, network failure, incomplete receipt and expired session');
