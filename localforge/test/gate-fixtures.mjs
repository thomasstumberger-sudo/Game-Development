/**
 * Fixture tests for the objective gate checks.
 *
 * A gate that never fires is worse than no gate, because it reads as evidence.
 * So every check here is proved twice: against an app broken in the exact way
 * the check exists to catch, and against a healthy app that a naive version of
 * the same check would wrongly condemn.
 *
 * Run: node test/gate-fixtures.mjs
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { inspectApp, startStaticServer, closeBrowser, ENTRY_ACTIONS } from '../src/browser.js';
import { Toolbelt } from '../src/tools.js';

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'forge-gate-'));
let failures = 0;

function report(pass, check, name, detail) {
  if (!pass) failures++;
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${check.padEnd(12)} ${name.padEnd(22)} ${detail}`);
}

function writeApp(name, files) {
  const dir = path.join(TMP, name);
  fs.mkdirSync(path.join(dir, 'src'), { recursive: true });
  for (const [f, body] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(dir, f)), { recursive: true });
    fs.writeFileSync(path.join(dir, f), body);
  }
  return dir;
}

const HTML = `<!doctype html><html><body style="margin:0;background:#141018;color:#eee">
<canvas id="game"></canvas><div id="overlay"></div>
<script type="module" src="./src/main.js"></script></body></html>`;

const ANIMATE = `
const ctx = c.getContext('2d');
let t = 0;
const loop = () => {
  ctx.fillStyle = '#141018'; ctx.fillRect(0, 0, c.width, c.height);
  for (let i = 0; i < 40; i++) {
    ctx.fillStyle = ['#7a5', '#58a', '#a76', '#696'][i % 4];
    ctx.beginPath();
    ctx.arc(200 + (i % 8) * 70, 150 + ((i / 8) | 0) * 70 + Math.sin((t + i) / 25) * 12, 28, 0, Math.PI * 2);
    ctx.fill();
  }
  t++; requestAnimationFrame(loop);
};
loop();`;

const HEAD = `const c = document.getElementById('game');
c.width = window.innerWidth; c.height = window.innerHeight;`;

// --------------------------------------------------------------- errorScreen
const ERROR_SCREEN_FIXTURES = {
  // The exact eight-hour failure: init throws, the app catches it and paints
  // its own crash card. Non-uniform pixels, live play area, 60 fps.
  'canvas-crash-card': {
    expect: true,
    files: {
      'index.html': HTML,
      'src/main.js': `${HEAD}
try {
  const state = undefined;
  state.tiles.get('0,0');
} catch (error) {
  console.error('Failed to initialize game:', error);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#ff0000'; ctx.fillRect(0, 0, 300, 140);
  ctx.fillStyle = '#fff'; ctx.font = '16px serif';
  ctx.fillText('Game initialization failed', 10, 30);
  ctx.fillText('Cannot read properties of undefined', 10, 50);
}`,
    },
  },

  // Same crash, reported in the DOM. Readable directly, so it is caught even
  // though the canvas behind it keeps animating.
  'dom-crash-overlay': {
    expect: true,
    files: {
      'index.html': HTML,
      'src/main.js': `${HEAD}${ANIMATE}
document.getElementById('overlay').textContent = 'Fatal error: renderer failed to start';`,
    },
  },

  // CONTROL: healthy animated game.
  'healthy-animated': {
    expect: false,
    files: { 'index.html': HTML, 'src/main.js': `${HEAD}${ANIMATE}` },
  },

  // CONTROL: a legitimately still scene (a paused board) that also logs a
  // harmless non-fatal error. Stillness alone must never fail the gate.
  'still-but-fine': {
    expect: false,
    files: {
      'index.html': HTML,
      'src/main.js': `${HEAD}
const ctx = c.getContext('2d');
for (let i = 0; i < 40; i++) {
  ctx.fillStyle = ['#7a5', '#58a', '#a76', '#696'][i % 4];
  ctx.fillRect(200 + (i % 8) * 70, 150 + ((i / 8) | 0) * 70, 56, 56);
}
console.error('could not load optional high-score table');`,
    },
  },
};

let port = 8830;
for (const [name, spec] of Object.entries(ERROR_SCREEN_FIXTURES)) {
  const dir = writeApp(name, spec.files);
  const server = await startStaticServer(dir, port);
  const res = await inspectApp({ url: `http://127.0.0.1:${port}/index.html`, actions: ENTRY_ACTIONS });
  server.close();
  port++;

  const got = Boolean(res.errorScreen);
  report(got === spec.expect, 'errorScreen', name,
    `got=${String(got).padEnd(5)} want=${String(spec.expect).padEnd(5)} ${res.errorScreen ?? ''}`);
}

await closeBrowser();

// -------------------------------------------------------- whole-app syntax
// The hole this closes: check_syntax used to look only at files the agent
// edited through the toolbelt, so a file corrupted by a shell redirect — or
// left broken by the other worker in a parallel pass — was invisible.
const GUTTERED = `    1  /**
    2   * An agent wrote this file out through 'cat -n'.
    3   */
    4  import { thing } from './other.js';
    5  export const value = thing;
