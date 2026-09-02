/**
 * Fixtures for the repo survey the planner reads.
 *
 * The planner used to decompose a goal with no view of the code, and produced
 * 26 cosmetic tasks for a game whose gameplay was already written. The survey
 * is the fix, so the things that would quietly break it are worth pinning:
 * a tree that does not parse (surveys run mid-edit), load order that is not
 * alphabetical, and a digest large enough to crowd out the goal itself.
 *
 * Pure: no Chrome, no Ollama.
 *
 * Run: node test/survey-fixtures.mjs
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { surveyApp } from '../src/survey.js';

let failures = 0;
function report(pass, name, detail) {
  if (!pass) failures++;
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name.padEnd(52)} ${detail}`);
}

function makeApp(files) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'forge-survey-'));
  for (const [rel, body] of Object.entries(files)) {
    const abs = path.join(dir, rel);
    fs.mkdirSync(path.dirname(abs), { recursive: true });
    fs.writeFileSync(abs, body);
  }
  return dir;
}

// --- empty project ----------------------------------------------------------
const empty = surveyApp(makeApp({}));
report(empty.empty && /from scratch/i.test(empty.text),
  'empty app is reported as a new project', empty.text.slice(0, 40));

// --- a real project ---------------------------------------------------------
const app = makeApp({
  'index.html': `<script src="src/data.js"></script>
<script src="src/combat.js"></script>
<script src="src/draw.js"></script>`,
  'src/data.js': 'const SPELLS = [1,2];\nconst CLASSES = {a:1};\n',
  'src/combat.js': 'function resolveAttack(a,b){}\nasync function applyDamage(x){}\nclass Encounter {}\n',
  'src/draw.js': 'const drawAll = () => {};\nfunction drawHud(){}\n',
});
const s = surveyApp(app);
report(!s.empty && s.fileCount === 4, 'counts every source file', `${s.fileCount} files`);
report(/resolveAttack/.test(s.text) && /applyDamage/.test(s.text) && /Encounter/.test(s.text),
  'finds functions, async functions and classes', 'combat symbols present');
report(/SPELLS/.test(s.text) && /CLASSES/.test(s.text),
  'finds top-level data tables', 'array and object consts present');
report(/drawAll/.test(s.text), 'finds arrow-function consts', 'drawAll present');

// Load order is the thing a planner needs and alphabetical order destroys:
// combat.js must appear before draw.js because the page says so.
const order = s.text.indexOf('src/combat.js') < s.text.indexOf('src/draw.js');
report(order && /Script load order/.test(s.text),
  'reports script load order, not alphabetical order', 'combat before draw');

// --- a tree mid-edit --------------------------------------------------------
// Surveys run on trees an agent is halfway through rewriting. A survey that
// throws is useless exactly when it is most needed.
let survivedBroken = true;
let brokenText = '';
try {
  brokenText = surveyApp(makeApp({
    'index.html': '<script src="src/ok.js"></script>',
    'src/ok.js': 'function fine(){}\n',
    'src/broken.js': 'this is not ( valid javascript at all {{{\n',
  })).text;
} catch (err) {
  survivedBroken = false;
  brokenText = err.message;
}
report(survivedBroken && /fine/.test(brokenText),
  'a file that does not parse does not break the survey', 'unparseable file tolerated');

// --- budget -----------------------------------------------------------------
const huge = {};
huge['index.html'] = '<html></html>';
for (let i = 0; i < 400; i++) huge[`src/mod${i}.js`] = `function f${i}(){}\n`.repeat(40);
const big = surveyApp(makeApp(huge));
report(big.text.length <= 6500, 'digest stays inside its context budget',
  `${big.text.length} chars for ${big.fileCount} files`);
report(/more file\(s\) not listed/.test(big.text),
  'truncation is stated rather than silent', 'says what it dropped');

// --- the stack-echo detector ------------------------------------------------
// The planner's "architecture" field is every coder agent's map of the
// project. Asked for it, the model pastes the stack description back: long,
// on-topic, and useless. A length check alone passes that straight through,
// which is exactly what happened on a live re-plan.
const { isEchoOf, looksCosmetic } = await import('../src/planner.js');
const stack = 'vanilla HTML, CSS and canvas 2D in the browser. Classic script tags in fixed load order, '
  + 'NOT ES modules, no import or export anywhere, no bundler, no third-party libraries.';

const echoed = 'Vanilla HTML, CSS and canvas 2D in the browser, using classic script tags in a fixed '
  + 'load order. Not ES modules; no import or export anywhere, no bundler and no third-party libraries.';
report(isEchoOf(echoed, stack), 'paraphrased stack echo is caught',
  'reflowed restatement rejected');

const real = 'State lives in a single global game object created by state.js. terrain.js owns the height '
  + 'array and exposes getTerrainY; projectiles.js steps ballistics each frame and calls deformTerrain '
  + 'on impact; draw.js renders sky, terrain then units in that order from loop.js.';
report(!isEchoOf(real, stack), 'a genuine architecture description survives',
  'real module breakdown kept');
report(!isEchoOf(real, ''), 'no stack to compare against is not an echo', 'empty stack handled');

// --- degenerate output -------------------------------------------------------
// A live re-plan returned this as the architecture. It is long enough for the
// length check and not an echo of anything, so both earlier guards passed it.
const { looksLikeProse } = await import('../src/planner.js');
const garbage = 'task_graph_v1.0.0_2024-05-21T10:00:00Z_8973d2f6-3c8b-4d5a-9e3a-1f2d4e6f8g7h_0001'
  + '.jsonld.jsonld.jsonld.jsonld.jsonld.jsonld';
report(!looksLikeProse(garbage), 'a repetition loop is rejected as architecture',
  'observed live: jsonld repetition');
report(looksLikeProse(real), 'real prose passes the prose check', 'module breakdown accepted');
report(!looksLikeProse('canvas'), 'a one-word answer is rejected', 'too short');
report(!looksLikeProse('a '.repeat(60)), 'padding without sentences is rejected', 'no real words');

// --- grounding: does the description describe THIS project? -----------------
// Observed live from qwen3:32b. Grammatical, confident, passes every check
// above, and says nothing about how the code is organised.
const { mentionsProject } = await import('../src/planner.js');
const s2 = s;
const real2 = 'State lives in a global object from state.js. combat.js owns resolveAttack and '
  + 'applyDamage; draw.js renders through drawAll each frame.';
const title = 'Wizard Wars Deepening & Beautification Plan (12 tasks, 1200ms total estimate, '
  + '60fps baseline preserved, zero page errors guaranteed)';
report(!mentionsProject(title, s2), 'a project title is not an architecture',
  'names no module of the surveyed project');
report(mentionsProject(real2, s2), 'a real module breakdown is grounded',
  'names combat.js and its symbols');
report(mentionsProject(title, { empty: true, text: '' }),
  'a new project has nothing to ground against', 'empty survey accepted');

// --- the balance classifier -------------------------------------------------
report(looksCosmetic({ id: 'add-screen-shake', title: 'Add screen shake on impact', description: '' }),
  'polish tasks are classified as cosmetic', 'screen shake');
report(looksCosmetic({ id: 'add-hit-flash-and', title: 'Add hit flash and damage numbers', description: '' }),
  'damage numbers are cosmetic', 'hit flash');
report(!looksCosmetic({ id: 'add-computer-opponent', title: 'Add computer opponent with AI', description: 'turn logic' }),
  'behavioural tasks are not misclassified', 'AI opponent');
report(!looksCosmetic({ id: 'add-match-structure-and', title: 'Add match structure and scoreboard', description: '' }),
  'match structure is behavioural', 'match structure');

console.log(failures ? `\n${failures} survey fixture(s) failed` : '\nall survey fixtures passed');
process.exit(failures ? 1 : 0);
