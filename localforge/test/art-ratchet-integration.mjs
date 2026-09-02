/**
 * Proof that the ratchet can revert a round that breaks nothing.
 *
 * `ratchet-integration.mjs` proves the health tier fires: a round that
 * corrupts the tree is rolled back. That is the easy half, and it was the only
 * half that worked. The baseline was scored with `fitness(baseline, null)`,
 * giving the inherited frame art=0, so every round that merely avoided
 * crashing outranked it and was kept no matter what it did to the picture.
 *
 * A real 3h run lost its terrain, sky, moon and starfield to one round that
 * painted an opaque rectangle over the whole canvas every frame. It ran at
 * 60fps with zero errors, the critic described the damage in plain English at
 * 29/100, and the round was kept — because 7029 > 7000.
 *
 * So these fixtures hold health flat and vary only the things the old
 * comparison could not see: the art score, and whether the build still
 * responds to input. Each is run twice, once against the fixed ratchet and
 * once with the baseline judgement suppressed, because a fixture that cannot
 * fail on the old code proves nothing.
 *
 * Uses real Chrome. No Ollama: the critic is a scripted stub.
 *
 * Run: node test/art-ratchet-integration.mjs
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { runTask } from '../src/worker.js';
import { RunState } from '../src/state.js';
import { startStaticServer, closeBrowser, inspectApp, ENTRY_ACTIONS } from '../src/browser.js';
import { config } from '../src/config.js';

let failures = 0;
function report(pass, name, detail) {
  if (!pass) failures++;
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name.padEnd(46)} ${detail}`);
}

const HTML = `<!doctype html><html><body style="margin:0;background:#141018">
<canvas id="game"></canvas>
<script type="module" src="./src/main.js"></script></body></html>`;

/** Rich frame: lots of colour, animating, centre of canvas well covered. */
const RICH = `
const c = document.getElementById('game');
c.width = 1600; c.height = 900;
const ctx = c.getContext('2d');
let t = 0;
function frame() {
  ctx.fillStyle = '#141018';
  ctx.fillRect(0, 0, c.width, c.height);
  for (let i = 0; i < 120; i++) {
    ctx.fillStyle = 'hsl(' + ((i * 37 + t) % 360) + ',70%,55%)';
    ctx.fillRect(300 + (i % 15) * 70, 250 + Math.floor(i / 15) * 70, 60, 60);
  }
  t += 2;
  requestAnimationFrame(frame);
}
frame();
`;

/**
 * Drab frame: the regression under test. Still animates, still fills the
 * centre, still 60fps, still zero errors — so every health check passes and
 * the art score is the only thing that separates it from RICH.
 */
const DRAB = `
const c = document.getElementById('game');
c.width = 1600; c.height = 900;
const ctx = c.getContext('2d');
let t = 0;
function frame() {
  ctx.fillStyle = '#141018';
  ctx.fillRect(0, 0, c.width, c.height);
  for (let i = 0; i < 120; i++) {
    ctx.fillStyle = i % 2 ? '#2b2b31' : '#232329';
    ctx.fillRect(300 + (i % 15) * 70, 250 + Math.floor(i / 15) * 70, 60, 60);
  }
  t += 2;
  requestAnimationFrame(frame);
}
frame();
`;

/**
 * RICH plus a click that repaints a big solid disk.
 *
 * The disk is drawn inside the one render loop, after the grid. Drawing it
 * from a second requestAnimationFrame loop looks equivalent and is not: the
 * two loops race, the grid's full-canvas clear lands on top, and the probe
 * sees a frame that never changed.
 *
 * Both variants come from one template so the only difference between them is
 * the listener — a hand-written pair drifts, and a string replace that
 * silently misses would make the fixture pass for the wrong reason.
 */
