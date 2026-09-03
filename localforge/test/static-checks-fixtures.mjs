/**
 * Fixtures for the deterministic gates that run before the vision critic.
 *
 * Each rule is proved twice: against code that must trip it, and against
 * healthy-but-unusual code that must not. A gate that never fires is worse
 * than no gate, and a gate that fires on working code stalls the run — the
 * first draft of this analyzer did the second, reporting every `onclick`
 * handler in a working game as dead code because it stripped HTML attribute
 * values before searching them.
 *
 * Pure: no Chrome, no Ollama.
 *
 * Run: node test/static-checks-fixtures.mjs
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { analyzeApp, newFindings, blocking, describeFindings } from '../src/static-checks.js';

let failures = 0;
function report(pass, name, detail) {
  if (!pass) failures++;
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name.padEnd(54)} ${detail}`);
}

function app(files) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'forge-static-'));
  for (const [rel, body] of Object.entries(files)) {
    const abs = path.join(dir, rel);
    fs.mkdirSync(path.dirname(abs), { recursive: true });
    fs.writeFileSync(abs, body);
  }
  return dir;
}
const has = (dir, rule) => analyzeApp(dir).findings.some((f) => f.rule === rule);
const HTML = '<canvas id="game"></canvas><script src="src/main.js"></script>';

// --- orphan-symbol ----------------------------------------------------------
report(has(app({
  'index.html': HTML,
  'src/main.js': 'function used(){ helper(); }\nfunction helper(){}\nused();\n',
  'src/dead.js': 'function addFloatingDamage(x, y, dmg) { return x + y + dmg; }\n',
}), 'orphan-symbol'), 'an uncalled function is caught', 'addFloatingDamage');

// The false positive that mattered: handlers referenced only from HTML.
report(!has(app({
  'index.html': '<button onclick="fireSpell()">cast</button><script src="src/main.js"></script>',
  'src/main.js': 'function fireSpell(){ return 1; }\n',
}), 'orphan-symbol'), 'an onclick-only handler is NOT an orphan', 'HTML attributes are searched');

// A function called only by itself through requestAnimationFrame is alive.
report(!has(app({
  'index.html': HTML,
  'src/main.js': 'function frameLoop(){ requestAnimationFrame(frameLoop); }\nframeLoop();\n',
}), 'orphan-symbol'), 'a self-scheduling loop is not an orphan', 'rAF self-reference counts');

// A name that appears only inside a comment is still dead.
report(has(app({
  'index.html': HTML,
  'src/main.js': 'function wiredUp(){}\nwiredUp();\n// TODO: call unusedThing() later\nfunction unusedThing(){}\n',
}), 'orphan-symbol'), 'a mention in a comment does not count as a call', 'comments stripped');

// --- canvas-zero-guard ------------------------------------------------------
report(has(app({
  'index.html': HTML,
  'src/main.js': 'const c=document.getElementById("game");\nif (c.width === 0) { c.width = 800; }\naddEventListener("resize",()=>{});\n',
}), 'canvas-zero-guard'), 'the dead 300x150 resize guard is caught', 'c.width === 0');

report(!has(app({
  'index.html': HTML,
  'src/main.js': 'const c=document.getElementById("game");\nconst r=c.getBoundingClientRect();\nif (c.width !== r.width) { c.width = r.width; }\naddEventListener("resize",()=>{});\n',
}), 'canvas-zero-guard'), 'a correct layout-size comparison passes', 'compares against rect');

// A bounding rect CAN legitimately be zero wide (hidden element), so this is a
// correct check and must not be reported as the dead 300x150 guard.
report(!has(app({
  'index.html': HTML,
  'src/main.js': 'const c=document.getElementById("game");\nconst rect=c.getBoundingClientRect();\nif (rect.width === 0) return;\naddEventListener("resize",()=>{});\n',
}), 'canvas-zero-guard'), 'rect.width === 0 is not the canvas guard', 'receiver must be the canvas');

// --- per-frame-allocation ---------------------------------------------------
// The exact shape that destroyed a build: a draw function building a sprite.
report(has(app({
  'index.html': HTML,
  'src/main.js': 'function drawTerrainTextures(){ const t = makeSprite(800,600,()=>{}); ctx.drawImage(t,0,0); }\ndrawTerrainTextures();\naddEventListener("resize",()=>{});\n',
}), 'per-frame-allocation'), 'a sprite built inside a draw function is caught', 'drawTerrainTextures');

report(!has(app({
  'index.html': HTML,
  'src/main.js': 'const cached = makeSprite(800,600,()=>{});\nfunction drawTerrain(){ ctx.drawImage(cached,0,0); }\ndrawTerrain();\naddEventListener("resize",()=>{});\n',
}), 'per-frame-allocation'), 'a sprite cached at load passes', 'allocation hoisted out');

// Allocation in a non-render function is not per-frame.
report(!has(app({
  'index.html': HTML,
  'src/main.js': 'function buildAssets(){ return makeSprite(800,600,()=>{}); }\nbuildAssets();\naddEventListener("resize",()=>{});\n',
}), 'per-frame-allocation'), 'allocation outside a render function passes', 'buildAssets');

// --- falsy-coordinate-guard -------------------------------------------------
report(has(app({
  'index.html': HTML,
  'src/main.js': 'function move(startQ){ if (!startQ) return; return startQ; }\nmove(1);\naddEventListener("resize",()=>{});\n',
}), 'falsy-coordinate-guard'), 'if (!startQ) is caught', '0 is a real coordinate');

// The false positive that mattered: a boolean ending in "r".
report(!has(app({
  'index.html': HTML,
  'src/main.js': 'let gameOver=false;\nfunction step(){ if (!gameOver) { tick(); } }\nfunction tick(){}\nstep();\naddEventListener("resize",()=>{});\n',
}), 'falsy-coordinate-guard'), 'a boolean named gameOver is NOT a coordinate', 'suffix needs a word boundary');

report(!has(app({
  'index.html': HTML,
  'src/main.js': 'function pick(tileQ){ if (tileQ == null) return; return tileQ; }\npick(0);\naddEventListener("resize",()=>{});\n',
}), 'falsy-coordinate-guard'), 'an explicit null check passes', 'tileQ == null');

// --- no-resize-listener -----------------------------------------------------
report(has(app({
  'index.html': HTML, 'src/main.js': 'const c=document.getElementById("game");\nc.width = 800;\n',
}), 'no-resize-listener'), 'a canvas sized with no resize listener is caught', 'no listener');

report(!has(app({
  'index.html': HTML,
  'src/main.js': 'const c=document.getElementById("game");\nc.width = 800;\naddEventListener("resize", () => { c.width = innerWidth; });\n',
}), 'no-resize-listener'), 'a resize listener satisfies the rule', 'listener present');

// --- createElement, which only matches with string literals intact ----------
report(has(app({
  'index.html': HTML,
  'src/main.js': 'function renderScene(){ const t = document.createElement("canvas"); ctx.drawImage(t,0,0); }\nrenderScene();\naddEventListener("resize",()=>{});\n',
}), 'per-frame-allocation'), 'createElement("canvas") in a render function is caught', 'literals preserved');

// --- line numbers -----------------------------------------------------------
// Blanking a block comment down to one space shifts every line after it, and
// the brief then sends the agent to a line that has nothing wrong with it.
{
  const dir = app({
    'index.html': HTML,
    'src/main.js': '/*\n * a\n * four\n * line\n */\nfunction wired(){}\nwired();\nfunction deadOne(){ return 1; }\naddEventListener("resize",()=>{});\n',
  });
  const f = analyzeApp(dir).findings.find((x) => x.symbol === 'deadOne');
  const src = fs.readFileSync(path.join(dir, 'src/main.js'), 'utf8').split('\n');
  report(f && /deadOne/.test(src[f.line - 1] ?? ''),
    'reported line survives a multi-line comment', `line ${f?.line}: ${(src[f?.line - 1] ?? '').slice(0, 30)}`);
}

