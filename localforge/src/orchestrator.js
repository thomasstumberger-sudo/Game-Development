/**
 * The conductor.
 *
 * Responsibilities:
 *  - fan out ready tasks across a worker pool, avoiding two agents editing the
 *    same file at the same time
 *  - persist after every transition so the run survives a crash
 *  - run the outer refinement loop: when the task list empties, ask the planner
 *    whether the result actually meets the bar, and let it queue more work
 *  - run the final blind comparison against reference images
 *  - write a human-readable report
 */
import fs from 'node:fs';
import path from 'node:path';
import { config, workspacePaths } from './config.js';
import { log, initLogger } from './logger.js';
import { RunState } from './state.js';
import { parseDirectives, planProject, gapAnalysis, readyTasks, breakDeadlock } from './planner.js';
import { scaffoldApp } from './scaffold.js';
import { runTask } from './worker.js';
import { startStaticServer, inspectApp, closeBrowser, ENTRY_ACTIONS } from './browser.js';
import { blindCompare, loadReferences } from './critic.js';
import { warmUp, listModels } from './ollama.js';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function runForge({ goal, workspace, resume = false, maxRefinementRounds = 3, domainOverride = null }) {
  const paths = workspacePaths(workspace);
  config.paths.workspace = workspace;

  for (const dir of [paths.forgeDir, paths.logs, paths.shots, paths.reports, paths.references, paths.app]) {
    fs.mkdirSync(dir, { recursive: true });
  }
  initLogger(paths.logs);

  // ---------------------------------------------------------------- state
  let state = resume ? RunState.load(paths.state) : null;
  if (state) {
    log.banner('RESUMING RUN', [
      `goal: ${state.data.directives?.one_line_goal ?? state.data.goal.slice(0, 60)}`,
      `progress: ${state.stats.completed}/${state.stats.total} tasks`,
    ]);
    // Anything caught mid-flight by the crash goes back in the queue.
    for (const t of state.data.tasks) if (t.status === 'running') t.status = 'pending';
  } else {
    state = new RunState(paths.state, { goal });
  }

  const deadline = config.budgets.wallClockMinutes
    ? Date.now() + config.budgets.wallClockMinutes * 60000
    : null;
  const outOfTime = () => deadline && Date.now() > deadline;

  // ------------------------------------------------------------ preflight
  await preflight();

  // ------------------------------------------------- directives + planning
  if (!state.data.directives) {
    state.data.directives = await parseDirectives(goal);
    state.save();
  }
  const directives = state.data.directives;
  if (domainOverride && directives.visual_domain !== domainOverride) {
    log.info('forge', `domain overridden: ${directives.visual_domain} -> ${domainOverride}`);
    directives.visual_domain = domainOverride;
    state.save();
  }

  log.banner(directives.project_name || 'LOCALFORGE RUN', [
    `goal        : ${directives.one_line_goal}`,
    `stack       : ${directives.stack}`,
    `judged as   : ${directives.visual_domain}`,
    `quality bar : ${(directives.quality_bar || '').slice(0, 60)}`,
    `fan-out     : ${directives.fan_out ? `yes (${config.budgets.concurrency} workers)` : 'no'}`,
    `loop        : ${directives.loop_until_perfect ? `yes (${config.budgets.critiqueRounds} rounds/task)` : 'no'}`,
    `blind A/B   : ${directives.blind_compare ? 'yes' : 'no'}`,
  ]);

  await scaffoldApp({ appDir: paths.app, directives });

  if (!state.data.tasks.length) {
    const plan = await planProject(goal, directives);
    state.data.architecture = plan.architecture;
    state.addTasks(plan.tasks);
  }

  // --------------------------------------------------------- static server
  const server = await startStaticServer(paths.app, config.browser.port);
  const appUrl = `http://127.0.0.1:${config.browser.port}/index.html`;
  log.ok('forge', `serving app at ${appUrl}`);

  // Confirm the skeleton loads before spending hours on top of it.
  const boot = await inspectApp({ url: appUrl, shotPath: path.join(paths.shots, '000-boot.png'), settleMs: 2500 });
  if (boot.loadError || boot.pageErrors.length) {
    log.error('forge', `skeleton does not load: ${boot.loadError ?? boot.pageErrors[0]}`);
  } else {
    log.ok('forge', `skeleton boots clean at ${boot.fps ?? '?'} fps`);
  }

  // -------------------------------------------------------- the main loops
  try {
    for (let round = state.data.round + 1; round <= maxRefinementRounds; round++) {
      state.data.round = round;
      state.save();

      // A parked task used to be dead forever: only 'pending' is ever picked up,
      // and nothing put it back. That made "keep working until it's good"
      // impossible — the outer loop could only invent new tasks while the actual
      // failures rotted. Each refinement round now revives them with a fresh,
      // larger attempt budget, since the project around them has moved on.
      if (round > 1) {
        const { parked, belowBar } = reviveStalledTasks(state);
        if (parked || belowBar) {
          log.info('forge', `revived ${parked} parked and ${belowBar} below-bar task(s) for another attempt`);
        }
      }

      log.banner(`BUILD PASS ${round}`, [
        `${state.stats.pending} task(s) queued`,
        `${config.budgets.concurrency} parallel worker(s)`,
      ]);

      await executePass({ state, paths, appUrl, outOfTime });

      if (outOfTime()) {
        log.warn('forge', 'wall-clock budget exhausted, stopping');
        break;
      }

      // Outer /loop: is it actually good enough?
      if (!directives.loop_until_perfect || round === maxRefinementRounds) break;

      const fileList = listFiles(paths.app);
      const gap = await gapAnalysis({
        goal, directives, tasks: state.data.tasks,
        critiques: state.data.critiques, fileList, round,
      });
      state.data.gapAnalysis = gap;
      state.save();

      // The planner decides "ship" from task titles and scores alone — it never
      // sees the build. It is not allowed to overrule the measured bar: while
      // any visually-judged task sits under passScore, the run keeps going.
      const belowBar = state.data.tasks.filter(
        (t) => t.visual && t.lastScore != null && t.lastScore < config.critic.passScore,
      );
      const unfinished = state.data.tasks.filter((t) => t.status === 'parked').length;

      if (gap.verdict === 'ship' && (belowBar.length || unfinished)) {
        log.warn('forge', `planner said ship, but ${belowBar.length} task(s) are below the `
          + `${config.critic.passScore} bar and ${unfinished} are parked — overruling, continuing`);
      } else if (gap.verdict === 'ship') {
        log.ok('forge', `planner says ship: ${gap.reasoning.slice(0, 160)}`);
        break;
      }

      const added = state.addTasks(gap.new_tasks);
      log.info('forge', `refinement round added ${added} task(s)`);

      // Only stop when there is genuinely nothing left to work on.
      if (!added && !belowBar.length && !unfinished) {
        log.ok('forge', 'nothing left below the bar and nothing parked, stopping');
        break;
      }
    }

    // ------------------------------------------------- final verification
    const final = await inspectApp({
      url: appUrl,
      shotPath: path.join(paths.shots, 'final.png'),
      bootShotPath: path.join(paths.shots, 'final-boot.png'),
      actions: ENTRY_ACTIONS,
      settleMs: 6000,
    });
    log.banner('FINAL VERIFICATION', [
      `frame rate     : ${final.fps ?? 'unknown'} fps`,
      `page errors    : ${final.pageErrors.length}`,
      `console errors : ${final.consoleErrors.length}`,
      `blank frame    : ${final.blankScreen ? 'YES' : 'no'}`,
      `play area dead : ${final.deadPlayfield ? 'YES' : 'no'}`,
      `crash screen   : ${final.errorScreen ? 'YES' : 'no'}`,
      `responds to input : ${final.interactive === null ? 'unknown' : final.interactive ? 'yes' : 'NO'}`,
      `renderer       : ${(final.webgl?.renderer ?? 'unknown').slice(0, 44)}`,
    ]);

    // The run can end mid-repair when the wall clock expires, so the last
    // thing written is not necessarily something that loads. Say so loudly
    // rather than letting RUN COMPLETE imply a working build.
    if (final.errorScreen) log.warn('forge', `the app is ending on a crash screen — ${final.errorScreen}`);

    // ----------------------------------------------- blind A/B comparison
    const references = loadReferences(paths.references);
    if (directives.blind_compare && references.length && final.screenshot) {
      log.banner('BLIND SIDE-BY-SIDE', [`${references.length} reference image(s)`]);
      for (const ref of references) {
        const res = await blindCompare({ screenshot: final.screenshot, referencePath: ref, directives });
        state.recordBlind(res);
        log[res.passed ? 'ok' : 'warn']('forge',
          `vs ${res.reference}: won ${res.wins}/${res.rounds} blind rounds`);
      }
    } else if (directives.blind_compare) {
      log.warn('forge', `blind comparison requested but ${paths.references} holds no reference images; skipped`);
    }

    state.data.status = 'finished';
    state.data.finishedAt = new Date().toISOString();
    state.data.finalHealth = {
      fps: final.fps, pageErrors: final.pageErrors, consoleErrors: final.consoleErrors,
      blankScreen: final.blankScreen, renderer: final.webgl?.renderer ?? null,
      deadPlayfield: final.deadPlayfield, interactive: final.interactive,
    };
    state.save();

    const reportPath = writeReport({ state, paths });
    log.banner('RUN COMPLETE', [
      `tasks    : ${state.stats.passed}/${state.stats.total} passed the bar`,
      `           ${state.stats.belowBar} accepted below it, ${state.stats.parked} parked`,
      `report   : ${path.relative(process.cwd(), reportPath)}`,
      `app      : ${path.relative(process.cwd(), paths.app)}`,
      `preview  : npx serve ${path.relative(process.cwd(), paths.app)}`,
    ]);
    return state;
  } finally {
    // close() only stops new connections; a live keep-alive socket from a
    // straggler page keeps the server — and the process — alive forever.
    server.closeAllConnections?.();
    server.close();
    await closeBrowser();
  }
}