const clickable = (listener) => `
const c = document.getElementById('game');
c.width = 1600; c.height = 900;
const ctx = c.getContext('2d');
let blob = null;
${listener}
function frame() {
  ctx.fillStyle = '#141018';
  ctx.fillRect(0, 0, c.width, c.height);
  for (let i = 0; i < 120; i++) {
    // Fixed hues, not cycling: the interactivity probe compares click-time
    // churn against idle churn, so a frame that repaints itself in new colours
    // every tick drowns out the click and reads as dead. That is the
    // busy-but-dead trap, and it is easy to build by accident.
    ctx.fillStyle = 'hsl(' + ((i * 37) % 360) + ',70%,55%)';
    ctx.fillRect(300 + (i % 15) * 70, 250 + Math.floor(i / 15) * 70, 60, 60);
  }
  if (blob) {
    ctx.fillStyle = '#ff2f6d';
    ctx.beginPath();
    ctx.arc(blob.x, blob.y, 90, 0, Math.PI * 2);
    ctx.fill();
  }
  requestAnimationFrame(frame);
}
frame();
`;

const INTERACTIVE = clickable(`addEventListener('pointerdown', (e) => {
  const r = c.getBoundingClientRect();
  blob = { x: e.clientX - r.left, y: e.clientY - r.top };
});`);

/** The same picture with the listener gone: controls dead, art untouched. */
const INTERACTIVE_BROKEN = clickable('/* listener removed */');

let port = 8794;

/**
 * Drive one task through the real round loop with a scripted agent and a
 * scripted critic.
 *
 * @param {object} o
 * @param {string} o.seed        app the task inherits
 * @param {string} o.round1      what the round-1 agent writes
 * @param {number} o.seedScore   art score the critic gives the inherited frame
 * @param {number} o.roundScore  art score the critic gives round 1
 * @param {boolean} o.judgeBaseline  false reproduces the old unscored baseline
 * @returns {Promise<string>} the file left on disk after the task
 */
async function run({ seed, round1, seedScore, roundScore, judgeBaseline }) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'forge-art-ratchet-'));
  const appDir = path.join(tmp, 'app');
  fs.mkdirSync(path.join(appDir, 'src'), { recursive: true });
  fs.writeFileSync(path.join(appDir, 'index.html'), HTML);
  fs.writeFileSync(path.join(appDir, 'src/main.js'), seed);

  const paths = { root: tmp, app: appDir, shots: path.join(tmp, 'shots') };
  fs.mkdirSync(paths.shots, { recursive: true });

  const server = await startStaticServer(appDir, port);
  const appUrl = `http://127.0.0.1:${port}/index.html`;
  port++;

  const state = new RunState(path.join(tmp, 'state.json'));
  state.data.goal = 'test';
  state.data.architecture = 'test';
  state.data.directives = { loop_until_perfect: true, visual_domain: '2d_game', quality_bar: 'test' };

  const task = {
    id: 'art-ratchet', title: 'make it worse without breaking it',
    description: 'test', acceptanceCriteria: [], files: ['src/main.js'],
    visual: true,
  };

  const script = { 1: () => fs.writeFileSync(path.join(appDir, 'src/main.js'), round1), 2: () => {} };
  const makeAgent = ({ round }) => ({
    async run() {
      (script[round] ?? (() => {}))();
      return { status: 'completed', filesTouched: ['src/main.js'], summary: 'scripted' };
    },
  });

  // First call is the baseline, the rest are rounds. Verdict is always FAIL so
  // the loop never exits early and the ratchet decision is always reached.
  let call = 0;
  const critiqueFn = async () => {
    call++;
    if (call === 1) {
      if (!judgeBaseline) throw new Error('baseline judgement suppressed (old behaviour)');
      return { score: seedScore, verdict: 'FAIL', issues: ['seed'], fixes: [], tier: 't', reads_as: 'seed' };
    }
    const onDisk = fs.readFileSync(path.join(appDir, 'src/main.js'), 'utf8');
    return {
      score: onDisk === seed ? seedScore : roundScore,
      verdict: 'FAIL', issues: ['round'], fixes: [], tier: 't', reads_as: 'round',
    };
  };

  const originalRounds = config.budgets.critiqueRounds;
  config.budgets.critiqueRounds = 2;
  await runTask({ task, state, paths, appUrl, slot: 1, makeAgent, critiqueFn });
  config.budgets.critiqueRounds = originalRounds;

  await server.close?.();
  return fs.readFileSync(path.join(appDir, 'src/main.js'), 'utf8');
}

