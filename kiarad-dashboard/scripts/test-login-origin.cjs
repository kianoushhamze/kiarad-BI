// Submit the real login component against a synthetic fetch; no live accounts.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
function compile(file) {
  return ts.transpileModule(fs.readFileSync(path.join(__dirname, '..', file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true },
  }).outputText;
}
const apiSource = compile('lib/api.ts');
const loginSource = compile('app/login/page.tsx');
async function scenario(origin, role, expectedPage, status = 200) {
  const window = { location: { origin, protocol: new URL(origin).protocol } };
  const process = { env: { NEXT_PUBLIC_API_URL: 'http://backend:8000' } };
  const apiExports = {};
  vm.runInNewContext(apiSource, { exports: apiExports, window, process });
  let state = 0, sent, saved, redirected, error;
  const react = {
    createElement: (type, props, ...children) => ({ type, props: props || {}, children: children.flat() }),
    useState: () => {
      const index = state++;
      return [['synthetic-user', 'synthetic-password', '', false][index], value => {
        if (index === 2) error = value;
      }];
    },
  };
  const component = {};
  vm.runInNewContext(loginSource, {
    exports: component, window, process,
    require: name => {
      if (name === 'react') return react;
      if (name === 'next/navigation') return { useRouter: () => ({ push: page => { redirected = page; } }) };
      if (name === '../../lib/api') return apiExports;
      if (name === '../../lib/secure-api') return { saveSession: (...args) => { saved = args; } };
      throw new Error('Unexpected import: ' + name);
    },
    fetch: async (url, options) => {
      sent = { url, options };
      return { ok: status === 200, json: async () => ({ access_token: 'synthetic-token', user: { role } }) };
    },
  });
  function findForm(node) {
    if (!node || typeof node !== 'object') return null;
    if (node.type === 'form') return node;
    return node.children?.map(findForm).find(Boolean);
  }
  const form = findForm(component.default());
  assert.ok(form);
  await form.props.onSubmit({ preventDefault() {} });
  assert.equal(sent.url, origin + '/api/auth/login');
  assert.equal(sent.options.method, 'POST');
  if (status === 200) {
    assert.equal(saved[0], 'synthetic-token');
    assert.equal(redirected, expectedPage);
  } else {
    assert.equal(saved, undefined);
    assert.equal(redirected, undefined);
    assert.ok(error);
  }
}
(async () => {
  await scenario('http://127.0.0.1:3000', 'ceo', '/management');
  await scenario('http://review.invalid:3000', 'visitor', '/visitors');
  await scenario('https://review.invalid', 'salesperson', '/visitors');
  await scenario('https://review.invalid', 'ceo', '/management', 401);
  console.log('PASS: 4 login submit scenarios (HTTP/HTTPS, role redirects, rejected credentials)');
})().catch(error => { console.error(error); process.exitCode = 1; });
