/**
 * End-to-end proof that the ratchet fires inside the real round loop.
 *
 * The unit fixtures prove capture/restore and the fitness ordering. Neither
 * proves the thing that actually mattered: that when a round breaks the build,
 * `runTask` puts the previous version back on disk before the next round — and
 * before the next task inherits it. That only shows up in the real
 * build -> check_syntax -> browser -> decide sequence, so this drives that
 * sequence with a scripted agent instead of a live model.
 *
 * Uses real Chrome. No Ollama: the task is marked non-visual so no vision call
 * is made.
 *
 * Run: node test/ratchet-integration.mjs
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

import { runTask } from '../src/worker.js';
import { RunState } from '../src/state.js';
import { startStaticServer, closeBrowser } from '../src/browser.js';
import { config } from '../src/config.js';

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'forge-ratchet-e2e-'));
let failures = 0;

function report(pass, name, detail) {
  if (!pass) failures++;
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name.padEnd(46)} ${detail}`);
}

// A minimal app that draws something in the middle of the canvas, so it passes
// the blank-frame and dead-playfield checks.
const GOOD_MAIN = `
const c = document.getElementById('game');
c.width = 1600; c.height = 900;
const ctx = c.getContext('2d');
let t = 0;
function frame() {
  ctx.fillStyle = '#141018';
  ctx.fillRect(0, 0, c.width, c.height);
  for (let i = 0; i < 60; i++) {
    ctx.fillStyle = 'hsl(' + ((i * 37 + t) % 360) + ',70%,55%)';
    ctx.fillRect(500 + (i % 10) * 60, 300 + Math.floor(i / 10) * 60, 52, 52);
  }
  t += 2;
  requestAnimationFrame(frame);
}
frame();
`;
const HTML = `<!doctype html><html><body style="margin:0;background:#141018">
<canvas id="game"></canvas>
<script type="module" src="./src/main.js"></script></body></html>`;

const appDir = path.join(TMP, 'app');
fs.mkdirSync(path.join(appDir, 'src'), { recursive: true });
fs.writeFileSync(path.join(appDir, 'index.html'), HTML);
fs.writeFileSync(path.join(appDir, 'src/main.js'), GOOD_MAIN);

const paths = {
  root: TMP,
  app: appDir,
  shots: path.join(TMP, 'shots'),
};
fs.mkdirSync(paths.shots, { recursive: true });

const port = 8793;
const server = await startStaticServer(appDir, port);
const appUrl = `http://127.0.0.1:${port}/index.html`;

const state = new RunState(path.join(TMP, 'state.json'));
state.data.goal = 'test';
state.data.architecture = 'test';
state.data.directives = {
  loop_until_perfect: true,
  visual_domain: '2d_game',
  quality_bar: 'test',
};

const task = {
  id: 'ratchet-e2e',
  title: 'break it then leave it alone',
  description: 'test',
  acceptanceCriteria: [],
  files: ['src/main.js'],
  visual: false, // keeps the vision critic out of this test
};

// Round 1 corrupts the entry module with a hard syntax error — the exact
// failure that ended two real runs. Later rounds do nothing at all, so if the
// corruption survives, the task can only finish broken.
const script = {
  1: () => fs.writeFileSync(path.join(appDir, 'src/main.js'), 'this is not ( valid javascript'),
  2: () => {},
};

let roundsRun = 0;
const makeAgent = ({ round }) => ({
  async run() {
    roundsRun++;
    (script[round] ?? (() => {}))();
    return { status: 'completed', filesTouched: ['src/main.js'], summary: 'scripted' };
  },
});

const originalRounds = config.budgets.critiqueRounds;
config.budgets.critiqueRounds = 2;

const result = await runTask({ task, state, paths, appUrl, slot: 1, makeAgent });

config.budgets.critiqueRounds = originalRounds;

// ------------------------------------------------------------------- assertions
const finalMain = fs.readFileSync(path.join(appDir, 'src/main.js'), 'utf8');

report(roundsRun === 2, 'both rounds ran', `${roundsRun} rounds`);
report(finalMain === GOOD_MAIN,
  'corrupted file was rolled back',
  finalMain === GOOD_MAIN ? 'entry module restored byte-for-byte' : `left as: ${finalMain.slice(0, 40)}`);
report(!finalMain.includes('not ( valid'),
  'the breakage did not survive the task', 'tree is parseable');
report(result.status === 'completed' || result.status === 'completed_below_bar',
  'task did not end on a corpse', `status=${result.status}`);

// The whole point: what the next task inherits must be the good tree. Checked
// the same way the gate checks it, rather than by evaluating the file here.
const parses = spawnSync(process.execPath, ['--check', path.join(appDir, 'src/main.js')]).status === 0;
report(parses, 'inherited tree parses', 'next task starts from working code');

await closeBrowser();
server.close();
fs.rmSync(TMP, { recursive: true, force: true });
console.log(failures ? `\n${failures} FAILURE(S)` : '\nratchet integration passed');
process.exit(failures ? 1 : 0);
