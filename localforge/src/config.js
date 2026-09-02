/**
 * Central configuration. Everything is overridable by environment variable so
 * you can retune the rig without touching code.
 */
import path from 'node:path';
import os from 'node:os';

const env = (k, d) => process.env[k] ?? d;
const num = (k, d) => (process.env[k] ? Number(process.env[k]) : d);
const bool = (k, d) => (process.env[k] ? /^(1|true|yes)$/i.test(process.env[k]) : d);

export const config = {
  ollama: {
    host: env('FORGE_OLLAMA_HOST', 'http://localhost:11434'),
    // How long models stay resident in VRAM between calls. Keeping them warm is
    // the single biggest speed win on a long autonomous run.
    keepAlive: env('FORGE_KEEP_ALIVE', '30m'),
    requestTimeoutMs: num('FORGE_REQUEST_TIMEOUT_MS', 15 * 60 * 1000),
    maxRetries: num('FORGE_MAX_RETRIES', 3),
  },

  /**
   * Role -> model mapping. Roles are what the code refers to; swap the model
   * names here to re-provision the whole system.
   *
   *   planner  - decomposes the goal into a task graph. Needs reasoning.
   *   coder    - does the actual file editing. Needs tool-calling + long context.
   *   critic   - grades screenshots. MUST have the `vision` capability.
   *   fast     - cheap classification/summarisation chores.
   */
  models: {
    // Stays on the coder model despite planning being a reasoning job. qwen3:32b
    // was measured against it on the same goal, seed and survey: 97s vs 14s per
    // plan, and a worse task graph (67% cosmetic vs 50%, tripping the
    // plan-balance warning). Both models return junk for the `architecture`
    // field, which is why that field is now guarded and the measured file map
    // is appended regardless. Planning quality came from letting the planner
    // read the code, not from the model.
    planner: env('FORGE_MODEL_PLANNER', 'qwen3-coder:30b-64k'),
    coder: env('FORGE_MODEL_CODER', 'qwen3-coder:30b-64k'),
    critic: env('FORGE_MODEL_CRITIC', 'gemma4:26b'),
    fast: env('FORGE_MODEL_FAST', 'gemma3:12b'),
  },

  // Context window per role. Larger = more VRAM. These are tuned for 2x24GB.
  contextTokens: {
    planner: num('FORGE_CTX_PLANNER', 32768),
    coder: num('FORGE_CTX_CODER', 49152),
    critic: num('FORGE_CTX_CRITIC', 16384),
    fast: num('FORGE_CTX_FAST', 8192),
  },

  temperature: {
    planner: num('FORGE_TEMP_PLANNER', 0.4),
    coder: num('FORGE_TEMP_CODER', 0.2),
    critic: num('FORGE_TEMP_CRITIC', 0.35),
    fast: num('FORGE_TEMP_FAST', 0.2),
  },

  budgets: {
    // Max tool-calling steps a single worker agent may take on one attempt.
    agentSteps: num('FORGE_AGENT_STEPS', 60),
    // Max build -> verify -> critique -> fix cycles per task. This is the /loop.
    critiqueRounds: num('FORGE_CRITIQUE_ROUNDS', 6),
    // Parallel worker agents.
    //
    // This is 1 because the scheduler's file locks do not make fan-out safe.
    // They cover each task's *declared* files, but verification is global by
    // necessity: check_syntax runs with { all: true } and the browser loads the
    // whole module graph. So worker A's round is still measured against a page
    // that worker B has half-rewritten, and one broken file anywhere fails both.
    // Agents also write outside their declared set — a 16h run at concurrency 2
    // deleted a module and added an off-layout one — which the locks cannot
    // prevent. Fan-out needs a per-worker tree and a merge step, not tighter
    // locks, before it earns its throughput back.
    concurrency: num('FORGE_CONCURRENCY', 1),
    // Whole-run wall clock guard, in minutes. 0 disables.
    wallClockMinutes: num('FORGE_WALL_CLOCK_MIN', 0),
    // Truncation limit for any single tool result fed back to the model.
    toolOutputChars: num('FORGE_TOOL_OUTPUT_CHARS', 12000),
    // A task that fails this many attempts in a row is parked, not retried forever.
    maxTaskAttempts: num('FORGE_MAX_TASK_ATTEMPTS', 3),
    // How many times a stalled task may be put back in the queue by a later
    // refinement pass. Without a cap this reset maxTaskAttempts every pass and
    // the same handful of tasks churned the same files for days.
    maxRevivals: num('FORGE_MAX_REVIVALS', 2),
  },

  critic: {
    // Score (0-100) a visual task must beat to be accepted.
    //
    // This was 82, which meant "indistinguishable from a shipped commercial
    // title" — and across 8 runs and ~301 critic evaluations it was never once
    // met. Best score ever recorded: 38. The rubric's own calibration rules pin
    // a hand-drawn canvas prototype below 30 on several axes by construction,
    // so 82 made the loop non-terminating: no task could pass, every task was
    // revived forever, and the run could only ever end on the wall clock.
    //
    // 62 is reachable by a genuinely polished canvas build while still sitting
    // far above the 38 that placeholder art has topped out at.
    passScore: num('FORGE_PASS_SCORE', 62),
    // How much of the composite score is art direction, the rest being whether
    // the thing actually works and the task actually got done.
    //
    // This used to be, implicitly, 1.0: every axis in every rubric grades
    // visual craft, so the number the ratchet hill-climbs measured nothing but
    // how pretty one static frame looked. A canvas game drawn with fillRect
    // cannot win those axes — the rubrics' own rules pin it under 30 on
    // several of them by construction — so across 8 runs and ~350 evaluations
    // nothing ever passed, best score ever 38, and "working" and "broken"
    // scored the same as long as neither threw an exception.
    //
    // At 0.65, a build that does what the task asked and still runs cleanly
    // clears the bar on respectable-but-not-commercial art (~42), while
    // placeholder art (~30) still fails. Art remains the majority of the
    // score; it is simply no longer all of it.
    artWeight: num('FORGE_ART_WEIGHT', 0.65),
    // How many blind A/B comparisons against each reference image. Odd number;
    // we swap presentation order every round to cancel positional bias.
    blindRounds: num('FORGE_BLIND_ROUNDS', 3),
    // Refuse to accept a visual task unless it also wins the blind comparison.
    requireBlindWin: bool('FORGE_REQUIRE_BLIND_WIN', false),
  },

  browser: {
    executablePath: env('FORGE_CHROME', '/usr/bin/google-chrome'),
    width: num('FORGE_VIEWPORT_W', 1600),
    height: num('FORGE_VIEWPORT_H', 900),
    // Time to let the scene warm up before we judge it.
    settleMs: num('FORGE_SETTLE_MS', 4000),
    // Duration of the frame-rate sample.
    fpsSampleMs: num('FORGE_FPS_SAMPLE_MS', 3000),
    port: num('FORGE_STATIC_PORT', 8777),
    headless: bool('FORGE_HEADLESS', true),
  },

  paths: {
    // Set at runtime by the CLI once the workspace is known.
    workspace: null,
    forgeRoot: path.resolve(new URL('..', import.meta.url).pathname),
  },

  // Commands the coder agent is never allowed to run, regardless of prompt.
  bannedCommandPatterns: [
    /\brm\s+-rf\s+[~/]/, /\bmkfs\b/, /\bdd\s+if=/, /:\(\)\s*\{/,
    /\bshutdown\b/, /\breboot\b/, /\bchown\s+-R\s+\//, /\bcurl\b[^|]*\|\s*(ba)?sh/,
    /\bsudo\b/, /\bgit\s+push\b/, /\bnpm\s+publish\b/,
  ],

  tmpDir: path.join(os.tmpdir(), 'localforge'),
};

export function workspacePaths(workspace) {
  return {
    root: workspace,
    app: path.join(workspace, 'app'),
    state: path.join(workspace, '.forge', 'state.json'),
    forgeDir: path.join(workspace, '.forge'),
    logs: path.join(workspace, '.forge', 'logs'),
    shots: path.join(workspace, '.forge', 'screenshots'),
    references: path.join(workspace, 'references'),
    reports: path.join(workspace, '.forge', 'reports'),
  };
}