/**
 * Run every currently-schedulable task, with a fixed-size worker pool.
 *
 * Two agents writing the same file concurrently is the fastest way to destroy a
 * run, so a task is only dispatched when none of its declared files are held by
 * an in-flight task.
 */
async function executePass({ state, paths, appUrl, outOfTime }) {
  const inFlight = new Map(); // promise -> task
  const heldFiles = new Set();
  let slot = 0;
  let broadInFlight = false;

  /**
   * Tasks that declare a glob ("src/*") or no files at all are integration and
   * polish passes that touch everything. Exact-name locking cannot protect
   * those, so they run exclusively: nothing else starts while one is in flight,
   * and one will not start while anything else is running.
   */
  const isBroad = (t) => !t.files.length || t.files.some((f) => /[*?]/.test(f));
  const conflicts = (task) => broadInFlight
    || (isBroad(task) && inFlight.size > 0)
    || task.files.some((f) => heldFiles.has(f));

  while (true) {
    // Breaking here with workers still in flight orphans them: their promises
    // are never awaited, so the pass returns while agents keep calling the
    // model and writing files. The run then finalises around them, and the
    // stragglers re-launch a browser through the closed-down singleton, which
    // pins the event loop and hangs the process indefinitely. Drain instead.
    if (outOfTime()) {
      if (inFlight.size) {
        log.warn('forge', `wall clock expired, draining ${inFlight.size} in-flight task(s)`);
        for (const { task, res } of await Promise.all(inFlight.keys())) {
          task.status = res.status?.startsWith('completed') ? 'completed' : 'pending';
          for (const f of task.files) heldFiles.delete(f);
        }
        inFlight.clear();
        state.save();
      }
      break;
    }

    let ready = readyTasks(state.data.tasks).filter((t) => !conflicts(t));

    // Nothing ready, nothing running, but work remains -> dependency deadlock.
    if (!ready.length && !inFlight.size) {
      const pendingLeft = state.data.tasks.some((t) => t.status === 'pending');
      if (!pendingLeft) break;
      if (readyTasks(state.data.tasks).length === 0 && !breakDeadlock(state.data.tasks)) break;
      continue;
    }

    // Fill the pool.
    while (ready.length && inFlight.size < config.budgets.concurrency) {
      const task = ready.shift();
      task.status = 'running';
      task.attempts = (task.attempts ?? 0) + 1;
      state.save();
      for (const f of task.files) heldFiles.add(f);
      if (isBroad(task)) broadInFlight = true;

      const mySlot = (slot++ % config.budgets.concurrency) + 1;
      const p = runTask({ task, state, paths, appUrl, slot: mySlot })
        .then((res) => ({ task, res }))
        .catch((err) => ({ task, res: { status: 'failed', note: err.message, critiques: [] } }));
      inFlight.set(p, task);
      ready = ready.filter((t) => !conflicts(t));
    }

    if (!inFlight.size) break;

    const { task, res } = await Promise.race(inFlight.keys());
    for (const [p, t] of inFlight) if (t === task) inFlight.delete(p);
    for (const f of task.files) heldFiles.delete(f);
    if (isBroad(task)) broadInFlight = false;

    if (res.status === 'completed' || res.status === 'completed_below_bar') {
      task.status = 'completed';
      task.note = res.status === 'completed_below_bar' ? 'accepted below the quality bar' : undefined;
    } else if (task.attempts >= config.budgets.maxTaskAttempts) {
      task.status = 'parked';
      task.note = res.note ?? 'exceeded attempt limit';
      log.error('forge', `parking "${task.id}" after ${task.attempts} attempts`);
    } else {
      task.status = 'pending'; // another go later
    }
    state.save();

    const s = state.stats;
    log.info('forge', `progress ${s.passed}/${s.total} at bar (+${s.belowBar} below), `
      + `${s.pending} queued, ${s.parked} parked`);
  }
}

