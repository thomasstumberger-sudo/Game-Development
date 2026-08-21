#!/usr/bin/env node
/**
 * localforge CLI.
 *
 *   forge run "<goal>" [--workspace ./out] [--concurrency 2] [--rounds 3]
 *   forge run --file goal.txt
 *   forge resume [--workspace ./out]
 *   forge status [--workspace ./out]
 *   forge doctor
 *   forge selftest
 *   forge shoot <url|path>          capture + health-check anything
 *   forge judge <image> [<goal>]    run the harsh critic on one image
 *   forge compare <ours> <reference>  blind A/B two images
 */
import fs from 'node:fs';
import path from 'node:path';
import { config, workspacePaths } from '../src/config.js';
import { log, initLogger, colors } from '../src/logger.js';
import { runForge } from '../src/orchestrator.js';
import { RunState } from '../src/state.js';
import { listModels, modelInfo, chatJSON } from '../src/ollama.js';
import { startStaticServer, inspectApp, closeBrowser } from '../src/browser.js';
import { critique, blindCompare } from '../src/critic.js';
import { Toolbelt } from '../src/tools.js';
import { Agent } from '../src/agent.js';
import { DOMAIN_KEYS, detectDomain } from '../src/rubrics.js';

const argv = process.argv.slice(2);
const command = argv[0];

function flag(name, fallback = null) {
  const i = argv.indexOf(`--${name}`);
  if (i === -1) return fallback;
  const v = argv[i + 1];
  return v && !v.startsWith('--') ? v : true;
}

function positionals() {
  const out = [];
  for (let i = 1; i < argv.length; i++) {
    if (argv[i].startsWith('--')) { if (argv[i + 1] && !argv[i + 1].startsWith('--')) i++; continue; }
    out.push(argv[i]);
  }
  return out;
}

function applyFlagOverrides() {
  const map = {
    concurrency: (v) => { config.budgets.concurrency = Number(v); },
    'critique-rounds': (v) => { config.budgets.critiqueRounds = Number(v); },
    'agent-steps': (v) => { config.budgets.agentSteps = Number(v); },
    'pass-score': (v) => { config.critic.passScore = Number(v); },
    'wall-clock': (v) => { config.budgets.wallClockMinutes = Number(v); },
    coder: (v) => { config.models.coder = v; },
    critic: (v) => { config.models.critic = v; },
    planner: (v) => { config.models.planner = v; },
  };
  for (const [name, fn] of Object.entries(map)) {
    const v = flag(name);
    if (v !== null && v !== true) fn(v);
  }
  if (flag('headed')) config.browser.headless = false;
}

const usage = `
${colors.bold}localforge${colors.reset} — autonomous multi-agent builds on local models

  ${colors.cyan}forge run "<goal>"${colors.reset}         start a new build
  ${colors.cyan}forge run --file goal.txt${colors.reset}  read the goal from a file
  ${colors.cyan}forge resume${colors.reset}               continue an interrupted run
  ${colors.cyan}forge status${colors.reset}               show progress of a run
  ${colors.cyan}forge doctor${colors.reset}               check models, GPU, chrome, deps
  ${colors.cyan}forge selftest${colors.reset}             prove the pipeline works end to end
  ${colors.cyan}forge shoot <url|dir>${colors.reset}      screenshot + health-check anything
  ${colors.cyan}forge judge <image>${colors.reset}        harsh critique of a single image
  ${colors.cyan}forge compare <ours> <ref>${colors.reset} blind A/B against a reference

Options
  --workspace <dir>       where the build lives (default ./build)
  --concurrency <n>       parallel worker agents (default ${config.budgets.concurrency})
  --critique-rounds <n>   max fix cycles per task (default ${config.budgets.critiqueRounds})
  --rounds <n>            outer refinement passes (default 3)
  --pass-score <0-100>    visual bar to clear (default ${config.critic.passScore})
  --wall-clock <minutes>  hard stop for the whole run
  --coder/--critic/--planner <model>   override models
  --domain <name>         force the critique rubric:
                          2d_game | 2_5d | 3d_realtime | ui_app
  --headed                show the browser window
`;

async function main() {
  applyFlagOverrides();

  switch (command) {
    case 'run': return cmdRun();
    case 'resume': return cmdResume();
    case 'status': return cmdStatus();
    case 'doctor': return cmdDoctor();
    case 'selftest': return cmdSelftest();
    case 'shoot': return cmdShoot();
    case 'judge': return cmdJudge();
    case 'compare': return cmdCompare();
    default:
      console.log(usage);
      process.exit(command ? 1 : 0);
  }
}

