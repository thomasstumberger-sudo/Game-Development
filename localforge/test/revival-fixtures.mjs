/**
 * Fixture tests for the task revival policy.
 *
 * `reviveStalledTasks` used to set `t.attempts = 0` on every refinement pass,
 * which made `maxTaskAttempts` unenforceable: the same task could be retried
 * for as long as the wall clock ran. Combined with a pass score no build ever
 * reached, that is why a 16h run re-attempted the same handful of tasks all
 * night and finished with fewer completed tasks than it started with.
 *
 * The policy now has to satisfy two opposing requirements, so both are proved
 * here: it must keep retrying work that is still improving, and it must let go
 * of work that is not. A policy that only did the first never terminates; one
 * that only did the second gives up on the first stumble.
 *
 * Run: node test/revival-fixtures.mjs   (fast, no Ollama, no Chrome)
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { reviveStalledTasks } from '../src/orchestrator.js';
import { RunState } from '../src/state.js';
import { config } from '../src/config.js';

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'forge-revival-'));
let failures = 0;

function report(pass, name, detail) {
  if (!pass) failures++;
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name.padEnd(44)} ${detail}`);
}

let n = 0;
function stateWith(tasks) {
  const s = new RunState(path.join(TMP, `state-${n++}.json`));
  s.data.tasks = tasks;
  return s;
}

const BAR = config.critic.passScore;

// --------------------------------------------------- below-bar work is retried
{
  const s = stateWith([{ id: 'a', status: 'completed', visual: true, lastScore: BAR - 20 }]);
  const { belowBar } = reviveStalledTasks(s);
  report(belowBar === 1 && s.task('a').status === 'pending',
    'below-bar task is revived', `status=${s.task('a').status}`);
  report(s.task('a').revivals === 1, 'revival is counted', `revivals=${s.task('a').revivals}`);
}

// ------------------------------------------------------ passing work is left be
{
  const s = stateWith([{ id: 'a', status: 'completed', visual: true, lastScore: BAR + 5 }]);
  const { belowBar } = reviveStalledTasks(s);
  report(belowBar === 0 && s.task('a').status === 'completed',
    'task at the bar is not revived', `score=${BAR + 5} >= ${BAR}`);
}

// ------------------------------------------------------------ improvement rule
{
  // Improving between revivals earns another attempt.
  const s = stateWith([{
    id: 'a', status: 'completed', visual: true, lastScore: 40, scoreAtLastRevival: 25, revivals: 1,
  }]);
  const { belowBar } = reviveStalledTasks(s);
  report(belowBar === 1 && s.task('a').status === 'pending',
    'improving task keeps its retries', '25 -> 40');
  report(s.task('a').scoreAtLastRevival === 40,
    'improvement baseline moves forward', `baseline=${s.task('a').scoreAtLastRevival}`);
}
{
  // Flat or falling between revivals ends it. This is the loop that ran all night.
  const s = stateWith([{
    id: 'a', status: 'completed', visual: true, lastScore: 23, scoreAtLastRevival: 23, revivals: 1,
  }]);
  const { belowBar } = reviveStalledTasks(s);
  report(belowBar === 0 && s.task('a').status === 'completed',
    'plateaued task is left alone', '23 -> 23');
}
{
  const s = stateWith([{
    id: 'a', status: 'completed', visual: true, lastScore: 19, scoreAtLastRevival: 27, revivals: 1,
  }]);
  const { belowBar } = reviveStalledTasks(s);
  report(belowBar === 0, 'regressing task is left alone', '27 -> 19');
}

// ------------------------------------------------------------- the hard ceiling
{
  const s = stateWith([{
    id: 'a', status: 'parked', visual: true, lastScore: 10, revivals: config.budgets.maxRevivals,
  }]);
  const { parked } = reviveStalledTasks(s);
  report(parked === 0 && s.task('a').status === 'parked',
    'revivals are capped', `cap=${config.budgets.maxRevivals}`);
}
{
  // The counter must survive revival, or the cap is decorative — this is the
  // exact bug: attempts was reset each pass and nothing else was counted.
  const s = stateWith([{ id: 'a', status: 'parked', visual: true, lastScore: 10 }]);
  let seen = [];
  for (let pass = 0; pass < 6; pass++) {
    reviveStalledTasks(s);
    seen.push(s.task('a').status);
    // Simulate the task failing again, improving each time so only the hard
    // ceiling can stop it.
    if (s.task('a').status === 'pending') {
      s.task('a').status = 'parked';
      s.task('a').lastScore = 10 + pass * 5;
    }
  }
  const revived = seen.filter((x) => x === 'pending').length;
  report(revived === config.budgets.maxRevivals,
    'cap holds across many passes', `revived ${revived}x over 6 passes`);
}

// ----------------------------------------------------- non-visual work untouched
{
  const s = stateWith([{ id: 'a', status: 'completed', visual: false, lastScore: null }]);
  const { belowBar } = reviveStalledTasks(s);
  report(belowBar === 0 && s.task('a').status === 'completed',
    'non-visual completed task is not revived', 'no score to judge');
}

fs.rmSync(TMP, { recursive: true, force: true });
console.log(failures ? `\n${failures} FAILURE(S)` : '\nall revival fixtures passed');
process.exit(failures ? 1 : 0);
