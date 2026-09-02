/**
 * One task, taken from brief to accepted result.
 *
 * The cycle, which is the literal implementation of "/loop until it's perfect":
 *
 *   build  -> a coder agent implements the task
 *   verify -> node --check, then the app is loaded in real Chrome: console
 *             errors, page errors, WebGL context, frame rate, blank-frame test
 *   judge  -> if the task is visual, the vision critic grades the screenshot
 *   fix    -> failures come back as a new brief containing the exact defects,
 *             and a fresh agent attacks them with a clean context
 *
 * Fresh context per round matters. Re-using the transcript of a failed attempt
 * poisons the next one: the model defends its earlier choices instead of
 * fixing them.
 */
import path from 'node:path';
import fs from 'node:fs';
import { Agent } from './agent.js';
import { Toolbelt } from './tools.js';
import { critique } from './critic.js';
import { inspectApp, ENTRY_ACTIONS } from './browser.js';
import { captureApp, restoreApp, fitness, describeFitness, SALVAGEABLE_FITNESS } from './snapshot.js';
import { config } from './config.js';
import { log } from './logger.js';
import { assetGuidance } from './rubrics.js';

/**
 * Does the build run cleanly enough to be worth judging on art?
 *
 * Used for both the ratchet baseline and each round, so the two are always
 * decided by the same rule. `interactive` is deliberately absent: it is a
 * relative test (see keepOrRevert), not a pass/fail one.
 */
function runtimeHealthy(h) {
  return Boolean(h)
    && !h.loadError
    && !h.pageErrors?.length
    && !h.consoleErrors?.length
    && !h.blankScreen
    && !h.deadPlayfield
    && !h.errorScreen;
}

/** Extra briefing about the scaffold the agent is building on top of. */
function scaffoldNotes(domain) {
  if (domain === '2d_game' || domain === '2_5d') {
    return `\nThe project already has a 2D scaffold in src/main.js exposing a global "game" object. USE IT, do not rebuild it:
- game.addLayer(z, name, draw(ctx, game)) registers a render layer, drawn in ascending z order.
- game.updaters.push({ name, update(dt, game) }) registers a FIXED-timestep update; dt is always 1/60.
- game.worldToScreen(x, y) converts world to screen coordinates${domain === '2_5d' ? ' using the isometric projection' : ''}. Always draw through it.
- game.makeSprite(w, h, paint) pre-renders artwork to an offscreen canvas. Do this once at load, never per frame.
- game.input.keys is a Set of held key codes; game.input.mouse has x, y and down.
Never add your own requestAnimationFrame loop. Never replace the loop in src/main.js.`;
  }
  if (domain === '3d_realtime') {
    return `\nThe project already has a three.js scaffold in src/main.js exposing window.scene, window.camera, window.renderer and window.updaters. Push per-frame callbacks to window.updaters instead of adding your own requestAnimationFrame loop.`;
  }
  return '';
}

const CODER_SYSTEM = `You are a senior graphics and gameplay engineer working inside an autonomous build system. You are given ONE task and you implement it completely.

CRITICAL — how your output reaches the project:
The ONLY thing that changes the project is a tool call. Anything you type as ordinary chat text is discarded and never reaches a file. Never paste code into your reply. Never say "here is the code". Put the code in the "content" field of a write_file call.

How you work:
- All paths are relative to the project root. index.html is at "index.html" and the entry module is at "src/main.js". Never prefix a path with "app/".
- Read before you write. Never edit a file you have not read in this session.
- Write complete, runnable code. Never emit "// TODO", "// ... rest of implementation", or placeholder stubs. Code that does not run is worse than no code.
- Keep the app runnable at all times. Another agent will load your work in a browser seconds after you finish; if it throws, the task fails.
- Match the existing architecture and import style you find in the project. Do not introduce a build step or a bundler unless one already exists.
- When you are done, run check_syntax, then call finish with a summary.

You have a limited number of tool calls. Do not waste them exploring files unrelated to your task.`;

/** The full system prompt, specialised for the project's visual domain. */
function coderSystem(domain) {
  return `${CODER_SYSTEM}\n\nASSET POLICY: ${assetGuidance(domain)}${scaffoldNotes(domain)}`;
}