function resolveWorkspace() {
  return path.resolve(flag('workspace') || './build');
}

/** Explicit --domain wins; otherwise infer from the description text. */
function domainFlag(text = '') {
  const v = flag('domain');
  if (v && v !== true) {
    if (!DOMAIN_KEYS.includes(v)) {
      console.error(`unknown domain "${v}". Valid: ${DOMAIN_KEYS.join(', ')}`);
      process.exit(1);
    }
    return v;
  }
  return detectDomain(text);
}

async function cmdRun() {
  const file = flag('file');
  const goal = file && file !== true ? fs.readFileSync(file, 'utf8') : positionals().join(' ');
  if (!goal?.trim()) {
    console.error('A goal is required: forge run "build me a ..." (or --file goal.txt)');
    process.exit(1);
  }
  const workspace = resolveWorkspace();
  const forced = flag('domain');
  await runForge({
    goal: goal.trim(),
    workspace,
    resume: fs.existsSync(workspacePaths(workspace).state) && flag('fresh') === null,
    maxRefinementRounds: Number(flag('rounds', 3)),
    domainOverride: forced && forced !== true ? domainFlag('') : null,
  });
}

async function cmdResume() {
  const workspace = resolveWorkspace();
  const paths = workspacePaths(workspace);
  const state = RunState.load(paths.state);
  if (!state) { console.error(`No run found at ${paths.state}`); process.exit(1); }
  await runForge({
    goal: state.data.goal,
    workspace,
    resume: true,
    maxRefinementRounds: Number(flag('rounds', 3)),
  });
}

async function cmdStatus() {
  const paths = workspacePaths(resolveWorkspace());
  const state = RunState.load(paths.state);
  if (!state) { console.error(`No run found at ${paths.state}`); process.exit(1); }
  const d = state.data;
  const s = state.stats;
  log.banner(d.directives?.project_name ?? 'run', [
    `status  : ${d.status}`,
    `round   : ${d.round}`,
    `tasks   : ${s.passed} at bar / ${s.belowBar} below bar / ${s.pending} pending / ${s.parked} parked / ${s.total} total`,
    `fps     : ${d.finalHealth?.fps ?? 'not measured yet'}`,
  ]);
  for (const t of d.tasks) {
    const mark = { completed: '✓', parked: '✗', running: '▸', pending: '·', failed: '✗' }[t.status] ?? '?';
    const score = t.lastScore != null ? ` ${t.lastScore}/100` : '';
    console.log(`  ${mark} ${t.id.padEnd(28)} ${t.status.padEnd(10)}${score}`);
  }
}

async function cmdDoctor() {
  initLogger(null);
  log.banner('localforge doctor');
  let fatal = 0;

  // Ollama + models
  try {
    const models = await listModels();
    log.ok('ollama', `reachable at ${config.ollama.host}, ${models.length} model(s) installed`);
    const names = new Set(models.map((m) => m.name));
    for (const [role, model] of Object.entries(config.models)) {
      if (!names.has(model)) { log.error('models', `${role}: ${model} NOT INSTALLED — ollama pull ${model}`); fatal++; continue; }
      const info = await modelInfo(model).catch(() => null);
      const caps = info?.capabilities ?? [];
      const needTools = role === 'coder' || role === 'planner';
      const needVision = role === 'critic';
      const problems = [];
      if (needTools && !caps.includes('tools')) problems.push('lacks tool-calling');
      if (needVision && !caps.includes('vision')) problems.push('LACKS VISION — the visual critic cannot work');
      if (problems.length) { log.error('models', `${role}: ${model} ${problems.join(', ')}`); fatal++; }
      else log.ok('models', `${role}: ${model} [${caps.join(', ')}]`);
    }
  } catch (err) {
    log.error('ollama', `unreachable: ${err.message}`); fatal++;
  }

  // Structured output support — the planner depends on it entirely.
  try {
    const res = await chatJSON({
      role: 'fast',
      schema: { type: 'object', properties: { ok: { type: 'boolean' } }, required: ['ok'] },
      messages: [{ role: 'user', content: 'Reply with {"ok": true}' }],
    });
    if (typeof res.ok === 'boolean') log.ok('ollama', 'structured JSON output works');
    else log.warn('ollama', 'structured output returned an unexpected shape');
  } catch (err) {
    log.error('ollama', `structured output failed: ${err.message}`); fatal++;
  }

  // Chrome + WebGL
  if (!fs.existsSync(config.browser.executablePath)) {
    log.error('chrome', `not found at ${config.browser.executablePath} (set FORGE_CHROME)`); fatal++;
  } else {
    log.ok('chrome', config.browser.executablePath);
    const tmp = path.join(config.tmpDir, 'webgl-probe');
    fs.mkdirSync(tmp, { recursive: true });
    fs.writeFileSync(path.join(tmp, 'index.html'),
      '<canvas id="c"></canvas><script>const gl=document.getElementById("c").getContext("webgl2");'
      + 'document.title = gl ? "WEBGL2_OK" : "NO_WEBGL";</script>');
    const server = await startStaticServer(tmp, config.browser.port + 1);
    try {
      const res = await inspectApp({ url: `http://127.0.0.1:${config.browser.port + 1}/index.html`, settleMs: 1200, fpsSampleMs: 600 });
      if (res.webgl?.present) log.ok('webgl', `context OK — renderer: ${res.webgl.renderer}`);
      else { log.error('webgl', 'no WebGL2 context in headless chrome'); fatal++; }
    } finally {
      server.close();
      await closeBrowser();
    }
  }

  // GPU
  try {
    const { execSync } = await import('node:child_process');
    const out = execSync('nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader', { encoding: 'utf8' });
    out.trim().split('\n').forEach((l, i) => log.ok('gpu', `${i}: ${l}`));
  } catch {
    log.warn('gpu', 'nvidia-smi unavailable; models will run on CPU and be very slow');
  }

  // Parallelism hint
  if (!process.env.OLLAMA_NUM_PARALLEL) {
    log.warn('tuning', `OLLAMA_NUM_PARALLEL is unset. With --concurrency > 1, set it to at least ${config.budgets.concurrency} on the ollama server for real parallelism.`);
  }

  console.log();
  if (fatal) { log.error('doctor', `${fatal} blocking problem(s) found`); process.exit(1); }
  log.ok('doctor', 'all systems go');
}

