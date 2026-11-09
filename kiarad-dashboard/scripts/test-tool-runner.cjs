const assert = require('node:assert/strict');
const { runTool } = require('./run-tool.cjs');
const enough = 4 * 1024 ** 3;
let calls = 0, captured;
function spawn(...args) { calls++; captured = args; return {status: 0}; }
function options(extra = {}) { return {env: {}, freeBytes: enough, spawn, ...extra}; }
assert.throws(() => runTool('build', options({freeBytes: 461 * 1024 ** 2})), /Only 461 MB/);
assert.equal(calls, 0, 'low memory must not start a child');
for (const value of ['bad', '0', '511', '8193', '2048 --inspect']) {
  assert.throws(() => runTool('build', options({env: {KIARAD_NODE_HEAP_MB: value}})), /integer/);
}
assert.equal(calls, 0, 'invalid options must not start a child');
assert.equal(runTool('build', options()), 0);
assert.equal(captured[1][0], '--max-old-space-size=2048');
assert.deepEqual(captured[1].slice(-2), ['build', '--webpack']);
assert.equal(captured[2].shell, false);
assert.equal(runTool('lint', options({env: {KIARAD_NODE_HEAP_MB:'1536'}})), 0);
assert.equal(captured[1][0], '--max-old-space-size=1536');
assert.ok(captured[1][1].endsWith('eslint/bin/eslint.js'));
assert.equal(runTool('typecheck', options({spawn: () => ({status: 2})})), 2);
assert.throws(() => runTool('build', options({spawn: () => ({signal: 'SIGTERM'})})), /SIGTERM/);
assert.throws(() => runTool('build', options({spawn: () => ({error: new Error('spawn failed')})})), /spawn failed/);
assert.equal(runTool('build', options({spawn: () => ({status: null})})), 1);
assert.throws(() => runTool('unknown', options()), /Expected/);
// Real child process: verify the heap flag and nonzero exit survive the wrapper.
const fs = require('node:fs');
const path = require('node:path');
const fixture = fs.mkdtempSync(path.join(__dirname, '.tool-test-'));
try {
  const bin = path.join(fixture, 'node_modules', 'eslint', 'bin');
  fs.mkdirSync(bin, {recursive: true});
  fs.writeFileSync(path.join(bin, 'eslint.js'), `require('node:fs').writeFileSync(__dirname+'/result.json', JSON.stringify(process.execArgv)); process.exit(7);`);
  assert.equal(runTool('lint', {root: fixture, freeBytes: enough, env: {...process.env, KIARAD_NODE_HEAP_MB: '1536'}}), 7);
  assert.ok(JSON.parse(fs.readFileSync(path.join(bin, 'result.json'), 'utf8')).includes('--max-old-space-size=1536'));
} finally {
  fs.rmSync(fixture, {recursive: true, force: true});
}
console.log('PASS: tool runner handles low memory, invalid limits, tool invocation, child errors and exit codes; no services changed');
