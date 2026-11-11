import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const html = readFileSync(new URL('../../site-healer/buy.html', import.meta.url),'utf8');
const start = html.indexOf('  function checkoutRequestId(');
const end = html.indexOf('\n  function submitOrder()',start);
assert.ok(start > 0 && end > start);
const source = html.slice(start,end);
const saved = new Map();
const storage = {getItem:key=>saved.get(key)??null, setItem:(key,value)=>saved.set(key,value)};
function client(localStorage=storage) {
 const context = vm.createContext({localStorage,window:{crypto:null},Date,Math,Uint32Array,Array,JSON});
 vm.runInContext(source,context);
 return context.checkoutRequestId;
}
const payload = {customer_name:'Test',phone:'09123456789',city:'Test',address:'Private address',items:[{code:'A',qty:1}]};
const key = client()(payload,'test-token');
assert.match(key,/^[A-Za-z0-9_-]{16,128}$/);
assert.equal(client()(payload,'test-token'),key,'retry after reload keeps key');
assert.notEqual(client()({...payload,city:'Other'},'test-token'),key,'changed checkout gets a new key');
assert.notEqual(client()(payload,'other-account-token'),key,'another account gets another key');
assert.ok(![...saved.values()].join('').includes('Private address'),'contact/address never persisted by retry helper');
assert.ok(![...saved.values()].join('').includes('test-token'),'token not persisted by retry helper');
const blockedStorage={getItem(){throw new Error('blocked')},setItem(){throw new Error('blocked')}};
assert.match(client(blockedStorage)(payload,'test-token'),/^[A-Za-z0-9_-]{16,128}$/);
console.log('PASS: 7 checkout retry-key scenarios; no network or real orders');
