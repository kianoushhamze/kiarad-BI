// Synthetic tokens and isolated storage only. Never reads a real browser session.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const tokenKey = 'kiarad_access_token', userKey = 'kiarad_session_user';
const source = fs.readFileSync(path.join(__dirname, '../lib/secure-api.ts'), 'utf8');
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
const storage = new Map();
const localStorage = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, String(value)), removeItem: key => storage.delete(key) };
let pending, sent;
const apiModule = { exports: {} };
vm.runInNewContext(code, { exports: apiModule.exports, module: apiModule,
  require: name => { assert.equal(name, './api'); return { API_URL: 'https://synthetic.invalid/api' }; },
  window: { location: { search: '' } }, URLSearchParams, localStorage, FormData,
  fetch: (url, options) => { sent = { url, options }; return new Promise((resolve, reject) => { pending = { resolve, reject }; }); },
});
const api = apiModule.exports;
let checks = 0;
function equal(actual, expected) { assert.equal(actual, expected); checks++; }
function login(token) { api.saveSession(token, { id: 1, username: 'synthetic', full_name: 'آزمون', role: 'ceo' }); }
function response(status, body = {}) { return { status, ok: status >= 200 && status < 300, json: async () => body }; }
function querySession({ stored = '', historyWorks = true } = {}) {
  const values = new Map(stored ? [[tokenKey, stored]] : []);
  const location = { pathname: '/tasks', search: '?next=%2Ftasks&token=legacy-synthetic&view=mine', hash: '#review' };
  let replaced = null;
  const testModule = { exports: {} };
  vm.runInNewContext(code, { exports: testModule.exports, module:testModule,
    require: () => ({ API_URL: 'https://synthetic.invalid/api' }),
    window: { location, history: { state: 'synthetic-navigation', replaceState: (_state, _title, url) => {
      if (!historyWorks) throw new Error('Synthetic history unavailable');
      assert.equal(_state, 'synthetic-navigation');
      replaced = url; location.search = new URL(url, 'https://synthetic.invalid').search;
    } } }, URLSearchParams, FormData,
    localStorage: { getItem: key => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, String(value)), removeItem: key => values.delete(key) },
    fetch: async () => response(401),
  });
  return { api: testModule.exports, values, location, replaced: () => replaced };
}
async function main() {
  login('old-synthetic');
  const old = api.secureApi('/example').catch(error => error);
  equal(sent.options.headers.Authorization, 'Bearer old-synthetic');
  login('fresh-synthetic'); pending.resolve(response(401));
  const staleError = await old;
  equal(staleError.status, 401); equal(api.getToken(), 'fresh-synthetic');
  equal(api.getSavedUser().username, 'synthetic');
  equal(staleError.message.includes('نشست قبلی'), true);

  const invalid = api.secureApi('/example').catch(error => error);
  pending.resolve(response(401));
  equal((await invalid).status, 401); equal(api.getToken(), ''); equal(storage.has(userKey), false);

  login('current-synthetic');
  const forbidden = api.secureApi('/example').catch(error => error);
  pending.resolve(response(403, { detail: 'مجاز نیست' }));
  equal((await forbidden).status, 403); equal(api.getToken(), 'current-synthetic');
  const network = api.secureApi('/example').catch(error => error);
  pending.reject(new Error('synthetic network failure'));
  equal((await network).message, 'synthetic network failure'); equal(api.getToken(), 'current-synthetic');

  api.clearSession();
  const anonymous = api.secureApi('/example').catch(error => error);
  login('new-synthetic'); pending.resolve(response(401)); await anonymous;
  equal(api.getToken(), 'new-synthetic');

  const ok = api.secureApi('/example', { headers: { 'X-Test': 'synthetic' } });
  equal(sent.options.headers['X-Test'], 'synthetic'); equal(sent.options.cache, 'no-store');
  pending.resolve(response(200, { accepted: true })); equal((await ok).accepted, true);

  const raw = api.authFetch('/raw'); pending.resolve(response(401));
  equal((await raw).status, 401); equal(api.getToken(), 'new-synthetic');
  equal(storage.get(tokenKey), 'new-synthetic');

  const existing = querySession({ stored: 'fresh-synthetic' });
  equal(existing.api.getToken(), 'fresh-synthetic');
  equal(existing.values.get(tokenKey), 'fresh-synthetic');
  equal(existing.replaced(), '/tasks?next=%2Ftasks&view=mine#review');
  existing.api.clearSession();
  existing.location.search = '?token=legacy-synthetic';
  equal(existing.api.getToken(), '');

  const legacy = querySession();
  equal(legacy.api.getToken(), 'legacy-synthetic');
  equal(legacy.values.get(tokenKey), 'legacy-synthetic');
  equal(legacy.replaced(), '/tasks?next=%2Ftasks&view=mine#review');
  const rejected = await legacy.api.secureApi('/synthetic').catch(error => error);
  equal(rejected.status, 401); equal(legacy.api.getToken(), '');
  legacy.location.search = '?token=legacy-synthetic';
  equal(legacy.api.getToken(), '');

  const historyUnavailable = querySession({ historyWorks: false });
  equal(historyUnavailable.api.getToken(), 'legacy-synthetic');
  historyUnavailable.api.clearSession();
  equal(historyUnavailable.api.getToken(), '');
  equal(historyUnavailable.values.has(tokenKey), false);

  const clearedBeforeRead = querySession();
  clearedBeforeRead.api.clearSession();
  equal(clearedBeforeRead.api.getToken(), '');

  const newBeforeRead = querySession();
  newBeforeRead.api.saveSession('fresh-synthetic', { username: 'synthetic' });
  equal(newBeforeRead.api.getToken(), 'fresh-synthetic');
  equal(newBeforeRead.values.get(tokenKey), 'fresh-synthetic');
  console.log(JSON.stringify({ checks, passed: true, network: false, real_session_used: false }));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