/** Build the brief for a first attempt. */
function initialBrief({ task, state, projectFiles }) {
  const criteria = task.acceptanceCriteria.map((c, i) => `${i + 1}. ${c}`).join('\n') || '(use your judgement)';
  return `# TASK: ${task.title}

${task.description}

## Acceptance criteria
${criteria}

## Files you are expected to create or edit
${task.files.length ? task.files.map((f) => `- ${f}`).join('\n') : '- (decide for yourself, keeping to the existing structure)'}

## Project architecture
${state.data.architecture || '(none recorded)'}

## The user's brief, verbatim
This is what the project must actually become. Honour its specifics — named
mechanics, art direction, palette, feel — not just the summary line.

${state.data.goal}

Quality bar: ${state.data.directives.quality_bar}

## Files currently in the project
${projectFiles.join('\n') || '(empty project)'}

Implement this task now. Start by reading the files you will change.`;
}

/** Build the brief for a repair round from concrete, measured failures. */
function repairBrief({ task, health, critiqueResult, round, goal, wasReverted }) {
  const lines = [`# REPAIR ROUND ${round}: ${task.title}`, ''];

  // Without this the agent reads the files, finds none of the edits it made
  // last round, and either re-applies them blindly or concludes the tools are
  // broken. Say plainly that the work was undone and why.
  if (wasReverted) {
    lines.push('## Your previous round was reverted\n'
      + 'The changes from the last round made the build measurably worse, so they '
      + 'were rolled back and the project is now exactly as it was before that '
      + 'attempt. Do not simply re-apply them. Work out why they broke the build '
      + 'and take a different, smaller approach.\n');
  }

  // Repair rounds are exactly where art direction gets lost, so restate it.
  if (goal) lines.push(`## The user's brief, verbatim\n${goal}\n`);

  if (health?.loadError) lines.push(`## The page failed to load\n${health.loadError}\n`);
  if (health?.pageErrors?.length) lines.push(`## Uncaught runtime errors (fix these first)\n${health.pageErrors.map((e) => `- ${e}`).join('\n')}\n`);
  if (health?.consoleErrors?.length) lines.push(`## Console errors\n${health.consoleErrors.slice(0, 10).map((e) => `- ${e}`).join('\n')}\n`);
  if (health?.failedRequests?.length) lines.push(`## Failed network requests\n${health.failedRequests.slice(0, 10).map((e) => `- ${e}`).join('\n')}\n`);
  if (health?.blankScreen) lines.push('## The rendered frame is blank\nThe canvas is a single flat colour. Nothing is being drawn. Check the camera position, the render loop, and whether anything was added to the scene.\n');
  if (health?.deadPlayfield) lines.push('## The play area is empty\nThe edges of the frame have content (HUD, panels, chrome) but the middle 60% is a single flat colour. The interface is rendering and the game itself is not. Check the camera transform, whether world-space draws are inside it, and whether anything is actually added to the scene.\n');
  if (health?.interactive === false) lines.push('## The build does not respond to input\nClicking the canvas changes nothing beyond its idle animation. Something between the event listener and the game state is broken: the listener may not be attached, the hit test may be in the wrong coordinate space, or the handler may be returning early. Verify a click produces a visible change before claiming this task is done.\n');
  if (health?.fps != null && health.fps < 30) lines.push(`## Performance\nMeasured ${health.fps} fps, which is below the 30 fps floor. Reduce draw calls, shadow resolution, or post-processing cost.\n`);

  if (critiqueResult) {
    // Split the number out. A single composite figure sends the agent to
    // repaint things when what it actually failed was the task itself, and a
    // run once spent every round chasing art scores while the feature it was
    // asked for was never wired up.
    const breakdown = critiqueResult.artScore != null
      ? ` — art ${critiqueResult.artScore}/100, function ${critiqueResult.functionScore}/100`
      : '';
    lines.push(`## Review: ${critiqueResult.score}/100 (needs ${config.critic.passScore})${breakdown}, reads as "${critiqueResult.readsAs}"`);
    if (critiqueResult.functionScore != null && critiqueResult.artScore != null
        && critiqueResult.functionScore < critiqueResult.artScore) {
      lines.push('\n**The functional half is the weaker one. Fix what the thing DOES before you touch how it looks.**');
    }
    if (critiqueResult.issues.length) {
      lines.push('\n### Defects to fix');
      lines.push(critiqueResult.issues.map((i) => `- ${i}`).join('\n'));
    }
    if (critiqueResult.fixes.length) {
      lines.push('\n### Required technical changes');
      lines.push(critiqueResult.fixes.map((f) => `- ${f}`).join('\n'));
    }
    const axes = Object.entries(critiqueResult.axisScores ?? {})
      .sort((a, b) => a[1] - b[1]).slice(0, 3)
      .map(([k, v]) => `${k} (${v}/100)`).join(', ');
    if (axes) lines.push(`\nWeakest axes, attack these: ${axes}`);
  }

  lines.push('\nFix every item above. Do not rewrite working code that was not criticised. Read the relevant files first, then make targeted changes.');
  return lines.join('\n');
}