/** Proves every layer works without spending an hour: plan → code → verify → judge. */
async function cmdSelftest() {
  const workspace = path.resolve(flag('workspace') || './selftest-run');
  const paths = workspacePaths(workspace);
  for (const d of [paths.forgeDir, paths.logs, paths.shots, paths.app]) fs.mkdirSync(d, { recursive: true });
  initLogger(paths.logs);
  log.banner('SELFTEST', ['exercises agent, tools, browser and critic']);

  // 1. Agent + tools: can it write a working file?
  fs.writeFileSync(path.join(paths.app, 'index.html'),
    '<!doctype html><meta charset="utf-8"><title>selftest</title><canvas id="c" width="800" height="450"></canvas>'
    + '<script type="module" src="./main.js"></script>');
  const toolbelt = new Toolbelt({ workspace, appDir: paths.app });
  const agent = new Agent({
    name: 'selftest',
    toolbelt,
    systemPrompt: 'You are a JavaScript engineer. The ONLY way to change the project is a tool call; '
      + 'chat text is discarded. Never paste code into your reply — put it in write_file. No placeholders.',
    role: 'coder',
    maxSteps: 12,
    fileHints: ['main.js'],
  });
  const res = await agent.run(
    'Create main.js in the app directory. It must get the 2D context of the canvas with id "c" and paint an '
    + 'animated vertical gradient background plus 40 glowing circles that drift upward, using requestAnimationFrame. '
    + 'It must produce no console errors. Then call check_syntax and finish.',
  );
  log[res.status === 'completed' ? 'ok' : 'warn']('selftest', `agent: ${res.status} in ${res.steps} steps, files: ${res.filesTouched.join(', ') || 'none'}`);

  // 2. Browser harness
  const server = await startStaticServer(paths.app, config.browser.port + 2);
  let health;
  try {
    health = await inspectApp({
      url: `http://127.0.0.1:${config.browser.port + 2}/index.html`,
      shotPath: path.join(paths.shots, 'selftest.png'),
      settleMs: 2500, fpsSampleMs: 1500,
    });
    log[health.ok ? 'ok' : 'warn']('selftest',
      `browser: ${health.fps ?? '?'} fps, ${health.consoleErrors.length} console errors, blank=${health.blankScreen}`);
  } finally {
    server.close();
  }

  // 3. Vision critic
  if (health?.screenshot) {
    try {
      const c = await critique({
        screenshot: health.screenshot,
        task: {
          id: 'selftest', title: 'Animated gradient with glowing particles',
          description: 'A canvas showing a gradient background and drifting glowing circles.',
          category: 'rendering',
          acceptanceCriteria: ['A gradient is visible', 'Multiple glowing circles are visible'],
        },
        directives: { one_line_goal: 'selftest scene', quality_bar: 'visually coherent', reference_targets: [] },
        health,
      });
      log.ok('selftest', `critic: ${c.score}/100, tier=${c.tier}, "${c.readsAs}", ${c.issues.length} issue(s)`);
      if (c.issues.length) console.log(c.issues.slice(0, 4).map((i) => `      - ${i}`).join('\n'));
    } catch (err) {
      log.error('selftest', `critic failed: ${err.message}`);
    }
  }

  await closeBrowser();
  log.banner('SELFTEST DONE', [`artifacts in ${path.relative(process.cwd(), workspace)}`]);
}