/**
 * Put stalled work back in the queue at the start of a refinement round.
 *
 * Two kinds of task were previously abandoned in place:
 *   - 'parked'  — hit the attempt limit; nothing ever picked them up again.
 *   - below-bar — marked 'completed' via completed_below_bar, so a task that
 *                 scored 8/100 counted as done and was never revisited.
 *
 * Both get a clean attempt budget. The project has changed underneath them
 * since they failed, so a retry is not the same retry.
 *
 * @returns {{parked:number, belowBar:number}}
 */
function reviveStalledTasks(state) {
  let parked = 0;
  let belowBar = 0;
  for (const t of state.data.tasks) {
    if (t.status === 'parked') {
      t.status = 'pending';
      t.attempts = 0;
      delete t.note;
      parked++;
    } else if (
      t.status === 'completed'
      && t.visual
      && t.lastScore != null
      && t.lastScore < config.critic.passScore
    ) {
      t.status = 'pending';
      t.attempts = 0;
      delete t.note;
      belowBar++;
    }
  }
  if (parked || belowBar) state.save();
  return { parked, belowBar };
}

async function preflight() {
  const models = await listModels().catch(() => []);
  if (!models.length) {
    throw new Error(`No models reachable at ${config.ollama.host}. Is ollama running? Try: ollama serve`);
  }
  const available = new Set(models.map((m) => m.name));
  const missing = Object.entries(config.models)
    .filter(([, m]) => !available.has(m))
    .map(([role, m]) => `${role}=${m}`);
  if (missing.length) {
    log.warn('forge', `configured models not installed: ${missing.join(', ')}. Pull them or override with FORGE_MODEL_*.`);
  }
  log.step('forge', 'warming models into VRAM');
  await warmUp(config.models.coder);
  await warmUp(config.models.critic);
  await sleep(200);
}