`;

const syntaxCases = [
  {
    name: 'untouched-corrupt',
    expectOk: false,
    files: { 'index.html': HTML, 'src/main.js': `${HEAD}${ANIMATE}`, 'src/render.js': GUTTERED },
  },
  {
    name: 'all-clean',
    expectOk: true,
    files: { 'index.html': HTML, 'src/main.js': `${HEAD}${ANIMATE}`, 'src/render.js': `export const x = 1;\n` },
  },
  {
    name: 'stale-backup-ignored',
    expectOk: true,
    files: {
      'index.html': HTML,
      'src/main.js': `${HEAD}${ANIMATE}`,
      // Agents leave these behind constantly. They are not loaded by the page,
      // so failing a round over one would stall the run for nothing.
      'src/render.js.bak': GUTTERED,
      'src/main.js.backup': GUTTERED,
    },
  },
  {
    name: 'node_modules-ignored',
    expectOk: true,
    files: {
      'index.html': HTML,
      'src/main.js': `${HEAD}${ANIMATE}`,
      'node_modules/junk/broken.js': GUTTERED,
    },
  },
];

for (const spec of syntaxCases) {
  const dir = writeApp(`syntax-${spec.name}`, spec.files);
  const toolbelt = new Toolbelt({ workspace: dir, appDir: dir });
  // Deliberately touch nothing: the point is that the sweep does not depend on
  // this agent having edited the broken file.
  const res = await toolbelt.check_syntax({ all: true });
  report(res.ok === spec.expectOk, 'syntax-all', spec.name,
    `ok=${String(res.ok).padEnd(5)} want=${String(spec.expectOk).padEnd(5)} ${(res.problems ?? []).join(' | ').slice(0, 60)}`);
}

// And the regression that motivated the flag: touched-files-only must miss it.
{
  const dir = writeApp('syntax-proves-the-hole', {
    'index.html': HTML, 'src/main.js': `${HEAD}${ANIMATE}`, 'src/render.js': GUTTERED,
  });
  const toolbelt = new Toolbelt({ workspace: dir, appDir: dir });
  const touchedOnly = await toolbelt.check_syntax({});
  report(touchedOnly.ok === true, 'syntax-all', 'old-behaviour-blind',
    `touched-only ok=${touchedOnly.ok} (proves the sweep is what catches it)`);
}

// ------------------------------------------------------------- interactive
// The hole this closes: `interactive` had no fixtures at all, and its
// frame-wide pixel-fraction metric is resolution-invariant — a 48px unit on a
// 1600x900 canvas moves ~0.2% of the frame, under the 1% floor. A build whose
// click-to-move worked reported NOT INTERACTIVE for a whole run.
const SMALL_SPRITE = `
const ctx = c.getContext('2d');
let ux = c.width / 2, uy = c.height / 2;
const draw = () => {
  ctx.fillStyle = '#141018'; ctx.fillRect(0, 0, c.width, c.height);
  for (let i = 0; i < 40; i++) {
    ctx.fillStyle = ['#2d3b22', '#1e3040', '#303840', '#243024'][i % 4];
    ctx.fillRect(200 + (i % 8) * 70, 150 + ((i / 8) | 0) * 70, 60, 60);
  }
  // A 48px unit: the whole point is that this is tiny relative to the frame.
  ctx.fillStyle = '#e0b070';
  ctx.beginPath(); ctx.arc(ux, uy, 24, 0, Math.PI * 2); ctx.fill();
  requestAnimationFrame(draw);
};
draw();`;

const INTERACTIVE_FIXTURES = {
  // The shamanfae case: clicking moves a small sprite one step. Responsive.
  'small-sprite-move': {
    expect: true,
    files: {
      'index.html': HTML,
      'src/main.js': `${HEAD}${SMALL_SPRITE}
c.addEventListener('mouseup', (e) => { ux = e.clientX; uy = e.clientY; });`,
    },
  },

  // Same small sprite, no listener at all. Must still read as dead.
  'small-sprite-dead': {
    expect: false,
    files: { 'index.html': HTML, 'src/main.js': `${HEAD}${SMALL_SPRITE}` },
  },

  // CONTROL: busy animation, no input handling. The idle baseline is what has
  // to reject this — locally dramatic every frame, but not because of us.
  'busy-but-dead': {
    expect: false,
    files: { 'index.html': HTML, 'src/main.js': `${HEAD}${ANIMATE}` },
  },

  // CONTROL: full-frame response. The frame-wide signal alone should catch it.
  'modal-on-click': {
    expect: true,
    files: {
      'index.html': HTML,
      'src/main.js': `${HEAD}
const ctx = c.getContext('2d');
let open = false;
const draw = () => {
  ctx.fillStyle = open ? '#c0d0e0' : '#141018';
  ctx.fillRect(0, 0, c.width, c.height);
  requestAnimationFrame(draw);
};
draw();
c.addEventListener('mouseup', () => { open = true; });`,
    },
  },
};

for (const [name, spec] of Object.entries(INTERACTIVE_FIXTURES)) {
  const dir = writeApp(`interactive-${name}`, spec.files);
  const server = await startStaticServer(dir, port);
  const res = await inspectApp({ url: `http://127.0.0.1:${port}/index.html` });
  server.close();
  port++;

  report(res.interactive === spec.expect, 'interactive', name,
    `got=${String(res.interactive).padEnd(5)} want=${String(spec.expect)}`);
}

await closeBrowser();

fs.rmSync(TMP, { recursive: true, force: true });
console.log(failures ? `\n${failures} fixture(s) FAILED` : '\nall gate fixtures passed');
process.exit(failures ? 1 : 0);