function listProjectFiles(appDir, limit = 120) {
  const out = [];
  const walk = (dir, prefix = '') => {
    if (out.length >= limit || !fs.existsSync(dir)) return;
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      if (e.name.startsWith('.') || e.name === 'node_modules') continue;
      const rel = prefix ? `${prefix}/${e.name}` : e.name;
      if (e.isDirectory()) walk(path.join(dir, e.name), rel);
      else out.push(rel);
      if (out.length >= limit) return;
    }
  };
  walk(appDir);
  return out;
}

/**
 * Run one task to acceptance or exhaustion.
 * @returns {Promise<{status:string, rounds:number, critiques:Array, health:object|null}>}
 */
export async function runTask({ task, state, paths, appUrl, slot, makeAgent = null, critiqueFn = critique }) {
  const name = `${slot ? `w${slot}` : 'worker'}:${task.id}`;
  const maxRounds = state.data.directives.loop_until_perfect ? config.budgets.critiqueRounds : 2;
  const critiques = [];
  let lastHealth = null;
  let lastCritique = null;

  log.step(name, `starting "${task.title}" (up to ${maxRounds} rounds)`);

  // ---- RATCHET BASELINE --------------------------------------------------
  // Measure the tree we inherited before touching it. Without this the first
  // round has nothing to be compared against, and a round that breaks a
  // working build would be kept simply for being first.
  //
  // One extra page load per task, against six rounds of several minutes each:
  // the cost is noise and it buys a correct floor.
  let best = captureApp(paths.app);
  const baseline = await inspectApp({
    url: appUrl,
    shotPath: path.join(paths.shots, `${task.id}-baseline.png`),
    actions: ENTRY_ACTIONS,
  });
  // Judge the inherited frame too, not just its health.
  //
  // This is the difference between a ratchet and a one-way door. Scoring the
  // baseline as null gives it art=0, so EVERY round that merely avoids
  // crashing outranks it and is kept — the comparison below can then only ever
  // fire on a health tier, and a round that guts the artwork while still
  // running at 60fps is unrevertable by construction. A 3h run lost its
  // terrain, sky, moon and stars that way while the critic described the
  // damage, in words, in the log, at 29/100, and the round was kept.
  let baselineCritique = null;
  if (task.visual && runtimeHealthy(baseline) && baseline.screenshot) {
    try {
      baselineCritique = await critiqueFn({
        screenshot: baseline.screenshot,
        task,
        directives: state.data.directives,
        health: baseline,
        goal: state.data.goal,
      });
    } catch (err) {
      // Fall back to health-only comparison for this task rather than aborting
      // it, but say so: while this is null the art ratchet is off.
      log.warn(name, `baseline critic failed (${err.message}); art regressions cannot be caught this task`);
    }
  }

  let bestFitness = fitness(baseline, baselineCritique);
  // Interactivity ratchets separately, on a relative test — see keepOrRevert.
  let bestInteractive = baseline?.interactive ?? null;
  let reverted = 0;
  let wasReverted = false;
  log.info(name, `baseline: ${describeFitness(bestFitness)}`
    + `${bestInteractive === false ? ' | not interactive' : ''}`);

  /**
   * The ratchet. Keep the round if it is at least as good as the best result
   * seen for this task; otherwise put the best result back on disk.
   *
   * Ties are kept deliberately. Reverting on equal fitness would throw away
   * every non-visual improvement — refactors, wiring, logic the critic cannot
   * see — and would make progress on a plateau impossible.
   *
   * @returns {boolean} true if the round's work survived
   */
  function keepOrRevert(round, health, crit) {
    const f = fitness(health, crit);

    // Interactivity is judged relatively, never absolutely. A build that never
    // responded to a bare click may be legitimate (pointer-locked 3D,
    // keyboard-only), so it is not condemned for staying that way. A build that
    // WAS responding and has stopped has broken its own controls, and no art
    // score should be able to buy that back — hence a veto rather than a tier.
    const lostInput = bestInteractive === true && health?.interactive === false;

    if (f >= bestFitness && !lostInput) {
      best = captureApp(paths.app);
      bestFitness = f;
      if (health?.interactive !== null && health?.interactive !== undefined) {
        bestInteractive = health.interactive;
      }
      wasReverted = false;
      log.info(name, `round ${round} kept: ${describeFitness(f)}`);
      return true;
    }

    const why = lostInput
      ? `it stopped responding to input (was interactive at ${describeFitness(bestFitness)})`
      : `${describeFitness(f)} is worse than ${describeFitness(bestFitness)}`;
    const { restored, removed } = restoreApp(paths.app, best);
    reverted++;
    wasReverted = true;
    log.warn(name, `round ${round} reverted: ${why} — ${restored} file(s) restored, ${removed} removed`);
    return false;
  }

  for (let round = 1; round <= maxRounds; round++) {
    // ---- BUILD -----------------------------------------------------------
    const toolbelt = new Toolbelt({ workspace: paths.root, appDir: paths.app });
    // makeAgent is a test seam. The ratchet is the one part of this loop that
    // cannot be proved by a unit test — it only means anything if it fires in
    // the real build -> verify -> revert sequence — and driving that with a
    // live model would be both slow and non-deterministic.
    const agentOpts = {
      name: `${name}#${round}`,
      toolbelt,
      systemPrompt: coderSystem(state.data.directives.visual_domain),
      role: 'coder',
      fileHints: task.files,
    };
    const agent = makeAgent ? makeAgent({ ...agentOpts, round }) : new Agent(agentOpts);

    const brief = round === 1
      ? initialBrief({ task, state, projectFiles: listProjectFiles(paths.app) })
      : repairBrief({ task, health: lastHealth, critiqueResult: lastCritique, round, goal: state.data.goal, wasReverted });

    const result = await agent.run(brief);
    log.info(name, `round ${round} agent: ${result.status}, ${result.filesTouched.length} file(s) touched`);

    if (result.status === 'model_error') {
      // The model died partway through. Whatever it had written by then is a
      // half-applied change nobody verified, so it must not be left on disk for
      // the next task to inherit.
      const { restored, removed } = restoreApp(paths.app, best);
      if (restored || removed) {
        log.warn(name, `model error mid-round; rolled back ${restored} file(s), removed ${removed}`);
      }
      return { status: 'failed', rounds: round, critiques, health: lastHealth, note: result.summary };
    }
    if (!result.filesTouched.length && round === 1) {
      log.warn(name, 'agent produced no files on the first round');
    }

    // ---- VERIFY (objective) ---------------------------------------------
    // Sweep the whole app, not just this agent's edits: a file broken by a
    // shell redirect or by the other worker still breaks the module graph, and
    // a round graded on a page that never loaded is a round thrown away.
    const syntax = await toolbelt.check_syntax({ all: true });
    if (!syntax.ok) {
      log.warn(name, `syntax errors: ${syntax.problems.join(' | ')}`);
      lastHealth = { syntaxError: true, pageErrors: syntax.problems, consoleErrors: [], failedRequests: [] };
      lastCritique = null;
      // A tree that will not parse cannot be judged and must not be inherited.
      // Revert now so the next round — and the next task — start from something
      // that at least loads.
      keepOrRevert(round, lastHealth, null);
      if (round === maxRounds) break;
      continue;
    }

    const shotPath = path.join(paths.shots, `${task.id}-r${round}.png`);
    // Two-shot: boot frame proves it loads, post-entry frame is what gets judged.
    lastHealth = await inspectApp({
      url: appUrl,
      shotPath,
      bootShotPath: path.join(paths.shots, `${task.id}-r${round}-boot.png`),
      actions: ENTRY_ACTIONS,
    });

    // An empty play area is a hard failure: chrome rendering over a dead game
    // is the exact state a whole run once shipped. Unresponsiveness is reported
    // and fed to the next repair brief, but does not fail the gate on its own —
    // some legitimate builds (pointer-locked 3D, keyboard-only) will not react
    // to a bare click, and failing those would stall the run for the wrong
    // reason.
    const healthy = runtimeHealthy(lastHealth);

    log.info(name, `runtime: ${healthy ? 'clean' : 'problems'} | ${lastHealth.fps ?? '?'} fps`
      + ` | ${lastHealth.pageErrors.length} page errors | ${lastHealth.consoleErrors.length} console errors`
      + `${lastHealth.blankScreen ? ' | BLANK FRAME' : ''}`
      + `${lastHealth.deadPlayfield ? ' | DEAD PLAYFIELD' : ''}`
      + `${lastHealth.errorScreen ? ' | CRASH SCREEN' : ''}`
      + `${lastHealth.interactive === false ? ' | NOT INTERACTIVE' : ''}`);

    // Spell the crash out. The whole point of this gate is that the repair
    // brief gets told what the vision critic could never see.
    if (lastHealth.errorScreen) log.warn(name, `crash screen: ${lastHealth.errorScreen}`);

    if (!healthy) {
      lastCritique = null;
      // Unjudged, so compare on health alone. A broken round that is still an
      // improvement on a more broken baseline is kept — that is how a task
      // digs the project out of a hole left by an earlier one.
      keepOrRevert(round, lastHealth, null);
      if (round === maxRounds) break;
      continue; // Never spend a vision call judging a broken build.
    }

    // ---- JUDGE (subjective) ---------------------------------------------
    if (!task.visual) {
      log.ok(name, `accepted after ${round} round(s) (non-visual task, runtime clean)`);
      return { status: 'completed', rounds: round, critiques, health: lastHealth };
    }

    if (!lastHealth.screenshot) {
      log.warn(name, 'no screenshot captured; accepting on runtime health alone');
      return { status: 'completed', rounds: round, critiques, health: lastHealth };
    }

    try {
      lastCritique = await critiqueFn({
        screenshot: lastHealth.screenshot,
        task,
        directives: state.data.directives,
        health: lastHealth,
        goal: state.data.goal,
      });
    } catch (err) {
      log.warn(name, `critic failed (${err.message}); accepting on runtime health`);
      return { status: 'completed', rounds: round, critiques, health: lastHealth };
    }

    critiques.push({ ...lastCritique, round, screenshot: shotPath });
    state.recordCritique({ ...lastCritique, round, screenshot: shotPath });
    task.lastScore = lastCritique.score;

    // Now that the round has both a health tier and an art score, it can be
    // ranked properly. A round that renders cleanly but scores worse than the
    // frame it replaced is a regression and goes back.
    keepOrRevert(round, lastHealth, lastCritique);

    if (lastCritique.verdict === 'PASS') {
      log.ok(name, `PASSED at ${lastCritique.score}/100 after ${round} round(s)`);
      return { status: 'completed', rounds: round, critiques, health: lastHealth };
    }

    log.warn(name, `round ${round} rejected at ${lastCritique.score}/100: ${lastCritique.issues[0] ?? 'below bar'}`);
  }

  // Out of rounds. What is on disk is the best result this task produced, not
  // the last one it tried — so salvageability is judged from the ratchet, not
  // from lastHealth, which may describe a round that was reverted away.
  const salvageable = bestFitness >= SALVAGEABLE_FITNESS;
  const status = salvageable ? 'completed_below_bar' : 'failed';
  log.warn(name, `exhausted ${maxRounds} rounds -> ${status}`
    + ` (best: ${describeFitness(bestFitness)}, ${reverted} round(s) reverted)`);
  return { status, rounds: maxRounds, critiques, health: lastHealth, bestFitness };
}
