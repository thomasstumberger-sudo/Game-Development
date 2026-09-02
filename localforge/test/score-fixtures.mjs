/**
 * Fixtures for the objective the whole forge climbs towards.
 *
 * Until now every rubric axis graded visual craft, so the number the ratchet
 * compared could not distinguish a round that implemented its task from one
 * that implemented nothing, and could not see a build whose controls had died.
 * That went unnoticed across eight runs and ~350 critic evaluations because
 * nothing anywhere asserted on the shape of the score.
 *
 * These are pure functions: no Chrome, no Ollama, instant.
 *
 * Run: node test/score-fixtures.mjs
 */
import { functionalScore, compositeScore } from '../src/critic.js';
import { config } from '../src/config.js';

let failures = 0;
function report(pass, name, detail) {
  if (!pass) failures++;
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name.padEnd(52)} ${detail}`);
}

const clean = { fps: 60, pageErrors: [], consoleErrors: [], interactive: true };
const dead = { fps: 60, pageErrors: [], consoleErrors: [], interactive: false };
const unknown = { fps: 60, pageErrors: [], consoleErrors: [], interactive: null };

// --- the task actually getting done has to move the number ------------------
const done = functionalScore({ health: clean, criteriaMet: 4, criteriaTotal: 4 }).score;
const notDone = functionalScore({ health: clean, criteriaMet: 0, criteriaTotal: 4 }).score;
report(done > notDone, 'meeting the acceptance criteria raises the score',
  `${notDone} -> ${done}`);
report(notDone < 60, 'a round that implemented nothing scores poorly',
  `unmet criteria => ${notDone}/100`);

// --- losing the controls has to move the number -----------------------------
const live = functionalScore({ health: clean, criteriaMet: 4, criteriaTotal: 4 }).score;
const broken = functionalScore({ health: dead, criteriaMet: 4, criteriaTotal: 4 }).score;
report(broken < live, 'dead controls cost function score', `${live} -> ${broken}`);

// An unknown probe result is not a failure, and must not be scored as one:
// pointer-locked and keyboard-only builds legitimately report null.
const un = functionalScore({ health: unknown, criteriaMet: 4, criteriaTotal: 4 }).score;
report(un === live, 'unknown interactivity is not punished', `null scores ${un}, true scores ${live}`);

// --- frame rate -------------------------------------------------------------
const slow = functionalScore({
  health: { ...clean, fps: 12 }, criteriaMet: 4, criteriaTotal: 4,
}).score;
report(slow < live, 'a 12fps build scores below a 60fps one', `${live} -> ${slow}`);

// --- the composite must still be mostly art ---------------------------------
const w = config.critic.artWeight;
report(w > 0.5 && w < 1, 'art is the majority of the composite but not all of it', `artWeight=${w}`);

// --- calibration: the bar has to be reachable by a working build ------------
// This is the whole point. Under the old scoring the bar was the art score
// alone, and a canvas prototype topped out at 38 against a bar of 62.
const bar = config.critic.passScore;
const workingDecentArt = compositeScore(42, 100);
const workingPlaceholderArt = compositeScore(30, 100);
const prettyButBroken = compositeScore(75, 0);

report(workingDecentArt >= bar,
  'working build with decent art can pass', `art 42 + function 100 => ${workingDecentArt} vs bar ${bar}`);
report(workingPlaceholderArt < bar,
  'placeholder art still fails even when it works', `art 30 + function 100 => ${workingPlaceholderArt}`);
report(prettyButBroken < bar,
  'pretty but non-functional still fails', `art 75 + function 0 => ${prettyButBroken}`);
report(compositeScore(42, 100) > compositeScore(42, 0),
  'at equal art, the working build wins', `${compositeScore(42, 0)} -> ${compositeScore(42, 100)}`);

// --- no functional signal at all --------------------------------------------
const none = functionalScore({ health: null, criteriaMet: 0, criteriaTotal: 0 });
report(none.score === 0 && none.parts.length > 0,
  'absent signal is reported, not silently treated as perfect', none.parts.join(','));

console.log(failures ? `\n${failures} score fixture(s) failed` : '\nall score fixtures passed');
process.exit(failures ? 1 : 0);