function listFiles(dir, limit = 150) {
  const out = [];
  const walk = (d, prefix = '') => {
    if (out.length >= limit || !fs.existsSync(d)) return;
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      if (e.name.startsWith('.') || e.name === 'node_modules') continue;
      const rel = prefix ? `${prefix}/${e.name}` : e.name;
      if (e.isDirectory()) walk(path.join(d, e.name), rel);
      else out.push(rel);
      if (out.length >= limit) return;
    }
  };
  walk(dir);
  return out;
}

function writeReport({ state, paths }) {
  const d = state.data;
  const lines = [
    `# ${d.directives?.project_name ?? 'Build'} — run report`,
    '',
    `- Goal: ${d.directives?.one_line_goal ?? d.goal.slice(0, 200)}`,
    `- Started: ${d.startedAt}`,
    `- Finished: ${d.finishedAt}`,
    `- Refinement rounds: ${d.round}`,
    '',
    '## Final runtime health',
    '',
    '| metric | value |',
    '| --- | --- |',
    `| frame rate | ${d.finalHealth?.fps ?? 'unknown'} fps |`,
    `| page errors | ${d.finalHealth?.pageErrors?.length ?? '?'} |`,
    `| console errors | ${d.finalHealth?.consoleErrors?.length ?? '?'} |`,
    `| blank frame | ${d.finalHealth?.blankScreen ? 'yes' : 'no'} |`,
    `| crash screen | ${d.finalHealth?.errorScreen ? `yes — ${d.finalHealth.errorScreen}` : 'no'} |`,
    `| renderer | ${d.finalHealth?.renderer ?? 'unknown'} |`,
    '',
    '## Tasks',
    '',
    '| task | status | visual score | attempts |',
    '| --- | --- | --- | --- |',
    ...d.tasks.map((t) => `| ${t.title} | ${t.status}${t.note ? ` (${t.note})` : ''} | ${t.lastScore ?? '—'} | ${t.attempts} |`),
    '',
  ];

  if (d.blindResults?.length) {
    lines.push('## Blind side-by-side results', '',
      '| reference | rounds won | verdict |', '| --- | --- | --- |',
      ...d.blindResults.map((b) => `| ${b.reference} | ${b.wins}/${b.rounds} | ${b.passed ? 'our build preferred' : 'reference preferred'} |`),
      '');
    const gaps = [...new Set(d.blindResults.flatMap((b) => b.gaps ?? []))];
    if (gaps.length) lines.push('### Gaps the judge identified', '', ...gaps.map((g) => `- ${g}`), '');
  }

  const worst = [...d.critiques].sort((a, b) => a.score - b.score).slice(0, 5);
  if (worst.length) {
    lines.push('## Lowest-scoring reviews', '');
    for (const c of worst) {
      lines.push(`### ${c.taskId} — ${c.score}/100 (${c.tier})`, `Reads as: ${c.readsAs}`, '');
      for (const i of (c.issues ?? []).slice(0, 6)) lines.push(`- ${i}`);
      lines.push('');
    }
  }

  lines.push('## Screenshots', '', `All frames: \`${path.relative(process.cwd(), paths.shots)}\``, '');

  const out = path.join(paths.reports, 'report.md');
  fs.writeFileSync(out, lines.join('\n'));
  return out;
}
