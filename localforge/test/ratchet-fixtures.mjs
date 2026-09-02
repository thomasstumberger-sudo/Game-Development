/**
 * Fixture tests for the round ratchet.
 *
 * The harness used to have no way to say "that round made it worse". A round
 * that broke the build left the breakage on disk, the next round started from
 * it, and the tree could only random-walk. Over a 16h run it walked into a
 * blank screen and stayed there: 304 of 322 verified rounds were broken.
 *
 * So the ratchet is the one thing that must never silently no-op. Every rule
 * here is proved in both directions: a worse round is reverted, and a better
 * or equal round is kept. A ratchet that reverts everything would look just as
 * "safe" in the logs while making progress impossible.
 *
 * Run: node test/ratchet-fixtures.mjs   (fast, no Ollama, no Chrome)
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { captureApp, restoreApp, fitness, describeFitness } from '../src/snapshot.js';

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'forge-ratchet-'));
let failures = 0;

function report(pass, group, name, detail) {
  if (!pass) failures++;
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${group.padEnd(10)} ${name.padEnd(34)} ${detail}`);
}

function makeApp(name, files) {
  const dir = path.join(TMP, name);
  fs.mkdirSync(dir, { recursive: true });
  for (const [f, body] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(dir, f)), { recursive: true });
    fs.writeFileSync(path.join(dir, f), body);
  }
  return dir;
}

function readAll(dir) {
  const out = {};
  const walk = (d, prefix = '') => {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const rel = prefix ? `${prefix}/${e.name}` : e.name;
      if (e.isDirectory()) walk(path.join(d, e.name), rel);
      else out[rel] = fs.readFileSync(path.join(d, e.name), 'utf8');
    }
  };
  walk(dir);
  return out;
}

// --------------------------------------------------------------- health states
const HEALTHY = { pageErrors: [], consoleErrors: [], blankScreen: false, deadPlayfield: false, errorScreen: null, interactive: true, fps: 60 };
const BLANK = { ...HEALTHY, blankScreen: true };
const DEAD_PLAY = { ...HEALTHY, deadPlayfield: true };
const PAGE_ERR = { ...HEALTHY, pageErrors: ['Duplicate export of drawMapWithEffects'] };
const CRASH = { ...HEALTHY, errorScreen: 'TypeError: state.tiles is undefined' };
const LOAD_ERR = { ...HEALTHY, loadError: 'net::ERR_CONNECTION_REFUSED' };

// ============================================================ capture / restore
{
  const dir = makeApp('roundtrip', {
    'index.html': '<!doctype html><body><canvas id=game></canvas></body>',
    'src/main.js': 'export const VERSION = 1;',
    'src/hex.js': 'export const SIZE = 32;',
  });
  const snap = captureApp(dir);
  const before = readAll(dir);

  // A round mangles one file, deletes another and adds a stray.
  fs.writeFileSync(path.join(dir, 'src/main.js'), 'export const VERSION = 2; // broken');
  fs.unlinkSync(path.join(dir, 'src/hex.js'));
  fs.writeFileSync(path.join(dir, 'src/main-fixed.js'), 'garbage');

  restoreApp(dir, snap);
  const after = readAll(dir);

  report(JSON.stringify(before) === JSON.stringify(after), 'restore', 'exact roundtrip',
    `${Object.keys(after).length} files`);
  report(!fs.existsSync(path.join(dir, 'src/main-fixed.js')), 'restore', 'removes files added after snap',
    'stray deleted');
  report(fs.existsSync(path.join(dir, 'src/hex.js')), 'restore', 'resurrects deleted file',
    'hex.js back');
}

{
  // The snapshot must be a copy, not a live view: restoring after further edits
  // still yields the original bytes.
  const dir = makeApp('detached', { 'src/main.js': 'original' });
  const snap = captureApp(dir);
  fs.writeFileSync(path.join(dir, 'src/main.js'), 'mutated');
  restoreApp(dir, snap);
  report(fs.readFileSync(path.join(dir, 'src/main.js'), 'utf8') === 'original',
    'restore', 'snapshot is detached', 'bytes preserved');
}

// ======================================================================= fitness
// Ordering is the whole contract: a round is kept only if it scores >= the best
// so far. Each pair below is a decision the 16h run got wrong.
const cases = [
  ['healthy beats blank', fitness(HEALTHY, null), fitness(BLANK, null)],
  ['healthy beats dead playfield', fitness(HEALTHY, null), fitness(DEAD_PLAY, null)],
  ['healthy beats page error', fitness(HEALTHY, null), fitness(PAGE_ERR, null)],
  ['healthy beats crash screen', fitness(HEALTHY, null), fitness(CRASH, null)],
  ['blank beats load error', fitness(BLANK, null), fitness(LOAD_ERR, null)],
  ['dead playfield beats blank', fitness(DEAD_PLAY, null), fitness(BLANK, null)],
  ['higher critic score wins', fitness(HEALTHY, { score: 44 }), fitness(HEALTHY, { score: 23 })],
];
for (const [name, better, worse] of cases) {
  report(better > worse, 'fitness', name, `${better} > ${worse}`);
}

// A critic score can never outrank a broken build. This is the exact inversion
// that let a pretty-but-dead frame beat a plain working one.
report(fitness(HEALTHY, { score: 0 }) > fitness(BLANK, { score: 99 }),
  'fitness', 'health outranks any score', 'clean/0 > blank/99');

// Unjudged healthy rounds must not be treated as zero-scoring, or the first
// clean round would out-rank every later judged one.
report(fitness(HEALTHY, null) <= fitness(HEALTHY, { score: 1 }),
  'fitness', 'unjudged is not a high score', 'null <= 1');

// Equal states must compare equal, so an unchanged round is kept rather than
// pointlessly reverted (reverting on ties would discard non-visual progress).
report(fitness(HEALTHY, { score: 30 }) === fitness(HEALTHY, { score: 30 }),
  'fitness', 'ties compare equal', 'idempotent');

report(typeof describeFitness(fitness(BLANK, null)) === 'string'
  && describeFitness(fitness(BLANK, null)).length > 0,
  'fitness', 'describes itself for the log', describeFitness(fitness(BLANK, null)));

// Every tier must resolve to its own label. Two tiers sharing a value silently
// mislabelled syntax errors as load errors in the round log.
const SYNTAX = { syntaxError: true, pageErrors: ['src/main.js: Unexpected token'], consoleErrors: [] };
report(describeFitness(fitness(SYNTAX, null)) === 'syntaxError',
  'fitness', 'syntax error labelled correctly', describeFitness(fitness(SYNTAX, null)));
report(fitness(LOAD_ERR, null) > fitness(SYNTAX, null),
  'fitness', 'unparseable is the worst state', 'syntax < loadError');
report(describeFitness(fitness(HEALTHY, { score: 44 })) === 'clean @ 44/100',
  'fitness', 'healthy label reads as clean', describeFitness(fitness(HEALTHY, { score: 44 })));

// ======================================================================== verdict
fs.rmSync(TMP, { recursive: true, force: true });
console.log(failures ? `\n${failures} FAILURE(S)` : '\nall ratchet fixtures passed');
process.exit(failures ? 1 : 0);