// --- art regression ---------------------------------------------------------
let out = await run({ seed: RICH, round1: DRAB, seedScore: 62, roundScore: 30, judgeBaseline: true });
report(out === RICH, 'art regression reverted',
  out === RICH ? 'clean-but-drab round rolled back, rich frame restored' : 'DRAB survived');

out = await run({ seed: RICH, round1: DRAB, seedScore: 62, roundScore: 30, judgeBaseline: false });
report(out === DRAB, 'old behaviour was blind to it',
  'unscored baseline keeps the drab round (proves the fixture bites)');

// --- art improvement must still be kept -------------------------------------
out = await run({ seed: DRAB, round1: RICH, seedScore: 30, roundScore: 62, judgeBaseline: true });
report(out === RICH, 'art improvement still kept', 'ratchet does not block progress');

// --- interactivity regression ----------------------------------------------
// Prove the fixture is interactive BEFORE testing that losing it is reverted.
// The veto is relative, so an app the probe never saw as interactive would let
// the broken round through and the fixture would "pass" on the old code too —
// which is exactly how it failed the first two times it was written.
{
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'forge-art-ratchet-probe-'));
  const appDir = path.join(tmp, 'app');
  fs.mkdirSync(path.join(appDir, 'src'), { recursive: true });
  fs.writeFileSync(path.join(appDir, 'index.html'), HTML);
  fs.writeFileSync(path.join(appDir, 'src/main.js'), INTERACTIVE);
  const server = await startStaticServer(appDir, port);
  const live = await inspectApp({
    url: `http://127.0.0.1:${port}/index.html`,
    shotPath: path.join(tmp, 'probe.png'),
    actions: ENTRY_ACTIONS,
  });
  port++;
  server.close?.();
  report(live.interactive === true, 'interactive fixture is actually interactive',
    `probe says interactive=${live.interactive}`);

  const dead = fs.mkdtempSync(path.join(os.tmpdir(), 'forge-art-ratchet-probe-'));
  fs.mkdirSync(path.join(dead, 'app/src'), { recursive: true });
  fs.writeFileSync(path.join(dead, 'app/index.html'), HTML);
  fs.writeFileSync(path.join(dead, 'app/src/main.js'), INTERACTIVE_BROKEN);
  const server2 = await startStaticServer(path.join(dead, 'app'), port);
  const liveDead = await inspectApp({
    url: `http://127.0.0.1:${port}/index.html`,
    shotPath: path.join(dead, 'probe.png'),
    actions: ENTRY_ACTIONS,
  });
  port++;
  server2.close?.();
  report(liveDead.interactive === false, 'broken variant reads as not interactive',
    `probe says interactive=${liveDead.interactive}`);
}

out = await run({
  seed: INTERACTIVE, round1: INTERACTIVE_BROKEN,
  seedScore: 40, roundScore: 70, judgeBaseline: true,
});
report(out === INTERACTIVE, 'lost input reverted despite better art',
  out === INTERACTIVE ? 'a higher score cannot buy back dead controls' : 'broken build survived');
report(INTERACTIVE !== INTERACTIVE_BROKEN, 'the two input variants really differ',
  'template produced a genuine pair');

await closeBrowser();
console.log(failures ? `\n${failures} art-ratchet fixture(s) failed` : '\nall art-ratchet fixtures passed');
process.exit(failures ? 1 : 0);