async function cmdShoot() {
  initLogger(null);
  const target = positionals()[0];
  if (!target) { console.error('usage: forge shoot <url|directory>'); process.exit(1); }
  let server = null;
  let url = target;
  if (!/^https?:/.test(target)) {
    const dir = path.resolve(target);
    server = await startStaticServer(fs.statSync(dir).isDirectory() ? dir : path.dirname(dir), config.browser.port + 3);
    url = `http://127.0.0.1:${config.browser.port + 3}/${fs.statSync(dir).isDirectory() ? 'index.html' : path.basename(dir)}`;
  }
  const out = path.resolve(flag('out') || 'shot.png');
  const res = await inspectApp({ url, shotPath: out });
  log.banner('CAPTURE', [
    `url            : ${url}`,
    `saved          : ${out}`,
    `frame rate     : ${res.fps ?? 'unknown'} fps`,
    `page errors    : ${res.pageErrors.length}`,
    `console errors : ${res.consoleErrors.length}`,
    `blank frame    : ${res.blankScreen ? 'YES' : 'no'}`,
    `play area dead : ${res.deadPlayfield ? 'YES' : 'no'}`,
    `crash screen   : ${res.errorScreen ? 'YES' : 'no'}`,
    `responds to input : ${res.interactive === null ? 'unknown' : res.interactive ? 'yes' : 'NO'}`,
  ]);
  for (const e of [...res.pageErrors, ...res.consoleErrors].slice(0, 10)) console.log(`  ! ${e}`);
  server?.close();
  await closeBrowser();
}

async function cmdJudge() {
  initLogger(null);
  const [img, ...rest] = positionals();
  if (!img) {
    console.error('usage: forge judge <image.png> ["what it should be"] [--domain 2d_game]');
    console.error(`       domains: ${DOMAIN_KEYS.join(', ')}`);
    process.exit(1);
  }
  const goal = rest.join(' ') || 'a visually polished game screen';
  const domain = domainFlag(goal);
  const c = await critique({
    screenshot: fs.readFileSync(path.resolve(img)),
    task: { id: 'adhoc', title: goal, description: goal, category: 'rendering', acceptanceCriteria: [] },
    directives: { one_line_goal: goal, quality_bar: 'commercial shipped quality', reference_targets: [] },
    health: null,
    domain,
  });
  log.banner(`VERDICT: ${c.score}/100 — ${c.tier}`, [`judged as: ${c.domain}`, `reads as: ${c.readsAs}`]);
  console.log('Defects:');
  for (const i of c.issues) console.log(`  - ${i}`);
  console.log('\nFixes:');
  for (const f of c.fixes) console.log(`  - ${f}`);
  console.log('\nAxis scores:', c.axisScores);
}

async function cmdCompare() {
  initLogger(null);
  const [ours, ref] = positionals();
  if (!ours || !ref) { console.error('usage: forge compare <ours.png> <reference.png>'); process.exit(1); }
  const res = await blindCompare({
    screenshot: fs.readFileSync(path.resolve(ours)),
    referencePath: path.resolve(ref),
    directives: { quality_bar: 'commercial shipped visual quality' },
    domain: domainFlag(''),
    rounds: Number(flag('rounds', config.critic.blindRounds)),
  });
  log.banner(`BLIND A/B: won ${res.wins}/${res.rounds}`, [res.passed ? 'our image preferred' : 'reference preferred']);
  for (const r of res.detail) console.log(`  round ${r.round}: ${r.oursWon ? 'OURS' : 'REFERENCE'} (${r.margin}) — ${r.reasoning.slice(0, 140)}`);
  if (res.gaps.length) { console.log('\nGaps to close:'); for (const g of res.gaps) console.log(`  - ${g}`); }
}

main().catch(async (err) => {
  log.error('forge', err.stack ?? err.message);
  await closeBrowser().catch(() => {});
  process.exit(1);
});
