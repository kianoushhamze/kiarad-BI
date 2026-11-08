// Run one tool with an explicit heap ceiling; never terminate running services.
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

function runTool(tool, options = {}) {
  const env = options.env ?? process.env;
  const root = options.root ?? path.resolve(__dirname, '..');
  const spawn = options.spawn ?? spawnSync;
  const free = options.freeBytes ?? os.freemem();
  const heapText = env.KIARAD_NODE_HEAP_MB ?? '2048';
  if (!/^\d+$/.test(heapText) || Number(heapText) < 512 || Number(heapText) > 8192) {
    throw new Error('KIARAD_NODE_HEAP_MB must be an integer between 512 and 8192.');
  }
  const commands = {
    build: ['next/dist/bin/next', 'build', '--webpack'],
    lint: ['eslint/bin/eslint.js', '.'],
    typecheck: ['typescript/bin/tsc', '--noEmit'],
  };
  const command = commands[tool];
  if (!command) throw new Error('Expected build, lint or typecheck.');
  const freeMB = Math.floor(free / 1024 / 1024);
  if (freeMB < 1024) {
    throw new Error(`Only ${freeMB} MB RAM is free. At least 1024 MB is required before starting ${tool}. Close unused apps or build on the server; services have not been stopped.`);
  }
  const args = [`--max-old-space-size=${heapText}`, path.join(root, 'node_modules', command[0]), ...command.slice(1)];
  const result = spawn(process.execPath, args, { cwd: root, env, stdio: 'inherit', shell: false });
  if (result.error) throw result.error;
  if (result.signal) throw new Error(`${tool} terminated by ${result.signal}.`);
  return Number.isInteger(result.status) ? result.status : 1;
}

module.exports = { runTool };
if (require.main === module) {
  try { process.exitCode = runTool(process.argv[2]); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