// --- the relative gate ------------------------------------------------------
// This is what keeps a pre-existing defect from stalling every round forever.
const dirty = app({
  'index.html': HTML,
  'src/main.js': 'function move(startQ){ if (!startQ) return; }\nmove(1);\naddEventListener("resize",()=>{});\n',
});
const before = analyzeApp(dirty).findings;
report(blocking(before).length > 0, 'the seed itself trips a blocking rule', 'inherited defect present');
report(newFindings(before, before).length === 0,
  'an inherited defect is not attributed to the round', 'nothing introduced => nothing blocks');

fs.writeFileSync(path.join(dirty, 'src/extra.js'), 'function neverCalled(){ return 42; }\n');
const after = analyzeApp(dirty).findings;
const introduced = newFindings(before, after);
report(blocking(introduced).length === 1 && introduced[0].symbol === 'neverCalled',
  'a newly introduced defect does block', `introduced: ${introduced.map((f) => f.symbol).join(',')}`);

// --- severity ---------------------------------------------------------------
report(blocking([{ severity: 'minor' }]).length === 0,
  'minor findings are advisory, never blocking', 'no-resize-listener cannot revert a round');

// --- brief rendering --------------------------------------------------------
const text = describeFindings(after);
report(/critical|major/.test(text) && /Fix:/.test(text),
  'findings render with severity and a fix', `${text.length} chars`);
report(describeFindings([]) === '', 'no findings renders nothing', 'empty string');
const many = Array.from({ length: 40 }, (_, i) => ({
  rule: 'orphan-symbol', severity: 'major', file: 'a.js', line: i, symbol: `f${i}`, message: 'm', fix: 'f',
}));
report(/and 28 more/.test(describeFindings(many)), 'a long list is capped, and says so', 'cap at 12');

console.log(failures ? `\n${failures} static-check fixture(s) failed` : '\nall static-check fixtures passed');
process.exit(failures ? 1 : 0);
