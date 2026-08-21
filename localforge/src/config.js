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
    // Parallel worker agents. Ollama serialises per-model unless you raise
    // OLLAMA_NUM_PARALLEL, so going much above 2-3 rarely helps on one box.
    concurrency: num('FORGE_CONCURRENCY', 2),
    // Whole-run wall clock guard, in minutes. 0 disables.
    wallClockMinutes: num('FORGE_WALL_CLOCK_MIN', 0),
    // Truncation limit for any single tool result fed back to the model.
    toolOutputChars: num('FORGE_TOOL_OUTPUT_CHARS', 12000),
    // A task that fails this many attempts in a row is parked, not retried forever.
    maxTaskAttempts: num('FORGE_MAX_TASK_ATTEMPTS', 3),
  },

  critic: {
    // Score (0-100) a visual task must beat to be accepted.
    passScore: num('FORGE_PASS_SCORE', 82),
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
